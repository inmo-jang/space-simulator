import time
import random
import numpy as np
import pygame
from modules.base_bt_nodes import SyncAction, Status
from modules.utils import config

LAMBDA = config['decision_making']['Hungarian']['task_reward_discount_factor']


class Hungarian(SyncAction):

    def __init__(self, name, agent):
        super().__init__(name, self.decide)
        self.agent = agent
        self.weights = np.ndarray([])
        self.r = None
        self.p = None
        self.agent_label = None
        self.task_label = None
        self.M = []
        self.Ey = set()
        self.Rc = set()
        self.Pc = set()
        self.Vc = set()
        self.E_cand = set()
        self.delta = None
        self.assigned_tasks = {}
        self.agent_idx_to_id = {}
        self.task_idx_to_id = {}
        self.task_idx_to_obj = {}
        self.num_original_agents = 0
        self.num_original_tasks = 0
        self.DUMMY_COST = 0.0

    def decide(self, agent, blackboard):
        _local_tasks_info = blackboard['local_tasks_info']
        _local_agents_info = blackboard['local_agents_info']

        for _agent in _local_agents_info:
            agent_id = _agent.agent_id
            assigned_task = self.assigned_tasks.get(agent_id, None)
            if assigned_task is not None and assigned_task.completed:
                self.assigned_tasks[agent_id] = None

        any_available = any(
            self.assigned_tasks.get(_agent.agent_id, None) is None
            for _agent in _local_agents_info
        )

        if any_available:
            self.weights = self.build_weights_matrix(_local_agents_info, _local_tasks_info)
            self.agent_label = np.min(self.weights, axis=1)
            self.task_label = np.zeros(self.p, dtype=float)
            self.hungarian(max_iter=100)

            print("\n" + "="*60)
            print("HUNGARIAN ALGORITHM RESULT")
            print("="*60)
            print(f"\n[INFO] Agents: {self.num_original_agents}, Tasks: {self.num_original_tasks}")
            print(f"[INFO] Matrix size: {self.r} x {self.p}")
            print("\n[WEIGHTS MATRIX] (cost = 1/reward, inf = dummy)")
            header = "          "
            for j in range(self.p):
                task_id = self.task_idx_to_id.get(j, f"T{j}")
                header += f"{str(task_id)[:8]:>10}"
            print(header)
            for i in range(self.r):
                agent_id = self.agent_idx_to_id.get(i, f"A{i}")
                row_str = f"{str(agent_id)[:8]:<10}"
                for j in range(self.p):
                    val = self.weights[i][j]
                    if np.isinf(val):
                        row_str += f"{'inf':>10}"
                    else:
                        row_str += f"{val:>10.4f}"
                print(row_str)
            print("\n[ASSIGNMENT RESULT]")
            for agent_id, task_obj in self.assigned_tasks.items():
                task_id = task_obj.task_id if task_obj else None
                print(f"  Agent {agent_id} -> Task {task_id}")
            print("="*60 + "\n")

        task_allocations = {}
        for _agent in _local_agents_info:
            agent_id = _agent.agent_id
            assigned_task = self.assigned_tasks.get(agent_id, None)
            assigned_tasks = [assigned_task] if assigned_task else []
            _agent.set_planned_tasks(assigned_tasks)
            task_allocations[agent_id] = assigned_task.task_id if assigned_task is not None else None

        task_allocations["timestamp"] = time.time()
        blackboard["task_allocations"] = task_allocations
        return Status.SUCCESS

    def build_weights_matrix(self, _local_agents_info, _local_tasks_info):
        num_agents = len(_local_agents_info)
        num_tasks = len(_local_tasks_info)
        self.num_original_agents = num_agents
        self.num_original_tasks = num_tasks
        n = max(num_agents, num_tasks)
        self.r = n
        self.p = n
        self.agent_idx_to_id = {i: agent.agent_id for i, agent in enumerate(_local_agents_info)}
        self.task_idx_to_id = {j: task.task_id for j, task in enumerate(_local_tasks_info)}
        self.task_idx_to_obj = {j: task for j, task in enumerate(_local_tasks_info)}
        weights = np.full((n, n), self.DUMMY_COST, dtype=float)
        for i, agent in enumerate(_local_agents_info):
            for j, task in enumerate(_local_tasks_info):
                expected_reward = self.compute_weight_value(agent, task)
                weights[i][j] = 1.0 / expected_reward
        if num_agents > num_tasks:
            for j in range(num_tasks, n):
                self.task_idx_to_id[j] = f"dummy_task_{j}"
                self.task_idx_to_obj[j] = None
        elif num_agents < num_tasks:
            for i in range(num_agents, n):
                self.agent_idx_to_id[i] = f"dummy_agent_{i}"
        return weights

    def compute_weight_value(self, agent, task):
        agent_position = agent.position
        task_position = pygame.Vector2(task.position)
        distance_to_task = agent_position.distance_to(task_position)
        expected_reward = LAMBDA**(distance_to_task/agent.max_speed + task.amount/agent.work_rate)
        return expected_reward

    def hungarian(self, max_iter=100):
        n = self.r
        iteration = 0
        self.build_equality_edges()
        matching, _ = self.find_matching_and_cover(self.agent_label, self.task_label)
        while len(matching) < n and iteration < max_iter:
            iteration += 1
            self.step_1_a()
            if len(self.E_cand) == 0:
                break
            delta = self.step_1_b()
            if delta is None or delta == 0:
                break
            self.build_equality_edges()
            matching, _ = self.find_matching_and_cover(self.agent_label, self.task_label)
        self._assign_from_matching(matching)

    def _assign_from_matching(self, matching):
        self.assigned_tasks = {}
        for (i, j) in matching:
            if i >= self.num_original_agents:
                continue
            if j >= self.num_original_tasks:
                continue
            agent_id = self.agent_idx_to_id[i]
            task_obj = self.task_idx_to_obj[j]
            self.assigned_tasks[agent_id] = task_obj

    def build_equality_edges(self, eps=1e-10):
        self.Ey = set()
        for i in range(self.r):
            for j in range(self.p):
                if abs(self.calculate_slack(i, j)) < eps:
                    self.Ey.add((i, j))
        return self.Ey

    def calculate_slack(self, i, j):
        return self.weights[i, j] - self.agent_label[i] - self.task_label[j]

    def bmp(self, r, match_r, match_p, adj, visited):
        if visited[r]:
            return False
        visited[r] = True
        for p in adj[r]:
            if match_p[p] == -1 or self.bmp(match_p[p], match_r, match_p, adj, visited):
                match_r[r] = p
                match_p[p] = r
                return True
        return False

    def find_matching_and_cover(self, r, p):
        self.agent_label = r
        self.task_label = p
        self.build_equality_edges()
        adj = [[] for _ in range(self.r)]
        for r_idx, p_idx in self.Ey:
            adj[r_idx].append(p_idx)
        match_r = [-1] * self.r
        match_p = [-1] * self.p
        rows = list(range(self.r))
        random.shuffle(rows)
        for r_idx in rows:
            visited = [False] * self.r
            self.bmp(r_idx, match_r, match_p, adj, visited)
        matching = []
        for r_idx in range(self.r):
            if match_r[r_idx] != -1:
                matching.append((r_idx, match_r[r_idx]))
        unmatched_r = [r for r in range(self.r) if match_r[r] == -1]
        reachable_r = set()
        reachable_p = set()

        def dfs_from_unmatched_rows(r_label):
            if r_label in reachable_r:
                return
            reachable_r.add(r_label)
            for p_label in adj[r_label]:
                if p_label not in reachable_p:
                    reachable_p.add(p_label)
                    if match_p[p_label] != -1:
                        dfs_from_unmatched_rows(match_p[p_label])

        for r in unmatched_r:
            dfs_from_unmatched_rows(r)
        Rc = [r for r in range(self.r) if r not in reachable_r]
        Pc = list(reachable_p)
        self.Rc = set(Rc)
        self.Pc = set(Pc)
        self.M = matching
        self.Vc = self.Rc.union(self.Pc)
        return matching, (Rc, Pc)

    def step_1_a(self):
        E_cand = set()
        uncovered_rows = [i for i in range(self.r) if i not in self.Rc]
        uncovered_cols = [j for j in range(self.p) if j not in self.Pc]
        if not uncovered_rows or not uncovered_cols:
            self.E_cand = E_cand
            return E_cand
        min_global_slack = np.inf
        best_edges = []
        for i in uncovered_rows:
            for j in uncovered_cols:
                slack = self.calculate_slack(i, j)
                if slack < min_global_slack:
                    min_global_slack = slack
                    best_edges = [(i, j)]
                elif slack == min_global_slack:
                    best_edges.append((i, j))
        E_cand = set(best_edges)
        self.E_cand = E_cand
        return E_cand

    def step_1_b(self):
        E_cand = self.E_cand
        if not E_cand:
            self.delta = None
            return None
        min_slack = np.inf
        for i, j in E_cand:
            slack = self.calculate_slack(i, j)
            if slack < min_slack:
                min_slack = slack
        delta = min_slack
        self.delta = delta
        self.update_labels(delta)
        return delta

    def update_labels(self, delta):
        if delta is None:
            raise ValueError("Delta is None, cannot update labels.")
        uncovered_p = [j for j in range(self.p) if j not in self.Pc]
        for i in self.Rc:
            self.agent_label[i] -= delta
        for j in uncovered_p:
            self.task_label[j] += delta
        return self.agent_label, self.task_label


