# API Contract: Airport Stand Allocation

> Framework: FastAPI. Base URL (local): `http://127.0.0.1:8000`. Interactive docs: `/docs` (auto-generated; the contract below is the source of truth).
> All endpoints are **read-only `GET`**, return `application/json`, and are served from one in-memory result computed at startup.
> Sample numbers are consistent with the planned sample data (49 valid flights, 11 stands, 15-minute buffer) but are illustrative; real values come from the generated CSVs.

---

## 0. Conventions

| Topic | Rule |
|---|---|
| Timestamps | ISO 8601 UTC with `Z` and whole seconds, e.g. `2027-01-15T06:05:00Z` (type `string`, format `date-time`) |
| Field naming | `snake_case` |
| Ordering | Lists are sorted deterministically (stated per endpoint) |
| Nullability | Fields that do not apply are `null`, never omitted (stable shape) |
| Enums | Upper-case strings (`PLB`, `REMOTE`, `ASSIGNED`, …) |
| Ratios | Floats in `[0, 1]`, rounded to 4 decimals |
| Pagination / filters | None (data is small; avoids complexity) |
| Auth | None |
| CORS | Not configured (no frontend yet) |

### 0.1 Shared enums

| Enum | Values |
|---|---|
| `aircraft_size`, `max_size` | `S`, `M`, `L` |
| `stand_type` | `PLB`, `REMOTE` |
| `status` | `ASSIGNED`, `UNASSIGNED` |
| `unassigned_reason_code` | `NO_COMPATIBLE_STAND`, `NO_STAND_AVAILABLE` |
| `issue.action` | `DROPPED`, `FIXED` |
| `issue.issue_code` (flights) | `MALFORMED_ROW`, `MISSING_VALUE`, `INVALID_AIRCRAFT_SIZE`, `MALFORMED_TIMESTAMP`, `DEPARTURE_NOT_AFTER_ARRIVAL`, `OUTSIDE_PLANNING_WINDOW`, `DUPLICATE_FLIGHT_ID`, `VALUE_NORMALISED` |
| `issue.issue_code` (stands) | `MALFORMED_ROW`, `MISSING_VALUE`, `INVALID_STAND_TYPE`, `INVALID_STAND_SIZE`, `DUPLICATE_STAND_ID`, `VALUE_NORMALISED` |
| `issue.source_file` | `flights.csv`, `stands.csv` |

### 0.2 Standard error body (all non-2xx responses)

```json
{
  "error": {
    "code": "STAND_NOT_FOUND",
    "message": "Stand 'X99' does not exist."
  }
}
```

| Field | Type | Description |
|---|---|---|
| `error.code` | string | Stable machine-readable code |
| `error.message` | string | Human-readable explanation (never a stack trace) |

