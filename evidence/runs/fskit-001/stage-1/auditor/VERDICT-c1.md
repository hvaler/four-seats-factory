# Auditor decision: fskit-001 · stage 1 · candidate 1

- **Run / stage:** fskit-001 · pocketful · stage 1 (active). No stage 2+ behaviour is in scope.
- **Auditor and seat ID:** auditor-thgx (hugo.valer/auditor-thgx), runtime model `claude-opus-5-5`.
- **Date (UTC):** 2026-09-28T21:35Z
- **Decision: ACCEPTED**
- **Product commit:** `beeaec72ff53fa75469c5f09236a786632f21fd8` (result, main).
- **Stage tree:** `git rev-parse beeaec72:stage-1` = `347efba502629e5b5bbd730f35c34bdfe208c478`. The commit's root tree is `a52de1f8ef40e9dcf0d64b6542ee0ec94ae2edbe`.
- **Test revisions** (each run from its own clean detached checkout):
  - adversary v2 `63c6adbbceecfa2147453ad261d7ffcc95649a94`, suite tree `25429c14…09a3`;
  - adversary v3 `d815d96b3a556ceb1a5ce1fee2577f133c2dfe89`, suite tree `ec553aa3…f7f8`;
  - auditor tools `9eeeae1d` (audit_probe.py), `31ba973b` (timing_probe.py) and `236ecf35` (audit_probe2.py).
- **Spec and checksum:** `pocketful/spec/stage-1.md`, SHA-256 `65497dea09a8b432598c71662320cf66c3550e183cfd76e2d7f97318e0d30aa4` (LF form `f5e4c644…38a6`), at kickoff `803560d2`.
- **Register:** r2, analyst@`8e913edb`, which includes the r1 rows.
- **Obligations covered:** every r2 spec row (S1-001…S1-206, S1-900…S1-903) has reproduced auditor evidence; see the table below. The decision rows D-01…D-32 were tested as decisions, not as spec.

## Commands the auditor ran, in a clean environment
All runs used the auditor's own clone `C:\nexus\dev\band-kit\clones\auditor-s1-1`, a fresh clone detached at `beeaec72` whose `status --porcelain` is empty. Images were built with `--no-cache`, and containers were started by the auditor with `--cpus 2 --memory 2g`. No other seat's process, container or log was reused. The auditor did not reuse `~/adv-venv`; the adversary suite ran in its own `~/aud-venv`, pinned to the suite's `requirements.txt`.

| Event | Command (abridged; full text in `events/`) | Result |
|---|---|---|
| 001 | Provenance and inspection: `git rev-parse`, log, diff, ls-files, grep of `src/` | PASS |
| 002 | `harness run --track pocketful --repo …/clones/auditor-s1-1 --stage 1 --out …/checks/fskit-001-s1-audit-1` (host mode) | stage 1: 147/147, 0 skipped |
| **003** | **`harness run … --stage 1 --mode isolated --out …/checks/fskit-001-s1-audit-2`** | **stage 1: 147/147, 0 skipped; revision beeaec72; state completed** |
| 004 | `audit_probe.py` at `0ed8f44` | 60/61. The 1 failure was an **auditor tool bug** (bad expectation); preserved and superseded by 005 |
| 005 | `audit_probe.py` at `9eeeae1d`, containers A and B | 61/61 |
| 006 | `timing_probe.py` against container C with PORT unset | 4/4 |
| 007 | Adversary suite v2 via its `run.sh`, run by the auditor | 301/301 |
| 008 | Adversary CONC tests (v2), 3 repetitions, each with a fresh image | 3 × 20/20 |
| 009 | `audit_probe2.py`, closing the rows analyst routed in 4837ffaf | 10/10 |
| 010 | Adversary suite v3 (addendum 9de21f5f) via its `run.sh`, run by the auditor | 325/325 |
| 011 | Route surface and evidence secret scan | PASS |

**Reports and logs** (SHA-256):

| Artifact | SHA-256 |
|---|---|
| `checks/fskit-001-s1-audit-2/report.json` (isolated) | `fb03079c4f363ca7ee8c56546d0670bbc01263d25da0a4ae8f88af156465a47b` |
| `checks/fskit-001-s1-audit-2/stage-1.log` | `7cebe52590f6644dc1be0a80609f4dfeefe1f3d58a3b3f995afcd4dd7b3e2505` |
| `checks/fskit-001-s1-audit-1/report.json` (host) | `d9787fcc19c8fa77a1ee9efeba74106898f63958cca8c17a395bf34be868a28a` |
| `checks/fskit-001-s1-audit-advsuite-1/results.json` | `d605066c…abaaa` |
| `checks/fskit-001-s1-audit-advsuite-2/results.json` | `0bb69af0…55ffc` |

Each events file holds the full artifact lists with their SHA-256.

**Provenance:** `report.json` reports `revision=beeaec72`. The runner logs confirm `clone_head=beeaec72`, `stage1_tree=347efba5` and a clean status. The test revisions were recorded from clean checkouts, so logs, source revision and test revision all refer to the same candidate.

**Counts, failures and skips:**
- Official harness: 147 collected, 147 passed, 0 failed, 0 errors, 0 skipped, 0 deselected.
- Adversary suite, reproduced: 325/325.
- Auditor probes: 75/75 on their final revisions.
- The only failure recorded is event 004, which was an auditor tool bug and is preserved as evidence.

**Next-stage probe, reported separately:** stage 2 fails in both runs, as expected. The first UI test fails (a Playwright `Page.fill` timeout) because a stage-1 image has no UI. This is not a defect, and nothing was changed to influence it.

