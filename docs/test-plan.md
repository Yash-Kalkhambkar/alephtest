# Test Plan: Airport Stand Allocation

> Framework: `pytest` (+ FastAPI `TestClient` via `httpx`). No implementation code here, only what to test and what to expect.
> IDs (`CSV-01`, `BUF-02`, …) can be used as test-function name prefixes, and map to acceptance criteria (`AC-xx`) in `project-brief.md`.

---

## 1. Strategy

### 1.1 What matters most, and why (this goes into README "Tests")

| Priority | Area | Why it matters |
|---|---|---|
| 1 | **Hard rules**: size fit, no overlap, buffer (H1–H3) | The assignment says these "must never be broken". A violation is the worst bug possible |
| 2 | **Data validation**: every bad-row kind is caught *and reported* | "Never silently skip anything" is the second most repeated requirement |
| 3 | **Unassigned handling and reasons** | Every valid flight must end as assigned or unassigned **with a reason** |
| 4 | **Metrics correctness** | Planners "need clear numbers they can trust" |
| 5 | **API contract** | Shape, ordering, status codes, error body |
| 6 | **Determinism and configuration** | Same inputs → same output; buffer is changeable |

Not tested (and why): uvicorn startup, `/docs` page, logging text, performance; low value for this task.

### 1.2 Test levels

| Level | Files | Uses |
|---|---|---|
| Unit | `test_validation_*`, `test_allocation_*`, `test_metrics`, `test_loader`, `test_generate_data` | In-memory objects or `tmp_path` CSVs; no HTTP |
| Property-style invariant | `test_allocation_rules` | Run allocator on the generated sample data and on a batch of small seeded random scenarios; assert `find_violations` is empty |
| Integration | `test_api` | `TestClient` against an app built from a `tmp_path` data folder (small, hand-written CSVs) plus one run on the committed sample data |

### 1.3 Fixtures and helpers (in `conftest.py`; names only)

- `make_flight(flight_id, size, arrival, departure)`: builds a `Flight` from `"HH:MM"` strings on the planning date (UTC).
- `make_stand(stand_id, stand_type, max_size)`.
- `flight_row(**overrides)`: a valid raw CSV row dict, overridable per test (so each validation test changes exactly one thing).
- `write_csvs(tmp_path, stands_text, flights_text)`: writes small CSV files.
- `settings_for(tmp_path, buffer_minutes=15)`: `Settings` pointing at `tmp_path`.
- `client_for(settings)`: `TestClient` over the app built with those settings.

**Why:** tests stay 3–6 lines long and each shows one fact; easy to extend live in the follow-up call.

### 1.4 Conventions

- One behaviour per test; test names read as sentences.
- Times written as `"HH:MM"` helpers so the 15-minute arithmetic is visible.
- Hand-computed expected values (written in comments/test data), **never** recomputed with the same code under test.
- Assert **both** the result and the reported reason/issue where relevant.

---

## 2. CSV loading and validation tests (`test_loader.py`, `test_validation_*`)

