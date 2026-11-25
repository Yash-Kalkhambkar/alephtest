"""Pytest fixtures and test helpers."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stand_allocation.config import Settings
from stand_allocation.models import Flight, Size, Stand, StandType


@pytest.fixture
def planning_date():
    """Planning date for tests."""
    return "2027-01-15"


@pytest.fixture
def window_start(planning_date):
    """Planning window start."""
    date = datetime.fromisoformat(planning_date).date()
    return datetime(date.year, date.month, date.day, 6, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def window_end(planning_date):
    """Planning window end."""
    date = datetime.fromisoformat(planning_date).date()
    return datetime(date.year, date.month, date.day, 12, 0, 0, tzinfo=timezone.utc)


def make_flight(
    flight_id: str,
    size: str,
    arrival: str,
    departure: str,
    date: str = "2027-01-15"
) -> Flight:
    """
    Build a Flight from HH:MM strings.
    
    Args:
        flight_id: Flight ID
        size: Aircraft size (S/M/L)
        arrival: Arrival time as "HH:MM"
        departure: Departure time as "HH:MM"
        date: ISO date string (default 2027-01-15)
    """
    date_obj = datetime.fromisoformat(date).date()
    
    arr_h, arr_m = map(int, arrival.split(":"))
    dep_h, dep_m = map(int, departure.split(":"))
    
    arrival_dt = datetime(
        date_obj.year, date_obj.month, date_obj.day,
        arr_h, arr_m, 0, tzinfo=timezone.utc
    )
    departure_dt = datetime(
        date_obj.year, date_obj.month, date_obj.day,
        dep_h, dep_m, 0, tzinfo=timezone.utc
    )
    
    return Flight(
        flight_id=flight_id,
        aircraft_size=Size[size],
        arrival_time=arrival_dt,
        departure_time=departure_dt
    )


def make_stand(stand_id: str, stand_type: str, max_size: str) -> Stand:
    """Build a Stand."""
    return Stand(
        stand_id=stand_id,
        stand_type=StandType[stand_type],
        max_size=Size[max_size]
    )


def flight_row(**overrides) -> dict:
    """
    Build a valid flight CSV row dict with optional overrides.
    
    Default is a valid flight on 2027-01-15.
    """
    default = {
        "flight_id": "TEST01",
        "aircraft_size": "M",
        "arrival_time": "2027-01-15T08:00:00Z",
        "departure_time": "2027-01-15T09:00:00Z"
    }
    default.update(overrides)
    return default


def stand_row(**overrides) -> dict:
    """Build a valid stand CSV row dict with optional overrides."""
    default = {
        "stand_id": "C01",
        "stand_type": "PLB",
        "max_size": "L"
    }
    default.update(overrides)
    return default


def write_csvs(tmp_path: Path, stands_text: str, flights_text: str):
    """
    Write CSV files from text.
    
    Args:
        tmp_path: Temporary directory
        stands_text: CSV content for stands (with header)
        flights_text: CSV content for flights (with header)
    """
    stands_file = tmp_path / "stands.csv"
    flights_file = tmp_path / "flights.csv"
    
    stands_file.write_text(stands_text, encoding="utf-8")
    flights_file.write_text(flights_text, encoding="utf-8")


def settings_for(tmp_path: Path, buffer_minutes: int = 15) -> Settings:
    """
    Create Settings for a test data directory.
    
    Args:
        tmp_path: Temporary directory containing CSV files
        buffer_minutes: Turnaround buffer
    """
    date = datetime(2027, 1, 15, tzinfo=timezone.utc)
    
    return Settings(
        turnaround_buffer_minutes=buffer_minutes,
        planning_date="2027-01-15",
        window_start_hour=6,
        window_end_hour=12,
        window_start_utc=datetime(2027, 1, 15, 6, 0, 0, tzinfo=timezone.utc),
        window_end_utc=datetime(2027, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        data_dir=tmp_path,
        stands_file=tmp_path / "stands.csv",
        flights_file=tmp_path / "flights.csv",
        random_seed=42,
        generated_valid_flights=48,
    )
