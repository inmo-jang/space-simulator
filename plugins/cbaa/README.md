# CBAA

This is the plugin for CBAA, based on the following paper:

H. Choi, L. Brunet, J.P. How, "Consensus-Based Decentralized Auctions or Robust Task Allocation", IEEE Transactions on Robotics, 25(4), 2009, pp. 912-926.


This plugin was implemented just for tutorial purpose. 



## Parameters Example

```yaml
plugin: plugins.cbaa.cbaa.CBAA
```



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