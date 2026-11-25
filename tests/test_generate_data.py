"""Tests for the data generator and sample-data properties."""

import pytest

from stand_allocation.config import PLANNING_DATE, RANDOM_SEED, GENERATED_VALID_FLIGHTS
from stand_allocation.generate_data import generate_sample_data
from stand_allocation.loader import load_csv
from stand_allocation.validation import validate_flights, validate_stands
from stand_allocation.models import IssueAction
from tests.conftest import settings_for


def _generate(tmp_path):
    generate_sample_data(
        output_dir=tmp_path,
        planning_date=PLANNING_DATE,
        seed=RANDOM_SEED,
        valid_flight_count=GENERATED_VALID_FLIGHTS,
    )
    return tmp_path


def test_generator_is_deterministic(tmp_path):
    """GEN-01 / AC-01: Running twice yields byte-identical files."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    generate_sample_data(out1, PLANNING_DATE, RANDOM_SEED, GENERATED_VALID_FLIGHTS)
    generate_sample_data(out2, PLANNING_DATE, RANDOM_SEED, GENERATED_VALID_FLIGHTS)

    assert (out1 / "stands.csv").read_bytes() == (out2 / "stands.csv").read_bytes()
    assert (out1 / "flights.csv").read_bytes() == (out2 / "flights.csv").read_bytes()


def test_at_least_five_distinct_dropped_codes(tmp_path):
    """GEN-02 / AC-02: Generated flights.csv has ≥5 distinct dropped issue codes."""
    _generate(tmp_path)
    settings = settings_for(tmp_path)

    rows = load_csv(tmp_path / "flights.csv",
                    {"flight_id", "aircraft_size", "arrival_time", "departure_time"})
    result = validate_flights(rows, settings)

    dropped_codes = {i.code for i in result.issues if i.action == IssueAction.DROPPED}
    assert len(dropped_codes) >= 5, f"Only {len(dropped_codes)} distinct dropped codes: {dropped_codes}"


def test_valid_flights_arrive_within_window(tmp_path):
    """GEN-03: All valid flights arrive in [06:00, 12:00)."""
    _generate(tmp_path)
    settings = settings_for(tmp_path)

    rows = load_csv(tmp_path / "flights.csv",
                    {"flight_id", "aircraft_size", "arrival_time", "departure_time"})
    result = validate_flights(rows, settings)

    for flight in result.valid:
        assert settings.window_start_utc <= flight.arrival_time < settings.window_end_utc


def test_committed_data_matches_generator(tmp_path):
    """GEN-05: Committed data/flights.csv is byte-identical to fresh generator output."""
    import pathlib
    committed_dir = pathlib.Path("data")

    if not committed_dir.exists():
        pytest.skip("Committed data directory not found")

    generate_sample_data(tmp_path, PLANNING_DATE, RANDOM_SEED, GENERATED_VALID_FLIGHTS)

    for fname in ("stands.csv", "flights.csv"):
        committed = (committed_dir / fname).read_bytes()
        fresh = (tmp_path / fname).read_bytes()
        assert committed == fresh, f"{fname} differs from generator output (stale committed file?)"


def test_allocation_determinism(tmp_path):
    """GEN-06 / AC-08: allocate() twice on the same input → identical result."""
    from datetime import timedelta
    from stand_allocation.allocation import allocate_stands

    _generate(tmp_path)
    settings = settings_for(tmp_path)

    rows = load_csv(tmp_path / "flights.csv",
                    {"flight_id", "aircraft_size", "arrival_time", "departure_time"})
    flights = validate_flights(rows, settings).valid

    stands_rows = load_csv(tmp_path / "stands.csv", {"stand_id", "stand_type", "max_size"})
    stands = validate_stands(stands_rows).valid

    buffer = timedelta(minutes=15)
    a1 = allocate_stands(flights, stands, buffer)
    a2 = allocate_stands(flights, stands, buffer)

    assert len(a1) == len(a2)
    for x, y in zip(a1, a2):
        assert x.flight.flight_id == y.flight.flight_id
        assert (x.stand.stand_id if x.stand else None) == (y.stand.stand_id if y.stand else None)


def test_no_hard_rule_violations_on_sample(tmp_path):
    """GEN-07 / AC-05: find_violations returns empty on generated sample."""
    from datetime import timedelta
    from stand_allocation.allocation import allocate_stands, find_violations
    from stand_allocation.validation import validate_stands

    _generate(tmp_path)
    settings = settings_for(tmp_path)

    rows = load_csv(tmp_path / "flights.csv",
                    {"flight_id", "aircraft_size", "arrival_time", "departure_time"})
    flights = validate_flights(rows, settings).valid

    stands_rows = load_csv(tmp_path / "stands.csv", {"stand_id", "stand_type", "max_size"})
    stands = validate_stands(stands_rows).valid

    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    violations = find_violations(allocations, stands, buffer)

    assert violations == [], f"Hard rule violations: {violations}"


def test_sample_has_unassigned_flight(tmp_path):
    """AC-09: Generated data must produce at least one unassigned flight."""
    from datetime import timedelta
    from stand_allocation.allocation import allocate_stands
    from stand_allocation.validation import validate_stands

    _generate(tmp_path)
    settings = settings_for(tmp_path)

    rows = load_csv(tmp_path / "flights.csv",
                    {"flight_id", "aircraft_size", "arrival_time", "departure_time"})
    flights = validate_flights(rows, settings).valid

    stands_rows = load_csv(tmp_path / "stands.csv", {"stand_id", "stand_type", "max_size"})
    stands = validate_stands(stands_rows).valid

    allocations = allocate_stands(flights, stands, timedelta(minutes=15))
    unassigned = [a for a in allocations if a.stand is None]

    assert len(unassigned) >= 1, "No unassigned flights – PLB scarcity not achieved"
