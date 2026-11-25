"""FastAPI application — 4 read-only endpoints served from one startup result."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ConfigError, Settings
from .loader import DataFileError
from .models import AllocationStatus, IssueAction, PipelineResult
from .schemas import (
    AllocationItem, AllocationsResponse,
    DataIssuesResponse, IssueItem, IssueSummary, IssueSummaryFile,
    MetricsResponse, PlanningWindow,
    StandFlightItem, StandScheduleResponse,
)
from .service import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings = Settings.from_env()
        logger.info("Running allocation pipeline…")
        app.state.result = run_pipeline(settings)
        logger.info("Ready")
        yield
    except (DataFileError, ConfigError) as e:
        logger.error("Startup failed: %s", e)
        raise
    finally:
        logger.info("Shutdown")


app = FastAPI(title="Airport Stand Allocation", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

_static = Path(__file__).parent.parent / "static"
if _static.exists():
    app.mount("/ui", StaticFiles(directory=str(_static), html=True), name="ui")


# --- error handlers ---

@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.detail, "message": str(exc.detail)}},
    )


@app.exception_handler(Exception)
async def _unexpected_error(request: Request, exc: Exception):
    logger.exception("Unexpected error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An internal error occurred."}},
    )


# --- helpers ---

def _result() -> PipelineResult:
    return app.state.result


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- endpoints ---

@app.get("/allocations", response_model=AllocationsResponse)
def get_allocations():
    result = _result()

    sorted_allocs = sorted(
        result.allocations,
        key=lambda a: (a.flight.arrival_time, a.flight.departure_time, a.flight.flight_id),
    )

    items = []
    for alloc in sorted_allocs:
        f = alloc.flight
        if alloc.stand:
            items.append(AllocationItem(
                flight_id=f.flight_id, aircraft_size=f.aircraft_size.name,
                arrival_time=_fmt(f.arrival_time), departure_time=_fmt(f.departure_time),
                status=AllocationStatus.ASSIGNED.value,
                stand_id=alloc.stand.stand_id, stand_type=alloc.stand.stand_type.value,
                unassigned_reason_code=None, unassigned_reason=None,
            ))
        else:
            items.append(AllocationItem(
                flight_id=f.flight_id, aircraft_size=f.aircraft_size.name,
                arrival_time=_fmt(f.arrival_time), departure_time=_fmt(f.departure_time),
                status=AllocationStatus.UNASSIGNED.value,
                stand_id=None, stand_type=None,
                unassigned_reason_code=alloc.reason.value if alloc.reason else None,
                unassigned_reason=alloc.message,
            ))

    assigned_n = sum(1 for a in result.allocations if a.stand)
    return AllocationsResponse(
        planning_window=PlanningWindow(
            start=result.settings["planning_window_start"],
            end=result.settings["planning_window_end"],
        ),
        turnaround_buffer_minutes=result.settings["turnaround_buffer_minutes"],
        total_flights=len(result.allocations),
        assigned_count=assigned_n,
        unassigned_count=len(result.allocations) - assigned_n,
        allocations=items,
    )


@app.get("/stands/{stand_id}", response_model=StandScheduleResponse)
def get_stand_schedule(stand_id: str):
    result = _result()
    nid = stand_id.strip().upper()

    stand = next((s for s in result.stands if s.stand_id == nid), None)
    if stand is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="STAND_NOT_FOUND")

    stand_allocs = sorted(
        [a for a in result.allocations if a.stand and a.stand.stand_id == nid],
        key=lambda a: a.flight.arrival_time,
    )

    flights = []
    prev_dep = None
    for alloc in stand_allocs:
        f = alloc.flight
        gap = int((f.arrival_time - prev_dep).total_seconds() / 60) if prev_dep else None
        flights.append(StandFlightItem(
            flight_id=f.flight_id, aircraft_size=f.aircraft_size.name,
            arrival_time=_fmt(f.arrival_time), departure_time=_fmt(f.departure_time),
            gap_before_minutes=gap,
        ))
        prev_dep = f.departure_time

    return StandScheduleResponse(
        stand_id=stand.stand_id, stand_type=stand.stand_type.value,
        max_size=stand.max_size.name, flight_count=len(flights), flights=flights,
    )


@app.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    return _result().metrics


@app.get("/data-issues", response_model=DataIssuesResponse)
def get_data_issues():
    result = _result()

    sorted_issues = sorted(
        result.issues,
        key=lambda i: (0 if i.source_file == "flights.csv" else 1, i.row_number),
    )

    items = [
        IssueItem(
            source_file=i.source_file, row_number=i.row_number, record_id=i.record_id,
            issue_code=i.code.value, action=i.action.value, field=i.field,
            original_value=i.original_value, message=i.message,
        )
        for i in sorted_issues
    ]

    fi = [i for i in result.issues if i.source_file == "flights.csv"]
    si = [i for i in result.issues if i.source_file == "stands.csv"]

    def _counts(issues, valid):
        return IssueSummaryFile(
            rows_read=valid + sum(1 for i in issues if i.action == IssueAction.DROPPED),
            valid=valid,
            dropped=sum(1 for i in issues if i.action == IssueAction.DROPPED),
            fixed=sum(1 for i in issues if i.action == IssueAction.FIXED),
        )

    by_code: dict[str, int] = {}
    for i in result.issues:
        by_code[i.code.value] = by_code.get(i.code.value, 0) + 1

    return DataIssuesResponse(
        summary=IssueSummary(
            total_issues=len(result.issues),
            flights=_counts(fi, len(result.flights)),
            stands=_counts(si, len(result.stands)),
            by_issue_code=by_code,
        ),
        issues=items,
    )
