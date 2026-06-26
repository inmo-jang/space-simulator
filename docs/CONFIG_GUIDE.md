# Configuration Manual for SPACE Simulator

This manual provides detailed descriptions of each parameter in the `config.yaml` file used by the SPACE Simulator. Understanding these parameters will help you customize the simulation according to your requirements.

## `decision_making` Section

- **`plugin`**: Specifies the Python module path and class name for the decision-making logic used by agents.
    - **Type**: String
    - **Example**: `plugins.my_decision_making_plugin.MyDecisionMakingClass`


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

- **`communication_radius`**: Distance within which another agent can be considered as a communication candidate.
    - **Type**: Float
    - **Example**: `500.0`
    - **Note**: `0` means global candidate access. The configured communication model still decides whether each message is received or dropped.

- **`situation_awareness_radius`**: Distance within which an agent can sense local tasks.
    - **Type**: Float
    - **Example**: `500.0`
    - **Note**: `0` means global task awareness.

## `communication` Section

This section defines the packet-level communication model used after agents select communication candidates by `agents.communication_radius`. Decision-making plugins continue to publish `agent.message_to_share` and consume `agent.messages_received`; the communication model only decides whether a non-empty packet is accepted or dropped.

- **`model`**: Communication channel model.
    - **Type**: String
    - **Options**: `Perfect`, `Bernoulli`, `GilbertElliot`, `Rayleigh`
    - **Example**: `Bernoulli`

- **`random_seed`**: Optional seed for reproducible packet drops.
    - **Type**: Integer or `null`
    - **Example**: `42`

- **`bernoulli.p_success`**: Independent probability that each message is received.
    - **Type**: Float in `[0, 1]`
    - **Example**: `0.8`

- **`gilbert_elliot`**: Two-state communication model for bursty drops.
    - `p_good_success`: Message success probability in the good state.
    - `p_bad_success`: Message success probability in the bad state.
    - `p_good_to_good`: Probability that a good link remains good at a transition check.
    - `p_bad_to_bad`: Probability that a bad link remains bad at a transition check.
    - `transition_interval_seconds`: Simulation-time interval between state transition checks.
    - `initial_state`: `Good` or `Bad`.

- **`rayleigh`**: Distance-sensitive fading model using path loss and a sampled Rayleigh channel envelope.
    - `transmit_power_db`: Transmit power in dB.
    - `sensitivity_threshold_db`: Minimum received power required for packet reception.
    - `path_loss_at_reference_db`: Path loss at `reference_distance`.
    - `reference_distance`: Reference distance for path-loss calculation.
    - `path_loss_exponent`: Environment-dependent path-loss exponent.
    - `fading_scale`: Rayleigh envelope scale.

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

- **`rendering_mode`**: toggle rendering of graphical output.
    - **Type**: Boolean
    - **Example**: `True`
- **`rendering_options`**: customize rendering settings when `rendering_mode` is enabled:
    - `agent_tail`: Enables drawing of agent trajectory tails.
    - `agent_communication_topology`: Enables visualization of agent communication topology.
    - `agent_id`: Displays agent identifiers on the screen.
    - `agent_assigned_task_id`: Shows the task identifier assigned to each agent.
    - `task_id`: Displays task identifiers on the tasks.

- **`saving_options`**: customize saved outputs:
    - `save_timewise_result_csv`: Saves time-series task, distance, and communication counts.
    - `save_agentwise_result_csv`: Saves per-agent task, distance, and communication counts.

This detailed explanation should help you configure the SPACE Simulator effectively by adjusting the parameters in the `config.yaml` file according to your needs.