| ID | Scenario | Input | Expected |
|---|---|---|---|
| CSV-01 | Happy path flights | 3 valid rows | 3 valid `Flight`s, 0 issues, `rows_read=3` |
| CSV-02 | Happy path stands | 3 valid rows | 3 `Stand`s, 0 issues |
| CSV-03 | Missing file | Non-existent path | `DataFileError` with the path in the message |
| CSV-04 | Missing required column in header (e.g. no `departure_time`) | Header lacks column | `DataFileError` naming the missing column |
| CSV-05 | Empty file (no header) | 0 bytes | `DataFileError` |
| CSV-06 | Header only, no rows | Header line | 0 valid, 0 issues, no crash |
| CSV-07 | Extra unknown column | Extra `notes` column | Ignored; rows still valid |
| CSV-08 | Row with too few columns | `AX1,M,2027-...` | `MALFORMED_ROW`, `DROPPED` |
| CSV-09 | Row with too many columns | 5 fields | `MALFORMED_ROW`, `DROPPED` |
| CSV-10 | UTF-8 BOM at file start | BOM + header | Loads normally (first column named correctly) |
| CSV-11 | Blank line in the middle | Empty line | Skipped; not counted as a record and not a crash |
| CSV-12 | Row numbers are file line numbers | Bad row on 5th data line | `row_number == 6` (header is line 1) |
| CSV-13 | Whitespace/lower-case normalisation | `" ax500 "`, `" m "` | Valid `Flight('AX500', M)` **and** one `FIXED` / `VALUE_NORMALISED` issue naming both fields |
| CSV-14 | A row dropped *and* needing normalisation | Padded row with bad size | Only the `DROPPED` issue (no `FIXED` noise) |
| CSV-15 | Accounting identity | The mixed sample file | `rows_read == valid + dropped` |
| CSV-16 | Missing `flight_id` | Blank id | `MISSING_VALUE`, `field="flight_id"`, `record_id=None` |
| CSV-17 | Missing aircraft size | Blank size | `MISSING_VALUE`, `field="aircraft_size"` |
| CSV-18 | Issue message is human-readable | Any dropped row | `message` non-empty, mentions the offending value |
| CSV-19 | Stand with invalid type (`GATE`) | | `INVALID_STAND_TYPE`, dropped |
| CSV-20 | Stand with invalid size (`XL`) | | `INVALID_STAND_SIZE`, dropped |
| CSV-21 | Duplicate stand id | `C01` twice | 2nd dropped with `DUPLICATE_STAND_ID`; first kept |
| CSV-22 | Missing stand field | Blank `max_size` | `MISSING_VALUE`, dropped |

---

## 3. Missing and malformed timestamp tests (`test_validation_flights.py`)

| ID | Scenario | `arrival_time` / `departure_time` | Expected |
|---|---|---|---|
| TS-01 | Valid with `Z` | `2027-01-15T06:05:00Z` | Parsed; tz-aware UTC (`tzinfo == UTC`, `utcoffset() == 0`) |
| TS-02 | Valid with `+00:00` | `2027-01-15T06:05:00+00:00` | Same instant as TS-01 |
| TS-03 | Non-UTC offset converted | `2027-01-15T08:05:00+02:00` | Parsed as `06:05Z` |
| TS-04 | Naive timestamp | `2027-01-15T06:05:00` | `MALFORMED_TIMESTAMP`; message mentions timezone |
| TS-05 | Wrong format | `15/01/2027 7pm` | `MALFORMED_TIMESTAMP`, `field="arrival_time"`, `original_value` kept |
| TS-06 | Garbage text | `soon` | `MALFORMED_TIMESTAMP` |
| TS-07 | Impossible date | `2027-02-30T06:00:00Z` | `MALFORMED_TIMESTAMP` |
| TS-08 | Impossible time | `2027-01-15T25:00:00Z` | `MALFORMED_TIMESTAMP` |
| TS-09 | Missing arrival | blank | `MISSING_VALUE`, `field="arrival_time"` |
| TS-10 | Missing departure (PDF `EV318`) | blank | `MISSING_VALUE`, `field="departure_time"`, `record_id="EV318"` |
| TS-11 | Whitespace-only timestamp | `"   "` | `MISSING_VALUE` (treated as empty) |
| TS-12 | Malformed *departure* only | arrival valid | `MALFORMED_TIMESTAMP`, `field="departure_time"` |
| TS-13 | Both malformed | | One issue only (first failing field: arrival); row dropped once (A7) |
| TS-14 | Output formatting | any parsed time | Serialised with trailing `Z`, no microseconds |
| TS-15 | Arrival before window start (`05:10Z`) | | `OUTSIDE_PLANNING_WINDOW`, dropped |
| TS-16 | Arrival exactly at window start `06:00Z` | | Valid (inclusive start) |
| TS-17 | Arrival exactly at window end `12:00Z` | | `OUTSIDE_PLANNING_WINDOW` (exclusive end) |
| TS-18 | Arrival `11:59Z`, departure `13:30Z` | | Valid (departure may be after window end, A3) |

---

## 4. Invalid aircraft size tests

