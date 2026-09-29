# Final report: fskit-001 (analyst, hugo.valer/analyst-thgs)

Run fskit-001 · Track pocketful · Target stage 4 · Room 83139981-6931-481f-b8a4-d6f6ca9d41eb · Dispatch message 3f95ab60-b690-489a-9370-80830f518f3f (enqueued 2026-09-28T20:40:47Z) · Kickoff 803560d2a678ace1414465c098eb0ab5380ffade.

This report distinguishes three things:
- **Target:** stage 4.
- **Internal acceptance:** the auditor's verdicts on exact revisions.
- **External evaluation:** unknown until the organisers judge; no claim is made about hidden tests.

## Outcome

- **Internally accepted stages:** 1, 2, 3 and 4. The verified contiguous prefix is **1–4**.
- **Final all-stage verification (S4-903): PASS.** Record: auditor@3430e17424dd46f1621ac532b795acbfb18c4a35, `evidence/runs/fskit-001/final/FINAL-VERIFICATION.md`, room message 06de0f65.
  - The auditor made a fresh clone of main at the final product candidate **181947069ba933c39661835296e89a891847c2a3**.
  - `harness run --all --mode isolated` wrote to `checks/fskit-001-all-final-1`: folder N claims stage N for N = 1..4, with 0 failed and 0 skipped.
  - The auditor followed every RUN.md independently.
  - The UI passed at 375 and 1280 px on stages 2–4.
  - All six upgrade pairs were reproduced fresh.
- **Public stage claim** (shipped checks only, directional): `claimed stage: 4`, highest contiguous 4.
- **Terminal state:** FOUR_STAGES_VERIFIED. This is internal verification only.

## Per stage

| Stage | Scope (specs) | Accepted candidate | Stage tree | Verdict (room) | Isolated harness (auditor) | Candidates / repairs | Wall time |
|---|---|---|---|---|---|---|---|
| 1 | stage-1.md | beeaec72ff53fa75469c5f09236a786632f21fd8 | 347efba502629e5b5bbd730f35c34bdfe208c478 | ACCEPTED 72be202b (auditor@fe7d0663) | 147/147 | 1 candidate, 0 repairs | 20:40:47Z → about 21:36Z (about 55 min) |
| 2 | stage-1–2 | 68583038e7ea52429b062af0f775d3cbfd96b7c3 | a8e6178d7b9d5ba4dde4999e78730fa99ff80fe2 | c1 f1f0847d REJECTED 4fc4757a; c2 ACCEPTED 4ced8436 (auditor@fa5f5186) | 147 + 35 | 2 candidates, 1 repair (F2-01) | 21:37:47Z → about 22:45Z (about 68 min) |
| 3 | stage-1–3 | 51a0bdd1c48207fb3e22fb163d1fd7972123aa3d | f586c4995f31122e887e462d54590b955f6b45a2 | c1 e4d35083 REJECTED b8d9c67c; c2 ACCEPTED 11dbc577 (auditor@b8b5a9dd) | 147 + 35 + 6 | 2 candidates, 1 repair (F3-01, F3-A01/F3-02) | 22:47:28Z → about 00:08Z (about 81 min) |
| 4 | stage-1–4 | 181947069ba933c39661835296e89a891847c2a3 | c7d50a979b158832f15055289bf8f44b5f5edb8b | ACCEPTED 10381cd3 (auditor@661a64d3) | 147 + 35 + 6 + 5 | 1 candidate, 0 repairs | 00:08:35Z → about 00:43Z (about 35 min) |

Each stage-N folder started as a byte copy of the accepted stage-(N−1) tree, in its own commit (327e7a4d, e8886337, 0a2ee743), and was extended only inside its own folder. Every earlier tree was re-verified unchanged at every later candidate and in the final clone.

## Coverage

Numbered obligation registers are under `evidence/runs/fskit-001/stage-N/OBLIGATIONS.md`, with the source section, boundary, method and state of each row:

| Stage | Revisions | Challenged by | Rows | Decisions |
|---|---|---|---|---|
| 1 | r1 → r2 | the auditor's coverage review and the adversary's R1 findings (24) | S1-001…S1-206, S1-900…903 | D-01…D-32 |
| 2 | r1 → r3 | B1–B9, R2-01…R2-21, F2-01 | S2-001…S2-904 | D2-01…D2-19 |
| 3 | r1 → r2 | C1–C7, R3-01…R3-16 | S3-001…S3-904 | D3-01…D3-21 |
| 4 | r1 → r2 | E1–E4, R4-01…R4-11 | S4-001…S4-903 | D4-01…D4-13 |

