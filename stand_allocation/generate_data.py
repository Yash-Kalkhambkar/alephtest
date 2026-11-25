"""Generate sample CSV data for testing."""

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def generate_sample_data(
    output_dir: Path,
    planning_date: str,
    seed: int,
    valid_flight_count: int
):
    """
    Generate stands.csv and flights.csv with seeded random data.
    
    Args:
        output_dir: Directory to write CSV files
        planning_date: ISO date string (YYYY-MM-DD)
        seed: Random seed for reproducibility
        valid_flight_count: Number of clean valid flights to generate
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    random.seed(seed)
    
    # Parse planning date
    date_obj = datetime.fromisoformat(planning_date).date()
    window_start = datetime(date_obj.year, date_obj.month, date_obj.day, 6, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(date_obj.year, date_obj.month, date_obj.day, 12, 0, 0, tzinfo=timezone.utc)
    
    # Generate stands
    stands_data = [
        ("C01", "PLB", "L"),
        ("C02", "PLB", "L"),
        ("C03", "PLB", "M"),
        ("C04", "PLB", "M"),
        ("C05", "PLB", "M"),
        ("C06", "PLB", "S"),
        ("R01", "REMOTE", "L"),
        ("R02", "REMOTE", "L"),
        ("R03", "REMOTE", "M"),
        ("R04", "REMOTE", "M"),
        ("R05", "REMOTE", "S"),
    ]
    
    stands_file = output_dir / "stands.csv"
    with open(stands_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["stand_id", "stand_type", "max_size"])
        for stand in stands_data:
            writer.writerow(stand)
    
    # Generate flights
    flights = []
    
    # Size distribution: 30% S, 50% M, 20% L
    sizes = ["S"] * 15 + ["M"] * 24 + ["L"] * 10
    random.shuffle(sizes)
    sizes = sizes[:valid_flight_count]
    
    # Ground time by size (minutes)
    ground_time_ranges = {
        "S": (30, 60),
        "M": (45, 90),
        "L": (75, 150)
    }
    
    # Generate arrival times
    # 40% in peak window 08:00-09:30, 60% spread uniformly
    arrival_times = []
    
    peak_start = window_start + timedelta(hours=2)  # 08:00
    peak_end = window_start + timedelta(hours=3, minutes=30)  # 09:30
    
    peak_count = int(valid_flight_count * 0.4)
    uniform_count = valid_flight_count - peak_count
    
    # Peak arrivals
    for _ in range(peak_count):
        offset_minutes = random.randint(0, 90)  # 90 minutes in peak window
        arrival = peak_start + timedelta(minutes=offset_minutes)
        arrival_times.append(arrival)
    
    # Uniform arrivals
    for _ in range(uniform_count):
        offset_minutes = random.randint(0, 360)  # 6 hours = 360 minutes
        arrival = window_start + timedelta(minutes=offset_minutes)
        # Snap to 5-minute intervals
        arrival = arrival.replace(second=0, microsecond=0)
        minutes = arrival.minute
        arrival = arrival.replace(minute=(minutes // 5) * 5)
        arrival_times.append(arrival)
    
    # Sort arrival times
    arrival_times.sort()
    
    # Build valid flights
    for i, (arrival, size) in enumerate(zip(arrival_times, sizes)):
        flight_id = f"FL{100 + i:03d}"
        
        # Ground time
        min_ground, max_ground = ground_time_ranges[size]
        ground_minutes = random.randrange(min_ground, max_ground + 1, 5)
        departure = arrival + timedelta(minutes=ground_minutes)
        
        flights.append({
            "flight_id": flight_id,
            "aircraft_size": size,
            "arrival_time": arrival.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "departure_time": departure.strftime("%Y-%m-%dT%H:%M:%SZ")
        })
    
    # Add normalisable row (will be FIXED)
    flights.append({
        "flight_id": " ax500 ",  # Will normalize to AX500
        "aircraft_size": " m ",  # Will normalize to M
        "arrival_time": (window_start + timedelta(hours=1, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departure_time": (window_start + timedelta(hours=2, minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    
    # Add bad rows (from PDF and additional)
    
    # 1. Departure before arrival (PDF CZ411)
    flights.append({
        "flight_id": "CZ411",
        "aircraft_size": "L",
        "arrival_time": (window_start + timedelta(hours=3, minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departure_time": (window_start + timedelta(hours=2, minutes=50)).strftime("%Y-%m-%dT%H:%M:%SZ")  # Before arrival
    })
    
    # 2. Invalid aircraft size (PDF DL902)
    flights.append({
        "flight_id": "DL902",
        "aircraft_size": "XL",  # Invalid
        "arrival_time": (window_start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departure_time": (window_start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    
    # 3. Missing departure time (PDF EV318)
    flights.append({
        "flight_id": "EV318",
        "aircraft_size": "M",
        "arrival_time": (window_start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departure_time": ""  # Missing
    })
    
    # 4. Malformed timestamp
    flights.append({
        "flight_id": "BA999",
        "aircraft_size": "S",
        "arrival_time": "15/01/2027 7pm",  # Wrong format
        "departure_time": (window_start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    
    # 5. Duplicate flight ID
    flights.append({
        "flight_id": "FL100",  # Duplicate of first flight
        "aircraft_size": "M",
        "arrival_time": (window_start + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departure_time": (window_start + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    
    # 6. Arrival outside window (before start)
    flights.append({
        "flight_id": "EA111",
        "aircraft_size": "L",
        "arrival_time": (window_start - timedelta(minutes=50)).strftime("%Y-%m-%dT%H:%M:%SZ"),  # 05:10
        "departure_time": (window_start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    
    # 7. Missing flight_id
    flights.append({
        "flight_id": "",  # Blank
        "aircraft_size": "S",
        "arrival_time": (window_start + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departure_time": (window_start + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    
    # Write flights
    flights_file = output_dir / "flights.csv"
    with open(flights_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["flight_id", "aircraft_size", "arrival_time", "departure_time"])
        writer.writeheader()
        for flight in flights:
            writer.writerow(flight)
    
    print(f"Generated {len(stands_data)} stands in {stands_file}")
    print(f"Generated {len(flights)} flight rows ({valid_flight_count} clean + 1 normalisable + 7 bad) in {flights_file}")


def main():
    """CLI entry point."""
    from .config import PLANNING_DATE, RANDOM_SEED, GENERATED_VALID_FLIGHTS, DEFAULT_DATA_DIR
    from pathlib import Path
    
    output_dir = Path(DEFAULT_DATA_DIR)
    
    generate_sample_data(
        output_dir=output_dir,
        planning_date=PLANNING_DATE,
        seed=RANDOM_SEED,
        valid_flight_count=GENERATED_VALID_FLIGHTS
    )


if __name__ == "__main__":
    main()