| ID | Scenario | Input | Expected |
|---|---|---|---|
| SZ-01 | `S`, `M`, `L` accepted | each | Valid, mapped to `Size.S/M/L` |
| SZ-02 | `XL` (PDF `DL902`) | `XL` | `INVALID_AIRCRAFT_SIZE`, dropped, message lists allowed sizes |
| SZ-03 | Lower-case `m` | `m` | Valid + `FIXED` (see CSV-13) |
| SZ-04 | Unknown text | `HUGE`, `Z`, `1` | `INVALID_AIRCRAFT_SIZE` |
| SZ-05 | Empty | blank | `MISSING_VALUE` (not `INVALID_AIRCRAFT_SIZE`) |
| SZ-06 | **Fit matrix**: all 9 aircraft × stand-max combinations | `can_fit` | ✅ for S→S,M,L; M→M,L; L→L only; ❌ otherwise (truth table in `technical-decisions.md` §8) |
| SZ-07 | Size ordering | `Size.S < Size.M < Size.L` | True |

---

## 5. Duplicate flight ID tests

| ID | Scenario | Expected |
|---|---|---|
| DUP-01 | Same `flight_id`, different data, two rows | First kept; second `DUPLICATE_FLIGHT_ID`, dropped; message names the first row number |
| DUP-02 | Exact duplicate row | Same behaviour as DUP-01 |
| DUP-03 | Duplicate differing only by case/whitespace (`ax798` vs `AX798 `) | Detected after normalisation |
| DUP-04 | Three rows, same id | Rows 2 and 3 each reported; exactly one flight kept |
| DUP-05 | First row invalid (bad size), second row valid with same id | Second **accepted** (compared to accepted ids only); first reported for its own reason |
| DUP-06 | Only one flight appears in `/allocations` per id | The kept one, once |

---

## 6. Departure-before-arrival tests

| ID | Scenario | Arrival → departure | Expected |
|---|---|---|---|
| DEP-01 | Departure before arrival (PDF `CZ411`) | `09:20 → 08:50` | `DEPARTURE_NOT_AFTER_ARRIVAL`, dropped |
| DEP-02 | Departure equals arrival | `09:00 → 09:00` | Dropped (A6) |
| DEP-03 | Departure one minute after arrival | `09:00 → 09:01` | Valid |
| DEP-04 | Message content | `09:20 → 08:50` | Contains both times (e.g. "Departure 08:50Z is not after arrival 09:20Z") |
| DEP-05 | Ordering vs other checks | Bad size **and** dep<arr | Reports the earlier check (`INVALID_AIRCRAFT_SIZE`) only |
| DEP-06 | Dropped flight is absent from allocations | any | Not in allocator input; present in issues |

---

## 7. Stand capacity (size-fit) tests (`test_allocation_rules.py`)

| ID | Scenario | Stands | Flights | Expected |
|---|---|---|---|---|
| CAP-01 | S aircraft on S stand | S | S | Assigned |
| CAP-02 | M aircraft on S-only stand | S | M | `UNASSIGNED / NO_COMPATIBLE_STAND` |
| CAP-03 | L aircraft on M-only stand | M | L | `UNASSIGNED / NO_COMPATIBLE_STAND` |
| CAP-04 | S aircraft on L stand when it is the only stand | L | S | Assigned (bigger stand accepted) |
| CAP-05 | L aircraft, only an L stand exists | L | L | Assigned |
| CAP-06 | Mixed: M and L flights, stands S, M | S, M | M, L | M assigned to M-stand; L unassigned `NO_COMPATIBLE_STAND` |
| CAP-07 | No stands at all | none | 1 flight | `NO_COMPATIBLE_STAND` (no crash) |
| CAP-08 | No flights | stands | none | Empty result, no crash |
| CAP-09 | **Best-fit**: S flight with free PLB-L and PLB-S | PLB L, PLB S | S | Gets PLB-S (smaller sufficient size) |
| CAP-10 | Best-fit protects big stand | PLB L, PLB S; flights S 06:00–07:00 then L 06:10–07:00 | | S → PLB-S; L → PLB-L (both on PLB) |
| CAP-11 | Capacity invariant on sample data | generated data | | `find_violations` has no size-fit violations |

