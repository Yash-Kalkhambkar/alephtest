"""Pydantic schemas for API responses."""

from pydantic import BaseModel


# Common

class PlanningWindow(BaseModel):
    start: str
    end: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# GET /allocations

class AllocationItem(BaseModel):
    flight_id: str
    aircraft_size: str
    arrival_time: str
    departure_time: str
    status: str
    stand_id: str | None
    stand_type: str | None
    unassigned_reason_code: str | None
    unassigned_reason: str | None


class AllocationsResponse(BaseModel):
    planning_window: PlanningWindow
    turnaround_buffer_minutes: int
    total_flights: int
    assigned_count: int
    unassigned_count: int
    allocations: list[AllocationItem]


# GET /stands/{stand_id}

class StandFlightItem(BaseModel):
    flight_id: str
    aircraft_size: str
    arrival_time: str
    departure_time: str
    gap_before_minutes: int | None


class StandScheduleResponse(BaseModel):
    stand_id: str
    stand_type: str
    max_size: str
    flight_count: int
    flights: list[StandFlightItem]


# GET /metrics

class AssignmentSummary(BaseModel):
    total_valid_flights: int
    assigned: int
    unassigned: int
    unassigned_rate: float


class PLBUsage(BaseModel):
    flights_on_plb: int
    flights_on_remote: int
    plb_rate_of_valid: float
    plb_rate_of_assigned: float


class UnassignedBreakdown(BaseModel):
    by_reason: dict[str, int]
    by_aircraft_size: dict[str, int]


class StandUtilisationItem(BaseModel):
    stand_id: str
    stand_type: str
    flight_count: int
    occupied_minutes: int
    utilisation: float


class StandUtilisation(BaseModel):
    window_minutes: int
    by_type: dict[str, float]
    by_stand: list[StandUtilisationItem]


class PeakConcurrency(BaseModel):
    aircraft_on_ground: int
    first_occurred_at: str | None
    stand_count: int


class DataQualityFile(BaseModel):
    rows_read: int
    valid: int
    dropped: int
    fixed: int


class DataQuality(BaseModel):
    flights: DataQualityFile
    stands: DataQualityFile


class MetricsResponse(BaseModel):
    planning_window: PlanningWindow
    turnaround_buffer_minutes: int
    scope: str
    assignment_summary: AssignmentSummary
    plb_usage: PLBUsage
    unassigned_breakdown: UnassignedBreakdown
    stand_utilisation: StandUtilisation
    peak_concurrency: PeakConcurrency
    data_quality: DataQuality


# GET /data-issues

class IssueItem(BaseModel):
    source_file: str
    row_number: int
    record_id: str | None
    issue_code: str
    action: str
    field: str | None
    original_value: str | None
    message: str


class IssueSummaryFile(BaseModel):
    rows_read: int
    valid: int
    dropped: int
    fixed: int


class IssueSummary(BaseModel):
    total_issues: int
    flights: IssueSummaryFile
    stands: IssueSummaryFile
    by_issue_code: dict[str, int]


class DataIssuesResponse(BaseModel):
    summary: IssueSummary
    issues: list[IssueItem]