Implementation note: register exception handlers so that `HTTPException`, validation errors and unexpected exceptions all produce this shape (FastAPI's default is `{"detail": ...}`, which we override for consistency).

### 0.3 Status codes common to every endpoint

| Code | When | `error.code` |
|---|---|---|
| `200 OK` | Success | n/a |
| `404 Not Found` | Unknown path or unknown resource | `NOT_FOUND` (unknown path) / `STAND_NOT_FOUND` |
| `405 Method Not Allowed` | Non-GET method used | `METHOD_NOT_ALLOWED` |
| `500 Internal Server Error` | Unexpected failure (logged server-side) | `INTERNAL_ERROR` |

Note: data-file problems (missing CSV, bad header) make the app **fail at startup**, not return errors at request time (see `technical-decisions.md` §12). Therefore no `503` is defined.

---

## 1. `GET /allocations`

Returns **every valid flight** with its stand, or `UNASSIGNED` with a reason. Invalid/dropped flights are **not** listed here; see `/data-issues`.

### Request

No parameters.

### Response `200`

| Field | Type | Description |
|---|---|---|
| `planning_window.start` | string (date-time) | Window start (UTC) |
| `planning_window.end` | string (date-time) | Window end (UTC), exclusive |
| `turnaround_buffer_minutes` | integer | Buffer used for this allocation |
| `total_flights` | integer | Number of allocations returned (= valid flights) |
| `assigned_count` | integer | Flights with a stand |
| `unassigned_count` | integer | Flights without a stand |
| `allocations` | array | Sorted by `arrival_time`, then `departure_time`, then `flight_id` |

**Allocation item**

| Field | Type | Nullable | Description |
|---|---|---|---|
| `flight_id` | string | no | Normalised flight id |
| `aircraft_size` | string | no | `S` \| `M` \| `L` |
| `arrival_time` | string (date-time) | no | UTC |
| `departure_time` | string (date-time) | no | UTC |
| `status` | string | no | `ASSIGNED` \| `UNASSIGNED` |
| `stand_id` | string | yes | Set iff `ASSIGNED` |
| `stand_type` | string | yes | `PLB` \| `REMOTE`; set iff `ASSIGNED` |
| `unassigned_reason_code` | string | yes | Set iff `UNASSIGNED` |
| `unassigned_reason` | string | yes | Human-readable reason; set iff `UNASSIGNED` |

Invariant: `status == "ASSIGNED"` ⇔ `stand_id != null` ⇔ `unassigned_reason_code == null`.

### Sample

```json
{
  "planning_window": {
    "start": "2027-01-15T06:00:00Z",
    "end": "2027-01-15T12:00:00Z"
  },
  "turnaround_buffer_minutes": 15,
  "total_flights": 49,
  "assigned_count": 44,
  "unassigned_count": 5,
  "allocations": [
    {
      "flight_id": "AX798",
      "aircraft_size": "M",
      "arrival_time": "2027-01-15T06:05:00Z",
      "departure_time": "2027-01-15T07:30:00Z",
      "status": "ASSIGNED",
      "stand_id": "C03",
      "stand_type": "PLB",
      "unassigned_reason_code": null,
      "unassigned_reason": null
    },
    {
      "flight_id": "BQ891",
      "aircraft_size": "L",
      "arrival_time": "2027-01-15T06:20:00Z",
      "departure_time": "2027-01-15T08:45:00Z",
      "status": "ASSIGNED",
      "stand_id": "C01",
      "stand_type": "PLB",
      "unassigned_reason_code": null,
      "unassigned_reason": null
    },
    {
      "flight_id": "NP610",
      "aircraft_size": "L",
      "arrival_time": "2027-01-15T08:40:00Z",
      "departure_time": "2027-01-15T11:00:00Z",
      "status": "UNASSIGNED",
      "stand_id": null,
      "stand_type": null,
      "unassigned_reason_code": "NO_STAND_AVAILABLE",
      "unassigned_reason": "All 4 stands that can take size L are occupied or within the 15-minute turnaround buffer at 2027-01-15T08:40:00Z."
    }
  ]
}
```

(The real response lists all 49 items; shortened here.)

### Errors

Only the common errors in §0.3. There is no input to validate.

---

## 2. `GET /stands/{stand_id}`

Returns one stand and the flights assigned to it, **in time order** (by `arrival_time`).

### Request

| Param | In | Type | Description |
|---|---|---|---|
| `stand_id` | path | string | Stand id, e.g. `C01`. Matching is **case-insensitive** and trims whitespace (ids are stored upper-case). Only stands that survived validation exist |

### Response `200`

| Field | Type | Description |
|---|---|---|
| `stand_id` | string | |
| `stand_type` | string | `PLB` \| `REMOTE` |
| `max_size` | string | `S` \| `M` \| `L` |
| `flight_count` | integer | Number of flights on this stand (0 allowed) |
| `flights` | array | Sorted by `arrival_time`; empty array if none |

**Flight item**

| Field | Type | Description |
|---|---|---|
| `flight_id` | string | |
| `aircraft_size` | string | |
| `arrival_time` | string (date-time) | |
| `departure_time` | string (date-time) | |
| `gap_before_minutes` | integer \| null | Minutes between the previous flight's departure and this arrival on this stand; `null` for the first flight. Always ≥ the buffer (lets a reader *see* rule H3 hold) |

### Sample: `GET /stands/C01`

```json
{
  "stand_id": "C01",
  "stand_type": "PLB",
  "max_size": "L",
  "flight_count": 3,
  "flights": [
    {
      "flight_id": "BQ891",
      "aircraft_size": "L",
      "arrival_time": "2027-01-15T06:20:00Z",
      "departure_time": "2027-01-15T08:45:00Z",
      "gap_before_minutes": null
    },
    {
      "flight_id": "KL204",
      "aircraft_size": "M",
      "arrival_time": "2027-01-15T09:00:00Z",
      "departure_time": "2027-01-15T10:15:00Z",
      "gap_before_minutes": 15
    },
    {
      "flight_id": "FR551",
      "aircraft_size": "S",
      "arrival_time": "2027-01-15T10:40:00Z",
      "departure_time": "2027-01-15T11:30:00Z",
      "gap_before_minutes": 25
    }
  ]
}
```

### Sample: stand with no flights, `GET /stands/R05`

```json
{
  "stand_id": "R05",
  "stand_type": "REMOTE",
  "max_size": "S",
  "flight_count": 0,
  "flights": []
}
```

### Errors

| Status | `error.code` | When | Body |
|---|---|---|---|
| `404` | `STAND_NOT_FOUND` | `stand_id` is not a known (valid) stand | `{"error":{"code":"STAND_NOT_FOUND","message":"Stand 'X99' does not exist."}}` |

There is no `422`: any string is a legal path value.

---

## 3. `GET /metrics`

Returns the planner metrics. **Scope of all allocation metrics:** valid flights with `arrival_time` ∈ [`planning_window.start`, `planning_window.end`). Definitions: `technical-decisions.md` §10.

### Response `200`

| Field | Type | Description |
|---|---|---|
| `planning_window` | object | `start`, `end` as in `/allocations` |
| `turnaround_buffer_minutes` | integer | |
| `scope` | string | Plain-text statement of the flights covered |
| `assignment_summary.total_valid_flights` | integer | |
| `assignment_summary.assigned` | integer | |
| `assignment_summary.unassigned` | integer | |
| `assignment_summary.unassigned_rate` | number | `unassigned / total_valid_flights`, `0.0` if total is 0 |
| `plb_usage.flights_on_plb` | integer | |
| `plb_usage.flights_on_remote` | integer | |
| `plb_usage.plb_rate_of_valid` | number | `flights_on_plb / total_valid_flights` |
| `plb_usage.plb_rate_of_assigned` | number | `flights_on_plb / assigned` (`0.0` if none assigned) |
| `unassigned_breakdown.by_reason` | object | Count per reason code (**both** codes always present, 0 allowed) |
| `unassigned_breakdown.by_aircraft_size` | object | Count per `S`/`M`/`L` (all three always present) |
| `stand_utilisation.window_minutes` | integer | Window length (360) |
| `stand_utilisation.by_type` | object | Mean utilisation for `PLB` and `REMOTE` (`0.0` if no stands of that type) |
| `stand_utilisation.by_stand` | array | One item per stand, sorted by `stand_id` |
| `stand_utilisation.by_stand[].stand_id` | string | |
| `stand_utilisation.by_stand[].stand_type` | string | |
| `stand_utilisation.by_stand[].flight_count` | integer | |
| `stand_utilisation.by_stand[].occupied_minutes` | integer | Ground minutes inside the window (clipped at window end; buffer not counted) |
| `stand_utilisation.by_stand[].utilisation` | number | `occupied_minutes / window_minutes` |
| `peak_concurrency.aircraft_on_ground` | integer | Max simultaneous valid aircraft (assigned or not) |
| `peak_concurrency.first_occurred_at` | string (date-time) \| null | First moment the peak is reached; `null` if no flights |
| `peak_concurrency.stand_count` | integer | Number of valid stands (compare with the peak) |
| `data_quality.flights` / `.stands` | object | `rows_read`, `valid`, `dropped`, `fixed` |

### Sample

```json
{
  "planning_window": {
    "start": "2027-01-15T06:00:00Z",
    "end": "2027-01-15T12:00:00Z"
  },
  "turnaround_buffer_minutes": 15,
  "scope": "All valid flights arriving in [2027-01-15T06:00:00Z, 2027-01-15T12:00:00Z).",
  "assignment_summary": {
    "total_valid_flights": 49,
    "assigned": 44,
    "unassigned": 5,
    "unassigned_rate": 0.102
  },
  "plb_usage": {
    "flights_on_plb": 27,
    "flights_on_remote": 17,
    "plb_rate_of_valid": 0.551,
    "plb_rate_of_assigned": 0.6136
  },
  "unassigned_breakdown": {
    "by_reason": {
      "NO_COMPATIBLE_STAND": 0,
      "NO_STAND_AVAILABLE": 5
    },
    "by_aircraft_size": { "S": 0, "M": 2, "L": 3 }
  },
  "stand_utilisation": {
    "window_minutes": 360,
    "by_type": { "PLB": 0.78, "REMOTE": 0.52 },
    "by_stand": [
      {
        "stand_id": "C01",
        "stand_type": "PLB",
        "flight_count": 3,
        "occupied_minutes": 290,
        "utilisation": 0.8056
      },
      {
        "stand_id": "R05",
        "stand_type": "REMOTE",
        "flight_count": 0,
        "occupied_minutes": 0,
        "utilisation": 0.0
      }
    ]
  },
  "peak_concurrency": {
    "aircraft_on_ground": 14,
    "first_occurred_at": "2027-01-15T08:55:00Z",
    "stand_count": 11
  },
  "data_quality": {
    "flights": { "rows_read": 56, "valid": 49, "dropped": 7, "fixed": 1 },
    "stands": { "rows_read": 11, "valid": 11, "dropped": 0, "fixed": 0 }
  }
}
```

(`by_stand` shows 2 of 11 items; ratios shown trimmed of trailing zeros. JSON numbers are the same values rounded to 4 decimals.)

### Reconciliation rules (tested)

- `assigned + unassigned = total_valid_flights`
- `flights_on_plb + flights_on_remote = assigned`
- sum of `unassigned_breakdown.by_reason` = sum of `by_aircraft_size` = `unassigned`
- every `utilisation` ∈ [0, 1]
- `data_quality.flights.rows_read = valid + dropped`

### Errors

Only the common errors in §0.3.

---

## 4. `GET /data-issues`

Returns every row that was **dropped or changed** during loading. Nothing is skipped silently: `rows_read = valid + dropped` for each file.

### Response `200`

| Field | Type | Description |
|---|---|---|
| `summary.total_issues` | integer | Length of `issues` |
| `summary.flights` / `summary.stands` | object | `rows_read`, `valid`, `dropped`, `fixed` |
| `summary.by_issue_code` | object | Count per issue code that occurs (only codes with count > 0) |
| `issues` | array | Sorted by `source_file` (`flights.csv` first), then `row_number` |

**Issue item**

| Field | Type | Nullable | Description |
|---|---|---|---|
| `source_file` | string | no | `flights.csv` \| `stands.csv` |
| `row_number` | integer | no | Line number in the file (header is line 1, first data row is line 2) |
| `record_id` | string | yes | `flight_id` / `stand_id` if it could be read |
| `issue_code` | string | no | See §0.1 |
| `action` | string | no | `DROPPED` \| `FIXED` |
| `field` | string | yes | Column concerned, e.g. `departure_time`; `null` for whole-row issues |
| `original_value` | string | yes | Raw text found in the file (`null` if the cell was empty/missing) |
| `message` | string | no | Planner-readable reason and, for `FIXED`, what it was changed to |

### Sample

```json
{
  "summary": {
    "total_issues": 8,
    "flights": { "rows_read": 56, "valid": 49, "dropped": 7, "fixed": 1 },
    "stands": { "rows_read": 11, "valid": 11, "dropped": 0, "fixed": 0 },
    "by_issue_code": {
      "DEPARTURE_NOT_AFTER_ARRIVAL": 1,
      "DUPLICATE_FLIGHT_ID": 1,
      "INVALID_AIRCRAFT_SIZE": 1,
      "MALFORMED_TIMESTAMP": 1,
      "MISSING_VALUE": 2,
      "OUTSIDE_PLANNING_WINDOW": 1,
      "VALUE_NORMALISED": 1
    }
  },
  "issues": [
    {
      "source_file": "flights.csv",
      "row_number": 12,
      "record_id": "CZ411",
      "issue_code": "DEPARTURE_NOT_AFTER_ARRIVAL",
      "action": "DROPPED",
      "field": "departure_time",
      "original_value": "2027-01-15T08:50:00Z",
      "message": "Departure 08:50Z is not after arrival 09:20Z."
    },
    {
      "source_file": "flights.csv",
      "row_number": 23,
      "record_id": "DL902",
      "issue_code": "INVALID_AIRCRAFT_SIZE",
      "action": "DROPPED",
      "field": "aircraft_size",
      "original_value": "XL",
      "message": "Aircraft size 'XL' is not supported (allowed: S, M, L)."
    },
    {
      "source_file": "flights.csv",
      "row_number": 31,
      "record_id": "EV318",
      "issue_code": "MISSING_VALUE",
      "action": "DROPPED",
      "field": "departure_time",
      "original_value": null,
      "message": "Departure time is missing."
    },
    {
      "source_file": "flights.csv",
      "row_number": 44,
      "record_id": "AX500",
      "issue_code": "VALUE_NORMALISED",
      "action": "FIXED",
      "field": "aircraft_size",
      "original_value": " m ",
      "message": "Aircraft size ' m ' normalised to 'M'; flight_id ' ax500 ' normalised to 'AX500'."
    }
  ]
}
```

(`summary` counts all 8 issues; `issues` shows 4 of 8 here. Row numbers are illustrative.)

Note: the `summary` above shows `MISSING_VALUE: 2` (missing departure + blank flight id), which is why `by_issue_code` totals 8.

### Errors

Only the common errors in §0.3.

---

## 5. Endpoint summary

| Method | Path | 200 body | Specific errors |
|---|---|---|---|
| GET | `/allocations` | `AllocationsResponse` | none |
| GET | `/stands/{stand_id}` | `StandScheduleResponse` | `404 STAND_NOT_FOUND` |
| GET | `/metrics` | `MetricsResponse` | none |
| GET | `/data-issues` | `DataIssuesResponse` | none |

### 5.1 Schemas (`schemas.py`, names only)

`PlanningWindow`, `AllocationItem`, `AllocationsResponse`, `StandFlightItem`, `StandScheduleResponse`, `MetricsResponse` (with nested models), `IssueItem`, `DataIssuesResponse`, `ErrorBody`, `ErrorResponse`.

**Why pydantic response models:** the contract is enforced in code (wrong field → test fails), `/docs` documents it automatically, and the domain dataclasses stay independent of the web layer.

### 5.2 Design notes

- **Why a stable shape with `null`s:** consumers (and tests) never have to check for missing keys.
- **Why `gap_before_minutes` on `/stands/{id}`:** it makes the 15-minute rule visible per stand, which is useful to a planner and to an interviewer.
- **Why no filters/pagination:** the data is tens of rows; extra query parameters add code and tests without value for this task.
- **Why `/allocations` excludes invalid flights:** an invalid flight has no trustworthy times or size, so listing it would imply a decision was made on it. It is reported in `/data-issues` instead (assumption A8).