---

## 8. Overlapping flight tests

| ID | Scenario | Setup | Expected |
|---|---|---|---|
| OVL-01 | Two overlapping flights, one stand | `06:00–08:00` and `07:00–09:00` | 2nd `UNASSIGNED / NO_STAND_AVAILABLE`; stand never double-booked |
| OVL-02 | Two overlapping flights, two identical stands | same | Each on a different stand |
| OVL-03 | Identical times | both `06:00–07:00`, one stand | 2nd unassigned |
| OVL-04 | Fully nested | `06:00–10:00` and `07:00–08:00`, one stand | 2nd unassigned |
| OVL-05 | Arrival inside the previous aircraft's *buffer* | `06:00–07:00`, next arrives `07:10` | Unassigned on one stand (see BUF-02) |
| OVL-06 | Many overlapping flights | N flights, K stands (N > K), same times | Exactly K assigned (when all fit), N−K unassigned |
| OVL-07 | Input order irrelevant | Same flights in shuffled order | Identical allocation (allocator sorts first; also AC-08) |
| OVL-08 | Checker catches overlap | Hand-built *bad* allocation with overlap | `find_violations` returns ≥ 1 message (**tests the checker itself**) |
| OVL-09 | Checker catches size misfit | Hand-built bad allocation | Violation reported |
| OVL-10 | Checker catches buffer breach | Hand-built bad allocation with 10-min gap | Violation reported |
| OVL-11 | Checker passes valid result | A valid allocation | Empty list |

OVL-08 to OVL-10 matter: the checker is the proof that rules are never broken, so it must itself be shown to detect breaches.

---

## 9. Turnaround buffer tests (default 15 min; `BUF-*`)

Single stand (`C01`, PLB, L), flight A `06:00–07:00` unless stated. Buffer is passed as a parameter.

| ID | Scenario | Next flight arrives | Buffer | Expected |
|---|---|---|---|---|
| BUF-01 | **Exactly 15 minutes** | `07:15` | 15 | **Assigned** to the same stand (gap == buffer allowed) |
| BUF-02 | **Less than 15 minutes** (14 min) | `07:14` | 15 | **Not** on this stand → `UNASSIGNED / NO_STAND_AVAILABLE` (single stand) |
| BUF-03 | 14 min 59 s | `07:14:59` | 15 | Not assigned (strict boundary) |
| BUF-04 | 15 min 1 s | `07:15:01` | 15 | Assigned |
| BUF-05 | Zero gap (back-to-back) | `07:00` | 15 | Not assigned |
| BUF-06 | Gap well above buffer | `08:00` | 15 | Assigned |
| BUF-07 | Buffer 0, back-to-back | `07:00` | 0 | Assigned (config respected) |
| BUF-08 | Buffer 30, gap 20 | `07:20` | 30 | Not assigned |
| BUF-09 | Buffer 30, gap 30 | `07:30` | 30 | Assigned |
| BUF-10 | Two stands, gap 10 | `07:10`, two identical stands | 15 | 2nd goes to the other stand |
| BUF-11 | Three flights in a chain | A `06:00–07:00`, B `07:15–08:15`, C `08:30–09:30` | 15 | All on one stand; every gap exactly 15 |
| BUF-12 | Chain broken by one short gap | A `06:00–07:00`, B `07:15–08:15`, C `08:20–09:00` | 15 | C not on this stand |
| BUF-13 | Buffer direction | Next flight arrives *before* previous departs + buffer, same stand | 15 | Never allowed (also covered by checker) |
| BUF-14 | Default value | `Settings()` | n/a | `turnaround_buffer_minutes == 15` |
| BUF-15 | Env override | `TURNAROUND_BUFFER_MINUTES=20` | 20 | Settings reads 20; allocations change accordingly |
| BUF-16 | Negative / non-numeric buffer | `-5`, `abc` | n/a | `ConfigError` at startup |
| BUF-17 | Buffer applies across stand types | PLB and REMOTE both | 15 | Same behaviour on both |
| BUF-18 | Buffer shows in `/stands/{id}` | API | 15 | Every `gap_before_minutes` ≥ 15 |

