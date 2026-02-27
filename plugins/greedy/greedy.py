import random
import pygame
from modules.utils import config
MODE = config['decision_making']['FirstClaimGreedy']['mode']
W_FACTOR_COST = config['decision_making']['FirstClaimGreedy']['weight_factor_cost']
ENFORCED_COLLABORATION = config['decision_making']['FirstClaimGreedy'].get('enforced_collaboration', False)

class FirstClaimGreedy: # Task selection within each agent's `situation_awareness_radius`
    def __init__(self, agent):
        self.agent = agent
        self.assigned_task = None
        self.my_cost = {}  # task_id -> 내가 해당 task에 대해 계산한 cost (낮을수록 우선)

    def decide(self, blackboard):
        # Place your decision-making code for each agent
        '''
        Output:
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''
        local_tasks_info = blackboard.get('local_tasks_info', {})
        assigned_task_id = blackboard.get('assigned_task_id', None)

        # Check if the existing task is still available
        self.assigned_task = local_tasks_info.get(assigned_task_id)

        # Give up the decision-making process if there is no task nearby
        if len(local_tasks_info) == 0:
            self.assigned_task = None
            self.agent.message_to_share = {
                'agent_id': self.agent.agent_id,
                'assigned_task_id': None,
                'cost': None,
                'task_position': None,
            }
            return None

        # Build neighbor_cost_map once, reuse in both conflict check and filtering
        neighbor_cost_map = self._build_neighbor_cost_map()
        
        # Conflict resolution: 현재 assigned task를 이웃이 더 낮은 cost로 claim했으면 양보
        if self.assigned_task is not None:
            if self._has_priority_conflict_fast(assigned_task_id, neighbor_cost_map):
                self.assigned_task = None
                self.my_cost.pop(assigned_task_id, None)

        # 매 tick마다 재평가: conflict resolution 후 최적 task 선택
        candidates = self.filter_tasks_with_conflict_resolution(list(local_tasks_info.values()), neighbor_cost_map)
        if len(candidates) == 0:
            self.agent.message_to_share = {
                'agent_id': self.agent.agent_id,
                'assigned_task_id': None,
                'cost': None,
                'task_position': None,
            }
            return None

        if MODE == "Random":
            target_task_id = random.choice(candidates).task_id
        elif MODE == "MinDist":
            target_task_id = self.find_min_dist_task(candidates)
        elif MODE == "MaxUtil":
            target_task_id, _ = self.find_max_utility_task(candidates)

        self.assigned_task = local_tasks_info[target_task_id]
        # 매 tick마다 cost 갱신 (로봇 이동에 따라 변함)
        self.my_cost[target_task_id] = self.compute_cost(self.assigned_task)

        self.agent.message_to_share = {
            'agent_id': self.agent.agent_id,
            'assigned_task_id': self.assigned_task.task_id,
            'task_position': {'x': self.assigned_task.position.x, 'y': self.assigned_task.position.y},  # 디버깅용 
            'cost': self.my_cost.get(self.assigned_task.task_id),
        }

        return self.assigned_task.task_id

    def _build_neighbor_cost_map(self) -> dict:
        neighbor_cost_map = {}
        for msg in self.agent.messages_received:
            # 딕셔너리가 'assigned_task_id'와 'cost'를 항상 가지고 있다면 직접 접근([])이 최선
            try:
                t_id = msg['assigned_task_id']
                c = msg['cost']
                if t_id is None or c is None: continue
                
                # 기존 값보다 작을 때만 갱신 (if-in 보다 get 기본값 활용이 깔끔함)
                if c < neighbor_cost_map.get(t_id, 1e18): 
                    neighbor_cost_map[t_id] = c
            except KeyError:
                continue
        return neighbor_cost_map

    def _has_priority_conflict_fast(self, task_id: int, neighbor_cost_map: dict) -> bool:
        """이웃이 나보다 낮은 cost로 task_id를 claim했으면 True 반환."""
        my_cost = self.my_cost.get(task_id)
        neighbor_cost = neighbor_cost_map.get(task_id)
        
        if neighbor_cost is None:
            return False
        if my_cost is None or neighbor_cost < my_cost:
            return True
        return False

    def _has_priority_conflict(self, task_id) -> bool:
        """이웃이 나보다 낮은 cost로 task_id를 claim했으면 True 반환."""
        my_cost = self.my_cost.get(task_id)
        for msg in self.agent.messages_received:
            if msg.get('assigned_task_id') != task_id:
                continue
            neighbor_cost = msg.get('cost')
            if neighbor_cost is None:
                continue
            if my_cost is None or neighbor_cost < my_cost:
                return True  # 이웃이 더 낮은 cost를 가짐
        return False

    def filter_tasks_with_conflict_resolution(self, tasks_info, neighbor_cost_map: dict):
        """내가 우선권을 가지는 task만 반환 (이웃이 더 낮은 cost면 제외)."""
        result = []
        for task in tasks_info:
            task_id = task.task_id
            my_cost = self.my_cost.get(task_id)
            neighbor_cost = neighbor_cost_map.get(task_id)
            
            # 이웃이 없거나, 내 cost가 더 좋음 → 포함
            if neighbor_cost is None or (my_cost is not None and neighbor_cost >= my_cost):
                result.append(task)
            else:
                # 이웃이 더 낮은 cost → 제외
                self.my_cost.pop(task_id, None)
        
        return result

    def find_min_dist_task(self, tasks_info):
        _tasks_distance = {
            task.task_id: self.compute_distance(task) for task in tasks_info
        }
        _min_task_id = min(_tasks_distance, key=_tasks_distance.get)
        return _min_task_id

    def find_max_utility_task(self, tasks_info):
        _current_utilities = {
            task.task_id: self.compute_utility(task) for task in tasks_info
        }

        _max_task_id = max(_current_utilities, key=_current_utilities.get)
        _max_utility = _current_utilities[_max_task_id]

        return _max_task_id, _max_utility

    def compute_cost(self, task):
        """Conflict resolution용 cost. 낮을수록 우선순위 높음."""
        if MODE == "MaxUtil":
            return -self.compute_utility(task)  # 높은 utility = 낮은 cost
        else:  # MinDist, Random
            return self.compute_distance(task)

    def compute_utility(self, task): # Individual Utility Function
        if task is None:
            return float('-inf')

        distance = (self.agent.position - task.position).length()
        return task.amount - W_FACTOR_COST * distance

    def compute_distance(self, task): # Individual Utility Function
        if task is None:
            return float('inf')

        distance = (self.agent.position - task.position).length()
        return distance
