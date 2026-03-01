import numpy as np
from collections import deque
from scipy.optimize import linear_sum_assignment
from modules.utils import config
from enum import Enum

# Configuration
LAMBDA = config['decision_making']['Hungarian']['task_reward_discount_factor']
DUMMY_COST = config['decision_making']['Hungarian']['dummy_cost']

class Phase(Enum):
    SYNC = 1
    MATCH = 2

class DistributedHungarian:
    
    def __init__(self, agent):
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
        
        # Mappings
        self.agent_idx_to_id = {}
        self.task_idx_to_id = {}
        self.task_idx_to_obj = {}
        
        # Assignment tracking
        self.assigned_task = None
        self.completed_tasks = set()
        self.gamma = 0  # Countervalue γ^i (논문의 Build_Latest_Graph 수렴 추적)

        # Init message
        self.global_adjacency = {}
        self._update_message()

    # ==============================================================
    # Main Decision Logic
    # ==============================================================
    
    def decide(self, blackboard):
        previous_assigned_task_id = self.assigned_task.task_id if self.assigned_task is not None else None  # For Debug        

        _local_tasks_info = blackboard.get('local_tasks_info', {})
        messages = self.agent.messages_received
        
        # Handle completed task
        self.assigned_task = _local_tasks_info.get(previous_assigned_task_id)        
        if self.assigned_task is None and previous_assigned_task_id is not None: 
            self._on_task_completed(previous_assigned_task_id)
        
        
        # Continuous Monitoring: Detect cluster changes
        if self._detect_cluster_changes(messages):
            self.assigned_task = None # Reset assignment on cluster change
            self._update_visualization()
        

            
        # Always Build/Sync Graph
        self._build_latest_graph(messages, _local_tasks_info)

        # Run Hungarian (Phase 2 logic)
        assigned_task = self._run_centralized_hungarian()
        self.assigned_task = assigned_task
        self._update_visualization()

        
        # Return result
        self._update_message()
        self.agent.reset_messages_received()
        
        # Debug Log for Assignment
        # assigned_id = self.assigned_task.task_id if self.assigned_task else "None"
        # print(f"[Agent {self.agent.agent_id}] Assigned Task: {assigned_id}")
        
        return self.assigned_task.task_id if self.assigned_task else None
    
    def _on_task_completed(self, task_id):
        self.completed_tasks.add(task_id)
        self._update_visualization()

    # def _initialize(self, tasks):
    #     self.R = [self.agent]
    #     self.P = sorted(tasks.values(), key=lambda t: t.task_id)
    #     self.initialised = True

    # ==============================================================
    # Cluster Synchronization (R/P Logic)
    # ==============================================================

    def _detect_cluster_changes(self, messages):
        """군집 내 멤버 변경(유입/이탈) 감지"""
        current_r_ids = {getattr(a, 'agent_id', a.get('agent_id') if isinstance(a, dict) else None) for a in self.R}
        perceived_ids = {self.agent.agent_id}
        
        for a in messages:
            perceived_ids.add(a.get('agent_id'))
            
        for msg in messages:
            if msg:
                for agent in msg.get('agents_info', []):
                    aid = getattr(agent, 'agent_id', None)
                    if aid is None and isinstance(agent, dict):
                        aid = agent.get('agent_id')
                    
                    if aid is not None:
                        perceived_ids.add(aid)
        
        if not current_r_ids.issubset(perceived_ids):
            self.gamma = 0
            return True
        if not perceived_ids.issubset(current_r_ids):
            self.gamma = 0
            return True
        return False



    def _build_latest_graph(self, messages, local_tasks):
        """Sync Graph"""
        valid_msgs = [m for m in messages if m and 'agent_id' in m]
        
        # 1. Collect Candidates
        candidates = {self.agent.agent_id:
                        {
                            'agent_id': self.agent.agent_id,
                            'position': self.agent.position
                        }
                    }
        for msg in messages:
            candidates[msg['agent_id']] = {
                'agent_id': msg['agent_id'],
                'position': msg.get('position', None)}
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
        my_neighbors = {msg['agent_id'] for msg in messages if 'agent_id' in msg}

        # 2.2 Merge Neighbors' Views via Link State Advertisement
        new_global_adj = {_agent_id: my_neighbors}
        
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
        visited = {_agent_id}
        queue = deque([_agent_id])

        while queue:
            curr = queue.popleft()
            for n in self.global_adjacency.get(curr, set()):
                if n not in visited:
                    visited.add(n)
                    if n in self.global_adjacency:
                        queue.append(n)

        # Update R
        self.R = [candidates[aid] for aid in sorted(visited) if aid in candidates]
        new_R_ids = visited
        
        # Update P
        observed_task_ids = {t.task_id for t in local_tasks.values()}

        # Collect tasks from all reachable neighbors
        current_p_map = {getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else None): t for t in self.P}
        for t in local_tasks.values():
            current_p_map[t.task_id] = t

        # Handle Completed Tasks + tasks_info (merged loop)
        for msg in valid_msgs:
            if msg['agent_id'] not in new_R_ids:
                continue
            for tid in msg.get('completed_tasks', set()):
                if tid not in self.completed_tasks:
                    self.completed_tasks.add(tid)
            for t in msg.get('tasks_info', []):
                tid = getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else None)
                if tid is not None and tid not in self.completed_tasks:
                    observed_task_ids.add(tid)
                    current_p_map[tid] = t

        # Filter P
        self.P = [t for tid, t in current_p_map.items() if tid in observed_task_ids and tid not in self.completed_tasks]
        self.P.sort(key=lambda t: getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else None))

        # Lead Robot Selection via γ (논문의 Build_Latest_Graph)
        # γ가 가장 높은 로봇(= 가장 수렴된 상태)의 countervalue를 상속
        neighbor_gammas = {_agent_id: self.gamma}
        for msg in valid_msgs:
            sender = msg.get('agent_id')
            if sender in visited:
                neighbor_gammas[sender] = msg.get('gamma', 0)

        lead_id = max(neighbor_gammas, key=neighbor_gammas.get)
        lead_gamma = neighbor_gammas[lead_id]
        if lead_id != _agent_id and lead_gamma > self.gamma:
            self.gamma = lead_gamma

    # ==============================================================
    # Messaging
    # ==============================================================
    def _update_message(self):
        # Prepare Graph to Send
        graph_to_send = self.global_adjacency.copy()
        # Ensure my fresh local view is in the message
        _agent_id = self.agent.agent_id
        graph_to_send[_agent_id] = {
            msg.get('agent_id') for msg in self.agent.messages_received
            if msg and 'agent_id' in msg
        }

        self.agent.message_to_share = {
                                       'agent_id': _agent_id,
                                       'adjacency_graph': graph_to_send, # Send Full Graph
                                       'position': self.agent.position,
                                       'agents_info': self.R, # Send Full Agent Objects (Data Payload)
                                       'tasks_info': self.P, # Send Full Task Objects (Data Payload)
                                       'completed_tasks': self.completed_tasks,
                                       'assigned_task_id': self.assigned_task.task_id if self.assigned_task else None,
                                       'gamma': self.gamma,  # Countervalue for lead robot selection
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
        self._build_weights_matrix()

        w = np.where(np.isinf(self.weights), 1e9, self.weights)
        row_ind, col_ind = linear_sum_assignment(w)
        matching = list(zip(row_ind.tolist(), col_ind.tolist()))

        result = self._assign_from_matching(matching)
        self.gamma += 1  # 매칭 완료 시 γ 증가 (논문의 Local_Hungarian 수렴 카운터)
        return result

        
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

        if num_agents > 0 and num_tasks > 0:
            AGENT_SPEED = 0.5
            agent_pos = np.array([[a.get('position').x, a.get('position').y] for a in local_agents])
            task_pos  = np.array([[t.position.x, t.position.y] for t in local_tasks])
            diff = agent_pos[:, np.newaxis, :] - task_pos[np.newaxis, :, :]
            distances = np.sqrt((diff ** 2).sum(axis=2))
            weights[:num_agents, :num_tasks] = 1.0 / (LAMBDA ** (distances / AGENT_SPEED))

        # Setting Dummies
        if num_agents > num_tasks:
            for j in range(num_tasks, n):
                self.task_idx_to_id[j] = f"dummy_task_{j}"
                self.task_idx_to_obj[j] = None
        elif num_agents < num_tasks:
            for i in range(num_agents, n):
                self.agent_idx_to_id[i] = f"dummy_agent_{i}"
        
        self.weights = weights

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
