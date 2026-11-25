"""Greedy stand allocator and independent hard-rule checker."""

from datetime import timedelta

from .models import Allocation, Flight, Stand, UnassignedReason


def can_fit(flight: Flight, stand: Stand) -> bool:
    """True if the aircraft fits on the stand (size <=  stand max)."""
    return flight.aircraft_size <= stand.max_size


def allocate_stands(
    flights: list[Flight],
    stands: list[Stand],
    buffer: timedelta,
) -> list[Allocation]:
    """
    Greedy first-come-first-served allocation.

    Sort by (arrival, departure, flight_id) for determinism, then for each
    flight pick the first free compatible stand ranked by:
      1. PLB before REMOTE
      2. Smallest sufficient size (best-fit keeps large stands for large aircraft)
      3. Stand ID alphabetically (tie-break)

    A flight is never left unassigned while a free compatible stand exists.
    """
    sorted_flights = sorted(
        flights,
        key=lambda f: (f.arrival_time, f.departure_time, f.flight_id),
    )

    # last departure recorded per stand so we can check the buffer in O(1)
    last_departure: dict[str, None] = {s.stand_id: None for s in stands}

    allocations = []

    for flight in sorted_flights:
        compatible = [s for s in stands if can_fit(flight, s)]

        if not compatible:
            allocations.append(Allocation(
                flight=flight, stand=None,
                reason=UnassignedReason.NO_COMPATIBLE_STAND,
                message=f"No stand can take size {flight.aircraft_size.name}.",
            ))
            continue

        free = [
            s for s in compatible
            if last_departure[s.stand_id] is None
            or flight.arrival_time >= last_departure[s.stand_id] + buffer
        ]

        if not free:
            buf_min = int(buffer.total_seconds() / 60)
            allocations.append(Allocation(
                flight=flight, stand=None,
                reason=UnassignedReason.NO_STAND_AVAILABLE,
                message=(
                    f"All {len(compatible)} stands that can take size {flight.aircraft_size.name} "
                    f"are occupied or within the {buf_min}-minute turnaround buffer "
                    f"at {flight.arrival_time.strftime('%Y-%m-%dT%H:%M:%SZ')}."
                ),
            ))
            continue

        best = min(
            free,
            key=lambda s: (0 if s.stand_type.value == "PLB" else 1, s.max_size, s.stand_id),
        )

        allocations.append(Allocation(flight=flight, stand=best, reason=None, message=None))
        last_departure[best.stand_id] = flight.departure_time

    return allocations


def find_violations(
    allocations: list[Allocation],
    stands: list[Stand],
    buffer: timedelta,
) -> list[str]:
    """
    Independent checker — re-reads the finished result from scratch and
    verifies all three hard rules hold. Does not reuse the allocator's
    shortcut. Returns a list of violation messages (empty = all good).

    H1: no overlapping flights on a stand
    H2: aircraft size <= stand max_size
    H3: gap between consecutive flights >= buffer
    """
    violations = []
    stand_by_id = {s.stand_id: s for s in stands}

    # group by stand
    by_stand: dict[str, list[Allocation]] = {}
    for alloc in allocations:
        if alloc.stand is None:
            continue
        by_stand.setdefault(alloc.stand.stand_id, []).append(alloc)

    for stand_id, stand_allocs in by_stand.items():
        stand = stand_by_id.get(stand_id)
        if stand is None:
            violations.append(f"Allocation references unknown stand '{stand_id}'")
            continue

        ordered = sorted(stand_allocs, key=lambda a: a.flight.arrival_time)

        for alloc in ordered:
            f = alloc.flight
            if not can_fit(f, stand):  # H2
                violations.append(
                    f"Flight {f.flight_id} (size {f.aircraft_size.name}) "
                    f"does not fit on stand {stand_id} (max {stand.max_size.name})"
                )

        for i in range(len(ordered) - 1):
            a, b = ordered[i].flight, ordered[i + 1].flight

            if b.arrival_time < a.departure_time:  # H1
                violations.append(
                    f"Stand {stand_id}: {a.flight_id} and {b.flight_id} overlap "
                    f"({a.arrival_time.strftime('%H:%M')}–{a.departure_time.strftime('%H:%M')} "
                    f"vs {b.arrival_time.strftime('%H:%M')}–{b.departure_time.strftime('%H:%M')})"
                )

            gap = b.arrival_time - a.departure_time
            if gap < buffer:  # H3
                violations.append(
                    f"Stand {stand_id}: gap between {a.flight_id} and {b.flight_id} "
                    f"is {int(gap.total_seconds() / 60)} min, "
                    f"less than the {int(buffer.total_seconds() / 60)}-min buffer"
                )

    return violations
