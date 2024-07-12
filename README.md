# SPADE (Swarm Planning And Decision Evaluation) Simulator

SPADE Simulator is a pygame-based application for simulating agent behavior using behavior trees. This documentation provides an overview of the code structure, installation instructions, and usage guidelines.

## Features

- Simulates multiple agents performing tasks
- Agents use behavior trees for decision-making
- Real-time task assignment and execution
- Debug mode for visualizing agent behavior

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/spade-simulator.git
    cd spade-simulator
    ```

2. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

3. Ensure you have the correct assets:
    - Place your logo image in the `assets` directory.

4. Run the simulator:
    ```sh
    python main.py
    ```

## Configuration

Modify the `config.yaml` file to adjust simulation parameters:
- Number of agents and tasks
- Screen dimensions
- Agent behavior parameters

Refer to the configuration guide [CONFIG_GUIDE.md](/docs/CONFIG_GUIDE.md)

## Usage

### Controls
- `ESC` or `Q`: Quit the simulation
- `P`: Pause/unpause the simulation
- `R`: Record the simulation as a GIF file

### Debug Mode
Enable debug mode in `config.yaml`:
```yaml
simulation:
  debug_mode: True
```

## Code Structure
- `main.py`: Entry point of the simulation, initializes pygame and manages the main game loop.
- `agent.py`: Defines the Agent class and manages agent behavior.
- `task.py`: Defines the Task class and manages task behavior.
- `behavior_tree.py`: Implements behavior tree nodes and execution logic.
- `utils.py`: Utility functions and configuration loading.
- `decision_making.py`: Contains decision-making logic for agents.

## Contributing
Feel free to fork the repository and submit pull requests. For major changes, please open an issue first to discuss what you would like to change.

## License
This project is licensed under the MIT License. See the LICENSE file for details.