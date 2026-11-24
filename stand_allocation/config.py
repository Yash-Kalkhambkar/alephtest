"""Configuration for the stand allocation system."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# Constants for data generation
RANDOM_SEED = 42
GENERATED_VALID_FLIGHTS = 48  # Plus 1 normalisable = 49 valid
PLANNING_DATE = "2027-01-15"

# Planning window (times in UTC)
WINDOW_START_HOUR = 6
WINDOW_END_HOUR = 12

# Turnaround buffer (minutes between consecutive flights on a stand)
DEFAULT_TURNAROUND_BUFFER_MINUTES = 15

# Data paths
DEFAULT_DATA_DIR = "data"
STANDS_FILENAME = "stands.csv"
FLIGHTS_FILENAME = "flights.csv"


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the allocation system."""
    
    # Turnaround buffer
    turnaround_buffer_minutes: int
    
    # Planning window
    planning_date: str  # ISO date YYYY-MM-DD
    window_start_hour: int
    window_end_hour: int
    window_start_utc: datetime
    window_end_utc: datetime
    
    # Data paths
    data_dir: Path
    stands_file: Path
    flights_file: Path
    
    # Generation params (for reproducibility)
    random_seed: int
    generated_valid_flights: int
    
    @staticmethod
    def from_env() -> "Settings":
        """Create settings from environment variables and defaults."""
        # Read overridable values
        buffer_minutes = int(os.getenv(
            "TURNAROUND_BUFFER_MINUTES",
            str(DEFAULT_TURNAROUND_BUFFER_MINUTES)
        ))
        planning_date = os.getenv("PLANNING_DATE", PLANNING_DATE)
        data_dir = Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR))
        
        # Validate buffer
        if buffer_minutes < 0:
            raise ConfigError(f"Turnaround buffer must be >= 0, got {buffer_minutes}")
        
        # Parse and validate planning date
        try:
            date_obj = datetime.fromisoformat(planning_date).date()
        except ValueError as e:
            raise ConfigError(f"Invalid planning date '{planning_date}': {e}")
        
        # Build window times
        window_start_utc = datetime(
            date_obj.year, date_obj.month, date_obj.day,
            WINDOW_START_HOUR, 0, 0,
            tzinfo=timezone.utc
        )
        window_end_utc = datetime(
            date_obj.year, date_obj.month, date_obj.day,
            WINDOW_END_HOUR, 0, 0,
            tzinfo=timezone.utc
        )
        
        if window_end_utc <= window_start_utc:
            raise ConfigError("Window end must be after window start")
        
        return Settings(
            turnaround_buffer_minutes=buffer_minutes,
            planning_date=planning_date,
            window_start_hour=WINDOW_START_HOUR,
            window_end_hour=WINDOW_END_HOUR,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            data_dir=data_dir,
            stands_file=data_dir / STANDS_FILENAME,
            flights_file=data_dir / FLIGHTS_FILENAME,
            random_seed=RANDOM_SEED,
            generated_valid_flights=GENERATED_VALID_FLIGHTS,
        )


class ConfigError(Exception):
    """Configuration error."""
    pass
