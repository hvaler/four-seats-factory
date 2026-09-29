# Auditor decision: fskit-001 · stage 3 · candidate 1

- **Auditor:** auditor-thgx, model `claude-opus-5-5`.
- **Date:** 2026-09-28T23:45Z (UTC)
- **Decision: REJECTED**
- **Product commit:** `e4d35083b81b277b008b2761002d260243e6a59d`.
- **Trees:** stage-3 `bfd2229fdeffecf26ab28cd3e9a24a640f983838`; stage-2 `a8e6178d` and stage-1 `347efba5`, both unchanged.
- **Specs:**
  - stage-1 `65497dea…0aa4`;
  - stage-2 `39aaf9d7…b13f`;
  - stage-3 `2255d3f2181c22dc6eac6919bf7712197d812248bd9de8a7e59260ede6056e54`.
- **Registers:** stage-3 r2 (analyst@5b89c4a2) plus D3-21, with the stage-1 and stage-2 registers in force.

## Unmet conditions (both are spec rows, both block)
1. **F3-A01: the process crashes with a JavaScript heap OOM under sustained statement reads.** Found by the auditor (event 009).
   - **Rules broken:** §2 (2 GiB, 50 in flight), §5 (no 5xx under concurrent load) and stage-3 "tokens last until reset".
   - **Evidence:** with 500 payments of history, the process died after 4,761 reads (exit 139, V8 heap limit), losing all state. Memory is never released.
   - **Required:** bounded snapshot storage, for example a token that re-derives the page from the immutable revision history. S3-060…065 and S3-084 must still hold.
2. **F3-01: a closed hold seen through an earlier `known_at` never expires at its deadline.** Reported by the adversary (4c962548) and reproduced by the auditor (event 010).
   - **Rules broken:** S3-081 and S3-057, from stage-3.md "Historical holds".
   - **Evidence:** `held` stays 1000 at `expires_at`+1 ms and at 2099 when `known_at` falls between the creation and the void. It should be 0.

## Other evidence on this candidate (all pass, kept for the re-audit)
| Event | Check | Result |
|---|---|---|
| 001 | Provenance | PASS |
| 002 / 003 | Harness `--stage 3`, host and **isolated** | 147 + 35 + 6, 0 skipped |
| 004→005 | Stage-3 probe with hand-computed history | 33/33 (run 1's failure was an auditor tool bug) |
| 006→007 | Upgrades 1→3 and 2→3 in fresh containers | 14/14 (run 1's failure was an auditor tool expectation) |
| 008 | Stage-1 and stage-2 regression on stage-3/, API and UI at 375 and 1280 px | 150/150 |

The adversary's stage-3 bundle for candidate 1 was not needed for this rejection: both unmet conditions are reproduced by the auditor. It will be reproduced on the repair candidate.

## Next action
- **Repair:** repair cycle 1 of 5, routed by the analyst (839d4053, 15 parts).
- **Re-audit from scratch on the repair revision:**
  - the memory and crash probe, repeated;
  - F3-01 cases A–D;
  - the harness, isolated;
  - the full adversary re-run;
  - upgrades;
  - regression;
  - stage-1 and stage-2 trees unchanged.
- This rejected candidate and all its evidence stay on record.
