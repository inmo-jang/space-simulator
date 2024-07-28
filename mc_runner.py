import subprocess
import argparse


def run_simulation(config_file):
    """Run the SPADE simulator with the given configuration file and save the results."""
    command = f"python main.py --config={config_file}"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)


def monte_carlo_test(config_file, num_runs):
    """Perform Monte Carlo testing by running the simulation multiple times."""
    for i in range(num_runs):        
        print(f"Running simulation {i+1}/{num_runs}...")
        run_simulation(config_file)

    print("Monte Carlo testing complete")


 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Monte Carlo testing for SPADE simulator")
    parser.add_argument("--config", type=str, default="config.yaml", help="Base configuration file name without extension (default: config.yaml)")
    parser.add_argument("--num_runs", type=int, default=3, help="Number of Monte Carlo runs (default: 3)")
    
    args = parser.parse_args()
    
    config_file = args.config
    num_runs = args.num_runs

    monte_carlo_test(config_file, num_runs)