class HungarianModeA(SyncAction):

    def __init__(self, name, agent):
        super().__init__(name, self.decide)
        self.agent = agent
        self.weights = np.ndarray([])
        self.r = None
        self.p = None
        self.agent_label = None
        self.task_label = None
        self.M = []
        self.Ey = set()
        self.Rc = set()
        self.Pc = set()
        self.Vc = set()
        self.E_cand = set()
        self.delta = None
        self.assigned_tasks = {}
        self.agent_idx_to_id = {}
        self.task_idx_to_id = {}
        self.task_idx_to_obj = {}
        self.num_original_agents = 0
        self.num_original_tasks = 0
        self.DUMMY_COST = 0.0

    def decide(self, agent, blackboard):
        _local_tasks_info = blackboard['local_tasks_info']
        _local_agents_info = blackboard['local_agents_info']

        for _agent in _local_agents_info:
            agent_id = _agent.agent_id
            assigned_task = self.assigned_tasks.get(agent_id, None)
            if assigned_task is not None and assigned_task.completed:
                self.assigned_tasks[agent_id] = None

        all_available = all(
            self.assigned_tasks.get(_agent.agent_id, None) is None
            for _agent in _local_agents_info
        )

        if all_available:
            self.weights = self.build_weights_matrix(_local_agents_info, _local_tasks_info)
            self.agent_label = np.min(self.weights, axis=1)
            self.task_label = np.zeros(self.p, dtype=float)
            self.hungarian(max_iter=100)

            print("\n" + "="*60)
            print("HUNGARIAN ALGORITHM RESULT")
            print("="*60)
            print(f"\n[INFO] Agents: {self.num_original_agents}, Tasks: {self.num_original_tasks}")
            print(f"[INFO] Matrix size: {self.r} x {self.p}")
            print("\n[WEIGHTS MATRIX] (cost = 1/reward, inf = dummy)")
            header = "          "
            for j in range(self.p):
                task_id = self.task_idx_to_id.get(j, f"T{j}")
                header += f"{str(task_id)[:8]:>10}"
            print(header)
            for i in range(self.r):
                agent_id = self.agent_idx_to_id.get(i, f"A{i}")
                row_str = f"{str(agent_id)[:8]:<10}"
                for j in range(self.p):
                    val = self.weights[i][j]
                    if np.isinf(val):
                        row_str += f"{'inf':>10}"
                    else:
                        row_str += f"{val:>10.4f}"
                print(row_str)
            print("\n[ASSIGNMENT RESULT]")
            for agent_id, task_obj in self.assigned_tasks.items():
                task_id = task_obj.task_id if task_obj else None
                print(f"  Agent {agent_id} -> Task {task_id}")
            print("="*60 + "\n")

        task_allocations = {}
        for _agent in _local_agents_info:
            agent_id = _agent.agent_id
            assigned_task = self.assigned_tasks.get(agent_id, None)
            assigned_tasks = [assigned_task] if assigned_task else []
            _agent.set_planned_tasks(assigned_tasks)
            task_allocations[agent_id] = assigned_task.task_id if assigned_task is not None else None

        task_allocations["timestamp"] = time.time()
        blackboard["task_allocations"] = task_allocations
        return Status.SUCCESS

    def build_weights_matrix(self, _local_agents_info, _local_tasks_info):
        num_agents = len(_local_agents_info)
        num_tasks = len(_local_tasks_info)
        self.num_original_agents = num_agents
        self.num_original_tasks = num_tasks
        n = max(num_agents, num_tasks)
        self.r = n
        self.p = n
        self.agent_idx_to_id = {i: agent.agent_id for i, agent in enumerate(_local_agents_info)}
        self.task_idx_to_id = {j: task.task_id for j, task in enumerate(_local_tasks_info)}
        self.task_idx_to_obj = {j: task for j, task in enumerate(_local_tasks_info)}
        weights = np.full((n, n), self.DUMMY_COST, dtype=float)
        for i, agent in enumerate(_local_agents_info):
            for j, task in enumerate(_local_tasks_info):
                expected_reward = self.compute_weight_value(agent, task)
                weights[i][j] = 1.0 / expected_reward
        if num_agents > num_tasks:
            for j in range(num_tasks, n):
                self.task_idx_to_id[j] = f"dummy_task_{j}"
                self.task_idx_to_obj[j] = None
        elif num_agents < num_tasks:
            for i in range(num_agents, n):
                self.agent_idx_to_id[i] = f"dummy_agent_{i}"
        return weights

    def compute_weight_value(self, agent, task):
        agent_position = agent.position
        task_position = pygame.Vector2(task.position)
        distance_to_task = agent_position.distance_to(task_position)
        expected_reward = LAMBDA**(distance_to_task/agent.max_speed + task.amount/agent.work_rate)
        return expected_reward

    def hungarian(self, max_iter=100):
        n = self.r
        iteration = 0
        self.build_equality_edges()
        matching, _ = self.find_matching_and_cover(self.agent_label, self.task_label)
        while len(matching) < n and iteration < max_iter:
            iteration += 1
            self.step_1_a()
            if len(self.E_cand) == 0:
                break
            delta = self.step_1_b()
            if delta is None or delta == 0:
                break
            self.build_equality_edges()
            matching, _ = self.find_matching_and_cover(self.agent_label, self.task_label)
        self._assign_from_matching(matching)

    def _assign_from_matching(self, matching):
        self.assigned_tasks = {}
        for (i, j) in matching:
            if i >= self.num_original_agents:
                continue
            if j >= self.num_original_tasks:
                continue
            agent_id = self.agent_idx_to_id[i]
            task_obj = self.task_idx_to_obj[j]
            self.assigned_tasks[agent_id] = task_obj

    def build_equality_edges(self, eps=1e-10):
        self.Ey = set()
        for i in range(self.r):
            for j in range(self.p):
                if abs(self.calculate_slack(i, j)) < eps:
                    self.Ey.add((i, j))
        return self.Ey

    def calculate_slack(self, i, j):
        return self.weights[i, j] - self.agent_label[i] - self.task_label[j]

    def bmp(self, r, match_r, match_p, adj, visited):
        if visited[r]:
            return False
        visited[r] = True
        for p in adj[r]:
            if match_p[p] == -1 or self.bmp(match_p[p], match_r, match_p, adj, visited):
                match_r[r] = p
                match_p[p] = r
                return True
        return False

    def find_matching_and_cover(self, r, p):
        self.agent_label = r
        self.task_label = p
        self.build_equality_edges()
        adj = [[] for _ in range(self.r)]
        for r_idx, p_idx in self.Ey:
            adj[r_idx].append(p_idx)
        match_r = [-1] * self.r
        match_p = [-1] * self.p
        rows = list(range(self.r))
        random.shuffle(rows)
        for r_idx in rows:
            visited = [False] * self.r
            self.bmp(r_idx, match_r, match_p, adj, visited)
        matching = []
        for r_idx in range(self.r):
            if match_r[r_idx] != -1:
                matching.append((r_idx, match_r[r_idx]))
        unmatched_r = [r for r in range(self.r) if match_r[r] == -1]
        reachable_r = set()
        reachable_p = set()

        def dfs_from_unmatched_rows(r_label):
            if r_label in reachable_r:
                return
            reachable_r.add(r_label)
            for p_label in adj[r_label]:
                if p_label not in reachable_p:
                    reachable_p.add(p_label)
                    if match_p[p_label] != -1:
                        dfs_from_unmatched_rows(match_p[p_label])

        for r in unmatched_r:
            dfs_from_unmatched_rows(r)
        Rc = [r for r in range(self.r) if r not in reachable_r]
        Pc = list(reachable_p)
        self.Rc = set(Rc)
        self.Pc = set(Pc)
        self.M = matching
        self.Vc = self.Rc.union(self.Pc)
        return matching, (Rc, Pc)

    def step_1_a(self):
        E_cand = set()
        uncovered_rows = [i for i in range(self.r) if i not in self.Rc]
        uncovered_cols = [j for j in range(self.p) if j not in self.Pc]
        if not uncovered_rows or not uncovered_cols:
            self.E_cand = E_cand
            return E_cand
        min_global_slack = np.inf
        best_edges = []
        for i in uncovered_rows:
            for j in uncovered_cols:
                slack = self.calculate_slack(i, j)
                if slack < min_global_slack:
                    min_global_slack = slack
                    best_edges = [(i, j)]
                elif slack == min_global_slack:
                    best_edges.append((i, j))
        E_cand = set(best_edges)
        self.E_cand = E_cand
        return E_cand

    def step_1_b(self):
        E_cand = self.E_cand
        if not E_cand:
            self.delta = None
            return None
        min_slack = np.inf
        for i, j in E_cand:
            slack = self.calculate_slack(i, j)
            if slack < min_slack:
                min_slack = slack
        delta = min_slack
        self.delta = delta
        self.update_labels(delta)
        return delta

    def update_labels(self, delta):
        if delta is None:
            raise ValueError("Delta is None, cannot update labels.")
        uncovered_p = [j for j in range(self.p) if j not in self.Pc]
        for i in self.Rc:
            self.agent_label[i] -= delta
        for j in uncovered_p:
            self.task_label[j] += delta
        return self.agent_label, self.task_label


