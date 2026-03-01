import random
import numpy as np
from collections import deque
from modules.utils import config

# Configuration
LAMBDA      = config['decision_making']['Hungarian']['task_reward_discount_factor']
AGENT_SPEED = 0.5
EPS         = 1e-9   # floating-point tolerance for equality-edge check


class DistributedHungarian:

    def __init__(self, agent):
        self.agent = agent

        # Global knowledge – live list references
        self.R = self.agent.agents_info   # list of agent objects
        self.P = self.agent.tasks_info    # list of task objects

        # Assignment tracking
        self.assigned_task   = None
        self.completed_tasks = set()

        # ── Paper initialization §IV.A ───────────────────────────────
        # For each robot i:
        #   j* = argmin_{j∈P} w(i, j)
        #   y(i) = w(i, j*),  y(j) = 0 ∀j ∈ {R\{i}} ∪ P,  γ = -1
        self.w_orig       = {}    # weight cache   : {(agent_id, task_id) -> float}
        self.w_lean_cache = {}    # w_lean from all agents : {(agent_id, task_id) -> float}
        self.E_y    = set() # equality subgraph  : {(agent_id, task_id)}
        self.E_cand = set() # candidate edges    : {(agent_id, task_id)}
        self.y_a    = {}    # agent  vertex labels (dual): {agent_id -> float}
        self.y_t    = {}    # task   vertex labels (dual): {task_id  -> float}
        self.gamma  = -1    # countervalue γ^i
        self._init_lean_graph()

    # ==============================================================
    # Main Decision Logic
    # ==============================================================

    def decide(self, _blackboard):
        own_msg = self.agent.message_to_share
        messages = self.agent.messages_received + ([own_msg] if own_msg else [])

        # Handle completed task
        if self.assigned_task and self.assigned_task.completed:
            self._on_task_completed(self.assigned_task.task_id)

        # Build_Latest_Graph(R, S)  – paper §IV.C
        self._build_latest_graph(messages)

        # Local_Hungarian (one step per tick, paper §IV.B)
        if self.gamma >= 0:
            self._run_local_hungarian()

        self._update_visualization()
        self._update_message()
        self.agent.reset_messages_received()

        return self.assigned_task.task_id if self.assigned_task else None

    def _on_task_completed(self, task_id):
        self.completed_tasks.add(task_id)
        self.assigned_task = None
        self._update_visualization()

    def _init_lean_graph(self):
        """Paper initialization §IV.A – called once at __init__.

        At t = t_0, each robot i:
          j*       = argmin_{j∈P} w^i_orig(i, j)
          G^i_lean = (V, ({(i,j*)}, ∅), w^i_lean)   eq. (3)
          y^i(j)   = 0, ∀j ∈ {R\{i}} ∪ P             eq. (4)
          y^i(i)   = w^i_orig(i, j*)                  eq. (4)
          γ^i      = -1                                eq. (5)
        """
        my_id = self.agent.agent_id

        # Prerequisite: compute w_orig to find j*
        self._recompute_w_orig()

        active_tasks = [t for t in self.P if not t.completed]
        if active_tasks:
            # Select j* = argmin_{j∈P} w^i_orig(i, j)
            j_star = min(active_tasks, key=lambda t: self.w_orig.get((my_id, t.task_id), float('inf')))

            # eq. (3): G^i_lean initialised with single edge (i, j*), E_cand = ∅
            self.E_y    = {(my_id, j_star.task_id)}
            self.E_cand = set()

            # eq. (4): first y(j) = 0 for all j ∈ R ∪ P, then y(i) = w(i, j*)
            self.y_a = {a.agent_id: 0.0 for a in self.R}        # y(j) = 0, j ∈ R
            self.y_t = {t.task_id:  0.0 for t in active_tasks}  # y(j) = 0, j ∈ P
            w_i_jstar     = self.w_orig.get((my_id, j_star.task_id), 0.0)
            self.y_a[my_id] = w_i_jstar if np.isfinite(w_i_jstar) else 0.0  # y(i) = w(i,j*)
        else:
            self.E_y    = set()
            self.E_cand = set()
            self.y_a    = {my_id: 0.0}
            self.y_t    = {}

        # eq. (5): γ^i = -1
        self.gamma = -1

        # Broadcast initial state G^i = (G^i_lean, y^i, γ^i)
        self._update_message()

    # ==============================================================
    # Build Latest Graph  (paper §IV.C)
    # ==============================================================

    def _build_latest_graph(self, messages):
        """Build_Latest_Graph(R, S) from the paper (§IV.C)."""
        self._recompute_w_orig()
        self.w_lean_cache.update(self.w_orig)   # own edges always up-to-date

        all_neg1 = self.gamma == -1 and all(msg.get('gamma', -1) == -1 for msg in messages)

        if all_neg1:
            # ── Case 1: γ == -1 for all (initialization phase) ──
            # self.E_y / self.y_a already hold own data; just merge neighbors'
            for msg in messages:
                self.w_lean_cache.update(msg.get('w_lean', {}))
                self.E_y.update(msg.get('E_y', ()))
                sender = msg['agent_id']
                self.y_a[sender] = msg.get('y_a', {}).get(sender, 0.0)
            self.E_cand = set()
            self.y_t    = {t.task_id: 0.0 for t in self.P if not t.completed}
            if len(self.E_y) >= len(self.R):
                self.gamma = 0

        else:
            # ── Case 2: some γ > -1 (matching phase) ──
            max_gamma  = max([self.gamma] + [msg.get('gamma', -1) for msg in messages])
            lead_msgs  = [msg for msg in messages if msg.get('gamma', -1) == max_gamma]

            # Adopt state from deterministically-chosen lead (min agent_id)
            # → 모든 로봇이 동일한 y_a/y_t를 adopt해야 수렴 가능
            lead_msg    = min(lead_msgs, key=lambda m: m['agent_id'])
            self.gamma  = lead_msg['gamma']
            self.y_a    = dict(lead_msg.get('y_a',   {}))
            self.y_t    = dict(lead_msg.get('y_t',   {}))
            self.E_y    = set(lead_msg.get('E_y',    ()))

            for msg in lead_msgs:
                self.w_lean_cache.update(msg.get('w_lean', {}))

            merged_E_cand = set()
            for msg in lead_msgs:
                merged_E_cand.update(msg.get('E_cand', ()))
            self.E_cand = merged_E_cand



    # ==============================================================
    # Weight Function
    # ==============================================================

    def _recompute_w_orig(self):
        """w^i_orig(i,j) = 1 / LAMBDA^(dist/speed) – for robot i (myself) only.

        Per paper §III: each robot i knows only its own cost function c^i,
        so w^i_orig is defined only for edges (i, j) where i = my_id.
        """
        my_id  = self.agent.agent_id
        my_pos = self.agent.position
        self.w_orig = {}
        if my_pos is None:
            return
        for t in self.P:
            if t.completed: continue
            dx   = my_pos.x - t.position.x
            dy   = my_pos.y - t.position.y
            dist = (dx**2 + dy**2) ** 0.5
            self.w_orig[(my_id, t.task_id)] = 1.0 / (LAMBDA ** (dist / AGENT_SPEED))

    def _compute_slack(self, agent_id, task_id):
        """slack(i,j) = w(i,j) - y_a(i) - y_t(j)  (≥ 0 for feasible labeling)."""
        w = self.w_lean_cache.get((agent_id, task_id), float('inf'))
        return w - self.y_a.get(agent_id, 0.0) - self.y_t.get(task_id, 0.0)

    def _get_equality_subgraph_edges(self):
        """Eqn(1): E_y = {(i,j) ∈ R×P : w(i,j) = y_a(i) + y_t(j)}.

        Full recomputation from w_lean_cache (all known edges from all agents).
        After y_a/y_t are updated, new equality edges may emerge from E_cand,
        so we must check all known edges, not just those already in E_y.
        """
        new_E_y = set()
        for (aid, tid), w in self.w_lean_cache.items():
            slack = w - self.y_a.get(aid, 0.0) - self.y_t.get(tid, 0.0)
            if abs(slack) < EPS:
                new_E_y.add((aid, tid))
        return new_E_y
 

    # ==============================================================
    # Local Hungarian  (paper §IV.B / Local_Hungarian)
    # ==============================================================

    def _run_local_hungarian(self):
        """Local_Hungarian (paper Algorithm 1, §IV.B)."""
        my_id = self.agent.agent_id

        # FindMaxMatching → if perfect, done
        match_agent, match_task = self._find_max_matching(self.E_y)
        # FindVertexCover → R \ R_c = uncovered robots
        cover_agents, cover_tasks = self._find_vertex_cover(self.E_y, match_agent, match_task)
        uncovered_robots = {a.agent_id for a in self.R} - cover_agents

        if len(match_agent) == len(self.R):
            tid_to_obj = {t.task_id: t for t in self.P if not t.completed}
            self.assigned_task = tid_to_obj.get(match_agent.get(my_id))
            self.assigned_task.task_id if self.assigned_task else None
            return

        # For broadcasting: only uncovered robots contribute to E_cand
        e_cand, _ = self._get_best_edge(my_id, uncovered_robots)
        if e_cand is not None:
            existing = next((e for e in self.E_cand if e[0] == my_id), None)
            if existing:
                self.E_cand.discard(existing)
            self.E_cand.add(e_cand)

        # stale entries from now-covered robots 제거
        self.E_cand = {e for e in self.E_cand if e[0] in uncovered_robots}


        if len(self.E_cand) == len(uncovered_robots):
            # Step 1(a): GetBestEdge → E_cand ← E_cand ∪ {(i, j*)}
            e_cand, _ = self._get_best_edge(my_id, uncovered_robots)
            if e_cand:
                if any(aid == my_id and tid != e_cand[1] for (aid, tid) in self.E_cand):
                    breakpoint()   # E_cand에 동일 agent, 다른 task가 이미 존재
                self.E_cand.add(e_cand)
            # Step 1(b): Adjust slack variables
            delta = min(self._compute_slack(i, j) for i, j in self.E_cand)
            for a in self.R:
                if a.agent_id in cover_agents:
                    self.y_a[a.agent_id] -= delta
            for t in self.P:
                if not t.completed and t.task_id not in cover_tasks:
                    self.y_t[t.task_id] += delta

            # Step 2: Get E_y  (Eqn. 1)
            self.E_y = self._get_equality_subgraph_edges()
            # FindMaxMatching → if perfect, done
            match_agent, match_task = self._find_max_matching(self.E_y)
            # FindVertexCover → R \ R_c = uncovered robots
            cover_agents, cover_tasks = self._find_vertex_cover(self.E_y, match_agent, match_task)
            new_uncovered_robots = {a.agent_id for a in self.R} - cover_agents

            # Debug
            if len(new_uncovered_robots) > len(uncovered_robots):
                print(f"[Warning - Agent ID: {my_id}] Uncovered robots increased from {len(uncovered_robots)} to {len(new_uncovered_robots)} after Local_Hungarian step!")
            

            # Remaining
            self.gamma += 1
            e_cand, _ = self._get_best_edge(my_id, new_uncovered_robots)
            self.E_cand = {e_cand} if e_cand is not None else set()
            # NOTE: _reduce_edge_set intentionally NOT called here.
            # hungarian_rev.py (centralized reference) NEVER reduces E_y between
            # iterations — it always keeps the full equality subgraph.
            # Calling _reduce_edge_set removes zero-slack edges from E_y, causing
            # _get_best_edge to re-select those same edges next tick → delta=0 → oscillation.

            print(f"Agent ID: {my_id}, Local_Hungarian step completed: γ={self.gamma}, E_y={self.E_y}, y_a={self.y_a}, y_t={self.y_t}, E_cand={self.E_cand}")
    
        



    # ── Bipartite Matching ─────────────────────────────────────────

    def _find_max_matching(self, E_y):
        """DFS augmenting-path maximum bipartite matching within E_y."""
        ey_adj = {}
        for (aid, tid) in E_y:
            ey_adj.setdefault(aid, set()).add(tid)

        match_agent = {}
        match_task  = {}

        def dfs(aid, visited_tasks):
            tasks = list(ey_adj.get(aid, set()))
            random.shuffle(tasks)   # 매칭 다양성: 항상 같은 robot이 같은 task를 독점하지 않도록
            for tid in tasks:
                if tid not in visited_tasks:
                    visited_tasks.add(tid)
                    if tid not in match_task or dfs(match_task[tid], visited_tasks):
                        match_agent[aid] = tid
                        match_task[tid]  = aid
                        return True
            return False

        agents = list(self.R)
        random.shuffle(agents)  # robot 처리 순서도 무작위화
        for a in agents:
            dfs(a.agent_id, set())
        return match_agent, match_task

    def _find_vertex_cover(self, E_y, match_agent, match_task):
        """König's theorem: minimum vertex cover from maximum matching."""
        ey_adj = {}
        for (aid, tid) in E_y:
            ey_adj.setdefault(aid, set()).add(tid)

        R_ids      = {a.agent_id for a in self.R}
        unmatched  = R_ids - set(match_agent.keys())
        vis_agents = set(unmatched)
        vis_tasks  = set()
        queue      = deque(sorted(unmatched))

        while queue:
            aid = queue.popleft()
            for tid in sorted(ey_adj.get(aid, set())):
                if tid not in vis_tasks:
                    vis_tasks.add(tid)
                    if tid in match_task:
                        next_aid = match_task[tid]
                        if next_aid not in vis_agents:
                            vis_agents.add(next_aid)
                            queue.append(next_aid)

        # Cover = matched agents NOT in alternating tree + tasks IN alternating tree
        cover_agents = set(match_agent.keys()) - vis_agents
        cover_tasks  = vis_tasks
        return cover_agents, cover_tasks

    def _get_best_edge(self, robot_id, uncovered_robots=None):
        """Get_Best_Edge (paper): min-slack edge from robot_id to uncovered tasks not in E_y."""
        if uncovered_robots is not None and robot_id not in uncovered_robots:
            return None, float('inf')
        min_slack = float('inf')
        best_tid  = None
        for t in self.P:
            if t.completed: continue
            tid = t.task_id
            if (robot_id, tid) in self.E_y:
                continue
            slack = self._compute_slack(robot_id, tid)
            if slack < min_slack:
                min_slack = slack
                best_tid  = tid
        if best_tid is not None:
            return (robot_id, best_tid), min_slack
        return None, float('inf')

    def _reduce_edge_set(self, match_agent):
        """Reduce_Edge_Set (paper §IV.B).

        Prunes E_y to the minimum number of equality subgraph edges such that:
        1) M and V_c remain unchanged (keep only matched edges)
        2) |E_y| + |E_cand| ≤ 2r - 1  (debug assertion)
        """
        # Condition 1: keep only matched edges → M and V_c preserved by construction
        matched_edges = {(aid, tid) for aid, tid in match_agent.items()}
        if len(matched_edges) < len(self.E_y):
            print(f"Reduce_Edge_Set: reducing |E_y| from {len(self.E_y)} to {len(matched_edges)}")
        self.E_y = matched_edges

        # Condition 2: debug assertion
        r = len(self.R)
        assert len(self.E_y) + len(self.E_cand) <= 2 * r - 1, (
            f"Reduce_Edge_Set: |E_y|={len(self.E_y)} + |E_cand|={len(self.E_cand)}"
            f" > 2r-1={2*r-1}"
        )

    # ==============================================================
    # Messaging & Visualization
    # ==============================================================

    def _update_message(self):
        # w^i_lean: broadcast full cache so all robots can reconstruct equality subgraph
        w_lean = dict(self.w_lean_cache)

        # Broadcast G^i = (G^i_lean, y^i, γ^i)
        # where G^i_lean = (V, (E^i_y, E^i_cand), w^i_lean)  – V is globally known
        self.agent.message_to_share = {
            'agent_id':         self.agent.agent_id,
            'assigned_task_id': self.assigned_task.task_id if self.assigned_task else None,
            # G^i_lean — 복사본 전송 (이후 in-place 수정이 message에 반영되지 않도록)
            'E_y':    set(self.E_y),
            'E_cand': set(self.E_cand),
            'w_lean': w_lean,   # dict(self.w_lean_cache) — 이미 복사
            # y^i = (y_a, y_t),  γ^i
            'y_a':    dict(self.y_a),
            'y_t':    dict(self.y_t),
            'gamma':  self.gamma,
        }

    def _update_visualization(self):
        if self.assigned_task:
            self.agent.set_planned_tasks([self.assigned_task])
        else:
            self.agent.set_planned_tasks([])
