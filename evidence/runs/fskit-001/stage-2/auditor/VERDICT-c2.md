# Auditor decision: fskit-001 · stage 2 · candidate 2 (repair cycle 1)

- **Run / stage:** fskit-001 · pocketful · stage 2 (active).
- **Auditor:** auditor-thgx (hugo.valer/auditor-thgx), model `claude-opus-5-5`.
- **Date:** 2026-09-28T22:46Z (UTC)
- **Decision: ACCEPTED**
- **Product commit:** `68583038e7ea52429b062af0f775d3cbfd96b7c3`. Its parent chain is 59ca569d → f1f0847d, and the rejected candidate 1 is preserved.
- **Stage tree:** `68583038:stage-2` = **`a8e6178d7b9d5ba4dde4999e78730fa99ff80fe2`**.
- **Accepted stage-1 tree, unchanged:** `68583038:stage-1` = `347efba502629e5b5bbd730f35c34bdfe208c478`.
- **Test revisions:**
  - adversary `bdb21efc6e3ccdbc952f3f6bc24b56313e7a1266` (suite v3; stage-2 suite tree `c8d96109`, stage-1 suite tree `51241af5`), and `207536fa` (v2);
  - auditor tools `c66eae37` (API), `9adf0051` (UI), `9a035d4b` (upgrade), `0455775b` (F2-01 recheck), and `9eeeae1d`/`236ecf35`/`31ba973b` (stage-1 probes).
- **Specs:**
  - stage-1.md `65497dea…0aa4`;
  - stage-2.md `39aaf9d7743c6fd831663e5b8363866f7d70795e5efb9000c2803f471397b13f`.
- **Registers:**
  - stage-1 r2 (analyst@8e913edb), in force cumulatively;
  - stage-2 r3 (analyst@b8eb2f0a), which includes D2-18 and D2-19.
- **Supersedes:** VERDICT-c1 (REJECTED, `f1f0847d`). That record and its events 001–012 are kept.

## Resolution of the rejection condition
F2-01 / D2-19 is **fixed**, as rechecked by the auditor in event 016. At 375 and 1280 px:
- A refused over-remainder capture keeps the typed `25.00`, and the error is shown.
- A later partial non-final capture of `7.00` leaves the item `open`, and the prefill follows the new remainder `13.00`.
- The payer's total is 4300 and held is 1300.

The repair diff is confined to `stage-2/src/ui/app.js` (+17/−4), a test and RUN.md (event 013).

## Evidence reproduced by the auditor on this candidate
All runs used a fresh clone `clones\auditor-s2-2`, images built by the auditor with `--no-cache`, containers under `--cpus 2 --memory 2g`, and the auditor's own venv.

| Event | Check | Result |
|---|---|---|
| 013 | Provenance: stage-1 unchanged; the repair only touches `stage-2/` | PASS |
| 014 | Harness `--stage 2`, host mode (`fskit-001-s2-audit-3`) | 147/147 + 35/35, 0 skipped |
| **015** | **Harness `--stage 2 --mode isolated` (`fskit-001-s2-audit-4`)** | **147/147 + 35/35, 0 skipped.** `report.json` `36164d38…d2b9`, revision 68583038 |
| 016 | F2-01 / D2-19 recheck, both halves, both widths | FIXED |
| 017 | Auditor probes: API 31/31; browser at 375 and 1280 px 44/44; 1→2 upgrade 7/7; stage-1 probes on stage-2/ 61/61 + 10/10 + 4/4 | PASS |
| 018 | Adversary suites v2 re-run by the auditor: stage-1 suite on stage-2/ 325/325; stage-2 suite 139/139 | PASS |
| 019 | Adversary suite v3 re-run by the auditor: stage-1 suite 325/325; stage-2 suite 148/148 | PASS |
| 020 | Adversary CONC tests, 2 repetitions on fresh images | 2 × 9/9 |

**Earlier evidence reused only for unchanged parts.** The image differs from candidate 1 only in `src/ui/app.js`. Even so, every check above was re-run on candidate 2 itself; nothing was carried over.

**Next-stage probe, reported separately:** stage 3 fails as expected in both harness runs. It passes 2/6 and then stops at `KeyError 'as_of'`, which is a stage-3 feature. Nothing was changed to influence it.

