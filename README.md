<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/logo-dark.svg">
    <img src="docs/brand/logo-light.svg" alt="Four Seats Factory" width="440">
  </picture>
</p>

# Four seats, and the payments service they built

*[Leer en español](README.es.md)*

**Track:** Pocketful · **Team:** four-seats · **Licence:** MIT

**[Video (3 min)](https://youtu.be/oiodvnGptt0)** · **[Live demo](https://four-seats-factory.onrender.com/login)** ·
**[Presentation (PDF)](docs/presentation/four-seats-factory.pdf)** ·
**[Evidence index](EVIDENCE-INDEX.md)** · **[How the factory works](FACTORY.md)**

Four agent seats in one BAND Desktop room: an **analyst** who turns the specification into numbered
obligations, an **implementer** who builds, an **adversary** who tries to refute what was built, and
an **auditor** who reproduces the evidence before anything is accepted. No seat accepts its own
work.

**One human message exists in this room.** It authorised all four stages and said nothing
afterwards. Every stage after the first was opened by the analyst itself, with no human input.

## What is here

| | |
|---|---|
| Stages | **4 of 4**, each frozen, each accepted by the auditor |
| Public harness, `--all --mode isolated`, from a fresh clone | every folder claims its own stage with **100% of its public checks**; stages 1–3 fail the next suite, as they must |
| Candidates rejected | **2**, carrying **3 findings** — two found by the adversary, one by the auditor — all repaired and re-audited inside the run |
| Wall-clock | **4 h 14 min**, dispatch to final report |
| Model spend | **~$136**, estimated at list prices; not a bill |

The harness figures are the **public** checks shipped with the kickoff. They are a portion of what is
applied before judging, and we make no claim about the hidden evaluation.

One of those rejections is the reason this repository is worth reading. On a stage-3 candidate the
official harness passed everything — 147 + 35 + 6 checks, isolated mode, zero skipped, plus 150/150
of regression and 14/14 of migrations — and the auditor rejected it anyway, because its own probe
made the service **crash with a heap out-of-memory after 4,761 statement reads** and lose all state.
After the repair, 20,000 reads returned 200 and the container sat at 39.7 MiB. `FACTORY.md` has all
three findings in full.

## What it built

A wallet service: people send money by handle, ask for it back, split bills, reserve money to be
collected later, see their balance at any past instant, correct payments without rewriting history,
and refund them. One Node.js process, no dependencies, every amount an exact integer.

![The stage-4 wallet, signed in as Ada from seed.json](docs/product/screenshots/wallet-desktop.png)

*A real capture of `stage-4/` seeded with [`seed.json`](seed.json): available, total and held shown
apart, and the activity feed.* More in [`docs/product/`](docs/product/):
[`FEATURES.md`](docs/product/FEATURES.md) for what each stage added, with screens and real stage-4
requests, and [`ARCHITECTURE.md`](docs/product/ARCHITECTURE.md) for how it is built.

## Map

- **`FACTORY.md`** — the design, the measured results, both rejections, what it cost, and what we
  would tell the next team. Start here.
- [`docs/product/`](docs/product/) — the service itself: architecture, features by stage, screenshots.
  Written after the run from the accepted code.
- **[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md)** — every claim in this README, with the file that backs
  it and the command that reproduces it.
- **[`RUNBOOK.md`](RUNBOOK.md)** and `setup/` — how to stand the factory up again and point it at a
  different problem.
- `mandates/` — the four standing instructions. The body of each is the text loaded into its seat;
  the `Harness` / `Model` header lines were normalised afterwards to the exact model ID the seats
  recorded (`claude-opus-5-5`, see decision D-17). Read one end to end: it never says what the
  product is.
- `stage-1/` … `stage-4/` — one self-contained service per stage. Each builds and runs on its own,
  with no dependency on the others.
- `verification/adversary/stage-N/` — the adversary's own test suites, versioned, separate from
  production code.
- `evidence/runs/fskit-001/` — the record: obligations, handoffs, verdicts, harness runs, upgrade
  reports. Every claim links an obligation, a product revision, a test revision, a command and a
  real result.
- `room.json` — the complete session exported from BAND. The single human message is `3f95ab60`.
  Four receiver leases were redacted; [`REDACTION.md`](REDACTION.md) records exactly what and proves
  nothing else changed.

## Running it

Each stage folder has its own `RUN.md` and builds in one command with no network at run time. To
check a stage against the official harness, from the kickoff checkout:

```
python -m harness run --track pocketful --repo <this repo> --stage 1 --mode isolated --out <new dir>
```

`--stage 2`, `3` and `4` do the same for the later folders, and `--all` verifies the whole chain.
Stages 2 to 4 serve a browser UI; the harness exercises it at 375 px and 1280 px.

Or all of it in one command — clone from GitHub into a new temporary directory, `harness check`,
then all four stages in isolated mode:

```
bash setup/verify-from-clone.sh <path-to-kickoff-checkout>
```

It needs Docker running and the kickoff's harness installed; set `PYTHON` if that is not in the
kickoff's `.venv`. About five minutes, and it writes nothing outside its temporary directories.

### Live demo

**<https://four-seats-factory.onrender.com/login>** — sign in as `ada@example.com`, `bob@example.com`
or `cy@example.com`, all with the password `correct horse`.

It runs `stage-4/` from this repository, built from its own `Dockerfile` with nothing changed, on
one instance. State lives in memory, as the specification allows, so a restart or a redeploy empties
it. If you find it empty, one call from the repository root restores the demo data — and that call
is part of the specification:

```
curl -X POST https://four-seats-factory.onrender.com/_test/reset -H "Content-Type: application/json" --data-binary @seed.json
```

Anyone can call it, so anyone can reset the demo. That is fine for seeded data and would not be for
real money.

### Running it yourself

```
cd stage-4
docker build -t pocketful-stage-4 . && docker run --rm -p 8080:8080 pocketful-stage-4
curl -X POST http://127.0.0.1:8080/_test/reset -H "Content-Type: application/json" --data-binary @../seed.json
```

Then open <http://127.0.0.1:8080/login> and sign in as `ada@example.com`, `bob@example.com` or
`cy@example.com`, all with the password `correct horse`. State lives in memory, as the specification
allows: a restart empties it, and the same `curl` restores it.

## Licence

Everything in this repository, every stage folder included, is under the MIT licence in
[`LICENSE`](LICENSE). Each stage's `package.json` was written by the implementer with
`"private": true` and `"license": "UNLICENSED"`, npm's metadata for a package that is not meant to be
published. That field is not the licence of this repository. We left it untouched because editing it
would change product trees the auditor had already accepted, and a human edit to accepted work is
exactly what this run avoided. Where the two seem to disagree, the root `LICENSE` governs.

## What we are not claiming

Three findings is not many, and we cannot tell from inside the run whether a fourth slipped past all
four filters. One run is one data point. The auditor reproduces but does not run mutation
testing, so a check that passes against deliberately broken code would still look fine here. The
cost figures are estimates from token counts, not a bill. `FACTORY.md` says all of this at greater
length, because a factory that hides its limits is not one you would reuse.
