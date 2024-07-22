# CHANGELOG.md
## Version 1.2.5 (24-07-22)
### New Features
- **Behavior Tree Defined by Groot**
  - Using [Groot2](https://www.behaviortree.dev/groot/), the visualization tool for BT.CPP, you can now define and visualize the behavior tree of agents in the SPADE simulator. The behavior tree file (`.xml`) should be specified by the `behavior_tree_xml` entry in the configuration file.

### Changes
- **Behavior Tree Blackboard Variables**
  - Removed unnecessary variables from the `blackboard`, such as `next_waypoint` and `task_completed`. Consequently, the `DecisionMakingNode` (including decision-making plugins like `grape.py` and `simple.py`) now only sets the `assigned_task_id` as its output, enhancing the readability of decision-making plugins.
  - Renamed `next_waypoint` to `random_waypoint` in the `ExplorationNode` to avoid confusion, as the original name might be misleading.
  - Added `_reset_bt_action_node_status()` to reset the statuses of behavior tree action nodes for each agent before starting the tree.


## Version 1.2.4 (24-07-21)

### New Features
- **Dynamic Task Generation (`main.py`)**:
  - By setting `dynamic_task_generation.enabled: True` in the configuration file, additional tasks (`tasks_per_generation`) can be generated at specified intervals (`interval_seconds`) until the maximum number of generations (`max_generations`) is reached.
  - Various scripts (`agent.py`, `task.py`, `grape.py`) have been updated to be compatible with the integration of these newly-generated tasks during a mission.

- **Rendering Mode**: 
  - Introduced `agent_work_done` feature: Displays the total distance moved and the amount of work done by each agent.

- **Time Series Plot Mode**  
  - When `time_recording_mode` is set to `True`, the simulation will save the time series data of agents' activities to CSV files and generate corresponding PNG plots. This feature provides a comprehensive view of the simulation's progress over time, including metrics such as total distance moved by agents, total task amount done, the number of remaining tasks, and the total amount of tasks.


## Version 1.2.3 (24-07-19)

### New Features
- **GRAPE Algorithm Enhancements (`grape.py`)**:
  - **Decision-Making Process**: It is now based on agents' local situation awareness (`situation_awareness_radius`) and local communication capability (`communication_radius`), not by global information.
  - **Decision-Making Process**: Added logic at the beginning of the `decide()` function to stop and exit the decision-making process if no nearby tasks are found using `self.agent.get_tasks_nearby()`.
  - **Renamed**: `get_assigned_task_id_from_partition()` to `get_assigned_task_from_partition()`: Updated to return the `Task` object directly for efficiency. Note: `self.assigned_task` is the agent's local information about which task it has chosen. This information is not shared outside the behavior tree or used elsewhere.
  - **Renamed**: `get_neighbor_agents_info()` to `get_neighbor_agents_info_in_partition()`: Changed to avoid confusion with `get_agents_nearby()`. `get_neighbor_agents_info_in_partition()` is used to get a list of agents within the same coalition based on partition information.

- **Local Information for Agents (`agent.py`)**
  - Added `get_tasks_nearby()` to list tasks within the agent's `situation_awareness_radius` as defined in `config.yaml`.
  - Added `get_agents_nearby()` to list agents within the agent's `communication_radius` as defined in `config.yaml`.
- **Random Exploration Search (`behavior_tree.py`)**
  - Added `ExplorationNode`: If there is no task nearby, agent selects a random location within the task generation range and sets it as the `next_waypoint`, enabling the agent to exploare new tasks while moving to this point.

- **Local Search (`simple.py`)**
  - Renamed `LocalRandomSearch` to `LocalSearch`, which refers to the decision-making methodology for selecting a task within the agent's `situation_awareness_radius`.
  - Implemented three modes (`Random`, `MinDist`, `MaxUtil`) within `LocalSearch`.
    - **`Random` mode**: Selects a task randomly.
    - **`MinDist` mode**: Selects the task with the shortest distance.
    - **`MaxUtil` mode**: Selects the task with the highest individual utility. Utilizes `weight_factor_cost` (defined in `config.yaml`) to balance task reward and cost.
  - To this end, `get_tasks_nearby()` was required to be modified such that it can provide "alive(not `completed`)" local tasks. 


### Changes
- **Random SearchBehavior Tree (`behavior_tree.py`)**
  - **Updated**: Enhanced `DecisionMakingNode` to complete the decision-making process by setting the `assigned_task_id` and recording the corresponding `next_waypoint` in the blackboard. This change removes the need for the `ConsensusCheckingNode`.
  - **Removed**: `ConsensusCheckingNode`
- **Behavior Tree Structure (`agent.py`)**
  - Modified to use a Fallback node to sequence Decision Making and Task Execution. If these fail (i.e., decision-making is not successful), the agent performs random movement through the Exploration node.
- **LocalRandomSearch Algorithm (simple.py)**:
  - Streamlined core logic for clarity by moving additional functionalities (such as random walk) to `DecisionMakingNode`.  


## Version 1.2.2 (24-07-17)
### New Features
- **LocalRandomSearch Algorithm (simple.py)**:
  - Implemented a random search algorithm enabling agents to select tasks randomly within their `situation_awareness_radius`. If no tasks are within range, agents randomly move to a new position for up to `max_random_movement_duration` seconds.
- **Configuration File Handling**: Added command-line argument parsing to `main.py` to accept a custom configuration file path using the `--config` option. (e.g., `python main.py --config=./examples/GRAPE_20_agents_200_tasks.yaml` )
- **Rendering Mode**: 
  - Added `rendering_mode` configuration option to toggle rendering of graphical output.
  - Introduced `rendering_options` under `simulation` configuration section to customize rendering settings when `rendering_mode` is enabled:
    - `agent_tail`: Enables drawing of agent trajectory tails.
    - `agent_communication_topology`: Enables visualization of agent communication topology.
    - `agent_id`: Displays agent identifiers on the screen.
    - `agent_assigned_task_id`: Shows the task identifier assigned to each agent.
    - `task_id`: Displays task identifiers on the tasks.
    - `agent_situation_awareness_circle`: Displays agent situational awareness circle. 

### Changes
- **Configuration**:
  - Splitted `decision_making` from `agents`. 
- **Decision-Making Status Display**
  - Moved the decision-making status drawing function from `main.py` to the respective decision-making modules. This change allows developers to implement their own display functions.


## Version 1.2.1 (24-07-16)
### New Features
- **Profiling Mode**: Added profiling capability using `cProfile`. Set `simulation.profiling_mode = True` to enable performance analysis of each function.
- **GRAPE Algorithm Enhancements**:
  - Added `execute_movements_during_convergence` parameter to `GRAPE` settings. This allows agents to make movements based on local decisions even if they haven't yet converged to a Nash stable partition.
  - Introduced `initialize_partition` and `reinitialize_partition_on_completion` methods (defined in `config.yaml`) to enhance the efficiency of achieving Nash stable partitions.

### Changes
- **Agent Global Information (agent.py)**:
  - Enabled each agent to access global information about all agents (i.e., `agents_info`). Note that `tasks_info` is also global information about tasks. 
- **Agent Draw (agent.py)**:
  - Introduced default drawing of agent tails for improved visualization.

- **GRAPE (grape.py)**
  - Resolved issues in `distributed_mutex` related to message handling.
  - Unified decision-making using `self.assigned_task` throughout the algorithm for clarity, eliminating confusion associated with `_assigned_task_id`.

- **GIF and Config Copy (main.py)**:
  - Integrated shutil to copy config.yaml alongside generated GIFs for easy simulation configuration reference.


## Version 1.2.0 (24-07-15)

### New Features
- **GRAPE (grape.py)**: Implemented the GRAPE algorithm in "Anonymous Hedonic Game for Task Allocation in a Large-Scale Multiple Agent System" (I. Jang, H.S. Shin, A. Tsourdos, IEEE Transactions on Robotics, Dec. 2018).
- **Agent Communication (agent.py)**:
  - Introduced `local_broadcast` method for agent local communication, utilizing `communication_radius` defined in `config.yaml`.
  - Added `draw_communication_topology` for visualizing communication lines based on agent topology.
- **Assigned Task Visualization**: Agents' colors now represent the colors of their assigned tasks for improved visual distinction.


## Version 1.1.0 (24.07-14)

### New Features
- **Simulation Time Display**: The simulation now uses a simulation time based on sampling time, which is displayed in the top right corner of the screen. This provides a more accurate representation of the simulation's progress rather than real-time elapsed.
- **Task Amount Visualization**: Tasks now have an amount range that determines their radius visually on the screen, enhancing the clarity of task sizes.

### Changes
- **Main Game Loop (main.py)**:
  - Updated the task time display to use `simulation_time` instead of real-time.
  - Draw `tasks` first and then `agents`.

- **Task Class (task.py)**:
  - Added `amount` attribute to represent the task's amount.
  - Added `reduce_amount` method to decrease the task's amount over time and mark it as completed.
  - Updated the `draw` method to visualize tasks based on their `amount`.

- **Behavior Tree (behavior_tree.py)**: 
  - Added `work_rate` to `TaskExecutingNode` to allow agents to work on tasks and reduce their amounts.

- **Configuration (config.yaml)**:
  - Added `work_rate` for agents.
  - Added `amounts` configuration to define the range of task amounts.
  - Added `task_visualisation_factor` to adjust the visual representation of tasks based on their amounts.

