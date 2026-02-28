import time
import pygame
import numpy as np
from modules.base_bt_nodes import SyncAction, Status
from modules.utils import config

LAMBDA = config['decision_making']['CBBA']['task_reward_discount_factor']
MAX_TASKS_PER_AGENT = config['decision_making']['CBBA']['max_tasks_per_agent']


class SGA(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)
        self.agent = agent
        self.bundles = {}            # agent_id -> list[task_id]
        self.paths = {}              # agent_id -> list[Task]
        self.assigned_tasks = {}     # agent_id -> Task or None (head)
        self.agents_score_list = {}  # agent_id -> {task_id: bid}
        self.winning_bids = {}      # task_id -> bid_value
        self.winning_agents = {}   # task_id -> agent_id

    def _decide(self, agent, blackboard):
        _local_tasks_info = blackboard['local_tasks_info']   # list[Task]
        _local_agents_info = blackboard['local_agents_info'] # list[Agent]
        
        self._init_agent_state(_local_agents_info)

        self._drop_completed_tasks(_local_agents_info)

        self._compute_sga(_local_tasks_info, _local_agents_info)

        task_allocations = {}
        for other_agent in _local_agents_info:
            agent_id = other_agent.agent_id
            path = self.paths.get(agent_id, [])
            assigned_task = path[0] if path else None
            self.assigned_tasks[agent_id] = assigned_task
            other_agent.set_planned_tasks(path)
            task_allocations[agent_id] = assigned_task.task_id if assigned_task is not None else None

        task_allocations["timestamp"] = time.time()
        blackboard["task_allocations"] = task_allocations
        return Status.SUCCESS

    def _drop_completed_tasks(self, agents):
        for other_agent in agents:
            agent_id = other_agent.agent_id
            assigned_task = self.assigned_tasks.get(agent_id, None)
            if assigned_task is not None and assigned_task.completed:
                _done_task_id = assigned_task.task_id
                if _done_task_id in self.bundles[agent_id]:
                    self.bundles[agent_id].remove(_done_task_id)
                if assigned_task in self.paths[agent_id]:
                    self.paths[agent_id].remove(assigned_task)
                self.assigned_tasks[agent_id] = None
                
    def _init_agent_state(self, agents):
        for other_agent in agents:
            agent_id = other_agent.agent_id
            if agent_id not in self.bundles:
                self.bundles[agent_id] = []
            if agent_id not in self.paths:
                self.paths[agent_id] = []

    def _compute_sga(self, _local_tasks_info, _local_agents_info):

        remaining_tasks = [t for t in _local_tasks_info if not t.completed]
        
        N_u = len(_local_agents_info)
        N_t = len(remaining_tasks)
        N_min = min(N_t, N_u * MAX_TASKS_PER_AGENT)

        for _ in range(N_min):
            if not remaining_tasks:
                break

            best_gain = float('-inf')
            best_agent = None
            best_task = None
            best_insertion_idx = None

            for _agent in _local_agents_info:
                _bundle = self.bundles.get(_agent.agent_id, [])
                _path = self.paths.get(_agent.agent_id, [])
                
                if len(_bundle) >= min(MAX_TASKS_PER_AGENT, len(remaining_tasks)):
                    continue

                my_bid_list, best_insertion_idx_list = self.get_my_bid_value_list(_agent, remaining_tasks, _path)

                task_to_add = self.get_best_task(my_bid_list)
                if task_to_add is None:
                    continue

                _gain = my_bid_list.get(task_to_add.task_id, float('-inf'))
                if _gain > best_gain:
                    best_gain = _gain
                    best_agent = _agent
                    best_task = task_to_add
                    best_insertion_idx = best_insertion_idx_list[task_to_add.task_id]

            if best_agent is None or best_task is None:
                break
            

            existing_winning_agent_id = self.winning_agents.get(best_task.task_id, None)
            # CBBA: _update와 동일
            self.winning_bids[best_task.task_id] = best_gain
            self.winning_agents[best_task.task_id] = best_agent.agent_id
            
            self.bundles[best_agent.agent_id].append(best_task.task_id)
            self.paths[best_agent.agent_id].insert(best_insertion_idx, best_task)
            
            # CBBA: update_bundle_and_path와 동일
            if existing_winning_agent_id is not None and existing_winning_agent_id != best_agent.agent_id:
                _bundle = self.bundles[existing_winning_agent_id]
                _n_bar = len(_bundle)
                for idx, task_id in enumerate(_bundle):
                    if self.winning_agents[task_id] != existing_winning_agent_id:
                        _n_bar = idx
                        break
                _tasks_to_remove = set(_bundle[_n_bar:])
                for _task_id in _bundle[_n_bar+1:]:
                    self.winning_bids[_task_id] = float('-inf')
                    self.winning_agents[_task_id] = None
                self.bundles[existing_winning_agent_id] = _bundle[0:_n_bar]
                self.paths[existing_winning_agent_id] = [t for t in self.paths[existing_winning_agent_id] if t.task_id not in _tasks_to_remove]


            # 전역 후보에서 제거
            remaining_tasks = [t for t in remaining_tasks if t.task_id != best_task.task_id]

    def get_my_bid_value_list(self, agent, tasks, path):
        S_p = self.calculate_score_along_path(agent, path)
        my_bid_list = {}
        best_insertion_idx_list = {}

        for task in tasks:
            _marginal_score_by_new_task = []
            if task in path:
                continue  # 내 path에 이미 있는 task는 건너뜀 (cbba.build_bundle 로직 반영)

            for idx in range(len(path) + 1):
                _alternative_path = self.get_alternative_path(path, task, idx)
                S_p_plus_j_at_idx = self.calculate_score_along_path(agent, _alternative_path)
                _marginal_score_by_new_task.append(S_p_plus_j_at_idx - S_p)

            _best_insertion_idx = np.argmax(_marginal_score_by_new_task)
            _c_ij = _marginal_score_by_new_task[_best_insertion_idx]
            my_bid_list[task.task_id] = _c_ij
            best_insertion_idx_list[task.task_id] = _best_insertion_idx

        return my_bid_list, best_insertion_idx_list

    def get_best_task(self, my_bid_list):
        """
        [Output] task object
        """
        ### Algorithm 3, Line 8
        for task_id, winning_bid_value in self.winning_bids.items():
            if task_id in my_bid_list:
                if winning_bid_value > my_bid_list[task_id]:
                    my_bid_list[task_id] = float('-inf')
            else:
                # Skip if y's key is not in my_bid_list
                continue       

        ### Algorithm 3, Line 9        
        best_task_id = max(my_bid_list, key=my_bid_list.get)
        best_task_score = my_bid_list[best_task_id]

        return self.agent.tasks_info[best_task_id] if best_task_score > float('-inf') else None

    def get_alternative_path(self, path, task, idx):
        _new_path = path[:] # Creates a shallow copy of the list
        try:
            if idx < 0:
                raise IndexError("Index cannot be negative.")
            elif idx > len(_new_path):
                raise IndexError(f"Index {idx} out of range for list of length {len(_new_path)}.")
            _new_path.insert(idx, task)
            return _new_path
        
        except IndexError as e:
            print(f"Error: {e}")     

    def calculate_score_along_path(self, agent, path): 
        """
        Compute S^{p_i} in Eqn (11) in the CBBA paper 
        """
        
        current_position = agent.position
        expected_reward_from_task = 0
        distance_to_next_task_from_start = 0
        for task in path:
            next_position = pygame.Vector2(task.position)
            distance_to_next_task_from_start += current_position.distance_to(next_position)
            # Time-discounted reward
            expected_reward_from_task += LAMBDA**(distance_to_next_task_from_start/agent.max_speed + task.amount/agent.work_rate) #*task.amount            
            current_position = next_position

        return expected_reward_from_task
