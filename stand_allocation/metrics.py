"""Planner metrics computed from the allocation result."""

from datetime import datetime

from .models import Allocation, DataIssue, IssueAction, Stand, StandType, UnassignedReason


def compute_metrics(
    allocations: list[Allocation],
    stands: list[Stand],
    all_issues: list[DataIssue],
    window_start: datetime,
    window_end: datetime,
    buffer_minutes: int,
    flights_rows_read: int = 0,
    stands_rows_read: int = 0,
) -> dict:
    """
    Compute all six planner metrics.

    rows_read values must be passed in from ValidationResult — they are the
    authoritative source. FIXED rows are a subset of valid, so:
      rows_read == valid + dropped   (FIXED is NOT added separately)
    """
    assigned   = [a for a in allocations if a.stand is not None]
    unassigned = [a for a in allocations if a.stand is None]

    total        = len(allocations)
    assigned_n   = len(assigned)
    unassigned_n = len(unassigned)

    unassigned_rate    = unassigned_n / total if total > 0 else 0.0
    plb_assigned       = [a for a in assigned if a.stand.stand_type == StandType.PLB]
    remote_assigned    = [a for a in assigned if a.stand.stand_type == StandType.REMOTE]
    plb_n              = len(plb_assigned)
    remote_n           = len(remote_assigned)
    plb_rate_of_valid  = plb_n / total      if total      > 0 else 0.0
    plb_rate_assigned  = plb_n / assigned_n if assigned_n > 0 else 0.0

    # unassigned breakdown
    by_reason: dict[str, int] = {r.value: 0 for r in UnassignedReason}
    by_size: dict[str, int]   = {"S": 0, "M": 0, "L": 0}
    for alloc in unassigned:
        if alloc.reason:
            by_reason[alloc.reason.value] += 1
        by_size[alloc.flight.aircraft_size.name] += 1

    # stand utilisation
    window_minutes = int((window_end - window_start).total_seconds() / 60)
    util_list: list[dict] = []
    util_by_type: dict[StandType, list[float]] = {StandType.PLB: [], StandType.REMOTE: []}

    for stand in stands:
        stand_flights = [a.flight for a in assigned if a.stand and a.stand.stand_id == stand.stand_id]
        occupied = 0
        for f in stand_flights:
            clip_start = max(f.arrival_time, window_start)
            clip_end   = min(f.departure_time, window_end)
            if clip_end > clip_start:
                occupied += int((clip_end - clip_start).total_seconds() / 60)

        utilisation = occupied / window_minutes if window_minutes > 0 else 0.0
        util_list.append({
            "stand_id": stand.stand_id,
            "stand_type": stand.stand_type.value,
            "flight_count": len(stand_flights),
            "occupied_minutes": occupied,
            "utilisation": round(utilisation, 4),
        })
        util_by_type[stand.stand_type].append(utilisation)

    util_list.sort(key=lambda x: x["stand_id"])

    avg_by_type = {
        t.value: round(sum(vals) / len(vals) if vals else 0.0, 4)
        for t, vals in util_by_type.items()
    }

    # peak concurrency — sweep arrival/departure events
    # sort: by time, then departures (-1) before arrivals (+1) at the same instant
    events: list[tuple] = []
    for alloc in allocations:
        f = alloc.flight
        if f.arrival_time < window_end and f.departure_time > window_start:
            arr = max(f.arrival_time, window_start)
            dep = min(f.departure_time, window_end)
            events.append((arr, 1, f.flight_id))
            events.append((dep, -1, f.flight_id))

    events.sort(key=lambda e: (e[0], e[1]))

    current = peak = 0
    peak_time = None
    for t, delta, _ in events:
        current += delta
        if current > peak:
            peak = current
            peak_time = t

    # data quality
    flights_issues = [i for i in all_issues if i.source_file == "flights.csv"]
    stands_issues  = [i for i in all_issues if i.source_file == "stands.csv"]

    def _quality(issues, valid, rows_read):
        dropped = sum(1 for i in issues if i.action == IssueAction.DROPPED)
        fixed   = sum(1 for i in issues if i.action == IssueAction.FIXED)
        return {"rows_read": rows_read, "valid": valid, "dropped": dropped, "fixed": fixed}

    return {
        "planning_window": {
            "start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end":   window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "turnaround_buffer_minutes": buffer_minutes,
        "scope": (
            f"All valid flights arriving in [{window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}, "
            f"{window_end.strftime('%Y-%m-%dT%H:%M:%SZ')})."
        ),
        "assignment_summary": {
            "total_valid_flights": total,
            "assigned": assigned_n,
            "unassigned": unassigned_n,
            "unassigned_rate": round(unassigned_rate, 4),
        },
        "plb_usage": {
            "flights_on_plb":    plb_n,
            "flights_on_remote": remote_n,
            "plb_rate_of_valid":    round(plb_rate_of_valid, 4),
            "plb_rate_of_assigned": round(plb_rate_assigned, 4),
        },
        "unassigned_breakdown": {"by_reason": by_reason, "by_aircraft_size": by_size},
        "stand_utilisation": {
            "window_minutes": window_minutes,
            "by_type":  avg_by_type,
            "by_stand": util_list,
        },
        "peak_concurrency": {
            "aircraft_on_ground": peak,
            "first_occurred_at": peak_time.strftime("%Y-%m-%dT%H:%M:%SZ") if peak_time else None,
            "stand_count": len(stands),
        },
        "data_quality": {
            "flights": _quality(flights_issues, total,         flights_rows_read),
            "stands":  _quality(stands_issues,  len(stands),   stands_rows_read),
        },
    }
