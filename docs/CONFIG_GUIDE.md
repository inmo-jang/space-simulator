# Configuration Manual for SPADE Simulator

This manual provides detailed descriptions of each parameter in the `config.yaml` file used by the SPADE Simulator. Understanding these parameters will help you customize the simulation according to your requirements.

## `agents` Section

This section defines the properties and behaviors of the agents in the simulation.

- **`quantity`**: Specifies the number of agents to be created in the simulation.
    - **Type**: Integer
    - **Example**: `1000`

- **`locations`**: Defines the initial position parameters for the agents.
    - **`x_min`**: Minimum x-coordinate for agent placement.
        - **Type**: Integer
        - **Example**: `0`
    - **`x_max`**: Maximum x-coordinate for agent placement.
        - **Type**: Integer
        - **Example**: `1400`
    - **`y_min`**: Minimum y-coordinate for agent placement.
        - **Type**: Integer
        - **Example**: `0`
    - **`y_max`**: Maximum y-coordinate for agent placement.
        - **Type**: Integer
        - **Example**: `1000`
    - **`non_overlap_radius`**: Minimum distance between agents to prevent overlap at the start.
        - **Type**: Integer
        - **Example**: `0`

- **`decision_making_module_path`**: Specifies the Python module path and class name for the decision-making logic used by agents.
    - **Type**: String
    - **Example**: `plugins.my_decision_making_plugin.MyDecisionMakingClass`

- **`max_speed`**: Maximum speed an agent can achieve.
    - **Type**: Float
    - **Example**: `3.0`

- **`max_accel`**: Maximum acceleration an agent can achieve.
    - **Type**: Float
    - **Example**: `0.1`

- **`max_angular_speed`**: Maximum angular speed (rotation speed) of an agent.
    - **Type**: Float
    - **Example**: `0.3`

- **`target_approaching_radius`**: Distance within which an agent starts slowing down as it approaches its target.
    - **Type**: Float
    - **Example**: `50.0`

## `tasks` Section

This section defines the properties of tasks within the simulation.

- **`quantity`**: Number of tasks to be generated in the simulation.
    - **Type**: Integer
    - **Example**: `3000`

- **`locations`**: Defines the initial position parameters for the tasks.
    - **`x_min`**: Minimum x-coordinate for task placement.
        - **Type**: Integer
        - **Example**: `0`
    - **`x_max`**: Maximum x-coordinate for task placement.
        - **Type**: Integer
        - **Example**: `1400`
    - **`y_min`**: Minimum y-coordinate for task placement.
        - **Type**: Integer
        - **Example**: `0`
    - **`y_max`**: Maximum y-coordinate for task placement.
        - **Type**: Integer
        - **Example**: `1000`
    - **`non_overlap_radius`**: Minimum distance between tasks to prevent overlap at the start.
        - **Type**: Integer
        - **Example**: `0`

- **`threshold_done_by_arrival`**: Distance within which a task is considered completed when an agent reaches it.
    - **Type**: Float
    - **Example**: `5.0`

## `simulation` Section

This section defines the overall simulation parameters.

- **`sampling_freq`**: The frequency at which the simulation updates (in frames per second).
    - **Type**: Float
    - **Example**: `60.0`

- **`agent_track_size`**: Number of positions to store for drawing the movement track of an agent.
    - **Type**: Integer
    - **Example**: `100`

- **`screen_width`**: Width of the simulation window in pixels.
    - **Type**: Integer
    - **Example**: `1400`

- **`screen_height`**: Height of the simulation window in pixels.
    - **Type**: Integer
    - **Example**: `1000`

- **`debug_mode`**: Toggle for enabling or disabling debug mode, which provides additional visual information.
    - **Type**: Boolean
    - **Example**: `False`

This detailed explanation should help you configure the SPADE Simulator effectively by adjusting the parameters in the `config.yaml` file according to your needs.
