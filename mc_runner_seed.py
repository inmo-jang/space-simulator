import subprocess
import yaml
import argparse
import time
import os

def run_simulation(config_file):
    """Run the SPACE simulator with the given configuration file and save the results."""
    command = f"python main.py --config={config_file}"
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        # print(result.stdout)  # Output the result for debugging or logging
    except subprocess.CalledProcessError as e:
        print(f"Error during simulation: {e.stderr}")  # Output the error for debugging or logging


def test_with_seeds(base_config_path, seed_range, num_runs):
    """Run simulations for each seed in the range, modifying the config file each time."""
    seed_start, seed_end = seed_range
    for seed in range(seed_start, seed_end + 1):
        print(f"Running simulation for seed {seed}...")

        # Load and modify the config
        with open(base_config_path, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['simulation']['random_seed'] = seed

        # Save to a temporary config file
        temp_config_path = f"temp_config_seed{seed}.yaml"
        with open(temp_config_path, 'w') as f:
            yaml.dump(config_data, f)

        for run_id in range(num_runs):
            print(f"  Run {run_id+1}/{num_runs} for seed {seed}")
            run_simulation(temp_config_path)

        # Optionally remove the temp file
        os.remove(temp_config_path)

    print("Testing with seeds complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch run Monte Carlo simulations using different configurations.")
    parser.add_argument("--config", default='mc_runner_seed.yaml', type=str, help="YAML file with the list of configurations and number of runs.")
    args = parser.parse_args()

   # Record the start time
    start_time = time.time()

    with open(args.config, 'r') as file:
        batch_config = yaml.safe_load(file)

    cases = batch_config['cases']
    num_runs = batch_config['num_runs']
    seed_range = batch_config['seed_ranges']

    for config_file in cases:
        print(f"\nRunning simulation with config: {config_file}")
        test_with_seeds(config_file, seed_range, num_runs)

    # Record the end time and calculate the elapsed time
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Total execution time: {elapsed_time:.2f} seconds")