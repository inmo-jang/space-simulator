import random
import pygame
from modules.utils import config
from enum import Enum
import numpy as np
import copy
import time
from modules.utils import merge_dicts

KEEP_MOVING_DURING_CONVERGENCE = config['decision_making']['CBBA'].get('execute_movements_during_convergence', False)
MAX_TASKS_PER_AGENT = config['decision_making']['CBBA']['max_tasks_per_agent']
LAMBDA = config['decision_making']['CBBA']['task_reward_discount_factor']
WINNING_BID_CANCEL = config['decision_making']['CBBA']['winning_bid_cancel']
NO_BUNDLE_DURATION = config['decision_making']['CBBA']['acceptable_empty_bundle_duration']

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

        self.agent.message_to_share = { # Message Initialization
            'agent_id': self.agent.agent_id,
            'assigned_task_id': None,
            'winning_agents': self.z, 
            'winning_bids': self.y,
            'message_received_time_stamp': self.s
            } 
        
        
        self.assigned_task = None
        self.no_bundle_duration = 0
        
        # self.planned_tasks = [] # For visualisation

    def decide(self, blackboard):
        # Place your decision-making code for each agent
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''        
        previous_assigned_task_id = self.assigned_task.task_id if self.assigned_task is not None else None  # For Debug
        previous_bundle = self.bundle[:]

        local_tasks_info = blackboard['local_tasks_info']

        # Check if the existing task is done or not available anymore (e.g., completed by others, disappeared due to dynamic environment, etc.)            
        self.assigned_task = local_tasks_info.get(previous_assigned_task_id)        
        if self.assigned_task is None and previous_assigned_task_id is not None: 
            if len(self.path) != 0 and self.path[0].task_id == previous_assigned_task_id:
                completed_task_id = self.path.pop(0).task_id
                self.bundle.remove(completed_task_id)

        # Give up the decision-making process if there is no task nearby 
        if len(local_tasks_info) == 0 and len(self.bundle) == 0: 
            return None
        
        # Neutralize all the winning bid information if there are local tasks nearby but the agent cannot choose any of them for a certain period
        if WINNING_BID_CANCEL:
            if len(self.bundle) == 0:
                self.no_bundle_duration += 1 # Increase the duration (unit BT tick) of having no bundle                   

            if self.no_bundle_duration > NO_BUNDLE_DURATION:
                # Neutralize
                self.z = {} 
                self.y = {} 
                self.s = {}                  
                self.no_bundle_duration = 0         

        if True:  # Phase.ASSIGNMENT_CONSENSUS
            # self.update_time_stamp() # NOTE: Moved after conflict resolution. s_i must reflect prior knowledge during Table I comparisons (s_km > s_im), otherwise merging s_k beforehand makes the comparison always false.
            candidates = list(local_tasks_info.values()) if isinstance(local_tasks_info, dict) else local_tasks_info            
            
            # Parse all neighbor messages once before the consensus loop (message caching)
            parsed_messages = []
            for other_agent_message in self.agent.messages_received:
                k_agent_id = other_agent_message.get('agent_id')
                if k_agent_id == self.agent.agent_id:
                    continue
                parsed_messages.append({
                    'agent_id': k_agent_id,
                    'z_k': other_agent_message.get('winning_agents') or {},
                    'y_k': other_agent_message.get('winning_bids') or {},
                    's_k': other_agent_message.get('message_received_time_stamp') or {}
                })
            
            # Now process each task with pre-parsed messages
            for task in candidates:
                z_i = self.z
                y_i = self.y
                s_i = self.s
                j = task.task_id
                
                for parsed_msg in parsed_messages:
                    z_k = parsed_msg['z_k']
                    y_k = parsed_msg['y_k']
                    s_k = parsed_msg['s_k']
                    k_agent_id = parsed_msg['agent_id']
                    
                    # # Skip if task is not in both bid lists
                    # if j not in y_k or j not in y_i: # NOTE: Commented out - this prevents Table I rules (e.g., Rule 4, 13) from firing when z_ij=None. The z_i.get(j) checks handle missing y_i[j] implicitly.
                    #     continue

                    try:    
                        if z_k.get(j) == k_agent_id:
                            # Rule 1
                            if z_i.get(j) == self.agent.agent_id:
                                if y_k[j] > y_i[j]:
                                    self._update(j, y_k, z_k)
                            # Rule 2
                            elif z_i.get(j) == k_agent_id:
                                self._update(j, y_k, z_k)
                            # Rule 4
                            elif z_i.get(j) == None:
                                self._update(j, y_k, z_k)     
                            # Rule 3
                            else:
                                m = z_i.get(j)
                                if m is not None:
                                    try: 
                                        if s_k.get(m, 0) > s_i.get(m, 0) or y_k[j] > y_i[j]:
                                            self._update(j, y_k, z_k)   
                                    except Exception as e:
                                        pass                                

                        elif z_k.get(j) == self.agent.agent_id:
                            # Rule 5
                            if z_i.get(j) == self.agent.agent_id:
                                self._leave()                            
                            # Rule 6
                            elif z_i.get(j) == k_agent_id:
                                self._reset(j)
                            # Rule 8
                            elif z_i.get(j) == None:
                                self._leave()                            
                            # Rule 7
                            else:
                                m = z_i.get(j)
                                if m is not None:
                                    try:                        
                                        if s_k.get(m, 0) > s_i.get(m, 0):
                                            self._reset(j)
                                    except Exception as e:
                                        pass

                        elif z_k.get(j) == None:
                            # Rule 14
                            if z_i.get(j) == self.agent.agent_id:
                                self._leave()                            
                            # Rule 15
                            elif z_i.get(j) == k_agent_id:
                                self._update(j, y_k, z_k)  
                            # Rule 17
                            elif z_i.get(j) == None:
                                self._leave()                            
                            # Rule 16
                            else:
                                m = z_i.get(j)
                                if m is not None:
                                    if s_k.get(m, 0) > s_i.get(m, 0):
                                        self._reset(j)
                        
                        else:
                            m = z_k.get(j)
                            if m is not None:
                                # Rule 9
                                if z_i.get(j) == self.agent.agent_id:
                                    if s_k.get(m, 0) > s_i.get(m, 0) and y_k[j] > y_i[j]:
                                        self._update(j, y_k, z_k)                                                         
                                # Rule 10
                                elif z_i.get(j) == k_agent_id:
                                    if s_k.get(m, 0) > s_i.get(m, 0):
                                        self._update(j, y_k, z_k)        
                                    else:
                                        self._reset(j)
                                # Rule 11
                                elif z_i.get(j) == m:                            
                                    if s_k.get(m, 0) > s_i.get(m, 0):
                                        self._update(j, y_k, z_k)                                    
                                # Rule 13
                                elif z_i.get(j) == None:
                                    if s_k.get(m, 0) > s_i.get(m, 0):
                                        self._update(j, y_k, z_k)                                    
                                # Rule 12
                                else:
                                    n = z_i.get(j)
                                    if n is not None:
                                        try:
                                            if s_k.get(m, 0) > s_i.get(m, 0) and s_k.get(n, 0) > s_i.get(n, 0):
                                                self._update(j, y_k, z_k)
                                            elif s_k.get(m, 0) > s_i.get(m, 0) and y_k[j] > y_i[j]:
                                                self._update(j, y_k, z_k)                        
                                            elif s_k.get(n, 0) > s_i.get(n, 0) and s_i.get(m, 0) > s_k.get(m, 0):
                                                self._reset(j)
                                        except Exception as e:
                                            pass
                    except Exception as e:
                        pass

            # Update time stamp after conflict resolution (Eqn 5)
            self.update_time_stamp()

            # Bundle Update
            updated_bundle, updated_path = self.update_bundle_and_path()
            self.bundle = updated_bundle
            self.path = updated_path

            if WINNING_BID_CANCEL:
                if len(self.bundle) > 0:
                    self.no_bundle_duration = 0

        # Rebid check: recalculate bid for the first task in the path
        if self.path:
            first_task = self.path[0]
            current_bid = self.calculate_score_along_path(self.agent.position, [first_task])
            if current_bid >= self.y.get(first_task.task_id, 0):
                self.y[first_task.task_id] = current_bid
            else:
                # Position worsened — abandon entire bundle and rebuild
                for task_id in self.bundle:
                    if self.z.get(task_id) == self.agent.agent_id:
                        self.y[task_id] = float('-inf')
                        self.z[task_id] = None
                self.bundle = []
                self.path = []

        if True:  # Phase.BUILD_BUNDLE
            self.build_bundle(local_tasks_info)
            # Broadcasting
            self.agent.message_to_share = {
                'agent_id': self.agent.agent_id,
                'assigned_task_id': self.assigned_task.task_id if self.assigned_task is not None else None,
                'winning_agents': copy.deepcopy(self.z),
                'winning_bids': copy.deepcopy(self.y),
                'message_received_time_stamp': copy.deepcopy(self.s)
                }
            self.agent.set_planned_tasks(self.path) # For visualisation (SPACE only)

        # Convergence Check
        if self.bundle == previous_bundle:
            # Converged!
            self.assigned_task = self.path[0] if self.path else None
            self.agent.message_to_share['assigned_task_id'] = self.assigned_task.task_id if self.assigned_task is not None else None
            self.agent.message_to_share['planned_tasks_id'] = [task.task_id for task in self.path]
            return self.assigned_task.task_id if self.assigned_task is not None else None

        else:
            self.assigned_task = None

        if KEEP_MOVING_DURING_CONVERGENCE:
            # Even though not being converged, let's move to the first task that I prefer to go
            self.assigned_task = self.path[0] if self.path else None
            return self.assigned_task.task_id if self.assigned_task is not None else None
        else:
            # self.agent.reset_movement()  # Neutralise the agent's current movement during converging to a consensus
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

        _tasks_to_remove = set(self.bundle[_n_bar:])
        for _task_id in _tasks_to_remove:
            if self.z.get(_task_id) == self.agent.agent_id:
                self.y[_task_id] = float('-inf')
                self.z[_task_id] = None

        _bundle = self.bundle[0:_n_bar]
        _path = [t for t in self.path if t.task_id not in _tasks_to_remove]

        return _bundle, _path

        


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
            task_to_add = self.get_best_task(my_bid_list, local_tasks_info)

            if task_to_add is None:
                break
            # Line 10
            best_insertion_idx = best_insertion_idx_list[task_to_add.task_id]

            # Line 11
            # self.bundle.insert(best_insertion_idx, task_to_add.task_id)
            self.bundle.append(task_to_add.task_id)
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
        for other_agent in self.agent.messages_received:            
            self.s[other_agent.get('agent_id')] = current_timestamp

        
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
        
        candidates = list(local_tasks_info.values()) if isinstance(local_tasks_info, dict) else local_tasks_info
        for task in candidates:
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
        # _new_path = copy.deepcopy(path)
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
        
    def get_best_task(self, my_bid_list, local_tasks_info):
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


        return local_tasks_info[best_task_id] if best_task_score > float('-inf') else None

    def calculate_score_along_path(self, agent_position, path): 
        """
        Compute S^{p_i} in Eqn (11) in the CBBA paper 
        """
        
        current_position = agent_position
        expected_reward_from_task = 0
        distance_to_next_task_from_start = 0
        for task in path:
            next_position = pygame.Vector2(task.position)
            distance_to_next_task_from_start += current_position.distance_to(next_position)
            # Time-discounted reward
            AGENT_SPEED = 0.5
            expected_reward_from_task += LAMBDA**(distance_to_next_task_from_start/AGENT_SPEED)         
            # expected_reward_from_task += (task.amount - (distance_to_next_task_from_start/self.agent.max_speed + task.amount/self.agent.work_rate))
            current_position = next_position

        return expected_reward_from_task

