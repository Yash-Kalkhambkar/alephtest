"""Tests for hard allocation rules (H1, H2, H3)."""

from datetime import timedelta

import pytest

from stand_allocation.allocation import allocate_stands, can_fit, find_violations
from stand_allocation.models import UnassignedReason
from tests.conftest import make_flight, make_stand


def test_size_fit_matrix():
    """H2: Aircraft size compatibility matrix."""
    # S aircraft
    assert can_fit(make_flight("F1", "S", "06:00", "07:00"), make_stand("C1", "PLB", "S"))
    assert can_fit(make_flight("F1", "S", "06:00", "07:00"), make_stand("C1", "PLB", "M"))
    assert can_fit(make_flight("F1", "S", "06:00", "07:00"), make_stand("C1", "PLB", "L"))
    
    # M aircraft
    assert not can_fit(make_flight("F1", "M", "06:00", "07:00"), make_stand("C1", "PLB", "S"))
    assert can_fit(make_flight("F1", "M", "06:00", "07:00"), make_stand("C1", "PLB", "M"))
    assert can_fit(make_flight("F1", "M", "06:00", "07:00"), make_stand("C1", "PLB", "L"))
    
    # L aircraft
    assert not can_fit(make_flight("F1", "L", "06:00", "07:00"), make_stand("C1", "PLB", "S"))
    assert not can_fit(make_flight("F1", "L", "06:00", "07:00"), make_stand("C1", "PLB", "M"))
    assert can_fit(make_flight("F1", "L", "06:00", "07:00"), make_stand("C1", "PLB", "L"))


def test_no_compatible_stand():
    """Flight unassigned when no stand is large enough."""
    stands = [make_stand("C1", "PLB", "S")]
    flights = [make_flight("F1", "L", "06:00", "07:00")]  # L aircraft, only S stand
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    assert len(allocations) == 1
    assert allocations[0].stand is None
    assert allocations[0].reason == UnassignedReason.NO_COMPATIBLE_STAND


def test_exactly_15_minute_buffer_allowed():
    """BUF-01: Exactly 15-minute gap is allowed."""
    stands = [make_stand("C1", "PLB", "L")]
    flights = [
        make_flight("F1", "M", "06:00", "07:00"),
        make_flight("F2", "M", "07:15", "08:00"),  # Exactly 15 min after F1
    ]
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    # Both should be assigned to the same stand
    assert len(allocations) == 2
    assert allocations[0].stand.stand_id == "C1"
    assert allocations[1].stand.stand_id == "C1"


def test_less_than_buffer_rejected():
    """BUF-02: Gap less than 15 minutes is rejected."""
    stands = [make_stand("C1", "PLB", "L")]
    flights = [
        make_flight("F1", "M", "06:00", "07:00"),
        make_flight("F2", "M", "07:14", "08:00"),  # 14 min after F1
    ]
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    # F1 on stand, F2 unassigned
    assert allocations[0].stand.stand_id == "C1"
    assert allocations[1].stand is None
    assert allocations[1].reason == UnassignedReason.NO_STAND_AVAILABLE


def test_overlapping_flights_rejected():
    """H1 & OVL-01: Overlapping flights not allowed on same stand."""
    stands = [make_stand("C1", "PLB", "L")]
    flights = [
        make_flight("F1", "M", "06:00", "08:00"),
        make_flight("F2", "M", "07:00", "09:00"),  # Overlaps F1
    ]
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    # F1 on stand, F2 unassigned (arrives before F1 departs + buffer)
    assert allocations[0].stand.stand_id == "C1"
    assert allocations[1].stand is None


def test_two_stands_no_conflict():
    """OVL-02: Two overlapping flights with two stands - both assigned."""
    stands = [
        make_stand("C1", "PLB", "M"),
        make_stand("C2", "PLB", "M")
    ]
    flights = [
        make_flight("F1", "M", "06:00", "08:00"),
        make_flight("F2", "M", "07:00", "09:00"),
    ]
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    # Both assigned to different stands
    assert allocations[0].stand is not None
    assert allocations[1].stand is not None
    assert allocations[0].stand.stand_id != allocations[1].stand.stand_id


def test_buffer_zero_allows_back_to_back():
    """BUF-07: Buffer of 0 allows back-to-back flights."""
    stands = [make_stand("C1", "PLB", "L")]
    flights = [
        make_flight("F1", "M", "06:00", "07:00"),
        make_flight("F2", "M", "07:00", "08:00"),  # Departs exactly when F1 arrives
    ]
    
    buffer = timedelta(minutes=0)
    allocations = allocate_stands(flights, stands, buffer)
    
    # Both on same stand
    assert allocations[0].stand.stand_id == "C1"
    assert allocations[1].stand.stand_id == "C1"


