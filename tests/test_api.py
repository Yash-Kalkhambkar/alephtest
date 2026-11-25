"""API integration tests."""

import pytest
from fastapi.testclient import TestClient


def test_allocations_endpoint_structure(tmp_path):
    """API-01: /allocations returns expected structure."""
    from tests.conftest import write_csvs, settings_for
    from stand_allocation.service import run_pipeline
    from stand_allocation.api import app
    
    # Create minimal test data
    stands_csv = """stand_id,stand_type,max_size
C01,PLB,L
R01,REMOTE,S"""
    
    flights_csv = """flight_id,aircraft_size,arrival_time,departure_time
FL100,M,2027-01-15T08:00:00Z,2027-01-15T09:00:00Z
FL101,S,2027-01-15T08:30:00Z,2027-01-15T09:30:00Z"""
    
    write_csvs(tmp_path, stands_csv, flights_csv)
    settings = settings_for(tmp_path)
    
    # Run pipeline and set on app
    result = run_pipeline(settings)
    app.state.result = result
    
    client = TestClient(app)
    response = client.get("/allocations")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check structure
    assert "planning_window" in data
    assert "turnaround_buffer_minutes" in data
    assert "total_flights" in data
    assert "assigned_count" in data
    assert "unassigned_count" in data
    assert "allocations" in data
    
    assert data["total_flights"] == 2
    assert data["assigned_count"] + data["unassigned_count"] == 2


def test_allocations_ordering(tmp_path):
    """API-04: Allocations sorted by arrival, departure, id."""
    from tests.conftest import write_csvs, settings_for
    from stand_allocation.service import run_pipeline
    from stand_allocation.api import app
    
    stands_csv = """stand_id,stand_type,max_size
C01,PLB,L"""
    
    # Out of order
    flights_csv = """flight_id,aircraft_size,arrival_time,departure_time
FL102,M,2027-01-15T09:00:00Z,2027-01-15T10:00:00Z
FL100,M,2027-01-15T08:00:00Z,2027-01-15T09:00:00Z
FL101,M,2027-01-15T08:00:00Z,2027-01-15T08:30:00Z"""
    
    write_csvs(tmp_path, stands_csv, flights_csv)
    settings = settings_for(tmp_path)
    
    result = run_pipeline(settings)
    app.state.result = result
    
    client = TestClient(app)
    response = client.get("/allocations")
    data = response.json()
    
    ids = [a["flight_id"] for a in data["allocations"]]
    # Should be sorted by arrival (08:00, 08:00, 09:00), then departure (08:30, 09:00), then id
    assert ids == ["FL101", "FL100", "FL102"]


def test_stands_endpoint(tmp_path):
    """API-08: /stands/{id} returns stand details."""
    from tests.conftest import write_csvs, settings_for
    from stand_allocation.service import run_pipeline
    from stand_allocation.api import app
    
    stands_csv = """stand_id,stand_type,max_size
C01,PLB,M"""
    
    flights_csv = """flight_id,aircraft_size,arrival_time,departure_time
FL100,M,2027-01-15T08:00:00Z,2027-01-15T09:00:00Z
FL101,M,2027-01-15T09:20:00Z,2027-01-15T10:00:00Z"""
    
    write_csvs(tmp_path, stands_csv, flights_csv)
    settings = settings_for(tmp_path, buffer_minutes=15)
    
    result = run_pipeline(settings)
    app.state.result = result
    
    client = TestClient(app)
    response = client.get("/stands/C01")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["stand_id"] == "C01"
    assert data["stand_type"] == "PLB"
    assert data["max_size"] == "M"
    assert data["flight_count"] == 2
    assert len(data["flights"]) == 2
    
    # Check gap_before
    assert data["flights"][0]["gap_before_minutes"] is None  # First flight
    assert data["flights"][1]["gap_before_minutes"] == 20  # 09:20 - 09:00 = 20


def test_stand_not_found(tmp_path):
    """API-13: Unknown stand returns 404."""
    from tests.conftest import write_csvs, settings_for
    from stand_allocation.service import run_pipeline
    from stand_allocation.api import app
    
    stands_csv = """stand_id,stand_type,max_size
C01,PLB,M"""
    
    flights_csv = """flight_id,aircraft_size,arrival_time,departure_time
FL100,M,2027-01-15T08:00:00Z,2027-01-15T09:00:00Z"""
    
    write_csvs(tmp_path, stands_csv, flights_csv)
    settings = settings_for(tmp_path)
    
    result = run_pipeline(settings)
    app.state.result = result
    
    client = TestClient(app)
    response = client.get("/stands/X99")
    
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "STAND_NOT_FOUND" in data["error"]["code"]


def test_metrics_endpoint(tmp_path):
    """API-15: /metrics returns all metrics."""
    from tests.conftest import write_csvs, settings_for
    from stand_allocation.service import run_pipeline
    from stand_allocation.api import app
    
    stands_csv = """stand_id,stand_type,max_size
C01,PLB,L"""
    
    flights_csv = """flight_id,aircraft_size,arrival_time,departure_time
FL100,M,2027-01-15T08:00:00Z,2027-01-15T09:00:00Z"""
    
    write_csvs(tmp_path, stands_csv, flights_csv)
    settings = settings_for(tmp_path)
    
    result = run_pipeline(settings)
    app.state.result = result
    
    client = TestClient(app)
    response = client.get("/metrics")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check all top-level keys present
    assert "assignment_summary" in data
    assert "plb_usage" in data
    assert "unassigned_breakdown" in data
    assert "stand_utilisation" in data
    assert "peak_concurrency" in data
    assert "data_quality" in data


def test_data_issues_endpoint(tmp_path):
    """API-19: /data-issues contains all bad rows."""
    from tests.conftest import write_csvs, settings_for
    from stand_allocation.service import run_pipeline
    from stand_allocation.api import app
    
    stands_csv = """stand_id,stand_type,max_size
C01,PLB,L"""
    
    # 1 valid, 1 bad size
    flights_csv = """flight_id,aircraft_size,arrival_time,departure_time
FL100,M,2027-01-15T08:00:00Z,2027-01-15T09:00:00Z
DL902,XL,2027-01-15T08:00:00Z,2027-01-15T09:00:00Z"""
    
    write_csvs(tmp_path, stands_csv, flights_csv)
    settings = settings_for(tmp_path)
    
    result = run_pipeline(settings)
    app.state.result = result
    
    client = TestClient(app)
    response = client.get("/data-issues")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["summary"]["total_issues"] == 1
    assert len(data["issues"]) == 1
    
    issue = data["issues"][0]
    assert issue["issue_code"] == "INVALID_AIRCRAFT_SIZE"
    assert issue["action"] == "DROPPED"
    assert issue["record_id"] == "DL902"
