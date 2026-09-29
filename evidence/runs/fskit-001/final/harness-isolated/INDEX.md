# Final all-stage harness run — the original reports

These are the files the official harness wrote during the auditor's final verification, copied
**unchanged** into the repository so they can be opened without access to the machine that ran them.
Nothing here was regenerated or edited.

| | |
|---|---|
| Original location | `C:\nexus\dev\band-kit\checks\fskit-001-all-final-1\` (outside the repository) |
| Kickoff | `band-ai/dark-factory-wearedevs` at `803560d2a678ace1414465c098eb0ab5380ffade` |
| Revision checked | `181947069ba933c39661835296e89a891847c2a3`, in the auditor's clean clone `clones/auditor-final-1` |
| Mode | `isolated` |
| Recorded in | [`../FINAL-VERIFICATION.md`](../FINAL-VERIFICATION.md), section 1 |

Command, exactly as the auditor ran it:

```
wsl -e bash -lc 'cd /mnt/c/nexus/dev/dark-factory-wearedevs && ~/df-venv/bin/python -m harness run --track pocketful --repo /mnt/c/nexus/dev/band-kit/clones/auditor-final-1 --all --mode isolated --out /mnt/c/nexus/dev/band-kit/checks/fskit-001-all-final-1'
```

## Integrity

`fskit-001-all-final-1.SHA256SUMS` is the auditor's manifest of all 31 files. From this directory:

```
sha256sum -c fskit-001-all-final-1.SHA256SUMS
```

returns `OK` for all 31. The manifest's own SHA-256 begins `d1e163dc` and ends `dc15`, and
`summary.json` is `aa80c76b30488b5f0b236535bc44dfc1543dfaf2aa2c6339e9eb4abaf48ec75c` — the two values
`FINAL-VERIFICATION.md` cites.

## What each folder passed

Each stage folder is run against every suite up to its own, plus the next stage's suite, which it is
expected to fail.

| Folder | Suite 1 | Suite 2 | Suite 3 | Suite 4 | Claims |
|---|---|---|---|---|---|
| `stage-1/` | 147/147 | *fails, as it must* | | | stage 1 |
| `stage-2/` | 147/147 | 35/35 | *fails, as it must* | | stage 2 |
| `stage-3/` | 147/147 | 35/35 | 6/6 | *fails, as it must* | stage 3 |
| `stage-4/` | 147/147 | 35/35 | 6/6 | 5/5 | stage 4 |

Zero skipped, zero errors, in every run. The counts come from the `*.counts.json` files beside each
`report.json`.

## Read this before quoting the numbers

- **`preview: true`** in `summary.json` means these are the *public* checks shipped with the kickoff.
  The harness says so itself: they are a portion of the tests applied before judging. A pass here is
  directional, not a promise about the hidden evaluation.
- **Stage 4 has no next stage.** For stages 1–3, `overshoot: null` is a real result: each folder
  failed the following suite, which is the freeze rule holding. For stage 4 there is no stage 5 to
  fail, so its `overshoot: null` is not an additional test passed.
