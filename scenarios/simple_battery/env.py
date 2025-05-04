from modules.base_env import BaseEnv
from modules.utils import ResultSaver
from scenarios.simple_battery.task import generate_tasks
from scenarios.simple_battery.agent import generate_agents
import numpy as np
import pygame
from modules.utils import pre_render_text

class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks
        
        # Set data recording
        self.result_saver = ResultSaver(config)
        self.balanceness = None
        # Initialise
        self.reset()

    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks()
        self.agents = generate_agents(self.tasks)
        
        # Initialize data recording
        self.data_records = []

    async def step(self):
        # Main simulation loop logic
        for agent in self.agents:
            if agent.available:
                await agent.run_tree()
                agent.update()

        self.update_simulation()


    def save_results(self):
        # Save gif
        if self.save_gif and self.rendering_mode == "Screen":        
            self.recording = False
            print("Recording stopped.")
            self.result_saver.save_gif(self.frames)          
     

        # Save time series data
        if self.save_timewise_result_csv:                    
            csv_file_path = self.result_saver.save_to_csv("timewise", self.data_records, ['time', 'agents_total_distance_moved', 'agents_total_task_amount_done', 'remaining_agents', 'balanceness', 'agent_resource_max','agent_resource_min','remaining_tasks', 'tasks_total_amount_left'])          
            self.result_saver.plot_timewise_result(csv_file_path)

        # Save agent-wise data            
        if self.save_agentwise_result_csv:        
            variables_to_save = ['agent_id', 'task_amount_done', 'distance_moved']
            agentwise_results = self.result_saver.get_agentwise_results(self.agents, variables_to_save)                        
            csv_file_path = self.result_saver.save_to_csv('agentwise', agentwise_results, variables_to_save)
            
            self.result_saver.plot_boxplot(csv_file_path, variables_to_save[1:])

        # Save yaml: TODO - To debug
        if self.save_config_yaml:                
            self.result_saver.save_config_yaml()           
   
    def record_timewise_result(self):
        agents_total_distance_moved = sum(agent.distance_moved for agent in self.agents)
        agents_total_task_amount_done = sum(agent.task_amount_done for agent in self.agents)
        remaining_tasks = len([task for task in self.tasks if not task.completed])
        remaining_agents = len([agent for agent in self.agents if agent.available])
        tasks_total_amount_left = sum(task.amount for task in self.tasks)
        
        ## Calculate "Balanceness: Jain's fairness index"
        agent_resources = np.array([agent.battery_level for agent in self.agents if agent.available])        
        balanceness = np.sum(agent_resources)**2 / (len(agent_resources) * np.sum(agent_resources**2)) if len(agent_resources) > 0 else 0
        agent_resource_max = np.max(agent_resources) if len(agent_resources) > 0 else 0
        agent_resource_min = np.min(agent_resources) if len(agent_resources) > 0 else 0

        self.data_records.append([
            self.simulation_time, 
            agents_total_distance_moved,
            agents_total_task_amount_done,
            remaining_agents,
            float(balanceness),
            float(agent_resource_max),
            float(agent_resource_min),
            remaining_tasks,
            tasks_total_amount_left
        ])

        self.balanceness = float(balanceness)
                  
    def draw_agents_info(self):
        # Draw agents network topology
        if self.rendering_options.get('agent_communication_topology'):
            for agent in self.agents:
                if not agent.available:
                    continue
                agent.draw_communication_topology(self.screen, self.agents)

        # Draw agents
        for agent in self.agents:                    
            if not agent.available:
                continue
            if self.rendering_options.get('agent_tail'): # Draw each agent's trajectory tail
                agent.draw_tail(self.screen)
            if self.rendering_options.get('agent_id'): # Draw each agent's ID
                agent.draw_agent_id(self.screen)
            if self.rendering_options.get('agent_assigned_task_id'): # Draw each agent's assigned task ID
                agent.draw_assigned_task_id(self.screen)
            if self.rendering_options.get('agent_work_done'): # Draw each agent's assigned task ID
                agent.draw_work_done(self.screen)

    def render(self):
        super().render()
        if self.rendering_mode == "Screen" and self.screen:
            # Display agent quantity
            self.agents_left = sum(1 for agent in self.agents if agent.available)
            task_time_text = pre_render_text(f'Agents left: {self.agents_left};', 36, (0, 0, 0))
            self.screen.blit(task_time_text, (self.screen_width - 550, 20))

            if self.balanceness is not None:
                task_time_text = pre_render_text(f'Balanceness: {self.balanceness:.3f};', 36, (0, 0, 0))
                self.screen.blit(task_time_text, (self.screen_width - 550, 60))
            