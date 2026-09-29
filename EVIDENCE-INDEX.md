# Evidence index

Every claim the README makes, the file that backs it, and how to check it yourself. Paths under
`evidence/` are relative to `evidence/runs/fskit-001/`. Message ids are ids in `room.json`.

| Claim | Evidence | Revision | How to check |
|---|---|---|---|
| **All four stage folders claim their own stage on the public harness** | [`final/harness-isolated/INDEX.md`](evidence/runs/fskit-001/final/harness-isolated/INDEX.md) and the 31 original reports beside it | `181947069` | `sha256sum -c fskit-001-all-final-1.SHA256SUMS` in that folder; or run `python -m harness run --track pocketful --repo <fresh clone> --all --mode isolated --out <new dir>` from the kickoff at `803560d2` |
| **The product trees published are the ones that passed** | [`final/FINAL-VERIFICATION.md`](evidence/runs/fskit-001/final/FINAL-VERIFICATION.md) | `181947069` → `HEAD` | `git diff --stat 181947069 HEAD -- stage-1 stage-2 stage-3 stage-4` prints nothing |
| **One human message in the whole room** | `room.json`, message `3f95ab60` | — | count events whose `senderType` is `User`: there is one, a `text` of 16,390 characters |
| **Each stage after the first was opened by the analyst** | `room.json`: handoffs at 21:39:14Z, 23:10:50Z, 00:10:43Z, all from `analyst-thgs` | — | filter `text` events by `STAGE N HANDOFF`; the only human message is the dispatch, before all of them |
| **No human wrote product code** | git history | all | `git log --format=%an -- stage-1 stage-2 stage-3 stage-4 \| sort \| uniq -c` → 21 commits, all `implementer-thgt` |
| **Stage 1 accepted with no repair** | [`stage-1/auditor/VERDICT-c1.md`](evidence/runs/fskit-001/stage-1/auditor/VERDICT-c1.md), message `72be202b` | `beeaec72` | the verdict's own table: isolated harness 147/147, adversary suites 301/301 and 325/325 |
| **Stage 2 candidate rejected for `F2-01`** (found by adversary, reproduced by auditor) | [`stage-2/auditor/VERDICT-c1.md`](evidence/runs/fskit-001/stage-2/auditor/VERDICT-c1.md), message `4fc4757a` | `f1f0847d` | the verdict cites the adversary's two failing UI tests at 375 and 1280 px and the auditor's own reproduction |
| **Stage 2 accepted after repair** | [`stage-2/auditor/VERDICT-c2.md`](evidence/runs/fskit-001/stage-2/auditor/VERDICT-c2.md), message `4ced8436` | `68583038` | — |
| **Stage 3 candidate rejected for `F3-A01` and `F3-01`**, with every suite green | [`stage-3/auditor/VERDICT-c1.md`](evidence/runs/fskit-001/stage-3/auditor/VERDICT-c1.md), message `b8d9c67c` | `e4d35083` | the verdict's table of passes on the same candidate, then the OOM at 4,761 reads |
| **The heap crash is fixed** | [`stage-3/auditor/VERDICT-c2.md`](evidence/runs/fskit-001/stage-3/auditor/VERDICT-c2.md), event 013, message `11dbc577` | `51a0bdd1` | start `stage-3/` or `stage-4/` with `--cpus 2 --memory 2g`, then `node test/perf/statement_memory.js http://127.0.0.1:8080 20000`; the auditor saw 20,000/20,000 at 39.7 MiB |
| **Stage 4 accepted** | [`stage-4/auditor/VERDICT-c1.md`](evidence/runs/fskit-001/stage-4/auditor/VERDICT-c1.md), message `10381cd3` | `18194706` | — |
| **All six upgrade pairs verified** | [`UPGRADE-REPORT.md`](evidence/runs/fskit-001/UPGRADE-REPORT.md), `final/upgrade-*` | per pair | 1→2, 1→3, 2→3, 1→4, 2→4, 3→4, each in separate containers with a populated export |
| **The whole chain in one place** | [`STAGE-REGISTER.md`](evidence/runs/fskit-001/STAGE-REGISTER.md) | — | every candidate, verdict and checkpoint, timestamped |
| **Mandates name no product** | `mandates/` | `HEAD` | `python -m harness check --track pocketful <repo>` → `ok`; or read one end to end |
| **Spend ≈ $136, mostly cache reads** | [`final/USAGE.json`](evidence/runs/fskit-001/final/USAGE.json) | — | the raw `band usage agents --json` rows for the four seats, with capture time; an estimate, not a bill |
| **Only credentials were redacted** | [`REDACTION.md`](REDACTION.md) | — | `grep -c "jrx_\[REDACTED\]" room.json` → 50; no `text` event contains one |

What none of this shows: that the hidden evaluation passes. Everything above is the public checks,
the band's own evidence, and what anyone can re-run.
