# Auditor decision: fskit-001 · stage 4 · candidate 1

- **Auditor:** auditor-thgx, model `claude-opus-5-5`.
- **Date:** 2026-09-29T00:43Z (UTC)
- **Decision: ACCEPTED**
- **Product commit:** `181947069ba933c39661835296e89a891847c2a3`.
- **Trees:**
  - `stage-4`: **`c7d50a979b158832f15055289bf8f44b5f5edb8b`**;
  - `stage-3`: `f586c499`, unchanged;
  - `stage-2`: `a8e6178d`, unchanged;
  - `stage-1`: `347efba5`, unchanged.

  All earlier acceptances stand.
- **Test revisions:**
  - adversary `854b2cc4446cda1b05d3f67fd1f9cca4777fad65` (all four suites) and `c60966f83cb56a0ef5772890cc6b0d9cb6066e20` (stage-4 v2);
  - auditor tools `s4_probe` (`cba82a2d`), `s4_upgrade_probe` (`cd52dc55`), plus the earlier-stage probe revisions listed in event 007.
- **Specs:** stage-1…3 as before; stage-4 `1894b002f8827fd36623df4ecf3deb204e20d7fafbbfa671894a114db80e6df1` (LF `ff79140f…`).
- **Registers:** stage-4 r2 (analyst@f81d68a1) plus D4-13, with the stage-1 r2, stage-2 r3 and stage-3 r2 (+ D3-21) registers cumulative.

## Evidence reproduced by the auditor
All runs used a fresh clone `clones\auditor-s4-1`, the auditor's own `--no-cache` image `sha256:32dce302…671d`, fresh containers under `--cpus 2 --memory 2g`, and the auditor's own venv.

| Event | Check | Result |
|---|---|---|
| 001 | Provenance: the S4-001 copy commit `0a2ee743:stage-4` = `f586c499`; only `stage-4/` changed; the earlier trees are unchanged | PASS |
| 002 | Harness `--stage 4`, host mode (`fskit-001-s4-audit-1`) | 147 + 35 + 6 + 5, 0 skipped, highest contiguous 4 |
| **003** | **Harness `--stage 4 --mode isolated` (`fskit-001-s4-audit-2`)** | **147 + 35 + 6 + 5, 0 skipped.** `report.json` `f8da5a9d…13f1`. There is no next-stage probe |
| 004 | Stage-4 probe (refunds, batches) | 29/29 |
| 005→006 | **Upgrades 1→4, 2→4 and 3→4** from the three ACCEPTED images in fresh containers | 14/14. Run 1's 2 errors were an auditor tool bug, preserved |
| 007 | Regression on `stage-4/`: stage-3 probe; memory gate (20,000 reads); stage-2 API; UI at 375 and 1280 px; stage-1 probes | 33, 20000/20000 at 45.5 MiB, 31, 44, 75 |
| 008 | Adversary suites at 854b2cc4, re-run by the auditor | 325 + 148 + 50 + 25 |
| 009 | Adversary stage-4 v2 at c60966f8, re-run by the auditor | 30/30 |

The adversary bundle cc537cc7 (adversary@2b8a4f2a) reports no open finding. It agrees with every result above.

## Coverage (stage-4 register r2)
Evidence key:
- P = auditor probes (004, 006, 007);
- A = adversary suites re-run by the auditor (008, 009);
- H = isolated harness (003).

| Rows | Evidence |
|---|---|
| S4-001, S4-002 | I001; H; UI at 375 and 1280 px (007) |
| S4-010…S4-026 (refunds: access, targets, amounts, limits, shape, available funds, no reopening, representations, immutability, correction floor, CONC and same-key, history) | P004, A |
| S4-030…S4-047 (batches: access, shape, completeness, instants, precedence, combined affordability, no-trace rejection, shared `recorded_at`, receipts, snapshots, member refunds, overlap CONC, conservation) | P004, A (v2 adds S4-025/026/030/036/038/040) |
| S4-050…S4-052 (upgrades 1→4, 2→4, 3→4; D4-13; imported histories) | P006, A (XC) |
| S4-900…S4-902 | H; UI; A stage-1/2/3 suites on `stage-4/`; P regression |
| Earlier cumulative rows | H suites 1–3; A stage-1/2/3 suites; P stage-1/2/3 probes; memory gate |
| D4-01…D4-13 | tested as decisions (P, A), reported separately |

## Limitations (recorded, not waived)
- Stage 4 adds no UI, so the UI evidence is regression only.
- There is no 32-item multi-settlement batch test.
- Only three constructed `historical_overdraft` batch cases were tested.
- Cost was measured at 500 payments only.
- Everything ran on a single host.
- 3→4 snapshot pages are not byte-equal, because `refund_of` is added. D4-13 permits this, and receipt replays are byte-identical.
- **No claim is made about hidden checks.**

---

# STAGE_ACCEPTED checkpoint: fskit-001 · stage 4

| Field | Value |
|---|---|
| Candidate commit | `181947069ba933c39661835296e89a891847c2a3` |
| Stage tree (`stage-4`) | `c7d50a979b158832f15055289bf8f44b5f5edb8b` |
| Earlier trees | stage-3 `f586c499`, stage-2 `a8e6178d`, stage-1 `347efba5`, all unchanged |
| Verdict | ACCEPTED by auditor-thgx, 2026-09-29T00:43Z |
| Final isolated stage harness | `checks/fskit-001-s4-audit-2/report.json` `f8da5a9ddee8bb68c88b61319130deac37b23ebc2171a04c67c081175c5b13f1` |
| Repair cycles (stage 4) | 0 of 5 |
| Infrastructure retries | 0 |
| Stage time | started 00:08:35Z, accepted about 00:43Z: about 35 of 360 min used |
| Run total | about 243 of 1440 min used |
| Next | S4-903, the final all-stage verification by the auditor |

`fskit-001,4,auditor,auditor-thgx,Claude Code,claude-opus-5-5,2026-09-29T00:09:00Z,2026-09-29T00:43:00Z,~2040,unknown,unknown,unknown,unknown,,true,wall clock from shell/room timestamps,token counts are not exposed to this seat at run time`
