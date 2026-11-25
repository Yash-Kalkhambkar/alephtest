"""Submission readiness check."""
from stand_allocation.config import Settings
from stand_allocation.service import run_pipeline
from stand_allocation.allocation import find_violations
from datetime import timedelta

settings = Settings.from_env()
result = run_pipeline(settings)

violations = find_violations(result.allocations, result.stands, timedelta(minutes=settings.turnaround_buffer_minutes))
dropped = [i for i in result.issues if i.action.value == "DROPPED"]
fixed   = [i for i in result.issues if i.action.value == "FIXED"]
assigned   = sum(1 for a in result.allocations if a.stand)
unassigned = [a for a in result.allocations if not a.stand]
metrics = result.metrics

print("=== SUBMISSION CHECKLIST ===\n")

checks = []

def chk(label, ok, detail=""):
    icon = "✓" if ok else "✗"
    print(f"  {icon}  {label}" + (f"  ({detail})" if detail else ""))
    checks.append(ok)

chk("No hard rule violations", len(violations) == 0, f"{len(violations)} found")
chk("49 valid flights", len(result.flights) == 49, str(len(result.flights)))
chk("At least 1 unassigned flight", len(unassigned) >= 1, str(len(unassigned)))
chk("At least 5 dropped rows", len(dropped) >= 5, str(len(dropped)))
chk("At least 1 fixed row", len(fixed) >= 1, str(len(fixed)))
chk("At least 5 distinct dropped codes", len({i.code for i in dropped}) >= 5,
    str(len({i.code for i in dropped})))
chk("11 stands", len(result.stands) == 11, str(len(result.stands)))
plb    = [s for s in result.stands if s.stand_type.value == "PLB"]
remote = [s for s in result.stands if s.stand_type.value == "REMOTE"]
chk("PLB is scarce (6 PLB < total capacity)", len(plb) == 6, f"{len(plb)} PLB, {len(remote)} REMOTE")

dq = metrics["data_quality"]
f_ok = dq["flights"]["rows_read"] == dq["flights"]["valid"] + dq["flights"]["dropped"]
s_ok = dq["stands"]["rows_read"]  == dq["stands"]["valid"]  + dq["stands"]["dropped"]
chk("rows_read == valid + dropped (flights)", f_ok, str(dq["flights"]))
chk("rows_read == valid + dropped (stands)",  s_ok, str(dq["stands"]))

sm = metrics["assignment_summary"]
chk("assigned + unassigned == total", sm["assigned"] + sm["unassigned"] == sm["total_valid_flights"])
p = metrics["plb_usage"]
chk("plb + remote == assigned", p["flights_on_plb"] + p["flights_on_remote"] == sm["assigned"])

for entry in metrics["stand_utilisation"]["by_stand"]:
    if not (0.0 <= entry["utilisation"] <= 1.0):
        chk("All utilisations in [0,1]", False, entry["stand_id"])
        break
else:
    chk("All utilisations in [0,1]", True)

chk("Buffer in metrics matches config",
    metrics["turnaround_buffer_minutes"] == settings.turnaround_buffer_minutes)

print()
print(f"  Dropped codes:  {sorted(i.code.value for i in dropped)}")
print(f"  Metrics keys:   {list(metrics.keys())}")
print()

passed = sum(checks)
total  = len(checks)
print(f"{'All good — ready to submit!' if passed == total else 'FIX THE FAILURES ABOVE'}")
print(f"{passed}/{total} checks passed")
