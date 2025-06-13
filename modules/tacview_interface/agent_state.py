# aircraft_state.py
"""
Defines the AircraftState data structure and utility constants.
"""

import math
import time
from dataclasses import dataclass, field

# Unit conversion constants
KNOTS_TO_MPS = 0.514444
MPS_TO_KNOTS = 1.0 / KNOTS_TO_MPS
RAD_TO_DEG = 180.0 / math.pi

@dataclass
class AircraftState:
    """Represents the state of a single aircraft."""
    # Metadata (must be first)
    aircraft_id: str
    
    # Position and orientation
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_m: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    
    # Velocities
    ground_speed_mps: float = 0.0
    
    # Systems
    throttle: float = 0.0
    
    # Status
    armed: bool = False
    mode: str = "UNKNOWN"
    
    # Configurable Metadata
    pilot_name: str = "PILOT"
    aircraft_type: str = "Generic"
    coalition: str = "Neutrals"
    country: str = "XX"
    
    last_update: float = field(default_factory=time.time)
    
    @property
    def ground_speed_knots(self) -> float:
        return self.ground_speed_mps * MPS_TO_KNOTS