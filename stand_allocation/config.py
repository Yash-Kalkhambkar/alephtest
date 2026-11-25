# Reviewed by Yash Kalkhambkar

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

RANDOM_SEED = 42
GENERATED_VALID_FLIGHTS = 48  # 48 clean + 1 normalisable = 49 valid
PLANNING_DATE = "2027-01-15"

WINDOW_START_HOUR = 6
WINDOW_END_HOUR = 12

DEFAULT_TURNAROUND_BUFFER_MINUTES = 15

DEFAULT_DATA_DIR = "data"
STANDS_FILENAME = "stands.csv"
FLIGHTS_FILENAME = "flights.csv"


@dataclass(frozen=True)
class Settings:
    turnaround_buffer_minutes: int
    planning_date: str
    window_start_hour: int
    window_end_hour: int
    window_start_utc: datetime
    window_end_utc: datetime
    data_dir: Path
    stands_file: Path
    flights_file: Path
    random_seed: int
    generated_valid_flights: int

    @staticmethod
    def from_env() -> "Settings":
        buffer_minutes = int(os.getenv(
            "TURNAROUND_BUFFER_MINUTES",
            str(DEFAULT_TURNAROUND_BUFFER_MINUTES)
        ))
        planning_date = os.getenv("PLANNING_DATE", PLANNING_DATE)
        data_dir = Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR))

        if buffer_minutes < 0:
            raise ConfigError(f"Turnaround buffer must be >= 0, got {buffer_minutes}")

        try:
            date_obj = datetime.fromisoformat(planning_date).date()
        except ValueError as e:
            raise ConfigError(f"Invalid planning date '{planning_date}': {e}")

        window_start_utc = datetime(
            date_obj.year, date_obj.month, date_obj.day,
            WINDOW_START_HOUR, 0, 0, tzinfo=timezone.utc
        )
        window_end_utc = datetime(
            date_obj.year, date_obj.month, date_obj.day,
            WINDOW_END_HOUR, 0, 0, tzinfo=timezone.utc
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
    pass
