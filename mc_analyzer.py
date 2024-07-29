import pandas as pd
import glob
import os
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
import yaml

class MonteCarloAnalyzer:
    def __init__(self, config_path):
        self.config = self.load_config(config_path)
        self.output_folder = self.config['output_folder']
        self.case_names = self.config['labels']
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
        
        for data in data_list:
            task_amount_done = data['task_amount_done'].tolist()
            distance_moved = data['distance_moved'].tolist()
            
            gini_task = self.gini_coefficient(task_amount_done)
            gini_distance = self.gini_coefficient(distance_moved)
            
            gini_coeff_task_amount_done.append(gini_task)
            gini_coeff_distance_moved.append(gini_distance)
        
        return {"gini_coeff_task_amount_done": gini_coeff_task_amount_done, 
                "gini_coeff_distance_moved": gini_coeff_distance_moved}

    def plot_box_plots(self, data, labels, title, ylabel, filename):
        """Plot and save box plots."""
        plt.figure(figsize=(10, 6))
        sns.boxplot(data=data)
        plt.xticks(range(len(labels)), labels)
        plt.title(title)
        plt.ylabel(ylabel)
        plt.savefig(os.path.join(self.output_folder, filename))
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
            case_name = self.case_names[idx]
            timewise_data_list = self.load_data(f"{case_path}_*_timewise.csv")
            timewise_case_data[case_name] = self.analyze_timewise_data(timewise_data_list)

            agentwise_data_list = self.load_data(f"{case_path}_*_agentwise.csv")
            agentwise_case_data[case_name] = self.analyze_agentwise_data(agentwise_data_list)
        
        # Plotting the results
        self.plot_box_plots([timewise_case_data[case]["final_times"] for case in self.case_names], 
                            self.case_names, 'Mission Completion Time Box Plot', 'Time (s)', 'mission_completion_time.png')
        
        self.plot_box_plots([timewise_case_data[case]["final_distances"] for case in self.case_names], 
                            self.case_names, 'Agents Total Distance Moved Box Plot', 'Distance', 'total_distance_moved.png')
        
        self.plot_box_plots([timewise_case_data[case]["final_tasks_done"] for case in self.case_names], 
                            self.case_names, 'Agents Total Task Amount Done Box Plot', 'Tasks Amount Done', 'total_task_amount_done.png')
        
        self.plot_combined_quartile_box_plots({case: timewise_case_data[case]["quartile_distances"] for case in self.case_names},
                                              self.case_names, 'Total Distance Moved Per Second by Mission Time Quartiles', 'Distance', 'quartile_distance_moved.png')
        
        self.plot_combined_quartile_box_plots({case: timewise_case_data[case]["quartile_tasks_done"] for case in self.case_names},
                                              self.case_names, 'Total Task Amount Done Per Second by Mission Time Quartiles', 'Tasks Done', 'quartile_task_done.png')

        self.plot_box_plots([agentwise_case_data[case]["gini_coeff_task_amount_done"] for case in self.case_names],
                            self.case_names, 'Gini Coefficient for Task Amount Done', 'Gini Coefficient', 'gini_task_amount_done.png')

        self.plot_box_plots([agentwise_case_data[case]["gini_coeff_distance_moved"] for case in self.case_names],
                            self.case_names, 'Gini Coefficient for Distance Moved', 'Gini Coefficient', 'gini_distance_moved.png')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Monte Carlo simulation results.")
    parser.add_argument("--config", type=str, default='mc_comparison.yaml', help="Path to the YAML configuration file (default: mc_comparison.yaml)")
    args = parser.parse_args()

    analyzer = MonteCarloAnalyzer(args.config)
    analyzer.run_analysis()

    debug = 1
