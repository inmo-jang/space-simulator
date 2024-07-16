### CHANGELOG.md

## Version 1.2.2 (24-07-17)
### New Features
- **Configuration File Handling**: Added command-line argument parsing to `main.py` to accept a custom configuration file path using the `--config` option. (e.g., `python main.py --config=./examples/GRAPE_20_agents_200_tasks.yaml` )

- **Rendering Mode**: 
  - Added `rendering_mode` configuration option to toggle rendering of graphical output.
  - Introduced `rendering_options` under `simulation` configuration section to customize rendering settings when `rendering_mode` is enabled:
    - `agent_tail`: Enables drawing of agent trajectory tails.
    - `agent_communication_topology`: Enables visualization of agent communication topology.
    - `agent_id`: Displays agent identifiers on the screen.
    - `agent_assigned_task_id`: Shows the task identifier assigned to each agent.
    - `task_id`: Displays task identifiers on the tasks.

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

