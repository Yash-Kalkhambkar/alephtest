"""Stand allocation logic."""

from datetime import timedelta

from .models import Allocation, Flight, Stand, UnassignedReason


def can_fit(flight: Flight, stand: Stand) -> bool:
    """Check if an aircraft can physically fit on a stand."""
    return flight.aircraft_size <= stand.max_size


def allocate_stands(
    flights: list[Flight],
    stands: list[Stand],
    buffer: timedelta
) -> list[Allocation]:
    """
    Allocate stands to flights using a greedy first-come-first-served strategy.
    
    Strategy:
    - Sort flights by (arrival, departure, flight_id)
    - For each flight, find compatible free stands
    - Pick the best available stand: PLB first, then smallest sufficient size, then alphabetically
    - If no stand available, mark unassigned with reason
    
    Args:
        flights: List of valid flights
        stands: List of valid stands
        buffer: Turnaround buffer (timedelta)
        
    Returns:
        List of Allocation objects, one per flight
    """
    # Sort flights by arrival time (then departure, then id for determinism)
    sorted_flights = sorted(
        flights,
        key=lambda f: (f.arrival_time, f.departure_time, f.flight_id)
    )
    
    # Track last departure time per stand
    stand_last_departure = {stand.stand_id: None for stand in stands}
    
    allocations = []
    
    for flight in sorted_flights:
        # Find compatible stands (by size)
        compatible_stands = [s for s in stands if can_fit(flight, s)]
        
        if not compatible_stands:
            # No stand can ever take this aircraft
            allocations.append(Allocation(
                flight=flight,
                stand=None,
                reason=UnassignedReason.NO_COMPATIBLE_STAND,
                message=f"No stand can take size {flight.aircraft_size.name}."
            ))
            continue
        
        # Find free stands (respecting buffer)
        free_stands = []
        for stand in compatible_stands:
            last_dep = stand_last_departure[stand.stand_id]
            if last_dep is None:
                # Stand never used
                free_stands.append(stand)
            elif flight.arrival_time >= last_dep + buffer:
                # Buffer respected
                free_stands.append(stand)
        
        if not free_stands:
            # All compatible stands are busy
            allocations.append(Allocation(
                flight=flight,
                stand=None,
                reason=UnassignedReason.NO_STAND_AVAILABLE,
                message=(
                    f"All {len(compatible_stands)} stands that can take size {flight.aircraft_size.name} "
                    f"are occupied or within the {int(buffer.total_seconds() / 60)}-minute turnaround buffer "
                    f"at {flight.arrival_time.strftime('%Y-%m-%dT%H:%M:%SZ')}."
                )
            ))
            continue
        
        # Pick best free stand: PLB first, then smallest size, then alphabetically
        best_stand = min(
            free_stands,
            key=lambda s: (
                0 if s.stand_type.value == "PLB" else 1,
                s.max_size,
                s.stand_id
            )
        )
        
        # Assign
        allocations.append(Allocation(
            flight=flight,
            stand=best_stand,
            reason=None,
            message=None
        ))
        
        # Update stand's last departure
        stand_last_departure[best_stand.stand_id] = flight.departure_time
    
    return allocations


def find_violations(
    allocations: list[Allocation],
    stands: list[Stand],
    buffer: timedelta
) -> list[str]:
    """
    Independent checker: verify no allocation violates the hard rules.
    
    Returns a list of violation messages (empty if all rules hold).
    
    Checks:
    - H1: No overlapping flights on a stand
    - H2: Aircraft size <= stand max_size
    - H3: Turnaround buffer between consecutive flights
    """
    violations = []
    
    # Build stand lookup
    stand_by_id = {s.stand_id: s for s in stands}
    
    # Group allocations by stand
    by_stand = {}
    for alloc in allocations:
        if alloc.stand is None:
            continue  # Unassigned flights don't occupy stands
        
        stand_id = alloc.stand.stand_id
        if stand_id not in by_stand:
            by_stand[stand_id] = []
        by_stand[stand_id].append(alloc)
    
    # Check each stand's schedule
    for stand_id, stand_allocs in by_stand.items():
        stand = stand_by_id.get(stand_id)
        if stand is None:
            violations.append(f"Allocation references unknown stand '{stand_id}'")
            continue
        
        # Sort by arrival
        sorted_allocs = sorted(stand_allocs, key=lambda a: a.flight.arrival_time)
        
        for alloc in sorted_allocs:
            flight = alloc.flight
            
            # H2: Size fit
            if not can_fit(flight, stand):
                violations.append(
                    f"Flight {flight.flight_id} (size {flight.aircraft_size.name}) "
                    f"does not fit on stand {stand_id} (max {stand.max_size.name})"
                )
        
        # H1 and H3: Check consecutive flights
        for i in range(len(sorted_allocs) - 1):
            curr = sorted_allocs[i]
            next_alloc = sorted_allocs[i + 1]
            
            curr_flight = curr.flight
            next_flight = next_alloc.flight
            
            # H1: No overlap [arrival, departure)
            if next_flight.arrival_time < curr_flight.departure_time:
                violations.append(
                    f"Stand {stand_id}: Flights {curr_flight.flight_id} and {next_flight.flight_id} overlap "
                    f"({curr_flight.arrival_time.strftime('%H:%M')}–{curr_flight.departure_time.strftime('%H:%M')} "
                    f"vs {next_flight.arrival_time.strftime('%H:%M')}–{next_flight.departure_time.strftime('%H:%M')})"
                )
            
            # H3: Buffer
            gap = next_flight.arrival_time - curr_flight.departure_time
            if gap < buffer:
                violations.append(
                    f"Stand {stand_id}: Gap between {curr_flight.flight_id} and {next_flight.flight_id} "
                    f"is {int(gap.total_seconds() / 60)} minutes, less than the {int(buffer.total_seconds() / 60)}-minute buffer"
                )
    
    return violations
