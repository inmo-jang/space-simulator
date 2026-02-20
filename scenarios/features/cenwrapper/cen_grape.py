import time
import random
from modules.base_bt_nodes import SyncAction, Status
from modules.utils import config

INITIALIZE_PARTITION = config['decision_making']['GRAPE']['initialize_partition']
REINITIALIZE_PARTITION = config['decision_making']['GRAPE']['reinitialize_partition_on_completion']
COST_WEIGHT_FACTOR = config['decision_making']['GRAPE']['cost_weight_factor']
SOCIAL_INHIBITION_FACTOR = config['decision_making']['GRAPE']['social_inhibition_factor']


class CenGRAPE(SyncAction):
    """
    Centralized GRAPE Algorithm
    - Leader agent가 모든 agent의 partition을 중앙에서 관리
    - agents_state: agent별 상태 (satisfied_flag, iteration, time_stamp, current_utilities)
    - 분산형 distributed_mutex 대신 중앙 직접 계산
    """
    def __init__(self, name, agent):
        super().__init__(name, self.decide)
        self.agent = agent
        self.partition = {}
        self.initialised = False
        self.agents_state = {}

    def decide(self, agent, blackboard):
        _local_tasks_info = blackboard['local_tasks_info']
        _local_agents_info = blackboard['local_agents_info']

        self._init_partition_structure(_local_tasks_info)
        self._init_agents_state(_local_agents_info)

        if not self.initialised and INITIALIZE_PARTITION == "Distance":
            if _local_tasks_info and _local_agents_info:
                self.partition = self.Initialise_partition_by_distance(_local_agents_info, _local_tasks_info)
                self._sync_agents_state_from_partition(_local_agents_info)
                self.initialised = True

        self._drop_completed_tasks(_local_agents_info, _local_tasks_info)

        if len(_local_tasks_info) == 0:
            blackboard["task_allocations"] = {"timestamp": time.time()}
            return Status.SUCCESS

        satisfied_count, consensus_step = self._compute_cen_grape(_local_agents_info, _local_tasks_info)

        # for debug
        # if consensus_step > 0:
        #     print(f"[CenGRAPE] Converged in {consensus_step} steps. Satisfied: {satisfied_count}/{len(_local_agents_info)}")

        task_allocations = {}
        for other_agent in _local_agents_info:
            agent_id = other_agent.agent_id
            agent_state = self.agents_state.get(agent_id, {})
            allocation = agent_state.get('allocation', None)
            task_allocations[agent_id] = allocation
            try:
                if allocation is not None:
                    assigned_task = next((t for t in _local_tasks_info if t.task_id == allocation), None)
                    other_agent.set_planned_tasks([assigned_task] if assigned_task else [])
                else:
                    other_agent.set_planned_tasks([])
            except Exception:
                pass

        task_allocations["timestamp"] = time.time()
        blackboard["task_allocations"] = task_allocations
        return Status.SUCCESS

    def _init_partition_structure(self, tasks_info):
        for task in tasks_info:
            if task.task_id not in self.partition:
                self.partition[task.task_id] = set()

    def _init_agents_state(self, _local_agents_info):
        for other_agent in _local_agents_info:
            agent_id = other_agent.agent_id
            if agent_id not in self.agents_state:
                self.agents_state[agent_id] = {
                    'id': agent_id,
                    'allocation': None,
                    'iteration': 0,
                    'time_stamp': random.uniform(0, 1),
                    'satisfied_flag': False,
                    'util': 0.0,
                    'current_utilities': {}
                }

    def Initialise_partition_by_distance(self, agents_info, tasks_info):
        partition = {task.task_id: set() for task in tasks_info}
        for other_agent in agents_info:
            task_distance = {
                task.task_id: float('inf') if task.completed else (other_agent.position - task.position).length()
                for task in tasks_info
            }
            if len(task_distance) > 0:
                preferred_task_id = min(task_distance, key=task_distance.get)
                partition.setdefault(preferred_task_id, set())
                partition[preferred_task_id].add(other_agent.agent_id)
        return partition

    def _sync_agents_state_from_partition(self, _local_agents_info):
        for other_agent in _local_agents_info:
            agent_id = other_agent.agent_id
            allocation = self.get_assigned_task_from_partition(agent_id)
            if agent_id in self.agents_state:
                self.agents_state[agent_id]['allocation'] = allocation

    def get_assigned_task_from_partition(self, agent_id):
        for task_id, coalition_members_id in self.partition.items():
            if agent_id in coalition_members_id:
                return task_id
        return None

    def _drop_completed_tasks(self, _local_agents_info, tasks_info):
        for task in tasks_info:
            if task.completed and task.task_id in self.partition:
                affected_agents = list(self.partition[task.task_id])
                if affected_agents:
                    self.partition[task.task_id] = set()
                    for agent_id in affected_agents:
                        if agent_id in self.agents_state:
                            self.agents_state[agent_id]['allocation'] = None
                            self.agents_state[agent_id]['satisfied_flag'] = False
                    if REINITIALIZE_PARTITION == "Distance":
                        _affected_agents = [a for a in _local_agents_info if a.agent_id in affected_agents]
                        __local_tasks_info = [t for t in tasks_info if not t.completed]
                        if _affected_agents and __local_tasks_info:
                            self._reInitialise_partition_for_agents(_affected_agents, __local_tasks_info)

    def _reInitialise_partition_for_agents(self, agents_info, tasks_info):
        for other_agent in agents_info:
            task_distance = {
                task.task_id: float('inf') if task.completed else (other_agent.position - task.position).length()
                for task in tasks_info
            }
            if len(task_distance) > 0:
                preferred_task_id = min(task_distance, key=task_distance.get)
                self.partition.setdefault(preferred_task_id, set())
                self.partition[preferred_task_id].add(other_agent.agent_id)
                if other_agent.agent_id in self.agents_state:
                    self.agents_state[other_agent.agent_id]['allocation'] = preferred_task_id

    def _compute_cen_grape(self, _local_agents_info, _local_tasks_info):
        num_agents = len(_local_agents_info)
        max_iterations = num_agents * len(_local_tasks_info) * 2
        satisfied_agents_count = 0
        consensus_step = 0

        while satisfied_agents_count < num_agents:
            satisfied_agents_count = 0
            for other_agent in _local_agents_info:
                agent_id = other_agent.agent_id
                agent_state = self.agents_state.get(agent_id)
                if agent_state is None:
                    continue
                current_task_id = agent_state['allocation']
                max_task_id, max_utility, current_utilities = self.find_max_utility_task(other_agent, _local_tasks_info)
                agent_state['current_utilities'] = current_utilities
                if max_utility == float('-inf'):
                    agent_state['satisfied_flag'] = True
                    satisfied_agents_count += 1
                    continue
                if current_task_id == max_task_id:
                    agent_state['satisfied_flag'] = True
                    agent_state['util'] = max_utility
                    satisfied_agents_count += 1
                else:
                    agent_state['satisfied_flag'] = False
                    agent_state['time_stamp'] = random.uniform(0, 1)
                    agent_state['iteration'] += 1
                    self.discard_agent_from_coalition(agent_id, current_task_id)
                    self.partition.setdefault(max_task_id, set())
                    self.partition[max_task_id].add(agent_id)
                    agent_state['allocation'] = max_task_id
                    agent_state['util'] = 0.0
            consensus_step += 1
            if consensus_step > max_iterations:
                break

        return satisfied_agents_count, consensus_step

    def find_max_utility_task(self, other_agent, tasks_info):
        current_utilities = {}
        for task in tasks_info:
            if task.completed:
                current_utilities[task.task_id] = float('-inf')
            else:
                current_utilities[task.task_id] = self.compute_utility(other_agent, task)
        if not current_utilities:
            return None, float('-inf'), {}
        max_task_id = max(current_utilities, key=current_utilities.get)
        max_utility = current_utilities[max_task_id]
        return max_task_id, max_utility, current_utilities

    def compute_utility(self, other_agent, task):
        if task is None:
            return float('-inf')
        self.partition.setdefault(task.task_id, set())
        num_collaborator = len(self.partition[task.task_id])
        if other_agent.agent_id not in self.partition[task.task_id]:
            num_collaborator += 1
        if num_collaborator == 0:
            num_collaborator = 1
        distance = (other_agent.position - task.position).length()
        utility = task.amount / num_collaborator - COST_WEIGHT_FACTOR * distance * (num_collaborator ** SOCIAL_INHIBITION_FACTOR)
        return utility

    def discard_agent_from_coalition(self, agent_id, task_id):
        if task_id is not None and task_id in self.partition:
            self.partition[task_id].discard(agent_id)
