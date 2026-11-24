"""Domain models for airport stand allocation."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum


class Size(IntEnum):
    """Aircraft and stand sizes. Ordered so <= comparisons work for compatibility."""
    S = 1
    M = 2
    L = 3


class StandType(str, Enum):
    """Stand type: PLB (passenger loading bridge) or REMOTE (bus)."""
    PLB = "PLB"
    REMOTE = "REMOTE"


class IssueAction(str, Enum):
    """Action taken on a data issue."""
    DROPPED = "DROPPED"
    FIXED = "FIXED"


class IssueCode(str, Enum):
    """Data issue codes for flights and stands."""
    # Common
    MALFORMED_ROW = "MALFORMED_ROW"
    MISSING_VALUE = "MISSING_VALUE"
    VALUE_NORMALISED = "VALUE_NORMALISED"
    
    # Flights
    INVALID_AIRCRAFT_SIZE = "INVALID_AIRCRAFT_SIZE"
    MALFORMED_TIMESTAMP = "MALFORMED_TIMESTAMP"
    DEPARTURE_NOT_AFTER_ARRIVAL = "DEPARTURE_NOT_AFTER_ARRIVAL"
    OUTSIDE_PLANNING_WINDOW = "OUTSIDE_PLANNING_WINDOW"
    DUPLICATE_FLIGHT_ID = "DUPLICATE_FLIGHT_ID"
    
    # Stands
    INVALID_STAND_TYPE = "INVALID_STAND_TYPE"
    INVALID_STAND_SIZE = "INVALID_STAND_SIZE"
    DUPLICATE_STAND_ID = "DUPLICATE_STAND_ID"


class UnassignedReason(str, Enum):
    """Reason a flight could not be assigned a stand."""
    NO_COMPATIBLE_STAND = "NO_COMPATIBLE_STAND"
    NO_STAND_AVAILABLE = "NO_STAND_AVAILABLE"


class AllocationStatus(str, Enum):
    """Allocation status."""
    ASSIGNED = "ASSIGNED"
    UNASSIGNED = "UNASSIGNED"


@dataclass(frozen=True)
class Stand:
    """A parking stand for aircraft."""
    stand_id: str
    stand_type: StandType
    max_size: Size


@dataclass(frozen=True)
class Flight:
    """A flight with arrival and departure times."""
    flight_id: str
    aircraft_size: Size
    arrival_time: datetime  # UTC-aware
    departure_time: datetime  # UTC-aware


@dataclass(frozen=True)
class DataIssue:
    """A problem found in input data."""
    source_file: str
    row_number: int
    record_id: str | None
    code: IssueCode
    action: IssueAction
    field: str | None
    original_value: str | None
    message: str


@dataclass(frozen=True)
class LoadedRow:
    """A raw CSV row with its line number."""
    row_number: int
    values: dict[str, str | None]


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a CSV file."""
    valid: list  # list of Stand or Flight
    issues: list[DataIssue]
    rows_read: int


@dataclass(frozen=True)
class Allocation:
    """Assignment of a flight to a stand, or unassigned with reason."""
    flight: Flight
    stand: Stand | None
    reason: UnassignedReason | None
    message: str | None
    
    def __post_init__(self):
        """Validate invariant: exactly one of stand or reason is set."""
        if (self.stand is None) == (self.reason is None):
            raise ValueError("Exactly one of stand or reason must be set")


@dataclass(frozen=True)
class PipelineResult:
    """Complete result of running the allocation pipeline."""
    stands: list[Stand]
    flights: list[Flight]
    allocations: list[Allocation]
    metrics: dict
    issues: list[DataIssue]
    settings: dict  # Snapshot of config used
