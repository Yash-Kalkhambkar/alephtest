"""Tests for flight validation."""

import pytest

from stand_allocation.config import Settings
from stand_allocation.models import IssueAction, IssueCode, LoadedRow
from stand_allocation.validation import validate_flights


def make_settings():
    """Create test settings."""
    from datetime import datetime, timezone
    return Settings(
        turnaround_buffer_minutes=15,
        planning_date="2027-01-15",
        window_start_hour=6,
        window_end_hour=12,
        window_start_utc=datetime(2027, 1, 15, 6, 0, 0, tzinfo=timezone.utc),
        window_end_utc=datetime(2027, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        data_dir=None,
        stands_file=None,
        flights_file=None,
        random_seed=42,
        generated_valid_flights=48,
    )


def test_valid_flight_accepted():
    """CSV-01: Valid flight is accepted."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "FL100",
        "aircraft_size": "M",
        "arrival_time": "2027-01-15T08:00:00Z",
        "departure_time": "2027-01-15T09:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 1
    assert len(result.issues) == 0
    assert result.valid[0].flight_id == "FL100"


def test_invalid_aircraft_size():
    """SZ-02: XL is invalid (PDF DL902)."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "DL902",
        "aircraft_size": "XL",
        "arrival_time": "2027-01-15T08:00:00Z",
        "departure_time": "2027-01-15T09:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.INVALID_AIRCRAFT_SIZE
    assert result.issues[0].action == IssueAction.DROPPED


def test_missing_departure_time():
    """TS-10 / CSV-03: Missing departure (PDF EV318)."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "EV318",
        "aircraft_size": "M",
        "arrival_time": "2027-01-15T08:00:00Z",
        "departure_time": ""
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.MISSING_VALUE
    assert result.issues[0].field == "departure_time"


def test_departure_before_arrival():
    """DEP-01: Departure before arrival (PDF CZ411)."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "CZ411",
        "aircraft_size": "L",
        "arrival_time": "2027-01-15T09:20:00Z",
        "departure_time": "2027-01-15T08:50:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.DEPARTURE_NOT_AFTER_ARRIVAL


def test_malformed_timestamp():
    """TS-05: Wrong format rejected."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "BA999",
        "aircraft_size": "S",
        "arrival_time": "15/01/2027 7pm",
        "departure_time": "2027-01-15T09:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.MALFORMED_TIMESTAMP
    assert result.issues[0].field == "arrival_time"


def test_naive_timestamp_rejected():
    """TS-04: Timestamp without timezone rejected."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "FL100",
        "aircraft_size": "M",
        "arrival_time": "2027-01-15T08:00:00",  # No Z or offset
        "departure_time": "2027-01-15T09:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.MALFORMED_TIMESTAMP
    assert "timezone" in result.issues[0].message.lower()


def test_arrival_outside_window():
    """TS-15: Arrival before window start."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "EA111",
        "aircraft_size": "L",
        "arrival_time": "2027-01-15T05:10:00Z",  # Before 06:00
        "departure_time": "2027-01-15T06:30:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.OUTSIDE_PLANNING_WINDOW


def test_duplicate_flight_id():
    """DUP-01: Second occurrence dropped."""
    settings = make_settings()
    rows = [
        LoadedRow(2, {
            "flight_id": "FL100",
            "aircraft_size": "M",
            "arrival_time": "2027-01-15T08:00:00Z",
            "departure_time": "2027-01-15T09:00:00Z"
        }),
        LoadedRow(3, {
            "flight_id": "FL100",  # Duplicate
            "aircraft_size": "L",
            "arrival_time": "2027-01-15T10:00:00Z",
            "departure_time": "2027-01-15T11:00:00Z"
        })
    ]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 1  # First kept
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.DUPLICATE_FLIGHT_ID
    assert result.issues[0].row_number == 3


def test_normalization_reported():
    """CSV-13: Whitespace and case normalized, reported as FIXED."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": " ax500 ",
        "aircraft_size": " m ",
        "arrival_time": "2027-01-15T08:00:00Z",
        "departure_time": "2027-01-15T09:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 1
    assert result.valid[0].flight_id == "AX500"
    assert result.valid[0].aircraft_size.name == "M"
    
    # Should have a FIXED issue
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.VALUE_NORMALISED
    assert result.issues[0].action == IssueAction.FIXED


def test_missing_flight_id():
    """CSV-16: Blank flight_id dropped."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "",
        "aircraft_size": "S",
        "arrival_time": "2027-01-15T08:00:00Z",
        "departure_time": "2027-01-15T09:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert len(result.issues) == 1
    assert result.issues[0].code == IssueCode.MISSING_VALUE
    assert result.issues[0].field == "flight_id"


def test_arrival_at_window_start_valid():
    """TS-16: Arrival exactly at window start is valid."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "FL100",
        "aircraft_size": "M",
        "arrival_time": "2027-01-15T06:00:00Z",  # Exactly at start
        "departure_time": "2027-01-15T07:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 1


def test_arrival_at_window_end_invalid():
    """TS-17: Arrival at window end (exclusive) is invalid."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "FL100",
        "aircraft_size": "M",
        "arrival_time": "2027-01-15T12:00:00Z",  # At end (exclusive)
        "departure_time": "2027-01-15T13:00:00Z"
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 0
    assert result.issues[0].code == IssueCode.OUTSIDE_PLANNING_WINDOW


def test_departure_after_window_allowed():
    """TS-18: Departure after window end is allowed."""
    settings = make_settings()
    rows = [LoadedRow(2, {
        "flight_id": "FL100",
        "aircraft_size": "M",
        "arrival_time": "2027-01-15T11:59:00Z",
        "departure_time": "2027-01-15T13:30:00Z"  # After 12:00
    })]
    
    result = validate_flights(rows, settings)
    
    assert len(result.valid) == 1


def test_accounting_identity():
    """CSV-15: rows_read == valid + dropped."""
    settings = make_settings()
    rows = [
        LoadedRow(2, {"flight_id": "F1", "aircraft_size": "M",
                     "arrival_time": "2027-01-15T08:00:00Z",
                     "departure_time": "2027-01-15T09:00:00Z"}),
        LoadedRow(3, {"flight_id": "F2", "aircraft_size": "XL",  # Bad
                     "arrival_time": "2027-01-15T08:00:00Z",
                     "departure_time": "2027-01-15T09:00:00Z"}),
        LoadedRow(4, {"flight_id": "F3", "aircraft_size": "S",
                     "arrival_time": "2027-01-15T08:00:00Z",
                     "departure_time": "2027-01-15T09:00:00Z"}),
    ]
    
    result = validate_flights(rows, settings)
    
    dropped = len([i for i in result.issues if i.action == IssueAction.DROPPED])
    assert result.rows_read == len(result.valid) + dropped
