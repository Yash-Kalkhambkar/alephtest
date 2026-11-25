"""Verify the generated sample data."""

from datetime import timedelta
from stand_allocation.config import Settings
from stand_allocation.service import run_pipeline
from stand_allocation.allocation import find_violations

settings = Settings.from_env()
result = run_pipeline(settings)

violations = find_violations(
    result.allocations,
    result.stands,
    timedelta(minutes=settings.turnaround_buffer_minutes)
)

dropped = [i for i in result.issues if i.action.value == "DROPPED"]
fixed = [i for i in result.issues if i.action.value == "FIXED"]
assigned = sum(1 for a in result.allocations if a.stand)
unassigned = sum(1 for a in result.allocations if not a.stand)

print("=" * 60)
print("SAMPLE DATA VERIFICATION")
print("=" * 60)
print(f"Hard rules violations: {len(violations)}")
print(f"Valid flights: {len(result.flights)}")
print(f"Assigned: {assigned}")
print(f"Unassigned: {unassigned}")
print(f"Total issues: {len(result.issues)}")
print(f"  - Dropped: {len(dropped)}")
print(f"  - Fixed: {len(fixed)}")
print()

if len(dropped) >= 5:
    print(f"✓ Requirement met: ≥5 dropped rows ({len(dropped)} found)")
    unique_codes = len(set(i.code.value for i in dropped))
    print(f"  Unique dropped codes: {unique_codes}")
    for code in set(i.code.value for i in dropped):
        count = sum(1 for i in dropped if i.code.value == code)
        print(f"    - {code}: {count}")
else:
    print(f"✗ Requirement NOT met: Need ≥5 dropped rows, only {len(dropped)}")

print()
if unassigned > 0:
    print(f"✓ At least one unassigned flight ({unassigned} found)")
else:
    print("✗ No unassigned flights (PLB not scarce enough)")

print()
if len(violations) == 0:
    print("✓ All hard rules hold")
else:
    print(f"✗ {len(violations)} hard rule violations:")
    for v in violations:
        print(f"  - {v}")
