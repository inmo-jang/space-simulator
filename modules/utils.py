import yaml
import random
import pygame
import imageio
import datetime
from PIL import Image
import os
import matplotlib.cm as cm
import shutil
import pandas as pd
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET

def load_config(config_file):
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

# Global variable to hold the configuration
config = None

def set_config(config_file):
    global config
    config = load_config(config_file)

# Pre-render static elements
def pre_render_text(text, font_size, color):
    font = pygame.font.Font(None, font_size)
    return font.render(text, True, color)

def generate_positions(quantity, x_min, x_max, y_min, y_max, radius=10):
    positions = []
    while len(positions) < quantity:
        pos = (random.randint(x_min + radius, x_max - radius),
               random.randint(y_min + radius, y_max - radius))
        if radius > 0:
            if all((abs(pos[0] - p[0]) > radius and abs(pos[1] - p[1]) > radius) for p in positions):
                positions.append(pos)
        else:
            positions.append(pos)
    return positions


# Generate task_colors based on tasks.quantity
def generate_task_colors(quantity):
    colors = cm.get_cmap('tab20', quantity)  # 'tab20' is a colormap with 20 distinct colors
    task_colors = {}
    for i in range(quantity):
        color = colors(i)  # Get color from colormap
        task_colors[i] = (int(color[0] * 255), int(color[1] * 255), int(color[2] * 255))  # Convert to RGB tuple
    return task_colors




# BT xml
def parse_behavior_tree(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    return root
    

def merge_dicts(dict1, dict2):
    # 두 개의 딕셔너리를 복사하여 합칠 딕셔너리를 초기화합니다.
    merged_dict = dict1.copy()
    
    # dict2의 항목을 순회합니다.
    for key, value in dict2.items():
        # 이미 merged_dict에 같은 키가 있으면 값을 비교하여 최대 값을 설정합니다.
        if key in merged_dict:
            merged_dict[key] = max(merged_dict[key], value)
        else:
            # 새로운 키일 경우 추가합니다.
            merged_dict[key] = value
            
    return merged_dict    


# Results saving
class ResultSaver:
    def __init__(self, config_file_path):
        self.config_file_path = config_file_path
        self.result_file_path = self.generate_output_filename()

    def generate_output_filename(self, extension = "csv"):
        agent_quantity = config['agents']['quantity']
        task_quantity = config['tasks']['quantity']
        decision_making_module_path = config['decision_making']['plugin']
        module_path, class_name = decision_making_module_path.rsplit('.', 1)
        datetime_now = datetime.datetime.now()
        current_time_string = datetime_now.strftime("%Y-%m-%d_%H-%M-%S")        
        
        current_date_string = datetime.datetime.now().strftime("%Y-%m-%d")
        output_parent_folder = config['simulation']['saving_options'].get('output_folder', 'output')
        with_date_subfolder = config['simulation']['saving_options'].get('with_date_subfolder', True)
        if with_date_subfolder:
            output_dir = os.path.join(output_parent_folder, current_date_string)       
        else:
            output_dir = output_parent_folder        
        os.makedirs(output_dir, exist_ok=True) 
        file_path = os.path.join(output_dir, f"{class_name}_{agent_quantity}_agents_{task_quantity}_tasks_{current_time_string}.{extension}")

        return file_path

    def change_file_extension(self, file_path, new_extension):
        base, _ = os.path.splitext(file_path)  # Split the file path into base and extension
        new_file_path = f"{base}.{new_extension}"  # Combine base with new extension
        return new_file_path



    def save_gif(self, frames):
        if frames:                  
            gif_recording_fps = config['simulation']['gif_recording_fps']
            gif_file_path = self.change_file_extension(self.result_file_path, "gif")

            # Convert pygame surface to PIL Image and save as GIF
            image_list = []
            for frame in frames:
                image = frame.swapaxes(0, 1)  # Swap axes to fix orientation
                image = Image.fromarray(image)
                image_list.append(image)

            imageio.mimsave(gif_file_path, image_list, duration=1.0/gif_recording_fps)  # Adjust duration for faster playback                    
            # imageio.mimsave(gif_file_path, frames)
            print(f"Saved GIF: {gif_file_path}")            

    def save_yaml(self):
        # Copy config.yaml to the result directory                 
        yaml_file_path = self.change_file_extension(self.result_file_path, "yaml")    
        shutil.copy(self.config_file_path, yaml_file_path)
        print(f"Copied {self.config_file_path} to: {yaml_file_path}")        

    def save_to_csv(self, time_records, data_records):
        csv_file_path = self.change_file_extension(self.result_file_path, "csv")    

        # Prepare data for DataFrame
        df = pd.DataFrame(data_records, columns=['agents_total_distance_moved', 'agents_total_task_amount_done', 'remaining_tasks', 'tasks_total_amount_left'])
        df.insert(0, 'time', time_records)  # Insert 'time' column at the beginning
        
        # Save the DataFrame to a CSV file    
        df.to_csv(csv_file_path, index=False)    
            
        return csv_file_path

    def save_time_series_plot(self, csv_file_path):
        # Read the CSV file
        df = pd.read_csv(csv_file_path)
        
        # Extract time and data columns
        time = df['time']
        agents_total_distance_moved = df['agents_total_distance_moved']
        agents_total_task_amount_done = df['agents_total_task_amount_done']
        remaining_tasks = df['remaining_tasks']
        tasks_total_amount_left = df['tasks_total_amount_left']


        plt.figure(figsize=(12, 8))

        plt.subplot(2, 2, 1)
        plt.plot(time, agents_total_distance_moved, label='Total Distance Moved by Agents')
        plt.xlabel('Time')
        plt.ylabel('Distance Moved')
        plt.legend()
        plt.grid(True)  

        plt.subplot(2, 2, 2)
        plt.plot(time, agents_total_task_amount_done, label='Total Task Amount Done by Agents')
        plt.xlabel('Time')
        plt.ylabel('Task Amount Done')
        plt.legend()
        plt.grid(True)  

        plt.subplot(2, 2, 3)
        plt.plot(time, remaining_tasks, label='The Number of Remaining Tasks')
        plt.xlabel('Time')
        plt.ylabel('The Number of Remaining Tasks')
        plt.legend()
        plt.grid(True)  

        plt.subplot(2, 2, 4)
        plt.plot(time, tasks_total_amount_left, label='Total Amount of Tasks')
        plt.xlabel('Time')
        plt.ylabel('Tasks Total Amount')
        plt.legend()
        plt.grid(True)  

        plt.tight_layout()

        img_file_path = self.change_file_extension(self.result_file_path, "png")   
        
        plt.savefig(img_file_path)
        # plt.show()
