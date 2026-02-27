from modules.base_agent import BaseAgent


class Agent(BaseAgent):
    """
    Catcher agent controlled by a Behaviour Tree.

    Holds a reference to the target (TargetTurtle) so that bt_nodes can
    access agent.target directly, mirroring the py_bt_ros design where
    target pose is received via ROS topic.
    """
    def __init__(self, agent_id, position, target):
        super().__init__(agent_id, position, tasks_info=[])
        self.color = (0, 80, 200)  # blue catcher
        self.target = target
