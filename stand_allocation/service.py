"""Pipeline orchestration — runs once at startup, result stored on app.state."""

import logging
from datetime import timedelta

from .allocation import allocate_stands, find_violations
from .config import Settings
from .loader import load_csv
from .metrics import compute_metrics
from .models import PipelineResult
from .validation import validate_flights, validate_stands

logger = logging.getLogger(__name__)


def run_pipeline(settings: Settings) -> PipelineResult:
    """
    Load → validate → allocate → verify → metrics.

    Raises DataFileError for bad CSV files (expected; handled at startup).
    Raises RuntimeError if the hard-rule checker finds a violation (programming bug).
    """
    logger.info("Loading data from %s", settings.data_dir)

    stands_rows  = load_csv(settings.stands_file,  {"stand_id", "stand_type", "max_size"})
    stands_result = validate_stands(stands_rows)
    logger.info(
        "Stands: %d valid, %d dropped, %d fixed from %d rows",
        len(stands_result.valid),
        sum(1 for i in stands_result.issues if i.action.value == "DROPPED"),
        sum(1 for i in stands_result.issues if i.action.value == "FIXED"),
        stands_result.rows_read,
    )

    flights_rows  = load_csv(settings.flights_file, {"flight_id", "aircraft_size", "arrival_time", "departure_time"})
    flights_result = validate_flights(flights_rows, settings)
    logger.info(
        "Flights: %d valid, %d dropped, %d fixed from %d rows",
        len(flights_result.valid),
        sum(1 for i in flights_result.issues if i.action.value == "DROPPED"),
        sum(1 for i in flights_result.issues if i.action.value == "FIXED"),
        flights_result.rows_read,
    )

    buffer = timedelta(minutes=settings.turnaround_buffer_minutes)
    allocations = allocate_stands(flights_result.valid, stands_result.valid, buffer)

    assigned_n = sum(1 for a in allocations if a.stand is not None)
    logger.info("Allocated: %d assigned, %d unassigned", assigned_n, len(allocations) - assigned_n)

    violations = find_violations(allocations, stands_result.valid, buffer)
    if violations:
        msg = "Hard rule violations:\n" + "\n".join(f"  {v}" for v in violations)
        logger.error(msg)
        raise RuntimeError(msg)
    logger.info("Hard rules verified — no violations")

    all_issues = stands_result.issues + flights_result.issues
    metrics = compute_metrics(
        allocations=allocations,
        stands=stands_result.valid,
        all_issues=all_issues,
        window_start=settings.window_start_utc,
        window_end=settings.window_end_utc,
        buffer_minutes=settings.turnaround_buffer_minutes,
        flights_rows_read=flights_result.rows_read,
        stands_rows_read=stands_result.rows_read,
    )

    return PipelineResult(
        stands=stands_result.valid,
        flights=flights_result.valid,
        allocations=allocations,
        metrics=metrics,
        issues=all_issues,
        settings={
            "turnaround_buffer_minutes": settings.turnaround_buffer_minutes,
            "planning_window_start": settings.window_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "planning_window_end":   settings.window_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