Decisions are kept apart from source requirements and were tested as decisions. One analyst error was corrected in the open: stage-2 register r3 re-labelled a clause the analyst had recorded as source text as decision D2-19, after the F2-01 dispute. Every earlier row stayed in force at later stages. The auditor re-verified them on each later folder (suites 1..N, plus the adversary's earlier suites re-run against the later folder).

## Independent verification

- **Implementer (implementer-thgt):** the only seat that wrote production code, under stage-N/.
- **Adversary (adversary-thgz):** wrote independent black-box suites derived from the specs, not from the shipped tests. Final test revisions: stage-1 v3 d815d96b; stage 2 bdb21efc; stage 3 9e49497e; stage 4 854b2cc4 plus v2 c60966f8. It also ran real-browser suites at 375 and 1280 px, concurrency repetitions, cross-container upgrades from the accepted images, and risk probes.
- **Auditor (auditor-thgx):** reproduced everything in its own clean clones, `--no-cache` images, fresh containers and its own venv. It re-ran the adversary suites and its own probes, and issued every verdict.
- **Defects caught and fixed through the room:**
  - F2-01: the capture draft was lost after a refusal; decision row, low severity.
  - F3-01: a closed hold was never expired under an earlier known_at; spec row.
  - F3-A01/F3-02: a JavaScript heap out-of-memory crash under sustained statement reads, caused by unbounded snapshots; spec row, reproduced independently by the auditor and the adversary.

  Each was reproduced by the implementer, repaired in a new commit and re-audited from scratch. The rejected candidates and their evidence are preserved.

## Upgrade evidence

`evidence/runs/fskit-001/UPGRADE-REPORT.md` lists all six pairs as PASS:

| Pair | First reproduced (auditor, at stage acceptance) | Stage record |
|---|---|---|
| 1→2 | 7/7 | 4ced8436 |
| 1→3, 2→3 | 14/14 | 11dbc577 |
| 1→4, 2→4, 3→4 | 14/14 | 10381cd3 |

All six were reproduced again from final-clone images in S4-903. Each pair used two containers, populated exports, and receipts replaying byte-identical (D2-13). Snapshot and credential contents were never stored in the repo or the room.

## Unresolved issues and limitations

- **D3-18:** stage-2 exports record no void time, so a stage-2 voided hold imported into stage 3 or 4 releases at the import time. That is an approximation which errs on the side of money safety. **D3-21** stops that approximation from blocking unrelated corrections.
- **D4-13:** after 3→4, stage-3 snapshot pages gain `refund_of: null`. Values and order are identical, but the bytes are not.
- **Lost capture response:** it is shown with the refusal style. The auditor judged S2-031 satisfied, and this is recorded as a limitation.
- **Not tested:** literal `+` in query instants (D3-20) only partly; a 32-item multi-settlement batch; scale beyond 500 payments; a small number of concurrency repetitions; runs on one host only.
- **Carried design tradeoffs:** state is in memory only (§2 permits this); scrypt runs at N=2^12 to meet the 5 s limit under 50 concurrent logins.
- **Hidden evaluation checks are unknown.** The public samples are 79%, 35%, 9% and 16% of each suite.

## Measured usage

- **Wall clock:** dispatch at 2026-09-28T20:40:47Z; final verification PASS at about 2026-09-29T00:52Z; about 252 of 1440 run minutes used. Per-stage times are in the table above.
- **Stage limits:** within every limit (≤ 81 of 360 min per stage; 2 of 20 repair cycles; 0 infrastructure retries).
- **Seats:** four Claude Code seats, each reporting model **claude-opus-5-5**. run-config.json lists claude-opus-5 (D-17 discrepancy recorded).
- **Tokens and cost: unknown.** No seat's runtime exposes token counts, and no provider spend cap was configured, so no financial ceiling could be enforced. Cost can only be computed afterwards from provider-side usage at list rates.
- **Commits** in main at 181947069 plus the evidence merges:

| Author | Commits |
|---|---|
| implementer-thgt | 21 |
| adversary-thgz | 20 |
| auditor-thgx | 27 |
| analyst-thgs | 44 |
| participant (pre-dispatch kit) | 2 |

  History was never amended, rebased or squashed.

## Evidence commits and product-tree preservation

- The final product candidate is 181947069ba933c39661835296e89a891847c2a3.
- After the final verification, the analyst merges the `analyst`, `adversary` and `auditor` evidence branches into main with evidence-only non-fast-forward merges.
- The merge commit and the post-merge tree check are recorded in STAGE-REGISTER.md and posted in the room. Every stage-N tree must equal its accepted tree after the merge.

## Room references (main)

- **Dispatch and acknowledgement:** 3f95ab60 / af21ebd8.
- **Handoffs:**

| Stage | Parts | Amendment |
|---|---|---|
| 1 | 191ed446 … f58d69a0 | 59c3f37a |
| 2 | b2ac2889 … 18de3a4a | a50d8930 |
| 3 | 4d96a517 … bcc439cd | 2bdd159f |
| 4 | 4524029d … 26ce1c7f | 366f3ea3 |

- **Repairs:** stage 2 f8850d4f … 98a32665; stage 3 839d4053 … bc21045c.
- **Verdicts:** 72be202b, 4fc4757a, 4ced8436, b8d9c67c, 11dbc577, 10381cd3. Final verification: 06de0f65.

Submission is not complete: the human exports the real room as room.json after the work has ended and completes the submission documentation. This report does not manufacture room.json.