---

## 10. Unassigned flight scenarios (`test_allocation_strategy.py`)

| ID | Scenario | Setup | Expected |
|---|---|---|---|
| UNA-01 | All compatible stands busy | 1 stand; 2 overlapping flights | 2nd: `NO_STAND_AVAILABLE`; message mentions the stand count, size and buffer |
| UNA-02 | No stand large enough | Only `S` stands; an `L` flight | `NO_COMPATIBLE_STAND` |
| UNA-03 | Reason distinguishes the two cases | Both situations in one run | Correct code on each flight |
| UNA-04 | Every valid flight appears exactly once | Mixed scenario | `len(allocations) == len(valid_flights)`; unique flight ids |
| UNA-05 | Invariant on each allocation | Mixed scenario | Exactly one of `stand` / `reason` set; message set iff unassigned |
| UNA-06 | Unassigned flights do not block stands | Flight U unassigned; later flight fits | Later flight assigned normally |
| UNA-07 | Fall back to REMOTE before unassigned | PLB busy, REMOTE free | Assigned to REMOTE (not unassigned) |
| UNA-08 | PLB preferred when both free | PLB and REMOTE free, same size | PLB chosen |
| UNA-09 | PLB occupied → next flight goes to REMOTE | 1 PLB; 2 overlapping flights; 1 REMOTE | 1st PLB, 2nd REMOTE |
| UNA-10 | Documented failure example (README §5) | The F1–F4 case in `technical-decisions.md` §7.8 | Result is exactly: F1 on PLB, F2–F4 on remote: 1 of 4 on PLB. **Pins the known limitation** so the README claim stays true |
| UNA-11 | Tie-break determinism | Two equal free stands | Lower `stand_id` chosen |
| UNA-12 | Sample data has ≥ 1 unassigned and ≥ 1 remote | Committed CSVs | True (AC-09); fails loudly if the data is retuned and loses scarcity |

---

## 11. Determinism, generator and data-file tests (`test_generate_data.py`)

| ID | Scenario | Expected |
|---|---|---|
| GEN-01 | Run generator twice into two folders | Byte-identical files (AC-01) |
| GEN-02 | Generated flights contain ≥ 5 **distinct** dropped issue codes after validation | AC-02 |
| GEN-03 | All generated valid flights arrive within the window | True |
| GEN-04 | PLB stands are scarce | Number of PLB stands < peak concurrency of valid flights |
| GEN-05 | Committed `data/*.csv` equal generator output for the default seed | Prevents a stale committed file |
| GEN-06 | Allocation determinism | `allocate()` twice on the same input → equal result (AC-08) |
| GEN-07 | Hard-rule invariant on sample | `find_violations(allocate(sample))` is empty (AC-05) |
| GEN-08 | Hard-rule invariant on random scenarios | 50 seeded random mini-scenarios (varying stands, sizes, durations) × buffers {0, 15, 30} → no violations |

---

## 12. Metrics tests (`test_metrics.py`)

Use a **tiny hand-built scenario** so every number can be computed by hand and written in the test.

**Scenario M** (window 06:00–12:00, buffer 15; stands: `P1` PLB-L, `R1` REMOTE-L):

| Flight | Size | Arrival | Departure | Expected result |
|---|---|---|---|---|
| F1 | L | 06:00 | 07:00 | `P1` (60 min) |
| F2 | M | 06:30 | 07:30 | `R1` (60 min; PLB busy) |
| F3 | S | 07:20 | 08:20 | `P1` (gap 20 ≥ 15) → 60 min |
| F4 | L | 06:40 | 07:40 | Unassigned: P1 busy (F1 until 07:00 + buffer), R1 busy (F2 until 07:30) |
| F5 | S | 11:30 | 12:30 | `P1` (free), 60 min of ground time, **30 inside window** |

