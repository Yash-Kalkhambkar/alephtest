# Reviewed by Yash Kalkhambkar

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum


class Size(IntEnum):
    # IntEnum so aircraft/stand fit check is just <=
    S = 1
    M = 2
    L = 3


class StandType(str, Enum):
    PLB = "PLB"
    REMOTE = "REMOTE"


class IssueAction(str, Enum):
    DROPPED = "DROPPED"
    FIXED = "FIXED"


class IssueCode(str, Enum):
    # shared
    MALFORMED_ROW = "MALFORMED_ROW"
    MISSING_VALUE = "MISSING_VALUE"
    VALUE_NORMALISED = "VALUE_NORMALISED"
    # flights
    INVALID_AIRCRAFT_SIZE = "INVALID_AIRCRAFT_SIZE"
    MALFORMED_TIMESTAMP = "MALFORMED_TIMESTAMP"
    DEPARTURE_NOT_AFTER_ARRIVAL = "DEPARTURE_NOT_AFTER_ARRIVAL"
    OUTSIDE_PLANNING_WINDOW = "OUTSIDE_PLANNING_WINDOW"
    DUPLICATE_FLIGHT_ID = "DUPLICATE_FLIGHT_ID"
    # stands
    INVALID_STAND_TYPE = "INVALID_STAND_TYPE"
    INVALID_STAND_SIZE = "INVALID_STAND_SIZE"
    DUPLICATE_STAND_ID = "DUPLICATE_STAND_ID"


class UnassignedReason(str, Enum):
    NO_COMPATIBLE_STAND = "NO_COMPATIBLE_STAND"
    NO_STAND_AVAILABLE = "NO_STAND_AVAILABLE"


class AllocationStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    UNASSIGNED = "UNASSIGNED"


@dataclass(frozen=True)
class Stand:
    stand_id: str
    stand_type: StandType
    max_size: Size


@dataclass(frozen=True)
class Flight:
    flight_id: str
    aircraft_size: Size
    arrival_time: datetime   # UTC-aware
    departure_time: datetime  # UTC-aware


@dataclass(frozen=True)
class DataIssue:
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
    row_number: int
    values: dict[str, str | None]


@dataclass(frozen=True)
class ValidationResult:
    valid: list
    issues: list[DataIssue]
    rows_read: int


@dataclass(frozen=True)
class Allocation:
    flight: Flight
    stand: Stand | None
    reason: UnassignedReason | None
    message: str | None

    def __post_init__(self):
        # Invariant: exactly one of stand or reason must be set
        if (self.stand is None) == (self.reason is None):
            raise ValueError("Exactly one of stand or reason must be set")


@dataclass(frozen=True)
class PipelineResult:
    stands: list[Stand]
    flights: list[Flight]
    allocations: list[Allocation]
    metrics: dict
    issues: list[DataIssue]
    settings: dict
