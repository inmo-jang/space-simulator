import subprocess
import yaml
import argparse
import time


def run_simulation(config_file):
    """Run the SPADE simulator with the given configuration file and save the results."""
    command = f"python main.py --config={config_file}"
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        print(result.stdout)  # Output the result for debugging or logging
    except subprocess.CalledProcessError as e:
        print(f"Error during simulation: {e.stderr}")  # Output the error for debugging or logging


def monte_carlo_test(config_file, num_runs):
    """Perform Monte Carlo testing by running the simulation multiple times."""
    for i in range(num_runs):        
        print(f"Running simulation {i+1}/{num_runs}...")
        run_simulation(config_file)

    print("Monte Carlo testing complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch run Monte Carlo simulations using different configurations.")
    parser.add_argument("--config", default='mc_runner.yaml', type=str, help="YAML file with the list of configurations and number of runs.")
    args = parser.parse_args()

   # Record the start time
    start_time = time.time()

    with open(args.config, 'r') as file:
        batch_config = yaml.safe_load(file)

    cases = batch_config['cases']
    num_runs = batch_config['num_runs']

    for config_file in cases:
        print(f"Running Monte Carlo simulation with config: {config_file}, num_runs: {num_runs}")
        monte_carlo_test(config_file, num_runs)
        print(f"Finished running with {config_file}")

    # Record the end time and calculate the elapsed time
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Total execution time: {elapsed_time:.2f} seconds")