Hand-computed expectations: total 5; assigned 4 (F1, F2, F3, F5); unassigned 1; `unassigned_rate = 0.2`; on PLB 3 (F1, F3, F5); on remote 1; `plb_rate_of_valid = 0.6`; `plb_rate_of_assigned = 0.75`.
Utilisation: `P1` occupied = 60 + 60 + 30 = 150 → `150/360 = 0.4167`; `R1` = 60 → `0.1667`. By type: PLB `0.4167`, REMOTE `0.1667`.
Peak concurrency (all 5 valid flights, window only): F1, F2, F4 are all on the ground 06:40–07:00 → **3**, first at `06:40`.

(Check order of processing when writing the test: by arrival then departure then id → F1 06:00, F2 06:30, F4 06:40, F3 07:20, F5 11:30. F4 sees P1 busy until 07:00(+15) and R1 busy until 07:30(+15) → unassigned. F3 at 07:20 ≥ 07:00+15 → P1. Matches the table.)

| ID | Scenario | Expected |
|---|---|---|
| MET-01 | Assignment summary on Scenario M | 5 / 4 / 1 / 0.2 |
| MET-02 | PLB usage on Scenario M | 3 / 1 / 0.6 / 0.75 |
| MET-03 | Unassigned breakdown | `by_reason`: `NO_STAND_AVAILABLE`=1, `NO_COMPATIBLE_STAND`=0; `by_aircraft_size`: `L`=1, `S`=0, `M`=0 |
| MET-04 | Utilisation values | `P1` 0.4167, `R1` 0.1667; by type PLB 0.4167, REMOTE 0.1667 |
| MET-05 | Utilisation clipped at window end | F5 contributes 30 minutes, not 60 |
| MET-06 | Utilisation excludes buffer | F1→F3 gap on `P1` not counted as occupied |
| MET-07 | Peak concurrency | 3 at `06:40` |
| MET-08 | Peak counts unassigned flights | F4 is included in the peak even though unassigned |
| MET-09 | Touching intervals are not simultaneous | One flight leaves 09:00, another arrives 09:00 → peak 1 |
| MET-10 | Empty input | 0 flights → all counts 0, all rates `0.0`, `first_occurred_at = null`, no `ZeroDivisionError` |
| MET-11 | No assigned flights | `plb_rate_of_assigned = 0.0` (no division error) |
| MET-12 | Type with no stands | Only PLB stands → REMOTE utilisation `0.0` |
| MET-13 | Reconciliation identities | `assigned+unassigned=total`; `plb+remote=assigned`; breakdown sums = unassigned; each utilisation ∈ [0,1] (also run on the sample data) |
| MET-14 | Data-quality counts | Using a file with 7 dropped / 1 fixed: `rows_read == valid + dropped` |
| MET-15 | Rounding only at the API layer | Internal value is full precision; API shows 4 decimals |

---

## 13. API integration tests (`test_api.py`)

Use `TestClient` against (a) a tiny fixture data folder with known contents, and (b) the committed sample data.

### 13.1 Fixture data for (a)

Stands: `C01 PLB L`, `R01 REMOTE S`. Flights: 4 clean rows (one overlapping so one is assigned remote, one unassigned) + 3 bad rows (bad size, missing departure, duplicate id). Expected numbers are written by hand.

### 13.2 Tests

