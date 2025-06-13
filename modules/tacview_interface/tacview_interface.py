# tacview_interface.py

import queue
import math
from threading import Thread
from modules.tacview_interface.agent_state import AircraftState
from modules.tacview_interface.tacview_server import TacviewServer

PIXEL_TO_METER = 100 # TODO: This needs to be moved to config.yaml
HOST = '0.0.0.0'
PORT = 42674

class TacViewInterface:
    def __init__(self, env, screen_width, screen_height):
        self.env = env
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.queue = queue.Queue(maxsize=100)
        self.tacview_server = TacviewServer(self.queue, host = HOST, port = PORT)
        self.tacview_server_thread = Thread(target=self.tacview_server.start, daemon=True)
        self.tacview_server_thread.start()


    def send_telemetry(self):
        for agent in self.env.agents:
            state = AircraftState(
                aircraft_id=f"{agent.agent_id+1000}",
                pilot_name=f"agent_{agent.agent_id}",
                aircraft_type="F-18",
                latitude=self.convert_to_lat(agent.position[1]),
                longitude=self.convert_to_lon(agent.position[0]),
                altitude_m=2000.0,
                yaw_deg=self.convert_to_yaw_deg(agent.rotation),
                roll_deg=self.convert_to_roll_deg(agent.rotation),
                pitch_deg=0.0,                
                ground_speed_mps=agent.velocity.length(),
                armed=True,
                mode="AUTO"                
            )
            try:
                self.queue.put_nowait(state)
            except queue.Full:
                pass



    def convert_to_lat(self, y_pixel):
        return 37.5665 - (y_pixel - self.screen_height / 2) * 0.00001 * PIXEL_TO_METER

    def convert_to_lon(self, x_pixel):
        return 126.9780 + (x_pixel - self.screen_width / 2) * 0.00001 * PIXEL_TO_METER

    def convert_to_yaw_deg(self, rotation):
        return (math.degrees(rotation) + 90) % 360
    
    def convert_to_roll_deg(self, rotation):
        return -20 * math.cos(rotation)    