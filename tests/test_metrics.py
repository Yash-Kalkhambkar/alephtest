"""Metrics tests using hand-computed scenario M from the test plan."""

# Scenario M (window 06:00–12:00, buffer 15 min):
#   Stands: P1 PLB-L, R1 REMOTE-L
#   F1 L 06:00–07:00  → P1  (60 min on P1)
#   F2 M 06:30–07:30  → R1  (PLB busy; 60 min on R1)
#   F3 S 07:20–08:20  → P1  (gap 20 min ≥ 15; 60 min on P1)
#   F4 L 06:40–07:40  → UNASSIGNED (P1 until 07:00+15=07:15; R1 until 07:30+15=07:45)
#   F5 S 11:30–12:30  → P1  (free; 30 min inside window, 30 outside)
#
# Hand-computed expectations:
#   total=5, assigned=4, unassigned=1, unassigned_rate=0.2
#   plb=3 (F1,F3,F5), remote=1 (F2), plb_rate_of_valid=0.6, plb_rate_of_assigned=0.75
#   P1 occupied = 60+60+30 = 150 → 150/360 = 0.4167
#   R1 occupied = 60        →  60/360 = 0.1667
#   peak: F1+F2+F4 on ground at 06:40 → 3

from datetime import datetime, timedelta, timezone

import pytest

from stand_allocation.allocation import allocate_stands
from stand_allocation.metrics import compute_metrics
from stand_allocation.models import DataIssue, IssueAction, IssueCode


def _dt(h, m=0):
    return datetime(2027, 1, 15, h, m, 0, tzinfo=timezone.utc)


WINDOW_START = _dt(6)
WINDOW_END = _dt(12)
BUFFER = timedelta(minutes=15)


def _make_scenario():
    from tests.conftest import make_flight, make_stand
    stands = [
        make_stand("P1", "PLB", "L"),
        make_stand("R1", "REMOTE", "L"),
    ]
    flights = [
        make_flight("F1", "L", "06:00", "07:00"),
        make_flight("F2", "M", "06:30", "07:30"),
        make_flight("F3", "S", "07:20", "08:20"),
        make_flight("F4", "L", "06:40", "07:40"),
        make_flight("F5", "S", "11:30", "12:30"),
    ]
    allocations = allocate_stands(flights, stands, BUFFER)
    return stands, flights, allocations


def _metrics(stands, allocations, issues=None):
    return compute_metrics(
        allocations=allocations,
        stands=stands,
        all_issues=issues or [],
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        buffer_minutes=15,
        flights_rows_read=len(allocations),
        stands_rows_read=len(stands),
    )


def test_scenario_allocation_order():
    """Confirm allocations match the hand-worked order."""
    stands, _, allocations = _make_scenario()
    by_id = {a.flight.flight_id: a for a in allocations}

    assert by_id["F1"].stand.stand_id == "P1"
    assert by_id["F2"].stand.stand_id == "R1"
    assert by_id["F3"].stand.stand_id == "P1"
    assert by_id["F4"].stand is None
    assert by_id["F5"].stand.stand_id == "P1"


def test_assignment_summary():
    """MET-01: Assignment counts and rate."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    s = m["assignment_summary"]
    assert s["total_valid_flights"] == 5
    assert s["assigned"] == 4
    assert s["unassigned"] == 1
    assert s["unassigned_rate"] == 0.2


def test_plb_usage():
    """MET-02: PLB usage counts and rates."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    p = m["plb_usage"]
    assert p["flights_on_plb"] == 3
    assert p["flights_on_remote"] == 1
    assert p["plb_rate_of_valid"] == 0.6
    assert p["plb_rate_of_assigned"] == 0.75


def test_unassigned_breakdown():
    """MET-03: Unassigned breakdown by reason and size."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    b = m["unassigned_breakdown"]
    assert b["by_reason"]["NO_STAND_AVAILABLE"] == 1
    assert b["by_reason"]["NO_COMPATIBLE_STAND"] == 0
    assert b["by_aircraft_size"]["L"] == 1
    assert b["by_aircraft_size"]["S"] == 0
    assert b["by_aircraft_size"]["M"] == 0


def test_stand_utilisation_values():
    """MET-04: Utilisation per stand."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    by_stand = {s["stand_id"]: s for s in m["stand_utilisation"]["by_stand"]}
    assert by_stand["P1"]["occupied_minutes"] == 150
    assert by_stand["P1"]["utilisation"] == round(150 / 360, 4)
    assert by_stand["R1"]["occupied_minutes"] == 60
    assert by_stand["R1"]["utilisation"] == round(60 / 360, 4)


