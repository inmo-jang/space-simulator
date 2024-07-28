import pandas as pd
import glob
import os
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
import yaml

def load_data(filepath_pattern):
    """Load data from CSV files matching the given file pattern."""
    all_files = glob.glob(filepath_pattern)
    print(f"Analysing {len(all_files)} results: {filepath_pattern}")
    all_data = [pd.read_csv(filename) for filename in all_files]
    return all_data

def analyze_data(data_list):
    """Perform analysis on the data."""
    final_times = []
    final_distances = []
    final_tasks_done = []
    quartile_distances = [[] for _ in range(4)]
    quartile_tasks_done = [[] for _ in range(4)]
    
    for data in data_list:
        final_time = data['time'].iloc[-1]
        final_distance = data['agents_total_distance_moved'].iloc[-1]
        final_tasks = data['agents_total_task_amount_done'].iloc[-1]
        
        final_times.append(final_time)
        final_distances.append(final_distance)
        final_tasks_done.append(final_tasks)
        
        # Calculate quartiles
        quartile_indices = [
            int(len(data) * q) - 1 for q in [0.25, 0.5, 0.75, 1.0]
        ]
        quartile_indices = [0] + quartile_indices  # Include the start index
        for i in range(4):
            start = quartile_indices[i]
            end = quartile_indices[i + 1]
            time_difference = data['time'].iloc[end] - data['time'].iloc[start]
            if time_difference > 0:            
                quartile_distances[i].append((data['agents_total_distance_moved'].iloc[end] - data['agents_total_distance_moved'].iloc[start]) / time_difference)
                quartile_tasks_done[i].append((data['agents_total_task_amount_done'].iloc[end] - data['agents_total_task_amount_done'].iloc[start]) / time_difference)
    
    return final_times, final_distances, final_tasks_done, quartile_distances, quartile_tasks_done

def plot_box_plots(data, labels, title, ylabel):
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=data)
    plt.xticks(range(len(labels)), labels)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.show()

def plot_combined_quartile_box_plots(quartile_data, case_names, title, ylabel):
    fig, axes = plt.subplots(1, 4, figsize=(20, 5), sharey=True)
    for i, ax in enumerate(axes):
        sns.boxplot(data=[quartile_data[case][i] for case in case_names], ax=ax)
        ax.set_title(f'Q{i+1}')
        ax.set_xticklabels(case_names)
        ax.set_ylabel(ylabel)
    fig.suptitle(title)
    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Monte Carlo simulation results.")
    parser.add_argument("--config", type=str, default='mc_comparison.yaml', help="Path to the YAML configuration file (default: mc_comparison.yaml)")
    args = parser.parse_args()
    
    # Load YAML configuration
    with open(args.config, 'r') as file:
        config = yaml.safe_load(file)
    
    case_data = {}
    case_names = config['labels']
    
    for idx, case_path in enumerate(config['cases']):
        data_list = load_data(f"{case_path}_*.csv")
        # case_name = os.path.basename(case_path)
        case_name = case_names[idx]
        # case_names.append(case_name)
        case_data[case_name] = analyze_data(data_list)
    
    # Plot 1: Mission completion time
    final_times_data = [case_data[case][0] for case in case_names]
    plot_box_plots(final_times_data, case_names, 'Mission Completion Time Box Plot', 'Time (s)')
    
    # Plot 2: Final agents_total_distance_moved
    final_distances_data = [case_data[case][1] for case in case_names]
    plot_box_plots(final_distances_data, case_names, 'Agents Total Distance Moved Box Plot', 'Distance')
    
    # Plot 3: Final agents_total_task_amount_done
    final_tasks_done_data = [case_data[case][2] for case in case_names]
    plot_box_plots(final_tasks_done_data, case_names, 'Agents Total Task Amount Done Box Plot', 'Tasks Amount Done')
    
    # Plot 4: Agents total distance moved by quartiles
    quartile_distances_data = {case: case_data[case][3] for case in case_names}
    plot_combined_quartile_box_plots(quartile_distances_data, case_names, 'Total Distance Moved Per Second by Mission Time Quartiles', 'Distance')
    
    # Plot 5: Agents total task amount done by quartiles
    quartile_tasks_done_data = {case: case_data[case][4] for case in case_names}
    plot_combined_quartile_box_plots(quartile_tasks_done_data, case_names, 'Total Task Amount Done Per Second by Mission Time Quartiles', 'Tasks Done')

    debug = 1