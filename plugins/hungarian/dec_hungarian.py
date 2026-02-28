import numpy as np
import pygame
import random
from modules.utils import config
from enum import Enum

# Configuration
LAMBDA = config['decision_making']['Hungarian']['task_reward_discount_factor']
DUMMY_COST = config['decision_making']['Hungarian']['dummy_cost']
EPSILON = 1e-10

class Phase(Enum):
    SYNC = 1
    MATCH = 2

class DistributedHungarian:
    
    def __init__(self, agent, blackboard):
        self.agent = agent
        
        # State
        self.phase = Phase.SYNC
        self.initialised = False
        
        # Cluster membership (Live Objects)
        self.R = []
        self.P = []
        
        # Hungarian Algorithm Variables (Local Context)
        self.weights = np.array([])
        self.r = 0
        self.p = 0
        self.agent_label = np.array([])
        self.task_label = np.array([])
        self.M = []
        self.Ey = set()
        self.Rc = set()
        self.Pc = set()
        self.E_cand = set()
        
        # Mappings
        self.agent_idx_to_id = {}
        self.task_idx_to_id = {}
        self.task_idx_to_obj = {}
        
        # Assignment tracking
        self.assigned_task = None
        self.completed_tasks = set()
        
        # Init message
        self.global_adjacency = {}
        self._update_message([], [])
    
    # ==============================================================
    # Main Decision Logic
    # ==============================================================
    
    def decide(self, blackboard):
        _local_agents_info = blackboard['local_agents_info']
        self.last_local_agents = _local_agents_info # Store for messaging
        _local_tasks_info = blackboard['local_tasks_info']
        messages = blackboard['messages_received']
        
        # Handle completed task
        if self.assigned_task and self.assigned_task.completed:
            self._on_task_completed(self.assigned_task.task_id, _local_tasks_info)
        
        # Initialize if needed
        if not self.initialised:
            self._initialize(_local_tasks_info)
        
        # Continuous Monitoring: Detect cluster changes
        if self._detect_cluster_changes(messages, _local_agents_info):
            self.assigned_task = None # Reset assignment on cluster change
            self._update_visualization()
        

            
        # Always Build/Sync Graph
        self._build_latest_graph(messages, _local_agents_info, _local_tasks_info)
        
        # Run Hungarian (Phase 2 logic)
        assigned_task = self._run_centralized_hungarian()
        self.assigned_task = assigned_task
        self._update_visualization()

        
        # Return result
        self._update_message(_local_agents_info, _local_tasks_info)
        self.agent.reset_messages_received()
        
        # Debug Log for Assignment
        # assigned_id = self.assigned_task.task_id if self.assigned_task else "None"
        # print(f"[Agent {self.agent.agent_id}] Assigned Task: {assigned_id}")
        
        return self.assigned_task.task_id if self.assigned_task else None
    
    def _on_task_completed(self, task_id, _local_tasks_info):
        self.completed_tasks.add(task_id)
        self.assigned_task = None
        self._update_visualization()

    def _initialize(self, tasks):
        self.R = [self.agent]
        self.P = sorted(tasks, key=lambda t: t.task_id)
        self.initialised = True

    # ==============================================================
    # Cluster Synchronization (R/P Logic)
    # ==============================================================
    
    def _detect_cluster_changes(self, messages, local_agents):
        """군집 내 멤버 변경(유입/이탈) 감지 (Live Object Safe)"""
        current_r_ids = {getattr(a, 'agent_id', a.get('agent_id') if isinstance(a, dict) else None) for a in self.R}
        perceived_ids = {self.agent.agent_id}
        
        for a in local_agents:
            perceived_ids.add(a.agent_id)
            
        for msg in messages:
            if msg:
                for agent in msg.get('agents_info', []):
                    aid = getattr(agent, 'agent_id', None)
                    if aid is None and isinstance(agent, dict):
                        aid = agent.get('agent_id')
                    
                    if aid is not None:
                        perceived_ids.add(aid)
        
        if not current_r_ids.issubset(perceived_ids): return True
        if not perceived_ids.issubset(current_r_ids): return True
        return False



    def _build_latest_graph(self, messages, local_agents, local_tasks):
        """Sync Graph"""
        valid_msgs = [m for m in messages if m and 'agent_id' in m]
        
        # 1. Collect Candidates
        candidates = {self.agent.agent_id: self.agent}
        for a in local_agents:
            candidates[a.agent_id] = a
        for msg in valid_msgs:
            for agent in msg.get('agents_info', []):
                aid = getattr(agent, 'agent_id', None)
                if aid is None and isinstance(agent, dict):
                    aid = agent.get('agent_id')
                
                if aid is not None and aid not in candidates:
                    candidates[aid] = agent
        
        # 2. Link State Graph Reconstruction
        # We maintain a global view `self.global_adjacency`.
        # Rule: We TRUST the direct neighbor's report about THEMSELF.
        # But we also accumulate their view of the world to bridge gaps.
        
        _agent_id = self.agent.agent_id
        
        # 2.1 Update My Local View in Global Graph
        my_neighbors = {a.agent_id for a in local_agents}
        self.global_adjacency[_agent_id] = my_neighbors
        
        # 2.2 Merge Neighbors' Views via Link State Advertisement
        # If I receive a message from 'sender', I trust 'sender's adjacency report' + 'sender's knowledge of others'
        for msg in valid_msgs:
            sender_id = msg.get('agent_id')
            if sender_id is not None:
                # Implicit edge: I hear sender -> I am connected to sender (Directional? No, assume bidir communication if msg received)
                # But strictly, Link State relies on Sender reporting who THEY see.
                
                # Merge the received graph
                received_adj = msg.get('adjacency_graph', {})
                if isinstance(received_adj, dict):
                    pass 
        
        new_global_adj = {}
        new_global_adj[_agent_id] = my_neighbors
        
        for msg in valid_msgs:
            sender_id = msg.get('agent_id')
            if sender_id is None: continue
            
            # Merge Sender's Full Graph
            received_graph = msg.get('adjacency_graph', {})
            for node, neighbors in received_graph.items():
                if node not in new_global_adj:
                    new_global_adj[node] = set(neighbors)
                else:
                    new_global_adj[node].update(neighbors)
                    
        self.global_adjacency = new_global_adj

        # BFS to find Connected Component (Reachability)
        reachable_ids = {_agent_id}
        queue = [_agent_id]
        visited = {_agent_id}
        
        while queue:
            curr = queue.pop(0)
            # Retrieve neighbors from the merged graph
            neighbors = self.global_adjacency.get(curr, set())
            if not neighbors:
                pass

            for n in neighbors:
                if n not in visited:
                    visited.add(n)
                    reachable_ids.add(n)
                    # Only traverse if we have adjacency info for 'n' (it's in the graph)
                    if n in self.global_adjacency:
                        queue.append(n)
        
        # Update R
        self.R = [candidates[aid] for aid in sorted(list(reachable_ids)) if aid in candidates]
        new_R_ids = reachable_ids
        
        # Handle Completed Tasks (Merge from all reachable nodes)
        for msg in valid_msgs:
            # Only trust messages from reachable agents
            if msg['agent_id'] in new_R_ids:
                for tid in msg.get('completed_tasks', set()):
                    if tid not in self.completed_tasks:
                        self.completed_tasks.add(tid)

        # Update P
        observed_task_ids = {t.task_id for t in local_tasks}
        
        # Collect tasks from all reachable neighbors
        current_p_map = {getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else None): t for t in self.P}
        for t in local_tasks:
            current_p_map[t.task_id] = t
            
        for msg in valid_msgs:
            if msg['agent_id'] in new_R_ids:
                for t in msg.get('tasks_info', []):
                    tid = getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else None)
                    if tid is not None and tid not in self.completed_tasks:
                        # tracking
                        observed_task_ids.add(tid)
                        current_p_map[tid] = t

        # Filter P
        self.P = [t for tid, t in current_p_map.items() if tid in observed_task_ids and tid not in self.completed_tasks]
        self.P.sort(key=lambda t: getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else None))

    # ==============================================================
    # Messaging
    # ==============================================================
    def _update_message(self, _local_agents_info, _local_tasks_info):
        # Prepare Graph to Send
        graph_to_send = self.global_adjacency.copy()
        # Ensure my fresh local view is in the message
        _agent_id = self.agent.agent_id
        if _local_agents_info is not None:
             graph_to_send[_agent_id] = {a.agent_id for a in _local_agents_info}
        
        self.agent.message_to_share = {
                                       'agent_id': _agent_id,
                                       'adjacency_graph': graph_to_send, # Send Full Graph
                                       'agents_info': self.R, # Send Full Agent Objects (Data Payload)
                                       'tasks_info': self.P, # Send Full Task Objects (Data Payload)
                                       'completed_tasks': self.completed_tasks,
                                       'assigned_task_id': self.assigned_task.task_id if self.assigned_task else None
                                       }

    def _update_visualization(self):
        if self.assigned_task:
            self.agent.set_planned_tasks([self.assigned_task])
        else:
            self.agent.set_planned_tasks([])

    # ==============================================================
    # Centralised Hungarian Logic
    # ==============================================================
    
    def _run_centralized_hungarian(self):
        """Run standard Hungarian locally on self.R and self.P"""
        # 1. Build Weights
        self._build_weights_matrix()
        
        # 2. Init Labels
        self.agent_label = np.min(self.weights, axis=1)
        self.task_label = np.zeros(self.p, dtype=float)
        
        # 3. Hungarian Loop
        max_iter = 100
        iteration = 0
        
        self._build_equality_edges()
        matching, _ = self._find_matching_and_cover(self.agent_label, self.task_label)
        
        while len(matching) < self.r and iteration < max_iter:
            iteration += 1
            
            E_cand = self._step_1_a()
            if not E_cand: break
            
            delta = self._step_1_b(E_cand)
            if delta is None or delta == 0: break
            
            self._build_equality_edges()
            matching, _ = self._find_matching_and_cover(self.agent_label, self.task_label)
            
        # 4. Assign
        assigned_task = self._assign_from_matching(matching)
        return assigned_task

        
    def _build_weights_matrix(self):
        # Flatten R and P for matrix construction
        local_agents = self.R
        local_tasks = self.P
        
        num_agents = len(local_agents)
        num_tasks = len(local_tasks)
        
        n = max(num_agents, num_tasks)
        self.r = n
        self.p = n
        
        # Build mappings
        self.agent_idx_to_id = {}
        for i, a in enumerate(local_agents):
            aid = getattr(a, 'agent_id', None)
            if aid is None and isinstance(a, dict):
                aid = a.get('agent_id')
            self.agent_idx_to_id[i] = aid
            
        self.task_idx_to_id = {}
        self.task_idx_to_obj = {}
        for j, t in enumerate(local_tasks):
            tid = getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else None)
            self.task_idx_to_id[j] = tid
            self.task_idx_to_obj[j] = t
            
        weights = np.full((n, n), DUMMY_COST, dtype=float)
        
        for i, agent in enumerate(local_agents):
            for j, task in enumerate(local_tasks):
                weights[i][j] = self._calculate_weight(agent, task)
                
        # Setting Dummies
        if num_agents > num_tasks:
            for j in range(num_tasks, n):
                self.task_idx_to_id[j] = f"dummy_task_{j}"
                self.task_idx_to_obj[j] = None
        elif num_agents < num_tasks:
            for i in range(num_agents, n):
                self.agent_idx_to_id[i] = f"dummy_agent_{i}"
        
        self.weights = weights

    def _calculate_weight(self, agent, task):
        agent_position = agent.position
        task_position = pygame.Vector2(task.position)
        distance_to_task = agent_position.distance_to(task_position)
        expected_reward = LAMBDA**(distance_to_task/agent.max_speed + task.amount/agent.work_rate) #* task.amount
        return 1.0 / expected_reward

    def _build_equality_edges(self):
        self.Ey = set()
        for i in range(self.r):
            for j in range(self.p):
                if abs(self.weights[i, j] - self.agent_label[i] - self.task_label[j]) < EPSILON:
                    self.Ey.add((i, j))

    def _step_1_a(self):
        E_cand = set()
        uncovered_rows = [i for i in range(self.r) if i not in self.Rc]
        uncovered_cols = [j for j in range(self.p) if j not in self.Pc]
        
        if not uncovered_rows or not uncovered_cols: return E_cand
        
        min_slack = float('inf')
        best_edges = []
        
        for i in uncovered_rows:
            for j in uncovered_cols:
                slack = self.weights[i, j] - self.agent_label[i] - self.task_label[j]
                if slack < min_slack:
                    min_slack = slack
                    best_edges = [(i, j)]
                elif slack == min_slack:
                    best_edges.append((i, j))
        return set(best_edges)

    def _step_1_b(self, E_cand):
        if not E_cand: return None
        min_slack = float('inf')
        for i, j in E_cand:
            slack = self.weights[i, j] - self.agent_label[i] - self.task_label[j]
            if slack < min_slack: min_slack = slack
            
        # Update labels
        for i in self.Rc: self.agent_label[i] -= min_slack
        for j in range(self.p):
            if j not in self.Pc:
                self.task_label[j] += min_slack
        return min_slack

    def _find_matching_and_cover(self, r_labels, p_labels):
        adj = [[] for _ in range(self.r)]
        for r_idx, p_idx in self.Ey:
            adj[r_idx].append(p_idx)
            
        match_r = [-1] * self.r
        match_p = [-1] * self.p
        
        # Deterministic Shuffle
        rows = list(range(self.r))
        random.shuffle(rows)
        
        for r_idx in rows:
            visited = [False] * self.r
            self._bmp(r_idx, match_r, match_p, adj, visited)
            
        matching = []
        for r_idx in range(self.r):
            if match_r[r_idx] != -1:
                matching.append((r_idx, match_r[r_idx]))
                
        # Build Cover
        unmatched_r = [r for r in range(self.r) if match_r[r] == -1]
        reachable_r, reachable_p = set(), set()
        
        def dfs(u):
            if u in reachable_r: return
            reachable_r.add(u)
            for v in adj[u]:
                if v not in reachable_p:
                    reachable_p.add(v)
                    if match_p[v] != -1:
                        dfs(match_p[v])
                        
        for u in unmatched_r: dfs(u)
        
        self.Rc = set([r for r in range(self.r) if r not in reachable_r])
        self.Pc = reachable_p
        
        return matching, (self.Rc, self.Pc)

    def _bmp(self, u, match_r, match_p, adj, visited):
        if visited[u]: return False
        visited[u] = True
        for v in adj[u]:
            if match_p[v] == -1 or self._bmp(match_p[v], match_r, match_p, adj, visited):
                match_r[u] = v
                match_p[v] = u
                return True
        return False

    def _assign_from_matching(self, matching):
        # Identify my assignment
        my_aid = self.agent.agent_id
        assigned_obj = None
        
        for i, j in matching:
            aid = self.agent_idx_to_id.get(i)
            if aid == my_aid:
                assigned_obj = self.task_idx_to_obj.get(j)
                break
        
        self.assigned_task = assigned_obj
        return assigned_obj
