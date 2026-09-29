# Auditor decision: fskit-001 · stage 3 · candidate 2 (repair cycle 1)

- **Auditor:** auditor-thgx, model `claude-opus-5-5`.
- **Date:** 2026-09-29T00:08Z (UTC)
- **Decision: ACCEPTED**
- **Product commit:** `51a0bdd1c48207fb3e22fb163d1fd7972123aa3d`. Its parent chain is 0f7974d5 → 168245a0 → e4d35083; the rejected candidate 1 is preserved.
- **Trees:**
  - `stage-3`: **`f586c4995f31122e887e462d54590b955f6b45a2`**;
  - `stage-2`: `a8e6178d7b9d5ba4dde4999e78730fa99ff80fe2`, unchanged, so the stage-2 acceptance stands;
  - `stage-1`: `347efba502629e5b5bbd730f35c34bdfe208c478`, unchanged, so the stage-1 acceptance stands.
- **Test revisions:**
  - adversary `9e49497e2a2334ea381347bf33162cb2387010f8` (stage-3 suite tree `5e5fda8f`);
  - auditor tools `459189a7` (s3_probe), `9abeae23` (upgrades), `repro_f3_01.py` and `risk_snapshot_count.py` (both committed at `888b934e`), plus the stage-1 and stage-2 probe revisions listed in event 016.
- **Specs:** stage-1 `65497dea…`, stage-2 `39aaf9d7…`, stage-3 `2255d3f2181c22dc6eac6919bf7712197d812248bd9de8a7e59260ede6056e54`.
- **Registers:**
  - stage-3 r2 (analyst@5b89c4a2) plus D3-21 (analyst@67243bd);
  - stage-1 r2 and stage-2 r3, cumulative.
- **Supersedes:** VERDICT-c1 (REJECTED, `e4d35083`), which is preserved together with events 001–010.

## Resolution of the rejection conditions
- **F3-01** is fixed (event 012). Cases A–D give `held` = 1000, 0, 0, 0. The adversary reached the same result independently (bundle event 013).
- **F3-A01 / F3-02** is fixed (event 013).
  - **Gate** (analyst 4c1e1466): 20,000 first statement reads over 500 payments, 20 in flight, `--cpus 2 --memory 2g`.
  - **Result:** 20,000/20,000 returned 200 with no failure. The container is still running at **39.7 MiB**, against a crash at 4,761 reads and 1.06 GiB on candidate 1.
  - The adversary's run agrees: peak 52.2 MiB, p99 0.210 s, 0 requests over 5 s.

## Evidence reproduced by the auditor on this candidate
All runs used a fresh clone `clones\auditor-s3-2`, the auditor's own `--no-cache` image `sha256:9d61adde…4838`, and fresh containers under `--cpus 2 --memory 2g`.

| Event | Check | Result |
|---|---|---|
| 011 | Provenance: the repair touches only `stage-3/` (5 files); stage-1 and stage-2 are unchanged | PASS |
| 012 | F3-01 recheck | fixed |
| 013 | Memory gate, 20,000 reads | PASS |
| 014 | Harness `--stage 3`, host mode (`fskit-001-s3-audit-3`) | 147 + 35 + 6, 0 skipped |
| **015** | **Harness `--stage 3 --mode isolated` (`fskit-001-s3-audit-4`)** | **147 + 35 + 6, 0 skipped.** `report.json` `aa662080…4c891`. The stage-4 probe fails as expected (`refund_of`) |
| 016 | Stage-3 probe with hand-computed history | 33/33 |
| 016 | **Upgrades 1→3 and 2→3** from the ACCEPTED images in fresh containers | 14/14 |
| 016 | Regression on `stage-3/`: stage-2 API; UI at 375 and 1280 px; stage-1 probes | 31 + 44 + 75 |
| 017 | Adversary suites re-run by the auditor: stage-1, stage-2 (UI at both widths, D2-18) and stage-3 | 325/325 + 148/148 + 50/50 |

