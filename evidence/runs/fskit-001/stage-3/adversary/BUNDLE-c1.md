# fskit-001 · Stage 3 · Adversary verification bundle, candidate 1

This is a challenge result, not a verdict. **Two open findings:**
- **F3-01**, a spec-row defect (analyst ruling 0797c462), reproduced by the implementer (a3564dfe).
- **F3-02**, high severity: a process crash under repeated statement reads.

## Revisions

| Item | Value |
|---|---|
| Candidate | `e4d35083b81b277b008b2761002d260243e6a59d` · stage-3 `bfd2229f…3838` · stage-2 `a8e6178d` · stage-1 `347efba5` (both unchanged) |
| Review clone | `clones\adversary-s3-1`; sources `clones\adversary-s1-1` at `beeaec72` and `clones\adversary-s2-2` at `68583038` |
| Test revisions | v1 `079cb56d` (runs c1-run1); v2 `9e49497e` (one test bug fixed: second-precision stage-1 timestamps in `test_upgrade_1_to_3`) |
| Registers | stage-3 r2 (analyst@5b89c4a2) + D3-21; stage-1 r2 and stage-2 r3 in force |

## Results

| Event | Check | Outcome |
|---|---|---|
| 001 | Harness `--stage 3` (`checks/fskit-001-s3-adversary-1`) | **PASS.** 147 + 35 + 6, 0 skipped, claimed 3. The stage-4 probe fails as expected. `report.json` `1a7cf2f2…5f50` |
| 002 | Stage-1 and stage-2 suites on `stage-3/` (S3-904, S3-901) | **PASS.** 325/325 and 148/148 (UI at 375 and 1280 px; D2-18 upgrade into stage 3) |
| 003 | Stage-3 suite v1 | 48/50. F3-01, plus 1 **TEST BUG** (preserved) |
| 004 | Stage-3 suite v2 | 49/50. The only failure is **F3-01** |
| 005 | F3-01 repro | **FAIL.** A voided hold viewed with `known_at` before the void never expires (held 1000 beyond `expires_at`) |
| 006 | F3-02: the analyst's snapshot risk probe, 2 runs | **FAIL.** The Node heap is exhausted after about 4,000 of 5,000 first statement reads over 500 payments; the process exits with code 139 and the service is gone. p99 0.27–0.30 s before the crash |
| 007 | D3-11 overdraft boundaries vs expiry | **PASS.** Expiry is honoured at `expires_at` in historical_overdraft, so F3-01 does not reach D3-11 |
| 008 | `test_s3_conc` × 3 | **PASS**, 18/18 |
| 009 | Provenance | **PASS.** The S3-001 copy commit equals `a8e6178d`, and stages 1–2 are unchanged |

## What remains untested or only partly tested

1. A literal `+` in the query (D3-20): only `%2B` is sent.
2. The D3-21 "more negative" rule is tested on one imported-artifact case only.
3. The historical-view grid is 8 × 5 instants for 3 users. No random or property-based exploration.
4. Snapshot validity after export/import (D3-10) is not tested.
5. Statement scale: at most 500 payments. Beyond F3-02, the O(n) latency with larger histories is not measured.
6. The stage-3 UI has no new obligations. Only the stage-2 UI regression was run, at both widths.
7. 3 CONC repetitions on a Docker daemon shared with the other seats.
8. The hidden tests are unknown.

## Usage

`fskit-001,3,adversary,f603ac21-88ea-434a-844e-bb621f8da63e,Claude Code,claude-opus-5-5,2026-09-28T22:50:00Z,2026-09-28T23:50:00Z,3600,unknown,unknown,unknown,unknown,,true,wall clock from shell timestamps (approximate to the minute),token counts are not exposed to this seat at run time`