**Harness integrity:** from WSL, git lists 66 files as modified in the kickoff checkout. `git diff --ignore-cr-at-eol` is empty, and with `core.autocrlf=true` the only entry is an untracked `.venv/`. So the difference is line endings only, and the harness itself is unmodified.

## Coverage against register r2
Evidence key:
- H = official harness (isolated, event 003)
- P = auditor probe (005/006/009)
- A = adversary suite reproduced by the auditor (007/008/010)
- I = auditor inspection (001/011)

| Rows | Evidence |
|---|---|
| S1-001, 002, 003 (invariants) | P005 (50-way overdraft storm, 20-way pay race with decline/cancel), A007/008/010 (proxy method per the r2 restatement), H |
| S1-004 | I011: exactly 16 spec routes, no deposit or withdraw surface |
| S1-010, 011, 012, 013, 013a, 014 | I001; auditor `docker build` per RUN.md; H003 isolated; P006 (PORT unset → 8080; reset100 0.43 s; login50 max 0.26 s); A |
| S1-015…S1-021 | P005/P009 (content type on every route, unknown fields everywhere, ID lengths, no ID collision), A, H |
| S1-030…S1-047 | P005/P009 (numeric forms, feed contract, S1-047 negative balance), A (EUR/JPY/BHD, near 2^53, seeded states), H |
| S1-050…S1-058 | P005/P009, A (13 malformed, 27 field-rule and 79 auth cases), H |
| S1-060…S1-069, S1-06A | P006 (signup races), P009 (D-09), A, I001 (scrypt), H |
| S1-070…S1-080 | P005 (15-way same key on all 5 paths, claimed-key precedence, cross-path, cross-user), A, H |
| S1-090…S1-150, S1-145, S1-206 | P005 (pay, decline and cancel lifecycle; zero-share pay), A, H |
| S1-160…S1-162 | P005 (the split table, including 1e9/5), A, H |
| S1-170…S1-181 | P005 (XC A→B continuity), P009 (tampered state, export during 16 writers), A (XC), I011 (S1-181) |
| S1-190…S1-205 | P005 (netting, rollback, D-28 precedence, 0/32/33 entries, private members hidden from the operator, concurrent settlements), A |
| S1-900…S1-903 | I001 (no stage-2 code, no test detection), H002/003 (probe fails as expected), this record and events 001–011 |

## Blocking findings or reproduction limits
- **No blocking findings.** Neither the adversary nor the auditor found a product defect.
- **Limitations** (recorded, not waived as defects):
  1. S1-001/002: transient cross-wallet atomicity is observed only through proxies, as stated in r2.
  2. All runs used one host and one Docker daemon. `--cpus 2` is a CFS quota on a 6-CPU host, not dedicated hardware.
  3. Concurrency repetitions: 3 by the auditor plus 10 by the adversary. Rarer races could go unseen.
  4. The shipped harness checks are a partial public sample. **This acceptance makes no claim about hidden evaluation checks.**
  5. Decision rows (D-xx) are the band's interpretations of unspecified points, not spec facts. An evaluator could read them differently.
  6. The passwords use scrypt N=2^12. That is below common guidance, but it is a password-hashing function as §6 requires. It was a declared tradeoff to stay within the S1-013a limit.

## Room references
- Handoff 191ed446…f58d69a0 (parts 1–7) and 59c3f37a (part 8, r2).
- Candidate 3d6a464f, 408b641f, fc3c5582, a993bc4e.
- Adversary bundle b2c7fb5d and addendum 9de21f5f.
- Analyst routing 4837ffaf.
- Auditor review c3740b90, interim 4827f0a2 and reproduction status e766a983.

## Change required and recipient
None for stage 1.

## Next action authorized by the dispatch
1. The analyst publishes the STAGE_ACCEPTED checkpoint in STAGE-REGISTER, using the checkpoint below, and starts stage 2.
2. The implementer copies the accepted `stage-1/` tree (`347efba5`) into `stage-2/`.
3. `stage-1/` must not change from now on. Any later change to it invalidates this acceptance until it is rechecked.

ACCEPTED is an internal acceptance of the identified candidate. It is not a statement about hidden tests or an official event result. A later product change requires a new decision.

---

# STAGE_ACCEPTED checkpoint: fskit-001 · stage 1

| Field | Value |
|---|---|
| Stage | 1 (pocketful) |
| Candidate commit | `beeaec72ff53fa75469c5f09236a786632f21fd8` |
| Stage tree hash (`stage-1`) | `347efba502629e5b5bbd730f35c34bdfe208c478` |
| Verdict | ACCEPTED by auditor-thgx, 2026-09-28T21:35Z |
| Final isolated harness | `checks/fskit-001-s1-audit-2/report.json` `fb03079c…a47b`: stage 1 pass 147/147 |
| Evidence | branch `auditor`: `evidence/runs/fskit-001/stage-1/auditor/` (events 001–011, c1/*, VERDICT-c1.md); adversary evidence at adversary@7eed1b73 |
| Repair cycles used | 0 of 5 |
| Infrastructure retries used | 0 (per-command limit 2) |
| Stage time | started 2026-09-28T20:40:47Z; accepted ~21:35Z; about 55 of 360 min used, about 305 min left (deadline 2026-09-29T02:40:47Z) |
| Run total | about 55 of 1440 min used; new work stops at 2026-09-29T20:10:47Z |
| Financial | No cap is available. Spend is measurable only afterwards from token counts, which this seat cannot read at run time. |

## Auditor METRICS

`fskit-001,1,auditor,auditor-thgx,Claude Code,claude-opus-5-5,2026-09-28T20:47:00Z,2026-09-28T21:35:00Z,~2880,unknown,unknown,unknown,unknown,,true,wall clock from shell/room timestamps,token counts are not exposed to this seat at run time`