class HungarianModeB(SyncAction):

    def __init__(self, name, agent):
        super().__init__(name, self.decide)
        self.agent = agent
        self.weights = np.ndarray([])
        self.r = None
        self.p = None
        self.agent_label = None
        self.task_label = None
        self.M = []
        self.Ey = set()
        self.Rc = set()
        self.Pc = set()
        self.Vc = set()
        self.E_cand = set()
        self.delta = None
        self.assigned_tasks = {}
        self.agent_idx_to_id = {}
        self.task_idx_to_id = {}
        self.task_idx_to_obj = {}
        self.num_original_agents = 0
        self.num_original_tasks = 0
        self.DUMMY_COST = 0.0

    def decide(self, agent, blackboard):
        _local_tasks_info = blackboard['local_tasks_info']
        _local_agents_info = blackboard['local_agents_info']

        for _agent in _local_agents_info:
            agent_id = _agent.agent_id
            assigned_task = self.assigned_tasks.get(agent_id, None)
            if assigned_task is not None and assigned_task.completed:
                self.assigned_tasks[agent_id] = None

        any_available = any(
            self.assigned_tasks.get(_agent.agent_id, None) is None
            for _agent in _local_agents_info
        )

        if any_available:
            self.weights = self.build_weights_matrix(_local_agents_info, _local_tasks_info)
            self.agent_label = np.min(self.weights, axis=1)
            self.task_label = np.zeros(self.p, dtype=float)
            self.hungarian(max_iter=100)

            print("\n" + "="*60)
            print("HUNGARIAN ALGORITHM RESULT")
            print("="*60)
            print(f"\n[INFO] Agents: {self.num_original_agents}, Tasks: {self.num_original_tasks}")
            print(f"[INFO] Matrix size: {self.r} x {self.p}")
            print("\n[WEIGHTS MATRIX] (cost = 1/reward, inf = dummy)")
            header = "          "
            for j in range(self.p):
                task_id = self.task_idx_to_id.get(j, f"T{j}")
                header += f"{str(task_id)[:8]:>10}"
            print(header)
            for i in range(self.r):
                agent_id = self.agent_idx_to_id.get(i, f"A{i}")
                row_str = f"{str(agent_id)[:8]:<10}"
                for j in range(self.p):
                    val = self.weights[i][j]
                    if np.isinf(val):
                        row_str += f"{'inf':>10}"
                    else:
                        row_str += f"{val:>10.4f}"
                print(row_str)
            print("\n[ASSIGNMENT RESULT]")
            for agent_id, task_obj in self.assigned_tasks.items():
                task_id = task_obj.task_id if task_obj else None
                print(f"  Agent {agent_id} -> Task {task_id}")
            print("="*60 + "\n")

        task_allocations = {}
        for _agent in _local_agents_info:
            agent_id = _agent.agent_id
            assigned_task = self.assigned_tasks.get(agent_id, None)
            assigned_tasks = [assigned_task] if assigned_task else []
            _agent.set_planned_tasks(assigned_tasks)
            task_allocations[agent_id] = assigned_task.task_id if assigned_task is not None else None

        task_allocations["timestamp"] = time.time()
        blackboard["task_allocations"] = task_allocations
        return Status.SUCCESS

    def build_weights_matrix(self, _local_agents_info, _local_tasks_info):
        num_agents = len(_local_agents_info)
        num_tasks = len(_local_tasks_info)
        self.num_original_agents = num_agents
        self.num_original_tasks = num_tasks
        n = max(num_agents, num_tasks)
        self.r = n
        self.p = n
        self.agent_idx_to_id = {i: agent.agent_id for i, agent in enumerate(_local_agents_info)}
        self.task_idx_to_id = {j: task.task_id for j, task in enumerate(_local_tasks_info)}
        self.task_idx_to_obj = {j: task for j, task in enumerate(_local_tasks_info)}
        weights = np.full((n, n), self.DUMMY_COST, dtype=float)
        for i, agent in enumerate(_local_agents_info):
            for j, task in enumerate(_local_tasks_info):
                expected_reward = self.compute_weight_value(agent, task)
                weights[i][j] = 1.0 / expected_reward
        if num_agents > num_tasks:
            for j in range(num_tasks, n):
                self.task_idx_to_id[j] = f"dummy_task_{j}"
                self.task_idx_to_obj[j] = None
        elif num_agents < num_tasks:
            for i in range(num_agents, n):
                self.agent_idx_to_id[i] = f"dummy_agent_{i}"
        return weights

    def compute_weight_value(self, agent, task):
        agent_position = agent.position
        task_position = pygame.Vector2(task.position)
        distance_to_task = agent_position.distance_to(task_position)
        expected_reward = LAMBDA**(distance_to_task/agent.max_speed + task.amount/agent.work_rate)
        return expected_reward

    def hungarian(self, max_iter=100):
        n = self.r
        iteration = 0
        self.build_equality_edges()
        matching, _ = self.find_matching_and_cover(self.agent_label, self.task_label)
        while len(matching) < n and iteration < max_iter:
            iteration += 1
            self.step_1_a()
            if len(self.E_cand) == 0:
                break
            delta = self.step_1_b()
            if delta is None or delta == 0:
                break
            self.build_equality_edges()
            matching, _ = self.find_matching_and_cover(self.agent_label, self.task_label)
        self._assign_from_matching(matching)

    def _assign_from_matching(self, matching):
        self.assigned_tasks = {}
        for (i, j) in matching:
            if i >= self.num_original_agents:
                continue
            if j >= self.num_original_tasks:
                continue
            agent_id = self.agent_idx_to_id[i]
            task_obj = self.task_idx_to_obj[j]
            self.assigned_tasks[agent_id] = task_obj

    def build_equality_edges(self, eps=1e-10):
        self.Ey = set()
        for i in range(self.r):
            for j in range(self.p):
                if abs(self.calculate_slack(i, j)) < eps:
                    self.Ey.add((i, j))
        return self.Ey

    def calculate_slack(self, i, j):
        return self.weights[i, j] - self.agent_label[i] - self.task_label[j]

    def bmp(self, r, match_r, match_p, adj, visited):
        if visited[r]:
            return False
        visited[r] = True
        for p in adj[r]:
            if match_p[p] == -1 or self.bmp(match_p[p], match_r, match_p, adj, visited):
                match_r[r] = p
                match_p[p] = r
                return True
        return False

    def find_matching_and_cover(self, r, p):
        self.agent_label = r
        self.task_label = p
        self.build_equality_edges()
        adj = [[] for _ in range(self.r)]
        for r_idx, p_idx in self.Ey:
            adj[r_idx].append(p_idx)
        match_r = [-1] * self.r
        match_p = [-1] * self.p
        rows = list(range(self.r))
        random.shuffle(rows)
        for r_idx in rows:
            visited = [False] * self.r
            self.bmp(r_idx, match_r, match_p, adj, visited)
        matching = []
        for r_idx in range(self.r):
            if match_r[r_idx] != -1:
                matching.append((r_idx, match_r[r_idx]))
        unmatched_r = [r for r in range(self.r) if match_r[r] == -1]
        reachable_r = set()
        reachable_p = set()

        def dfs_from_unmatched_rows(r_label):
            if r_label in reachable_r:
                return
            reachable_r.add(r_label)
            for p_label in adj[r_label]:
                if p_label not in reachable_p:
                    reachable_p.add(p_label)
                    if match_p[p_label] != -1:
                        dfs_from_unmatched_rows(match_p[p_label])

        for r in unmatched_r:
            dfs_from_unmatched_rows(r)
        Rc = [r for r in range(self.r) if r not in reachable_r]
        Pc = list(reachable_p)
        self.Rc = set(Rc)
        self.Pc = set(Pc)
        self.M = matching
        self.Vc = self.Rc.union(self.Pc)
        return matching, (Rc, Pc)

    def step_1_a(self):
        E_cand = set()
        uncovered_rows = [i for i in range(self.r) if i not in self.Rc]
        uncovered_cols = [j for j in range(self.p) if j not in self.Pc]
        if not uncovered_rows or not uncovered_cols:
            self.E_cand = E_cand
            return E_cand
        min_global_slack = np.inf
        best_edges = []
        for i in uncovered_rows:
            for j in uncovered_cols:
                slack = self.calculate_slack(i, j)
                if slack < min_global_slack:
                    min_global_slack = slack
                    best_edges = [(i, j)]
                elif slack == min_global_slack:
                    best_edges.append((i, j))
        E_cand = set(best_edges)
        self.E_cand = E_cand
        return E_cand

    def step_1_b(self):
        E_cand = self.E_cand
        if not E_cand:
            self.delta = None
            return None
        min_slack = np.inf
        for i, j in E_cand:
            slack = self.calculate_slack(i, j)
            if slack < min_slack:
                min_slack = slack
        delta = min_slack
        self.delta = delta
        self.update_labels(delta)
        return delta

    def update_labels(self, delta):
        if delta is None:
            raise ValueError("Delta is None, cannot update labels.")
        uncovered_p = [j for j in range(self.p) if j not in self.Pc]
        for i in self.Rc:
            self.agent_label[i] -= delta
        for j in uncovered_p:
            self.task_label[j] += delta
        return self.agent_label, self.task_label
