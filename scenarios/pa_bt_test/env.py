from modules.base_env import BaseEnv
from modules.utils import ResultSaver
from scenarios.pa_bt_test.task import generate_tasks
from scenarios.pa_bt_test.agent import generate_agents

from modules.base_bt_nodes import Status
from modules.ppa_bt_constructor import load_library, expand_behavior_tree


class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # Load PPA library from the CSV file
        ppa_library_path = config['simulation'].get('ppa_library_path', 'ppa_library.csv')
        self.ppa_library = load_library(ppa_library_path)

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks
        
        # Set data recording
        self.result_saver = ResultSaver(config)

        # Initialise
        self.reset()

    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks()
        self.agents = generate_agents(self.tasks)
        
        # Initialize data recording
        self.data_records = []

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

        # Save yaml: TODO - To debug
        # if self.save_config_yaml:                
            # self.result_saver.save_config_yaml()           
   
    def record_timewise_result(self):
        agents_total_distance_moved = sum(agent.distance_moved for agent in self.agents)
        agents_total_task_amount_done = sum(agent.task_amount_done for agent in self.agents)
        remaining_tasks = len([task for task in self.tasks if not task.completed])
        tasks_total_amount_left = sum(task.amount for task in self.tasks)
        
        self.data_records.append([
            self.simulation_time, 
            agents_total_distance_moved,
            agents_total_task_amount_done,
            remaining_tasks,
            tasks_total_amount_left
        ])        

    # base_env에서 override           
    async def step(self):
        # Main simulation loop logic
        for agent in self.agents:
            result = await agent.run_tree()
            
            if result == Status.FAILURE:  # Check if the result is FAILURE
                failed_conditions = agent.find_failed_conditions()  # Identify failed conditions
                
                for failed_condition in failed_conditions:
                    # Expand the behavior tree based on the failed condition
                    agent.tree = expand_behavior_tree(agent.tree, failed_condition, self.ppa_library)

            agent.update()
        # 필요 시, 디버그 추가, agent.blackboard 활용. (대신 last agent인 경우만)

        self.update_simulation()