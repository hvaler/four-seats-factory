# fskit-001 · Stage 3 · Adversary verification bundle, candidate 2 (repair cycle 1)

This is a challenge result, not a verdict. **No open finding.** F3-01 and F3-02/F3-A01 are fixed, and their failing evidence (events 003–006) is preserved.

## Revisions

| Item | Value |
|---|---|
| Candidate | `51a0bdd1c48207fb3e22fb163d1fd7972123aa3d` · stage-3 `f586c4995f31122e887e462d54590b955f6b45a2` · stage-2 `a8e6178d` · stage-1 `347efba5` (both unchanged). Its parents are `168245a0`, `0f7974d5` → `e4d35083` |
| Review clone | `clones\adversary-s3-2`; sources `clones\adversary-s1-1` at `beeaec72` and `clones\adversary-s2-2` at `68583038` |
| Test revision | `9e49497e2a2334ea381347bf33162cb2387010f8` (stage-3 suite v2; stage-1/2 suites as at v3 `bdb21efc`) |

## Results

| Event | Check | Outcome |
|---|---|---|
| 010 | Harness `--stage 3` (`checks/fskit-001-s3-adversary-2`) | **PASS.** 147 + 35 + 6, 0 skipped, claimed 3. The stage-4 probe fails as expected. `report.json` `ca3701ed…538f` |
| 011 | All three suites (`c2-run1/`) | **PASS.** Stage-1 325/325, stage-2 148/148 (UI at 375 and 1280 px, D2-18 upgrade into stage 3), stage-3 50/50 (including the F3-01 test and XC 1→3 / 2→3) |
| 012 | Memory gate (analyst 78ccefc0), `c2-probes/` | **PASS.** 20,000 first reads with 20 in flight over 500 payments: all 200, p99 0.210 s, max 0.666 s, 0 over 5 s, **peak 52.2 MiB**, still running. Rerun at the original 5,000/10 parameters: all 200, peak 38.7 MiB (candidate 1 crashed at about 1.07 GiB) |
| 013 | F3-01 repro and D3-11 check rerun | **PASS.** Cases B and C now give held 0; controls unchanged; D3-11 gives 409 inside the hold window and 201 after expiry |
| 014 | `test_s3_conc` × 3 | **PASS**, 18/18 |
| 015 | Repair diff inspection | **PASS.** 5 files under `stage-3/` only (+279/−15); stages 1–2 unchanged |

## What remains untested or only partly tested

These are unchanged from BUNDLE-c1:
- a literal `+` in instants (D3-20);
- D3-21 on one imported case only;
- an 8 × 5 as_of × known_at grid;
- snapshots after export/import (D3-10), which the implementer's own tests cover but mine do not;
- histories of at most 500 payments;
- 3 CONC repetitions on a shared Docker daemon;
- the hidden tests are unknown.

**New:** the page cost of a snapshot is now O(entries of the user), since each page is re-derived. It was measured only at 500 payments, where p99 is 0.21 s at 20 in flight.

## Usage

`fskit-001,3,adversary,f603ac21-88ea-434a-844e-bb621f8da63e,Claude Code,claude-opus-5-5,2026-09-28T23:48:30Z,2026-09-29T00:10:00Z,1290,unknown,unknown,unknown,unknown,,true,wall clock from shell timestamps (approximate to the minute),token counts are not exposed to this seat at run time`
