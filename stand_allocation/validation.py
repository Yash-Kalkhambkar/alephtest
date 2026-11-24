"""Data validation for flights and stands."""

from datetime import datetime, timezone

from .models import (
    DataIssue,
    Flight,
    IssueAction,
    IssueCode,
    LoadedRow,
    Size,
    Stand,
    StandType,
    ValidationResult,
)


def parse_utc_timestamp(text: str | None) -> datetime | None:
    """
    Parse an ISO 8601 timestamp to a UTC-aware datetime.
    
    Args:
        text: Timestamp string (must have timezone info)
        
    Returns:
        UTC-aware datetime, or None if text is None/empty/whitespace
        
    Raises:
        ValueError: If text is malformed or naive (no timezone)
    """
    if text is None or not text.strip():
        return None
    
    text = text.strip()
    
    # Python 3.10 fromisoformat doesn't accept 'Z', replace with +00:00
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as e:
        raise ValueError(f"Not a valid ISO 8601 timestamp: {e}")
    
    # Reject naive timestamps
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("Timestamp must include timezone information")
    
    # Convert to UTC
    return dt.astimezone(timezone.utc)


def format_utc_timestamp(dt: datetime) -> str:
    """Format a UTC datetime as ISO 8601 with 'Z'."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_flights(rows: list[LoadedRow], settings) -> ValidationResult:
    """
    Validate flight rows.
    
    Returns ValidationResult with valid Flight objects and issues.
    First failure per row wins (one issue per row).
    """
    valid_flights = []
    issues = []
    accepted_ids = set()
    
    for row in rows:
        vals = row.values
        row_num = row.row_number
        
        # Check column count (DictReader gives None for missing columns)
        expected_cols = {"flight_id", "aircraft_size", "arrival_time", "departure_time"}
        if any(col not in vals for col in expected_cols):
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=None,
                code=IssueCode.MALFORMED_ROW,
                action=IssueAction.DROPPED,
                field=None,
                original_value=None,
                message=f"Row is malformed (expected columns: {', '.join(expected_cols)})."
            ))
            continue
        
        # Normalize whitespace and case
        flight_id_raw = vals.get("flight_id", "").strip()
        size_raw = vals.get("aircraft_size", "").strip()
        arrival_raw = vals.get("arrival_time", "").strip()
        departure_raw = vals.get("departure_time", "").strip()
        
        flight_id = flight_id_raw.upper()
        size_str = size_raw.upper()
        
        # Track if normalization happened (report only if row is accepted)
        normalized = (
            flight_id_raw != flight_id or
            size_raw != size_str
        )
        normalized_msg = []
        if flight_id_raw != flight_id:
            normalized_msg.append(f"flight_id '{flight_id_raw}' normalised to '{flight_id}'")
        if size_raw != size_str:
            normalized_msg.append(f"aircraft_size '{size_raw}' normalised to '{size_str}'")
        
        # Required values
        if not flight_id:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=None,
                code=IssueCode.MISSING_VALUE,
                action=IssueAction.DROPPED,
                field="flight_id",
                original_value=flight_id_raw or None,
                message="Flight ID is missing."
            ))
            continue
        
        if not size_str:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.MISSING_VALUE,
                action=IssueAction.DROPPED,
                field="aircraft_size",
                original_value=size_raw or None,
                message="Aircraft size is missing."
            ))
            continue
        
        if not arrival_raw:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.MISSING_VALUE,
                action=IssueAction.DROPPED,
                field="arrival_time",
                original_value=None,
                message="Arrival time is missing."
            ))
            continue
        
        if not departure_raw:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.MISSING_VALUE,
                action=IssueAction.DROPPED,
                field="departure_time",
                original_value=None,
                message="Departure time is missing."
            ))
            continue
        
        # Aircraft size validation
        try:
            size = Size[size_str]
        except KeyError:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.INVALID_AIRCRAFT_SIZE,
                action=IssueAction.DROPPED,
                field="aircraft_size",
                original_value=size_raw,
                message=f"Aircraft size '{size_str}' is not supported (allowed: S, M, L)."
            ))
            continue
        
        # Timestamp parsing
        try:
            arrival_time = parse_utc_timestamp(arrival_raw)
            if arrival_time is None:
                raise ValueError("empty")
        except ValueError as e:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.MALFORMED_TIMESTAMP,
                action=IssueAction.DROPPED,
                field="arrival_time",
                original_value=arrival_raw,
                message=f"Arrival time '{arrival_raw}' is not a valid ISO 8601 UTC timestamp ({e})."
            ))
            continue
        
        try:
            departure_time = parse_utc_timestamp(departure_raw)
            if departure_time is None:
                raise ValueError("empty")
        except ValueError as e:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.MALFORMED_TIMESTAMP,
                action=IssueAction.DROPPED,
                field="departure_time",
                original_value=departure_raw,
                message=f"Departure time '{departure_raw}' is not a valid ISO 8601 UTC timestamp ({e})."
            ))
            continue
        
        # Departure after arrival
        if departure_time <= arrival_time:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.DEPARTURE_NOT_AFTER_ARRIVAL,
                action=IssueAction.DROPPED,
                field="departure_time",
                original_value=departure_raw,
                message=f"Departure {format_utc_timestamp(departure_time)} is not after "
                        f"arrival {format_utc_timestamp(arrival_time)}."
            ))
            continue
        
        # Arrival within planning window
        if not (settings.window_start_utc <= arrival_time < settings.window_end_utc):
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.OUTSIDE_PLANNING_WINDOW,
                action=IssueAction.DROPPED,
                field="arrival_time",
                original_value=arrival_raw,
                message=f"Arrival {format_utc_timestamp(arrival_time)} is outside the planning window "
                        f"{format_utc_timestamp(settings.window_start_utc)}–"
                        f"{format_utc_timestamp(settings.window_end_utc)}."
            ))
            continue
        
        # Duplicate ID (after normalization)
        if flight_id in accepted_ids:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.DUPLICATE_FLIGHT_ID,
                action=IssueAction.DROPPED,
                field="flight_id",
                original_value=flight_id_raw,
                message=f"Flight ID '{flight_id}' is already used by an earlier row; this row ignored."
            ))
            continue
        
        # Row is valid - accept it
        flight = Flight(
            flight_id=flight_id,
            aircraft_size=size,
            arrival_time=arrival_time,
            departure_time=departure_time,
        )
        valid_flights.append(flight)
        accepted_ids.add(flight_id)
        
        # Report normalization if it happened
        if normalized:
            issues.append(DataIssue(
                source_file="flights.csv",
                row_number=row_num,
                record_id=flight_id,
                code=IssueCode.VALUE_NORMALISED,
                action=IssueAction.FIXED,
                field="aircraft_size" if size_raw != size_str else "flight_id",
                original_value=f"{flight_id_raw} / {size_raw}",
                message="; ".join(normalized_msg) + "."
            ))
    
    return ValidationResult(
        valid=valid_flights,
        issues=issues,
        rows_read=len(rows)
    )


def validate_stands(rows: list[LoadedRow]) -> ValidationResult:
    """
    Validate stand rows.
    
    Returns ValidationResult with valid Stand objects and issues.
    """
    valid_stands = []
    issues = []
    accepted_ids = set()
    
    for row in rows:
        vals = row.values
        row_num = row.row_number
        
        # Check column count
        expected_cols = {"stand_id", "stand_type", "max_size"}
        if any(col not in vals for col in expected_cols):
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=None,
                code=IssueCode.MALFORMED_ROW,
                action=IssueAction.DROPPED,
                field=None,
                original_value=None,
                message=f"Row is malformed (expected columns: {', '.join(expected_cols)})."
            ))
            continue
        
        # Normalize
        stand_id_raw = vals.get("stand_id", "").strip()
        type_raw = vals.get("stand_type", "").strip()
        size_raw = vals.get("max_size", "").strip()
        
        stand_id = stand_id_raw.upper()
        type_str = type_raw.upper()
        size_str = size_raw.upper()
        
        normalized = (
            stand_id_raw != stand_id or
            type_raw != type_str or
            size_raw != size_str
        )
        
        # Required values
        if not stand_id:
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=None,
                code=IssueCode.MISSING_VALUE,
                action=IssueAction.DROPPED,
                field="stand_id",
                original_value=None,
                message="Stand ID is missing."
            ))
            continue
        
        if not type_str:
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=stand_id,
                code=IssueCode.MISSING_VALUE,
                action=IssueAction.DROPPED,
                field="stand_type",
                original_value=None,
                message="Stand type is missing."
            ))
            continue
        
        if not size_str:
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=stand_id,
                code=IssueCode.MISSING_VALUE,
                action=IssueAction.DROPPED,
                field="max_size",
                original_value=None,
                message="Max size is missing."
            ))
            continue
        
        # Validate stand type
        try:
            stand_type = StandType(type_str)
        except ValueError:
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=stand_id,
                code=IssueCode.INVALID_STAND_TYPE,
                action=IssueAction.DROPPED,
                field="stand_type",
                original_value=type_raw,
                message=f"Stand type '{type_str}' is not valid (allowed: PLB, REMOTE)."
            ))
            continue
        
        # Validate max size
        try:
            max_size = Size[size_str]
        except KeyError:
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=stand_id,
                code=IssueCode.INVALID_STAND_SIZE,
                action=IssueAction.DROPPED,
                field="max_size",
                original_value=size_raw,
                message=f"Max size '{size_str}' is not valid (allowed: S, M, L)."
            ))
            continue
        
        # Duplicate ID
        if stand_id in accepted_ids:
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=stand_id,
                code=IssueCode.DUPLICATE_STAND_ID,
                action=IssueAction.DROPPED,
                field="stand_id",
                original_value=stand_id_raw,
                message=f"Stand ID '{stand_id}' is already used by an earlier row; this row ignored."
            ))
            continue
        
        # Row is valid
        stand = Stand(
            stand_id=stand_id,
            stand_type=stand_type,
            max_size=max_size,
        )
        valid_stands.append(stand)
        accepted_ids.add(stand_id)
        
        # Report normalization if it happened
        if normalized:
            issues.append(DataIssue(
                source_file="stands.csv",
                row_number=row_num,
                record_id=stand_id,
                code=IssueCode.VALUE_NORMALISED,
                action=IssueAction.FIXED,
                field=None,
                original_value=f"{stand_id_raw} / {type_raw} / {size_raw}",
                message=f"Values normalised to '{stand_id}' / '{type_str}' / '{size_str}'."
            ))
    
    return ValidationResult(
        valid=valid_stands,
        issues=issues,
        rows_read=len(rows)
    )
