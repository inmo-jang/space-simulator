import random
import pygame
from modules.utils import config
from enum import Enum
import numpy as np
import copy
import time
from modules.utils import merge_dicts

MAX_TASKS_PER_AGENT = config['decision_making']['CBBA']['max_tasks_per_agent']
LAMBDA = config['decision_making']['CBBA']['task_reward_discount_factor']
WINNGIN_BID_DISCOUNT_FACTOR = config['decision_making']['CBBA']['winngin_bid_discount_factor']
SAMPLE_FREQ = config['simulation']['sampling_freq']

class Phase(Enum):
    BUILD_BUNDLE = 1
    ASSIGNMENT_CONSENSUS = 2

class CBBA:  
    def __init__(self, agent):
        self.agent = agent        

        self.z = {} # Winning agent list (key: task_id; value: agent_id)
        self.y = {} # Winning bid list (key: task_id; value: bid value)
        self.s = {} # Time stamp list (key: agent_id; value: time stamp)
        self.bundle = [] # Bundle (a list of task id)      
        self.path = [] # Path (a list of task object) 

        self.phase = Phase.BUILD_BUNDLE

        self.agent.message_to_share = { # Message Initialization
            'agent_id': self.agent.agent_id,
            'winning_agents': self.z, 
            'winning_bids': self.y,
            'message_received_time_stamp': self.s
            } 
        
        
        self.assigned_task = None

    def decide(self, blackboard):
        # Place your decision-making code for each agent
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''        
        # Give up the decision-making process if there is no task nearby 
        local_tasks_info = self.agent.get_tasks_nearby(with_completed_task=False)
        if len(local_tasks_info) == 0: 
            return None

        # Check if the existing task is done
        if self.assigned_task is not None and self.assigned_task.completed:
            if len(self.path) == 0:
                print(f"agent_id = {self.agent.agent_id}; bundle = {self.bundle}; path = {self.path}; assigned_task_id = {self.assigned_task.task_id}")
            if len(self.path) != 0 and self.path[0] == self.assigned_task:
                self.path.pop(0)
                self.bundle.pop(0)
            self.assigned_task = None
            self.phase = Phase.BUILD_BUNDLE

        if len(self.bundle) == 0:
            self.phase = Phase.BUILD_BUNDLE
            
        # Discount winning bid
        self.discount_winning_bid(WINNGIN_BID_DISCOUNT_FACTOR)
        # Look for a task within situation awareness radius if there is no existing assigned task
        # if self.assigned_task is None:
        if self.phase == Phase.BUILD_BUNDLE:
            # Phase 1 Build Bundle 
            self.build_bundle(local_tasks_info)            
            # Broadcasting
            self.agent.message_to_share = { 
                'agent_id': self.agent.agent_id,
                'winning_agents': copy.deepcopy(self.z), 
                'winning_bids': copy.deepcopy(self.y),
                'message_received_time_stamp': copy.deepcopy(self.s)
                } 
            
            self.phase = Phase.ASSIGNMENT_CONSENSUS
            self.agent.set_planned_tasks(self.path) # For visualisation
            return None
        
        if self.phase == Phase.ASSIGNMENT_CONSENSUS:
            self.update_time_stamp()
            # Phase 2 Consensus
            for task in local_tasks_info: 
                for other_agent_message in self.agent.messages_received:
                    k_agent_id = other_agent_message.get('agent_id')
                    if k_agent_id == self.agent.agent_id:
                        continue
                    z_k = other_agent_message.get('winning_agents')
                    y_k = other_agent_message.get('winning_bids')
                    s_k = other_agent_message.get('message_received_time_stamp')

                    z_i = self.z
                    y_i = self.y
                    s_i = self.s

                    j = task.task_id
                    if y_k.get(j) is None or y_i.get(j) is None:
                        continue

                    try:    
                        if z_k[j] == k_agent_id:
                            # Rule 1
                            if z_i[j] == self.agent.agent_id:
                                if y_k[j] > y_i[j]:
                                    self._update(j, y_k, z_k)
                            # Rule 2
                            elif z_i[j] == k_agent_id:
                                self._update(j, y_k, z_k)
                            # Rule 4
                            elif z_i[j] == None:
                                self._update(j, y_k, z_k)     
                            # Rule 3
                            else:
                                m = z_i[j]                                                                                    
                                try: 
                                    if s_k.get(m) > s_i.get(m) or y_k[j] > y_i[j]:
                                        self._update(j, y_k, z_k)   
                                except Exception as e:
                                    pass                                

                        elif z_k[j] == self.agent.agent_id:
                            # Rule 5
                            if z_i[j] == self.agent.agent_id:
                                self._leave()                            
                            # Rule 6
                            elif z_i[j] == k_agent_id:
                                self._reset(j)
                            # Rule 8
                            elif z_i[j] == None:
                                self._leave()                            
                            # Rule 7
                            else:
                                m = z_i[j]    
                                try:                        
                                    if s_k.get(m) > s_i.get(m):
                                        self._reset(j)
                                except Exception as e:
                                    pass

                        elif z_k[j] == None:
                            # Rule 14
                            if z_i[j] == self.agent.agent_id:
                                self._leave()                            
                            # Rule 15
                            elif z_i[j] == k_agent_id:
                                self._update(j, y_k, z_k)  
                            # Rule 17
                            elif z_i[j] == None:
                                self._leave()                            
                            # Rule 16
                            else:
                                m = z_i[j]                            
                                if s_k.get(m) > s_i.get(m):
                                    self._reset(j)
                        
                        else:
                            m = z_k[j]                        
                            # Rule 9
                            if z_i[j] == self.agent.agent_id:
                                if s_k.get(m) > s_i.get(m) and y_k[j] > y_i[j]:
                                    self._update(j, y_k, z_k)                                                         
                            # Rule 10
                            elif z_i[j] == k_agent_id:
                                if s_k.get(m) > s_i.get(m):
                                    self._update(j, y_k, z_k)        
                                else:
                                    self._reset(j)
                            # Rule 11
                            elif z_i[j] == m:                            
                                if s_k.get(m) > s_i.get(m):
                                    self._update(j, y_k, z_k)                                    
                            # Rule 13
                            elif z_i[j] == None:
                                if s_k.get(m) > s_i.get(m):
                                    self._update(j, y_k, z_k)                                    
                            # Rule 12
                            else:
                                n = z_i[j]                        
                                try:
                                    if s_k.get(m) > s_i.get(m) and s_k.get(n) > s_i.get(n):
                                        self._update(j, y_k, z_k)
                                    elif s_k.get(m) > s_i.get(m) and y_k[j] > y_i[j]:
                                        self._update(j, y_k, z_k)                        
                                    elif s_k.get(n) > s_i.get(n) and s_i.get(m) > s_k.get(m):
                                        self._reset(j)
                                except Exception as e:
                                    pass
                    except Exception as e:
                        pass

            # Bundle Update
            updated_bundle, updated_path = self.update_bundle_and_path()
            
            # Reset Message
            self.agent.reset_messages_received()

            if updated_bundle == self.bundle: # NOTE: 원래 모든 agents가 다 converge할 때까지 기다려야하는데, 분산화 현실성상 진행
                # Converged!

                # _next_assigned_task = next((task for task in self.agent.assigned_tasks if task.completed is False), None)
                self.assigned_task = self.path[0] if self.path else None
                
                return copy.deepcopy(self.assigned_task.task_id) if self.assigned_task is not None else None

            else:
                self.bundle = updated_bundle
                self.path = updated_path
                self.agent.set_planned_tasks(self.path) # For visualisation
                self.assigned_task = None # NOTE: 불만족 상황이 되었으니 assigned_task 초기화
                self.phase = Phase.BUILD_BUNDLE
            
        
        return None
    
    def _update(self, task_id, y_k, z_k):
        self.y[task_id] = y_k[task_id]   # Winning bid update
        self.z[task_id] = z_k[task_id]   # Winning agent update


    def _reset(self, task_id):
        self.y[task_id] = 0     # Winning bid reset
        self.z[task_id] = None  # Winning agent reset

    def _leave(self):
        pass

    def update_bundle_and_path(self):
        _n_bar = len(self.bundle)
        for idx, task_id in enumerate(self.bundle):
            if self.z[task_id] != self.agent.agent_id:
                _n_bar = idx
                break

        _bundle = self.bundle[0:_n_bar]
        _path = self.path[0:_n_bar]

        return _bundle, _path

    def discount_winning_bid(self, discount_factor = 0.999):
        return {key: value * discount_factor for key, value in self.y.items()}
        


    def build_bundle(self, local_tasks_info):
        """
        Construct bundle and path list with local information.
        Algorithm 3 in CBBA paper
        """
        # J = list(range(self.task_num))
        

        while len(self.bundle) < min(MAX_TASKS_PER_AGENT, len(local_tasks_info)):
            # Calculate S_p for the constructed path list
            

            # Line 7
            my_bid_list, best_insertion_idx_list = self.get_my_bid_value_list(local_tasks_info) 

            # Line 8~9
            task_to_add = self.get_best_task(my_bid_list)

            if task_to_add is None:
                break
            # Line 10
            best_insertion_idx = best_insertion_idx_list[task_to_add.task_id]

            # Line 11
            self.bundle.insert(best_insertion_idx, task_to_add.task_id)
            # Line 12
            self.path.insert(best_insertion_idx, task_to_add)
            # Line 13
            self.y[task_to_add.task_id] = my_bid_list[task_to_add.task_id]
            # LIne 14
            self.z[task_to_add.task_id] = self.agent.agent_id

    
    def update_time_stamp(self):
        """
        Eqn (5)
        """

        # For neighbor agents
        current_timestamp = int(time.time())
        for other_agent in self.agent.agents_nearby:            
            self.s[other_agent.agent_id] = current_timestamp

        
        # For two-hop neighbor agents
        max_timestamp = {}     
        for other_agent_message in self.agent.messages_received:
            time_stamp = other_agent_message.get("message_received_time_stamp")
            max_timestamp = merge_dicts(max_timestamp, time_stamp)

        # Finally merge
        self.s = merge_dicts(self.s, max_timestamp)
        



    def get_my_bid_value_list(self, local_tasks_info):
        # Calculate S_p for the constructed path list
        S_p = self.calculate_score_along_path(self.agent.position, self.path)

        my_bid_list = {} # My new bid list (key: task_id; value: bid value), denoted by 'c' in the paper (Algorithm 3 Line 3)
        best_insertion_idx_list = {} # (key: task_id; value: bundle insertion position)
        
        for task in local_tasks_info:
            _marginal_score_by_new_task = []
            if task in self.path: # TODO: This might take longer computation
                continue

            for idx in range(len(self.path) + 1):
                _alternative_path = self.get_alternative_path(self.path, task, idx)
                S_p_plus_j_at_idx = self.calculate_score_along_path(self.agent.position, _alternative_path)
                _marginal_score_by_new_task.append(S_p_plus_j_at_idx - S_p)
            
            _best_insertion_idx = np.argmax(_marginal_score_by_new_task)
            _c_ij = _marginal_score_by_new_task[_best_insertion_idx] # Line 7 in Algorithm 3
            my_bid_list[task.task_id] = _c_ij
            best_insertion_idx_list[task.task_id] = _best_insertion_idx

        return my_bid_list, best_insertion_idx_list
    
    def get_alternative_path(self, path, task, idx):
        _new_path = copy.deepcopy(path)
        try:
            if idx < 0:
                raise IndexError("Index cannot be negative.")
            elif idx > len(_new_path):
                raise IndexError(f"Index {idx} out of range for list of length {len(_new_path)}.")
            _new_path.insert(idx, task)
            return _new_path
        
        except IndexError as e:
            print(f"Error: {e}")        
        
    def get_best_task(self, my_bid_list):
        """
        [Output] task object
        """
        ### Algorithm 3, Line 8
        for task_id, winning_bid_value in self.y.items():
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

    def calculate_score_along_path(self, agent_position, path): 
        """
        Compute S^{p_i} in Eqn (11) in the CBBA paper 
        """
        
        current_position = agent_position
        expected_reward_from_task_task = 0
        distance_to_next_task_from_start = 0
        for task in path:
            next_position = pygame.Vector2(task.position)
            distance_to_next_task_from_start += current_position.distance_to(next_position)
            # Time-discounted reward
            # expected_reward_from_task_task += LAMBDA**(distance_to_next_task_from_start/self.agent.max_speed)*task.amount            
            expected_reward_from_task_task += (task.amount - (distance_to_next_task_from_start/self.agent.max_speed))
            current_position = next_position

        return expected_reward_from_task_task

        