| ID | Endpoint | Scenario | Expected |
|---|---|---|---|
| API-01 | `GET /allocations` | Status and top-level shape | `200`; keys: `planning_window`, `turnaround_buffer_minutes`, `total_flights`, `assigned_count`, `unassigned_count`, `allocations` |
| API-02 | `/allocations` | Counts | `total_flights == assigned_count + unassigned_count`; `== len(allocations)` |
| API-03 | `/allocations` | Item invariants | `ASSIGNED` ⇒ `stand_id`, `stand_type` set and reason `null`; `UNASSIGNED` ⇒ reason code + text set, `stand_id` `null` |
| API-04 | `/allocations` | Ordering | Sorted by arrival, then departure, then id |
| API-05 | `/allocations` | Dropped flights absent | Bad-row ids not present (A8) |
| API-06 | `/allocations` | Timestamp format | Every time string matches `...Z` and parses to UTC |
| API-07 | `/allocations` | Hard rules hold *through the API* | Reconstruct per-stand schedules from the JSON and check no overlap, size fit, gap ≥ `turnaround_buffer_minutes` |
| API-08 | `GET /stands/C01` | Happy path | `200`; fields `stand_id`, `stand_type`, `max_size`, `flight_count`, `flights` |
| API-09 | `/stands/{id}` | Time order | `flights` sorted by `arrival_time` |
| API-10 | `/stands/{id}` | `gap_before_minutes` | First is `null`; others ≥ buffer; matches hand-computed values |
| API-11 | `/stands/{id}` | Stand without flights | `200`, `flight_count: 0`, `flights: []` |
| API-12 | `/stands/{id}` | Case/whitespace | `/stands/c01` returns `C01` |
| API-13 | `/stands/X99` | Unknown stand | `404`; body `{"error":{"code":"STAND_NOT_FOUND","message":...}}` (exact shape) |
| API-14 | `/stands/{id}` | Flight in this endpoint matches `/allocations` | Same stand for each flight in both endpoints |
| API-15 | `GET /metrics` | Status and shape | `200`; all documented top-level keys present |
| API-16 | `/metrics` | Values on fixture data | Match hand-computed numbers (see MET) |
| API-17 | `/metrics` | Reconciles with `/allocations` | `assigned` equals count of `ASSIGNED` items |
| API-18 | `GET /data-issues` | Status and shape | `200`; `summary` + `issues` |
| API-19 | `/data-issues` | Contains every bad row | One issue each for bad size, missing time, duplicate id; correct `row_number`, `issue_code`, `action`, `record_id` |
| API-20 | `/data-issues` | Message present and readable | Non-empty `message` on every item |
| API-21 | `/data-issues` | Accounting | `rows_read == valid + dropped` per file; `total_issues == len(issues)` |
| API-22 | `/data-issues` | FIXED rows listed | Normalised row appears with `action: "FIXED"` and the flight **does** appear in `/allocations` |
| API-23 | Sample data | Committed CSVs through the API | `/data-issues` shows ≥ 5 distinct dropped codes (AC-02); `/allocations` has ≥ 1 unassigned (AC-09) |
| API-24 | Unknown path | `GET /nope` | `404` with the standard error body (`NOT_FOUND`) |
| API-25 | Wrong method | `POST /allocations` | `405`, standard error body |
| API-26 | Buffer change via settings | App built with buffer 0 vs 30 | `/allocations` differs accordingly; `/metrics.turnaround_buffer_minutes` echoes it |
| API-27 | Startup with missing data file | App creation with missing `flights.csv` | Raises `DataFileError` (fail fast); no half-working app |
| API-28 | Idempotence | Call each endpoint twice | Identical JSON |

---

## 14. Coverage map: requirement → tests

| Requirement | Tests |
|---|---|
| H1 one aircraft at a time | OVL-*, GEN-07/08, API-07 |
| H2 size fit | CAP-*, SZ-06, GEN-07/08 |
| H3 buffer (configurable) | BUF-*, API-26 |
| ≥ 5 bad row kinds, none silent | CSV-*, TS-*, SZ-02, DUP-*, DEP-*, GEN-02, API-19/23 |
| Every flight assigned or unassigned + reason | UNA-04/05, API-03 |
| PLB preference | UNA-07/08/09, UNA-10, CAP-09/10 |
| 4 endpoints | API-* |
| ≥ 4 metrics | MET-* |
| Determinism / seeded data | GEN-01/05/06, OVL-07 |
| UTC handling | TS-01..03, TS-14, API-06 |

## 15. Exit criteria

- All tests above implemented (IDs may be merged where they share a parametrised test).
- `pytest` passes from a clean clone using the README commands, in under ~5 seconds.
- No test depends on the current date/time, network, or on test execution order.
- Any change to the sample data or the allocation rules updates UNA-10 / UNA-12 / API-23 in the same commit, so the README claims stay true.
