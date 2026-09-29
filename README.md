# Four seats, and the payments service they built

*[Leer en español](README.es.md)*

**Track:** Pocketful · **Team:** four-seats · **Licence:** MIT

Four agent seats in one BAND Desktop room: an **analyst** who turns the specification into numbered
obligations, an **implementer** who builds, an **adversary** who tries to refute what was built, and
an **auditor** who reproduces the evidence before anything is accepted. No seat accepts its own
work.

**One human message exists in this room.** It authorised all four stages and said nothing
afterwards. Every stage after the first was opened by the analyst itself, four minutes after the
previous one was accepted.

## What is here

| | |
|---|---|
| Stages | **4 of 4**, each frozen, each independently audited |
| Public harness, `--all --mode isolated`, from a fresh clone | every folder claims its own stage, **100% of its checks**, no overshoot |
| Auditor rejections | **2**, both repaired and re-audited inside the run |
| Wall-clock | **4 h 14 min**, dispatch to final report |
| Model spend | **~$136**, estimated at list prices |

One of those rejections is the reason this repository is worth reading. On a stage-3 candidate the
official harness passed everything — 147 + 35 + 6 checks, isolated mode, zero skipped, plus 150/150
of regression and 14/14 of migrations — and the auditor rejected it anyway, because its own probe
made the service **crash with a heap out-of-memory after 4,761 statement reads** and lose all state.
`FACTORY.md` has both in full.

## Map

- **`FACTORY.md`** — the design, the measured results, both rejections, what it cost, and the four
  things we would tell the next team. Start here.
- `mandates/` — the four standing instructions, exactly as loaded into the seats. Read one end to
  end: it never says what the product is.
- `stage-1/` … `stage-4/` — one self-contained service per stage. Each builds and runs on its own,
  with no dependency on the others.
- `verification/adversary/stage-N/` — the adversary's own test suites, versioned, separate from
  production code.
- `evidence/runs/fskit-001/` — the record: obligations, handoffs, verdicts, harness runs, upgrade
  reports. Every claim links an obligation, a product revision, a test revision, a command and a
  real result.
- `room.json` — the complete session exported from BAND. The single human message is easy to find.

## Running it

Each stage folder has its own `RUN.md` and builds in one command with no network at run time. To
check a stage against the official harness, from the kickoff checkout:

```
python -m harness run --track pocketful --repo <this repo> --stage 1 --mode isolated --out <new dir>
```

`--stage 2`, `3` and `4` do the same for the later folders, and `--all` verifies the whole chain.
Stages 2 to 4 serve a browser UI; the harness exercises it at 375 px and 1280 px.

## What we are not claiming

Two rejections is not many, and we cannot tell from inside the run whether a third defect slipped
past all four filters. One run is one data point. The auditor reproduces but does not run mutation
testing, so a check that passes against deliberately broken code would still look fine here. The
cost figures are estimates from token counts, not a bill. `FACTORY.md` says all of this at greater
length, because a factory that hides its limits is not one you would reuse.