def test_utilisation_clipped_at_window_end():
    """MET-05: F5 departs at 12:30, only 30 min inside window counted."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    by_stand = {s["stand_id"]: s for s in m["stand_utilisation"]["by_stand"]}
    # P1 = F1(60) + F3(60) + F5(30 clipped) = 150
    assert by_stand["P1"]["occupied_minutes"] == 150


def test_utilisation_excludes_buffer_gap():
    """MET-06: The 15-min gap between F1 and F3 on P1 is not counted as occupied."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    by_stand = {s["stand_id"]: s for s in m["stand_utilisation"]["by_stand"]}
    # If buffer were counted, P1 would have 60 + 15 + 60 + 30 = 165
    assert by_stand["P1"]["occupied_minutes"] == 150


def test_peak_concurrency():
    """MET-07 & MET-08: Peak is 3 at 06:40 (F1, F2, F4 all on ground)."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    p = m["peak_concurrency"]
    assert p["aircraft_on_ground"] == 3
    assert p["first_occurred_at"] == "2027-01-15T06:40:00Z"
    assert p["stand_count"] == 2


def test_peak_counts_unassigned():
    """MET-08: Unassigned flight F4 is included in the peak count."""
    stands, _, allocations = _make_scenario()
    # Verify F4 is unassigned
    by_id = {a.flight.flight_id: a for a in allocations}
    assert by_id["F4"].stand is None
    # Peak still 3 — if unassigned were excluded it would be 2
    m = _metrics(stands, allocations)
    assert m["peak_concurrency"]["aircraft_on_ground"] == 3


def test_touching_flights_not_simultaneous():
    """MET-09: One flight leaves 09:00, next arrives 09:00 → not simultaneous."""
    from tests.conftest import make_stand
    from stand_allocation.models import Allocation

    stand = make_stand("C1", "PLB", "L")
    from tests.conftest import make_flight
    f1 = make_flight("F1", "M", "08:00", "09:00")
    f2 = make_flight("F2", "M", "09:00", "10:00")

    allocs = [
        Allocation(flight=f1, stand=stand, reason=None, message=None),
        Allocation(flight=f2, stand=stand, reason=None, message=None),
    ]
    m = compute_metrics(
        allocations=allocs, stands=[stand], all_issues=[],
        window_start=WINDOW_START, window_end=WINDOW_END,
        buffer_minutes=0, flights_rows_read=2, stands_rows_read=1,
    )
    assert m["peak_concurrency"]["aircraft_on_ground"] == 1


def test_empty_input():
    """MET-10: No flights → all zeros, no division error."""
    from tests.conftest import make_stand
    stands = [make_stand("C1", "PLB", "L")]
    m = compute_metrics(
        allocations=[], stands=stands, all_issues=[],
        window_start=WINDOW_START, window_end=WINDOW_END,
        buffer_minutes=15, flights_rows_read=0, stands_rows_read=1,
    )
    s = m["assignment_summary"]
    assert s["total_valid_flights"] == 0
    assert s["unassigned_rate"] == 0.0
    assert m["plb_usage"]["plb_rate_of_valid"] == 0.0
    assert m["plb_usage"]["plb_rate_of_assigned"] == 0.0
    assert m["peak_concurrency"]["aircraft_on_ground"] == 0
    assert m["peak_concurrency"]["first_occurred_at"] is None


def test_reconciliation_identities():
    """MET-13: assigned+unassigned=total; plb+remote=assigned; utils in [0,1]."""
    stands, _, allocations = _make_scenario()
    m = _metrics(stands, allocations)

    s = m["assignment_summary"]
    assert s["assigned"] + s["unassigned"] == s["total_valid_flights"]

    p = m["plb_usage"]
    assert p["flights_on_plb"] + p["flights_on_remote"] == s["assigned"]

    unassigned_by_reason = sum(m["unassigned_breakdown"]["by_reason"].values())
    unassigned_by_size = sum(m["unassigned_breakdown"]["by_aircraft_size"].values())
    assert unassigned_by_reason == s["unassigned"]
    assert unassigned_by_size == s["unassigned"]

    for entry in m["stand_utilisation"]["by_stand"]:
        assert 0.0 <= entry["utilisation"] <= 1.0
