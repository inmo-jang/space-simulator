import os
import pygame
from modules.agent import Agent

class BTRunner:
    def __init__(self, config):
        self.config = config
        self.bt_viz_cfg = config['bt_runner'].get('bt_visualiser', {})
        self.bt_tick_rate = config['bt_runner']['bt_tick_rate']
        pygame.init()
        if self.bt_viz_cfg.get('enabled', False):
            os.environ['SDL_VIDEO_WINDOW_POS'] = "0,30"  # top-left corner
            self.screen_height = self.bt_viz_cfg.get('screen_height',500)
            self.screen_width = self.bt_viz_cfg.get('screen_width',500) 
            self.screen = pygame.display.set_mode((self.screen_width, self.screen_height), pygame.RESIZABLE)
            self.background_color = (224, 224, 224)
            from .bt_visualiser import BTViewer
            self.bt_visualiser = BTViewer(
                direction=self.bt_viz_cfg.get('direction', 'Vertical')
            )
        self.clock = pygame.time.Clock()

        # Initialise
        self.reset()
                

    def reset(self):
        # Initialization        
        self.running = True
        self.paused = False   
        self.agent = None

        ros_namespace = self.config['agent'].get('namespaces', [])

        # Initialize agent
        self.agent = Agent(ros_namespace)

        # Provide global info and create BT
        scenario_path = self.config['scenario'].get('environment').replace('.', '/')
        behavior_tree_xml = f"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/{scenario_path}/{self.config['agent']['behavior_tree_xml']}"
        self.agent.create_behavior_tree(str(behavior_tree_xml))  


    async def step(self):
        # Main bt_runner loop logic
        await self.agent.run_tree()
        self.clock.tick(self.bt_tick_rate)


    def close(self):
        if self.agent and hasattr(self.agent, 'tree'):
            self.agent.halt_tree()

    def render(self):
        if self.bt_viz_cfg.get('enabled', False):
            self.bt_visualiser.render_tree(self.screen, self.agent.tree)
                    
            if self.paused:
                font = pygame.font.Font(None, 48) 
                text = font.render("Paused", True, (255, 0, 0))
                self.screen.blit(text, (10, 10))       

            pygame.display.flip()


    def handle_keyboard_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_p:
                    self.paused = not self.paused