import yaml
import random
import pygame
import imageio
import datetime
from PIL import Image
import os
import matplotlib.cm as cm
import shutil

def load_config(config_file):
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

# Load configuration file
config = load_config('config.yaml')

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

def save_gif(frames):
    if frames:        
        gif_recording_fps = config['simulation']['gif_recording_fps']

        agent_quantity = config['agents']['quantity']
        task_quantity = config['tasks']['quantity']
        decision_making_module_path = config['agents']['decision_making_module_path']
        module_path, class_name = decision_making_module_path.rsplit('.', 1)
        datetime_now = datetime.datetime.now()
        current_time_string = datetime_now.strftime("%Y-%m-%d_%H-%M-%S")        
        
        current_date_string = datetime.datetime.now().strftime("%Y-%m-%d")
        output_dir = os.path.join('output', current_date_string)       
        os.makedirs(output_dir, exist_ok=True) 
        gif_filename = os.path.join(output_dir, f"{class_name}_{agent_quantity}_agents_{task_quantity}_tasks_{current_time_string}.gif")

        

        # Convert pygame surface to PIL Image and save as GIF
        image_list = []
        for frame in frames:
            image = frame.swapaxes(0, 1)  # Swap axes to fix orientation
            image = Image.fromarray(image)
            image_list.append(image)

        imageio.mimsave(gif_filename, image_list, duration=1.0/gif_recording_fps)  # Adjust duration for faster playback                    
        # imageio.mimsave(gif_filename, frames)
        print(f"Saved GIF: {gif_filename}")

        # Copy config.yaml to the same directory
        config_file_path = 'config.yaml'        
        new_config_filename = os.path.join(output_dir, os.path.basename(gif_filename).replace('.gif', '.yaml'))
        shutil.copy(config_file_path, new_config_filename)
        print(f"Copied config.yaml to: {new_config_filename}")        

# Generate task_colors based on tasks.quantity
def generate_task_colors(quantity):
    colors = cm.get_cmap('tab20', quantity)  # 'tab20' is a colormap with 20 distinct colors
    task_colors = {}
    for i in range(quantity):
        color = colors(i)  # Get color from colormap
        task_colors[i] = (int(color[0] * 255), int(color[1] * 255), int(color[2] * 255))  # Convert to RGB tuple
    return task_colors

task_colors = generate_task_colors(config['tasks']['quantity'])