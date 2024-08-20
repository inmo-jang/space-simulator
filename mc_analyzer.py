import pandas as pd
import glob
import os
import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import seaborn as sns
import yaml
import numpy as np

class MonteCarloAnalyzer:
    def __init__(self, config_path):
        self.config = self.load_config(config_path)
        self.output_folder = self.config['output_folder']
        self.case_names = self.config['cases']
        self.xticklabels = self.config['xticklabels']
        self.colors = self.config.get('colors', [])  # Load colors from YAML config        
        os.makedirs(self.output_folder, exist_ok=True)

    def load_config(self, config_path):
        """Load YAML configuration."""
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        return config

    def load_data(self, filepath_pattern):
        """Load data from CSV files matching the given file pattern."""
        all_files = glob.glob(filepath_pattern)
        print(f"Analysing {len(all_files)} results: {filepath_pattern}")
        all_data = [pd.read_csv(filename) for filename in all_files]
        return all_data

    def gini_coefficient(self, data):
        """Calculate the Gini coefficient for a list of data."""
        n = len(data)
        if n == 0:
            return 0
        sorted_data = sorted(data)
        cumulative_total = sum((i + 1) * val for i, val in enumerate(sorted_data))
        sum_values = sum(sorted_data)
        if sum_values == 0:
            return 0
        return (2 * cumulative_total) / (n * sum_values) - (n + 1) / n


    def analyze_timewise_data(self, data_list):
        """Perform timewise data analysis."""
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
            quartile_indices = [int(len(data) * q) - 1 for q in [0.25, 0.5, 0.75, 1.0]]
            quartile_indices = [0] + quartile_indices  # Include the start index
            for i in range(4):
                start = quartile_indices[i]
                end = quartile_indices[i + 1]
                time_difference = data['time'].iloc[end] - data['time'].iloc[start]
                if time_difference > 0:            
                    quartile_distances[i].append((data['agents_total_distance_moved'].iloc[end] - data['agents_total_distance_moved'].iloc[start]) / time_difference)
                    quartile_tasks_done[i].append((data['agents_total_task_amount_done'].iloc[end] - data['agents_total_task_amount_done'].iloc[start]) / time_difference)
        
        return {"final_times": final_times, 
                "final_distances": final_distances, 
                "final_tasks_done": final_tasks_done, 
                "quartile_distances": quartile_distances, 
                "quartile_tasks_done": quartile_tasks_done}

    def analyze_agentwise_data(self, data_list):
        """Perform agentwise data analysis."""
        gini_coeff_task_amount_done = []
        gini_coeff_distance_moved = []
        average_task_amount_done_per_agent = []
        average_distance_moved_per_agent = []
        std_task_amount_done = []
        std_distance_moved = []
        
        for data in data_list:
            task_amount_done = data['task_amount_done'].tolist()
            distance_moved = data['distance_moved'].tolist()
            
            gini_task = self.gini_coefficient(task_amount_done)
            gini_distance = self.gini_coefficient(distance_moved)
            
            gini_coeff_task_amount_done.append(gini_task)
            gini_coeff_distance_moved.append(gini_distance)

            average_task_amount_done_per_agent.append(sum(task_amount_done)/len(task_amount_done))
            average_distance_moved_per_agent.append(sum(distance_moved)/len(distance_moved))

            std_task_amount_done.append(np.std(task_amount_done)/np.mean(task_amount_done))
            std_distance_moved.append(np.std(distance_moved)/np.mean(distance_moved))
        
        return {"gini_coeff_task_amount_done": gini_coeff_task_amount_done, 
                "gini_coeff_distance_moved": gini_coeff_distance_moved, 
                "average_task_amount_done_per_agent": average_task_amount_done_per_agent, 
                "average_distance_moved_per_agent": average_distance_moved_per_agent, 
                "std_task_amount_done": std_task_amount_done, 
                "std_distance_moved": std_distance_moved
                }

    def plot_box_plots(self, data, xticklabels, title, ylabel, filename, ylim = None):
        """Plot and save box plots."""
        plt.figure(figsize=(6, 3))

        color_map = plt.get_cmap('tab10')  # Choose a color map (or any other you prefer)


        box_plot = sns.boxplot(data=data, width=0.5, palette=[color_map(i) for i in self.colors])

        plt.xticks(range(len(xticklabels)), xticklabels, fontsize=12)  # Increase font size for x-ticks
    
        plt.title(title, fontsize=14)  # Increase font size for title
        plt.ylabel(ylabel, fontsize=12)  # Increase font size for y-axis label    
        if self.config.get('xlabel'):            
            plt.xlabel(self.config.get('xlabel'), fontsize=12)  # Increase font size for y-axis label

        # Add a legend
        if 'legends' in self.config and 'legend_colors' in self.config:
            legends = self.config['legends']
            legend_colors = self.config['legend_colors']
            
            # Create legend handles
            legend_handles = [
                patches.Patch(color=color_map(color_index), label=label)
                for color_index, label in zip(legend_colors, legends)
            ]
            plt.legend(handles=legend_handles, loc='upper right', fontsize=12)
                    
        plt.grid(True, linestyle='--', which='major', axis='y')  # Only horizontal grid
        plt.tight_layout(pad=0.1)
        if ylim:
            plt.ylim(ylim)
        plt.savefig(os.path.join(self.output_folder, filename), bbox_inches='tight', pad_inches=0.1)        
        plt.close()

    def plot_combined_quartile_box_plots(self, quartile_data, case_names, title, ylabel, filename):
        """Plot and save combined quartile box plots."""
        fig, axes = plt.subplots(1, 4, figsize=(20, 5), sharey=True)
        for i, ax in enumerate(axes):
            sns.boxplot(data=[quartile_data[case][i] for case in case_names], ax=ax)
            ax.set_title(f'Q{i+1}')
            ax.set_xticks(range(len(case_names)))
            ax.set_xticklabels(case_names)
            ax.set_ylabel(ylabel)
        fig.suptitle(title)
        plt.savefig(os.path.join(self.output_folder, filename))
        plt.close()

    def run_analysis(self):
        """Run the complete analysis and save the plots."""
        timewise_case_data = {}
        agentwise_case_data = {}
        
        for idx, case_path in enumerate(self.config['cases']):
            case_name = case_path
            timewise_data_list = self.load_data(f"{case_path}_*_timewise.csv")
            timewise_case_data[case_name] = self.analyze_timewise_data(timewise_data_list)

            agentwise_data_list = self.load_data(f"{case_path}_*_agentwise.csv")
            agentwise_case_data[case_name] = self.analyze_agentwise_data(agentwise_data_list)
        
        # Plotting the results
        self.plot_box_plots([timewise_case_data[case]["final_times"] for case in self.case_names], 
                            self.xticklabels, 'Mission Completion Time', 'Time (s)', 'mission_completion_time.png')
        
        # self.plot_box_plots([timewise_case_data[case]["final_distances"] for case in self.case_names], 
        #                     self.xticklabels, 'Sum(Agents Distance Moved)', 'Distance', 'total_distance_moved.png')
        
        # self.plot_box_plots([timewise_case_data[case]["final_tasks_done"] for case in self.case_names], 
        #                     self.xticklabels, 'Sum(Agents Task Amount Done)', 'Tasks Amount Done', 'total_task_amount_done.png')
        
        # self.plot_combined_quartile_box_plots({case: timewise_case_data[case]["quartile_distances"] for case in self.case_names},
        #                                       self.case_names, 'Total Distance Moved Per Second by Mission Time Quartiles', 'Distance', 'quartile_distance_moved.png')
        
        # self.plot_combined_quartile_box_plots({case: timewise_case_data[case]["quartile_tasks_done"] for case in self.case_names},
        #                                       self.case_names, 'Total Task Amount Done Per Second by Mission Time Quartiles', 'Tasks Done', 'quartile_task_done.png')

        # self.plot_box_plots([agentwise_case_data[case]["gini_coeff_task_amount_done"] for case in self.case_names],
        #                     self.xticklabels, 'Gini Coefficient for Task Amount Done', 'Gini Coefficient', 'gini_task_amount_done.png')

        # self.plot_box_plots([agentwise_case_data[case]["gini_coeff_distance_moved"] for case in self.case_names],
        #                     self.xticklabels, 'Gini Coefficient for Distance Moved', 'Gini Coefficient', 'gini_distance_moved.png')

        self.plot_box_plots([agentwise_case_data[case]["average_task_amount_done_per_agent"] for case in self.case_names],
                            self.xticklabels, 'Average Task Amount Done Per Agent', 'Tasks Amount Done', 'agent_task_amount_done.png')
        
        self.plot_box_plots([agentwise_case_data[case]["average_distance_moved_per_agent"] for case in self.case_names],
                            self.xticklabels, 'Average Distance Moved Per Agent', 'Distance', 'agent_distance_moved.png')        

        # self.plot_box_plots([agentwise_case_data[case]["std_task_amount_done"] for case in self.case_names],
        #                     self.xticklabels, 'Std/Ave of Task Amount Done', 'Coefficient of Variation', 'std_task_amount_done.png')
        
        # self.plot_box_plots([agentwise_case_data[case]["std_distance_moved"] for case in self.case_names],
        #                     self.xticklabels, 'Std/Ave of Distance Moved', 'Coefficient of Variation', 'std_distance_moved.png')        



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Monte Carlo simulation results.")
    parser.add_argument("--config", type=str, default='mc_analyzer.yaml', help="Path to the YAML configuration file (default: mc_analyzer.yaml)")
    args = parser.parse_args()

    analyzer = MonteCarloAnalyzer(args.config)
    analyzer.run_analysis()