**Product quality (S2-030…034), auditor judgement.** Based on the screenshots at 375 and 1280 px (`c2/ui/*.png`) and the measured proxies:
- The UI is coherent and calm, with one consistent visual system.
- Available is the 38 px headline; total and held are 17 px secondary.
- Status badges are distinct.
- Error, uncertain and success notices differ: red ✕, amber ?, green ✓.
- Primary actions are obvious.
- Labels are visible and the focus ring is 3 px.
- Contrast is 6.25–16.5:1.
- There is no horizontal scroll with worst-case content.
- XSS renders as text.
- Timestamps are human-formatted, except the RFC 3339 testid text.

**Satisfied.**

## Coverage
Key:
- H = isolated harness (015);
- P = auditor probes (016/017);
- A = adversary suites re-run by the auditor (018–020);
- I = inspection (013, and 001 for unchanged files).

| Rows | Evidence |
|---|---|
| Stage-1 cumulative rows S1-001…S1-206, S1-900…903, as superseded by stage 2 | H suite 1; P stage-1 probes (75/75); A stage-1 suite on stage-2/ (325/325); S1-001/002/070/090/091/092/112/196 superseded forms in P API and A |
| S2-001, S2-002 | I013/001, H isolated (browser suite with no outbound) |
| S2-010…S2-028 (routes, testids, formats, decimals, refresh, competing clients, uncertain writes, authorizations UI) | P UI at both widths (44), A UI suite v3, H suite 2 |
| S2-030…S2-035 (product quality, XSS) | P UI proxies and screenshots, auditor judgement above, A |
| S2-040…S2-044, S2-902 (1→2 upgrade) | P upgrade (7/7, fresh containers, ACCEPTED stage-1 image, D2-13 bytes, D2-18 browser), A XC in both D2-18 shapes |
| S2-050…S2-074 (holds, captures, expiry, concurrency) | P API (31), A API + CONC (5 + 2 repetitions) |
| S2-900…S2-904 | H014/015; P and A browser evidence; this record; A and P stage-1 suites on stage-2/ |
| D2-01…D2-19 | tested as decisions (P and A), reported separately from spec rows |

## Limitations (recorded, not waived)
- **Loading states:** observed only in passing.
- **Uncertain outcomes:** uncertain-write recovery is required and tested for payments only. A lost capture response is shown as a refusal, which is the adversary's non-finding note; the spec is silent on this.
- **Upgrade method:** the D2-18 upgrade scenario was driven by Playwright request routing.
- **Concurrency:** single host with CFS `--cpus 2`; 7 concurrency repetitions in total.
- **Contrast:** checked on sampled elements only.
- **Decisions:** the D2-xx rows are band interpretations.
- **No claim about hidden evaluation checks.**

ACCEPTED is internal acceptance of the identified candidate. Any later change to `stage-2/` (or to `stage-1/`) invalidates this decision until it is rechecked.

---

# STAGE_ACCEPTED checkpoint: fskit-001 · stage 2

| Field | Value |
|---|---|
| Stage | 2 (pocketful) |
| Candidate commit | `68583038e7ea52429b062af0f775d3cbfd96b7c3` |
| Stage tree (`stage-2`) | `a8e6178d7b9d5ba4dde4999e78730fa99ff80fe2` |
| Stage-1 tree in this commit | `347efba502629e5b5bbd730f35c34bdfe208c478`, unchanged, so stage-1 acceptance stands |
| Verdict | ACCEPTED by auditor-thgx, 2026-09-28T22:46Z |
| Final isolated harness | `checks/fskit-001-s2-audit-4/report.json` `36164d38c6b1957f306110536282867dbd53ec7139d4f4bfbb0ac17d7d07d2b9` |
| Evidence | branch `auditor`: `evidence/runs/fskit-001/stage-2/auditor/` (events 001–020, c1/, c2/, VERDICT-c1.md, VERDICT-c2.md, UPGRADE-1to2.md); adversary@4abc62a9 |
| Repair cycles used (stage 2) | 1 of 5 |
| Infrastructure retries used | 0 |
| Stage time | started 21:37:47Z, accepted about 22:46Z: about 68 of 360 min used, about 292 min left (deadline 2026-09-29T03:37:47Z) |
| Run total | about 125 of 1440 min used (started 20:40:47Z); new work stops at 2026-09-29T20:10:47Z |
| Financial | no cap available; token counts are not readable by this seat at run time |

## Auditor METRICS (stage 2)

`fskit-001,2,auditor,auditor-thgx,Claude Code,claude-opus-5-5,2026-09-28T21:38:00Z,2026-09-28T22:46:00Z,~4080,unknown,unknown,unknown,unknown,,true,wall clock from shell/room timestamps,token counts are not exposed to this seat at run time`
