### CHANGELOG.md

## Version 1.1.0

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

