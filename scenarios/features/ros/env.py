from modules.base_env import BaseEnv
from modules.utils import ResultSaver
from scenarios.features.ros.agent import generate_agents
from scenarios.features.ros.ros_bridge import ROSBridge

class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # Set data recording
        self.result_saver = ResultSaver(config)

        # ROS Bridge
        self.ros_bridge = ROSBridge.get()

        # Initialise
        self.reset()

    def reset(self):
        super().reset()

        # Initialize agents 
        self.agents = generate_agents(seed=self.seed, ros_bridge=self.ros_bridge)
        
        # Initialize data recording
        self.data_records = []

    async def step(self):
        # Main simulation loop logic
        for agent in self.agents:
            await agent.run_tree()
            agent.update()
    
    def render(self):
        pass

    def save_results(self):
        # Save gif
        if self.save_gif and self.rendering_mode == "Screen":        
            self.recording = False
            print("Recording stopped.")
            self.result_saver.save_gif(self.frames)          
     

        # Save time series data
        if self.save_timewise_result_csv:        
            csv_file_path = self.result_saver.save_to_csv("timewise", self.data_records, ['time', 'agents_total_distance_moved', 'agents_total_task_amount_done', 'remaining_tasks', 'tasks_total_amount_left'])          
            self.result_saver.plot_timewise_result(csv_file_path)
        
        # Save agent-wise data            
        if self.save_agentwise_result_csv:        
            variables_to_save = ['agent_id', 'task_amount_done', 'distance_moved']
            agentwise_results = self.result_saver.get_agentwise_results(self.agents, variables_to_save)                        
            csv_file_path = self.result_saver.save_to_csv('agentwise', agentwise_results, variables_to_save)
            
            self.result_saver.plot_boxplot(csv_file_path, variables_to_save[1:])

        # Save yaml
        if self.save_config_yaml:                
            self.result_saver.save_config_yaml()           
   
    def record_timewise_result(self):
        pass
        # agents_total_distance_moved = sum(agent.distance_moved for agent in self.agents)
        # agents_total_task_amount_done = sum(agent.task_amount_done for agent in self.agents)
        # remaining_tasks = len([task for task in self.tasks if not task.completed])
        # tasks_total_amount_left = sum(task.amount for task in self.tasks)
        
        # self.data_records.append([
        #     self.simulation_time, 
        #     agents_total_distance_moved,
        #     agents_total_task_amount_done,
        #     remaining_tasks,
        #     tasks_total_amount_left
        # ])        
                  