**Product quality (UI regression, S3-901).** Stage 3 added no UI. Every stage-2 UI row still holds at both widths (44/44), and the screenshots are in `c2/ui/`. The stage-2 judgement on S2-030…034 stands.

## Coverage (stage-3 register r2)
Evidence key:
- P = auditor probes (012, 013, 016);
- A = adversary suite re-run by the auditor (017);
- H = isolated harness (015).

| Rows | Evidence |
|---|---|
| S3-001, S3-002 | 001/011 inspection; H |
| S3-010…S3-012 (timestamps, seeded `created_at`) | P, A |
| S3-020…S3-023 (`as_of`: validation, inclusivity, echo, the four fields as one view) | P, A, H |
| S3-030…S3-036 (statements: window, order, balances, pagination, visibility) | P, A, H |
| S3-040…S3-055 (revisions, corrections, `insufficient_funds` vs `historical_overdraft` in all named cases, `known_at`, time moves) | P, A |
| S3-056…S3-058 (linked payments, deadline expiry, D3-18) | P, A |
| S3-060…S3-065 (snapshots, concurrency) | P, A; memory gate 013 |
| S3-070…S3-072, S3-902 (settlements, captures, upgrades 1→3 and 2→3) | P upgrades, A XC |
| S3-080…S3-085 (historical holds, CONC) | P, A (including 3 CONC repetitions) |
| S3-900…S3-904 | H; UI at both widths; this record; stage-1 and stage-2 suites on stage-3/ |
| Earlier cumulative rows (S1-*, S2-*) | H suites 1–2; A stage-1 and stage-2 suites; P stage-1/2 regression |
| D3-01…D3-21 | tested as decisions (P, A) and reported separately |

## Limitations (recorded, not waived)
- **D3-18** (a stage-2 void releases at the import time) is an approximation, because the stage-2 exports record no void time.
- The literal `+` in instants (D3-20) is only partly tested.
- The memory gate was run at a 500-payment history. The snapshot page cost is O(entries).
- Everything ran on a single host with CFS `--cpus 2`.
- **No claim is made about hidden checks.** The public stage-3 sample is only 6 tests; the independent suites carry the stage-3 evidence.

ACCEPTED is internal acceptance of this exact candidate. Any later change to `stage-3/`, `stage-2/` or `stage-1/` invalidates it until it is rechecked.

---

# STAGE_ACCEPTED checkpoint: fskit-001 · stage 3

| Field | Value |
|---|---|
| Candidate commit | `51a0bdd1c48207fb3e22fb163d1fd7972123aa3d` |
| Stage tree (`stage-3`) | `f586c4995f31122e887e462d54590b955f6b45a2` |
| Earlier trees in this commit | stage-2 `a8e6178d`, stage-1 `347efba5`, both unchanged |
| Verdict | ACCEPTED by auditor-thgx, 2026-09-29T00:08Z |
| Final isolated harness | `checks/fskit-001-s3-audit-4/report.json` `aa6620807192d061ac1abc51e78759a893ae1e1bb4cecbe4950c0dca63c94891` |
| Evidence | branch `auditor`: `evidence/runs/fskit-001/stage-3/auditor/` (events 001–017, c1/, c2/, VERDICT-c1.md, VERDICT-c2.md, UPGRADE-1to3-2to3.md); adversary@6bbed1a3 |
| Repair cycles (stage 3) | 1 of 5 |
| Infrastructure retries | 0 |
| Stage time | started 22:47:28Z, accepted about 00:08Z: about 81 of 360 min used (deadline 2026-09-29T04:47:28Z) |
| Run total | about 208 of 1440 min used (started 2026-09-28T20:40:47Z) |

`fskit-001,3,auditor,auditor-thgx,Claude Code,claude-opus-5-5,2026-09-28T22:48:00Z,2026-09-29T00:08:00Z,~4800,unknown,unknown,unknown,unknown,,true,wall clock from shell/room timestamps,token counts are not exposed to this seat at run time`
