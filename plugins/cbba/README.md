# CBBA

This is the plugin for CBBA, based on the following paper:

H. Choi, L. Brunet, J.P. How, "Consensus-Based Decentralized Auctions or Robust Task Allocation", IEEE Transactions on Robotics, 25(4), 2009, pp. 912-926.

## How It Works

CBBA (Consensus-Based Bundle Allocation) is a decentralized method designed for MT-SR (Multiple Task - Single Robot) scenarios, where each agent performs multiple tasks sequentially, and each task requires only one agent. In CBBA, agents build task bundles by bidding on their desired tasks and sharing these bids with their neighbors. The consensus process among agents resolves conflicts and determines task assignments without requiring a central auctioneer.

Based on the original paper, following enhancements were implemented:

- **Winning Bid Reset Mechanism**: In dynamic environments, CBBA may be required to address outdated information in winning bid/agents information. To address this issue, we introduced a mechanism where if an agent's task bundle remains empty for a certain period, it resets all known winning bid values and winning agent IDs. 




## Parameters Example

```yaml
plugin: plugins.cbba.cbba.CBBA
CBBA:  
  max_tasks_per_agent: 5 
  task_reward_discount_factor: 0.999 
  winning_bid_cancel: True
  acceptable_empty_bundle_duration: 500 # sec
```


### Parameter Descriptions

- **`max_tasks_per_agent`**: 
  The maximum length of the bundle that each agent can construct.

- **`task_reward_discount_factor`**: 
  The discount factor used in the time-discounted reward when an agent is constructing its task path. This factor determines how rewards are discounted over time.

- **`winning_bid_cancel`**: 
  Allows an agent to reset its stored winning bid and winning agent information. This parameter should be used in conjunction with `acceptable_empty_bundle_duration`.

- **`acceptable_empty_bundle_duration`**: 
  When `winning_bid_cancel` is `True`, this parameter defines the maximum duration (in seconds) that an agent will accept an empty bundle while still recognizing local tasks. If the bundle remains empty for longer than this duration, the agent will reset its winning bid and winning agent information.


## Sample Result

<div style="display: flex; flex-direction: row;">
    <img src="result/CBBA_a10_t100_2024-08-20_17-26-49.gif" alt="GIF" width="600" height="450">
</div>

### `config.yaml` used

This was executed with the following configuration:
```yaml
decision_making: 
  plugin: plugins.cbba.cbba.CBBA
  CBBA:  
    max_tasks_per_agent: 5 
    task_reward_discount_factor: 0.999 
    winning_bid_cancel: True
    acceptable_empty_bundle_duration: 500 

agents:
  behavior_tree_xml: default_bt.xml 
  quantity: 10
  locations:
    x_min: 0
    x_max: 1400
    y_min: 0
    y_max: 1000
    non_overlap_radius: 0 
  max_speed: 0.25  
  max_accel: 0.05
  max_angular_speed: 0.25
  target_approaching_radius: 50
  work_rate: 1  
  communication_radius: 500 
  situation_awareness_radius: 500 
  random_exploration_duration: 1000.0 

tasks:
  quantity: 100
  locations:
    x_min: 0
    x_max: 1400
    y_min: 0
    y_max: 1000
    non_overlap_radius: 0
  threshold_done_by_arrival: 10.0
  amounts:  
    min: 6.0
    max: 60.0      
  dynamic_task_generation:
    enabled: True
    interval_seconds: 2000
    max_generations: 3
    tasks_per_generation: 25

simulation:
  sampling_freq: 1.0 
  speed_up_factor: 0 
  max_simulation_time: 0
  agent_track_size: 400  
  screen_width: 1400 
  screen_height: 1000 
  gif_recording_fps: 0.05  
  task_visualisation_factor: 3  
  profiling_mode: False
  rendering_mode: Screen  
  rendering_options: 
    agent_tail: True
    agent_communication_topology: True
    agent_situation_awareness_circle: False
    agent_id: True
    agent_work_done: True
    agent_assigned_task_id: True
    agent_path_to_assigned_tasks: True
    task_id: False
  saving_options:
    output_folder: output
    with_date_subfolder: True
    save_gif: False
    save_timewise_result_csv: True    
    save_agentwise_result_csv: True
    save_config_yaml: True
```