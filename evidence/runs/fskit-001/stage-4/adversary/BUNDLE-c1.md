# fskit-001 · Stage 4 · Adversary verification bundle, candidate 1

This is a challenge result, not a verdict. **No open finding.**

## Revisions

| Item | Value |
|---|---|
| Candidate | `181947069ba933c39661835296e89a891847c2a3` · stage-4 `c7d50a979b158832f15055289bf8f44b5f5edb8b` · stage-3 `f586c499` · stage-2 `a8e6178d` · stage-1 `347efba5` (all three unchanged) |
| Review clone | `clones\adversary-s4-1`; sources at `beeaec72` (s1-1), `68583038` (s2-2) and `51a0bdd1` (s3-2) |
| Test revisions | v1 `854b2cc4` (the full run); v2 `c60966f8` (5 added tests plus the CONC repetitions) |
| Registers | stage-4 r2 (analyst@f81d68a1) + D4-13; all earlier registers in force |

## Results

| Event | Check | Outcome |
|---|---|---|
| 001 | Harness `--stage 4` (`checks/fskit-001-s4-adversary-1`) | **PASS.** 147 + 35 + 6 + 5, 0 skipped, highest contiguous 4, claimed 4. `report.json` `4e09d2db…74b7` |
| 002 | All four suites (`c1-run1/`) | **PASS.** 325 · 148 (UI at 375 and 1280 px; D2-18 into stage 4) · 50 (1→4 and 2→4 through the stage-3 upgrade tests) · 25 (XC 1→4, 2→4, 3→4). **Observation:** 3→4 snapshot pages are not byte-equal, because `refund_of` was added; D4-13 permits this, and every stage-3 field is identical |
| 003 | v2 additions: S4-025 refund in history, S4-026 refund revisions, S4-030/036 operator-sender, S4-038 two-instant combined, S4-040 recorded_at ordering | **PASS**, 5/5 |
| 004 | CONC + XC module × 3 | **PASS**, 30/30 |
| 005 | Statement memory gate on stage 4 (20,000 reads, 20 in flight) | **PASS.** All 200, p99 0.276 s, peak 50.4 MiB |
| 006 | Provenance | **PASS.** S4-001 copy == `f586c499`; earlier trees unchanged |

## What remains untested or only partly tested

1. Refunds and batches have no UI; the spec requires only the API.
2. Batch sizes above 32 were tested only for rejection. There is no 32-item batch across many settlements.
3. `historical_overdraft` for batches: three constructed cases, with no random exploration.
4. The combined check's O(n) cost, and snapshot paging cost, are not measured beyond 500 payments.
5. 3 CONC repetitions on a shared Docker daemon.
6. Carried over: D3-18 and D3-21 approximations; the lost-capture display.
7. The hidden tests are unknown.

## Usage

`fskit-001,4,adversary,f603ac21-88ea-434a-844e-bb621f8da63e,Claude Code,claude-opus-5-5,2026-09-29T00:09:00Z,2026-09-29T00:42:00Z,1980,unknown,unknown,unknown,unknown,,true,wall clock from shell timestamps (approximate to the minute),token counts are not exposed to this seat at run time`
