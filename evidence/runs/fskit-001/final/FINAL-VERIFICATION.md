# fskit-001 · S4-903 · Final all-stage verification (auditor)

- **Auditor:** auditor-thgx (hugo.valer/auditor-thgx), model `claude-opus-5-5`.
- **Run window:** 2026-09-29T00:46Z → 00:52Z (UTC).
- **Outcome: PASS.** All four stage folders are verified on the final submission candidate. This is an internal verification only: **it makes no claim about hidden evaluation checks**, and the shipped checks are a partial public sample.

## Submission candidate (fresh clone)
- **Clone:** `C:\nexus\dev\band-kit\clones\auditor-final-1`, a fresh `git clone` of `C:\nexus\dev\band-kit\result`, detached at `main`. `status --porcelain` is empty.
- **Commit:** **`181947069ba933c39661835296e89a891847c2a3`**. This equals the ACCEPTED stage-4 candidate; `main` had not moved.

| Folder | Tree hash | Accepted at | Verdict message |
|---|---|---|---|
| `stage-1/` | `347efba502629e5b5bbd730f35c34bdfe208c478` | beeaec72 | 72be202b |
| `stage-2/` | `a8e6178d7b9d5ba4dde4999e78730fa99ff80fe2` | 68583038 | 4ced8436 |
| `stage-3/` | `f586c4995f31122e887e462d54590b955f6b45a2` | 51a0bdd1 | 11dbc577 |
| `stage-4/` | `c7d50a979b158832f15055289bf8f44b5f5edb8b` | 18194706 | 10381cd3 |

Every tree equals its accepted tree, so none of the evidence merges changed an accepted product tree.

## 1. Official harness `--all --mode isolated`
**Command:**

```
wsl -e bash -lc 'cd /mnt/c/nexus/dev/dark-factory-wearedevs && ~/df-venv/bin/python -m harness run --track pocketful --repo /mnt/c/nexus/dev/band-kit/clones/auditor-final-1 --all --mode isolated --out /mnt/c/nexus/dev/band-kit/checks/fskit-001-all-final-1'
```

- Exit 0. Kickoff `803560d2`, which is clean apart from CRLF line endings and an untracked `.venv/`.
- `summary.json` sha256 `aa80c76b30488b5f0b236535bc44dfc1543dfaf2aa2c6339e9eb4abaf48ec75c`: `mode: isolated`, and folders 1–4 are each `claimed: true`, `share 1.0`, `highest_contiguous` 1/2/3/4.
- The full artifact list is in `checks/fskit-001-all-final-1.SHA256SUMS` (31 files), itself sha256 `d1e163dc…dc15`.

| Folder | Suites run (collected / passed / failed / skipped) | Claimed | report.json sha256 |
|---|---|---|---|
| stage-1 | 1: 147/147/0/0 | 1 | `c40fb58e…b321` |
| stage-2 | 1: 147/147/0/0 · 2: 35/35/0/0 | 2 | `98d21068…0e6f` |
| stage-3 | 1: 147 · 2: 35 · 3: 6/6/0/0 | 3 | `a20a7216…0e6f` |
| stage-4 | 1: 147 · 2: 35 · 3: 6 · 4: 5/5/0/0 | 4 | `5a9a6455…028f` |

**Final four-folder claims:** stage-1 claims 1, stage-2 claims 2, stage-3 claims 3, stage-4 claims 4. The highest contiguous stage is **4**.

## 2. Each RUN.md followed independently
For each folder, the documented command `docker build -t pocketful-stage-N . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-stage-N` was run from inside the folder, with `-d` added so the auditor could probe it. The log is `final/runmd-check.log` (sha256 `bb08ad4d…1081`).

| Folder | Build | Image | First healthy | Health body | UI (`Accept: text/html`) |
|---|---|---|---|---|---|
| stage-1 | exit 0 | `sha256:91dca604…8919` | 774 ms | `{"status":"ok"}` | n/a (API only) |
| stage-2 | exit 0 | `sha256:8b8f2f91…84ee` | 847 ms | ok | `/` 200 text/html; `/requests` 200 text/html |
| stage-3 | exit 0 | `sha256:9c0f03ab…3056` | 695 ms | ok | same |
| stage-4 | exit 0 | `sha256:f57104bd…42fb` | 699 ms | ok | same |

## 3. Required UI at 375 and 1280 px (final images)
The tool was `s2_ui_probe.py`, with Chromium 153 run by the auditor. Each image was checked for:
- routes and testids, and formats;
- decimal rules, with a network log;
- double submit, refused pay, latest-refresh-wins, lost response and retry;
- stale buttons, split preview, and authorize/capture/void;
- auth and logout, worst-case layout, XSS, contrast, labels and focus.

| Image | Result | Results sha256 |
|---|---|---|
| stage-2 | **44/44** | `affe12c5…98a9` |
| stage-3 | **44/44** | `19494c80…75d7` |
| stage-4 | **44/44** | `229b2602…07a9` |

Screenshots are in `final/ui-stage-N/`.

## 4. All six upgrade pairs against the final trees (fresh containers, images built from the final clone)
| Pair | Tool | Result | Results sha256 |
|---|---|---|---|
| 1→2 | `s2_upgrade_probe.py` (API, and D2-18 browser at 375 and 1280) | **7/7** | `984a2dfd…4efc` |
| 1→3, 2→3 | `s3_upgrade_probe.py` | **14/14** | `fb12e03b…4b59` |
| 1→4, 2→4, 3→4 | `s4_upgrade_probe.py` (including a stage-3 snapshot paging per D4-13) | **14/14** | `0da495dd…4d29` |

Each pair checks:
- a populated source export;
- old tokens valid and destination credentials removed;
- **byte-identical replays of the original receipts**;
- the imported state exercised: history, corrections, refunds, batches, captures and pending requests;
- conservation.

All six pairs were reproduced fresh here, so no earlier pair evidence was reused.

## Remaining budgets at the end of the final verification
- **Stages:** 1 used 0 of 5 repairs; 2 used 1; 3 used 1; 4 used 0. No infrastructure retries were used in any stage.
- **Run:** started 2026-09-28T20:40:47Z, final verification done at about 00:52Z, so about 251 of 1440 minutes were used. New work stops at 20:10:47Z.
- **Financial:** no cap was available. Token counts could not be read by the auditor seat at run time.

## Limitations (carried from the stage verdicts, not waived)
- **D3-18:** a stage-2 void releases at the import time, an approximation, because stage-2 exports record no void time.
- **D4-13:** 3→4 snapshot pages are not byte-equal (`refund_of` is added), while receipt replays are byte-identical.
- **D-xx rows** are the band's interpretations of unspecified points.
- **Single host:** every run used one Docker daemon with CFS `--cpus 2`, and concurrency repetitions were limited.
- **Hidden evaluation checks:** no claim is made. The public stage-3 and stage-4 samples are 6 and 5 tests.

## Rejected candidates (preserved)
- Stage 2: `f1f0847d` (F2-01 / D2-19).
- Stage 3: `e4d35083` (F3-A01/F3-02 heap OOM crash; F3-01).

Their records are `stage-2/auditor/VERDICT-c1.md` and `stage-3/auditor/VERDICT-c1.md`.

`fskit-001,final,auditor,auditor-thgx,Claude Code,claude-opus-5-5,2026-09-29T00:46:00Z,2026-09-29T00:52:00Z,~360,unknown,unknown,unknown,unknown,,true,wall clock,token counts not exposed to this seat`