def test_checker_catches_size_violation():
    """OVL-09: Independent checker detects size misfit."""
    from stand_allocation.models import Allocation
    
    stand = make_stand("C1", "PLB", "S")
    flight = make_flight("F1", "L", "06:00", "07:00")
    
    # Manually create invalid allocation
    bad_alloc = Allocation(flight=flight, stand=stand, reason=None, message=None)
    
    violations = find_violations([bad_alloc], [stand], timedelta(minutes=15))
    
    assert len(violations) > 0
    assert "does not fit" in violations[0]


def test_checker_catches_overlap():
    """OVL-08: Independent checker detects overlapping flights."""
    from stand_allocation.models import Allocation
    
    stand = make_stand("C1", "PLB", "L")
    f1 = make_flight("F1", "M", "06:00", "08:00")
    f2 = make_flight("F2", "M", "07:00", "09:00")
    
    # Manually create overlapping allocations
    allocs = [
        Allocation(flight=f1, stand=stand, reason=None, message=None),
        Allocation(flight=f2, stand=stand, reason=None, message=None),
    ]
    
    violations = find_violations(allocs, [stand], timedelta(minutes=15))
    
    assert len(violations) > 0
    assert "overlap" in violations[0].lower()


def test_checker_catches_buffer_breach():
    """OVL-10: Independent checker detects buffer breach."""
    from stand_allocation.models import Allocation
    
    stand = make_stand("C1", "PLB", "L")
    f1 = make_flight("F1", "M", "06:00", "07:00")
    f2 = make_flight("F2", "M", "07:10", "08:00")  # Only 10 min gap
    
    allocs = [
        Allocation(flight=f1, stand=stand, reason=None, message=None),
        Allocation(flight=f2, stand=stand, reason=None, message=None),
    ]
    
    violations = find_violations(allocs, [stand], timedelta(minutes=15))
    
    assert len(violations) > 0
    assert "buffer" in violations[0].lower() or "gap" in violations[0].lower()


def test_plb_preferred_over_remote():
    """UNA-08: PLB preferred when both free."""
    stands = [
        make_stand("C1", "PLB", "M"),
        make_stand("R1", "REMOTE", "M")
    ]
    flights = [make_flight("F1", "M", "06:00", "07:00")]
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    # Should get PLB
    assert allocations[0].stand.stand_id == "C1"
    assert allocations[0].stand.stand_type.value == "PLB"


def test_fallback_to_remote_when_plb_busy():
    """UNA-09: Falls back to REMOTE when PLB busy."""
    stands = [
        make_stand("C1", "PLB", "M"),
        make_stand("R1", "REMOTE", "M")
    ]
    flights = [
        make_flight("F1", "M", "06:00", "08:00"),
        make_flight("F2", "M", "07:00", "09:00"),  # Overlaps F1
    ]
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    # F1 gets PLB, F2 gets REMOTE
    assert allocations[0].stand.stand_id == "C1"
    assert allocations[1].stand.stand_id == "R1"


def test_best_fit_smallest_sufficient_size():
    """CAP-09: Best-fit prefers smallest sufficient stand."""
    stands = [
        make_stand("C1", "PLB", "L"),
        make_stand("C2", "PLB", "S")
    ]
    flights = [make_flight("F1", "S", "06:00", "07:00")]
    
    buffer = timedelta(minutes=15)
    allocations = allocate_stands(flights, stands, buffer)
    
    # Should get the S stand, not the L
    assert allocations[0].stand.stand_id == "C2"


def test_determinism():
    """OVL-07 & AC-08: Same inputs produce identical allocations."""
    stands = [
        make_stand("C1", "PLB", "M"),
        make_stand("R1", "REMOTE", "M")
    ]
    flights = [
        make_flight("F2", "M", "07:00", "08:00"),
        make_flight("F1", "M", "06:00", "07:00"),  # Intentionally out of order
    ]
    
    buffer = timedelta(minutes=15)
    
    allocs1 = allocate_stands(flights, stands, buffer)
    allocs2 = allocate_stands(flights, stands, buffer)
    
    # Results should be identical
    assert len(allocs1) == len(allocs2)
    for a1, a2 in zip(allocs1, allocs2):
        assert a1.flight.flight_id == a2.flight.flight_id
        if a1.stand:
            assert a2.stand is not None
            assert a1.stand.stand_id == a2.stand.stand_id
        else:
            assert a2.stand is None
