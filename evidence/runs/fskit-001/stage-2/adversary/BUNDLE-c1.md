# fskit-001 · Stage 2 · Adversary verification bundle, candidate 1

This is a challenge result, not a verdict. **One open finding: F2-01**, low severity, against the D2-19 decision row (analyst ruling 50c67d05). It was reproduced independently by the auditor (0414ea1e) and by the implementer (ed36541f).

## Revisions

| Item | Value |
|---|---|
| Candidate | `f1f0847d23be4b7cee84fcc00436a26ff48a0915` · `stage-2` tree `583b05637641c51decce4c7cac8e75847a8d77f6` · `stage-1` tree `347efba5…c478` (the accepted tree, unchanged) |
| Review clone | `clones\adversary-s2-1` (fresh, detached, clean). Stage-1 source for XC: `clones\adversary-s1-1` at `beeaec72` (stage-1 tree `347efba5`) |
| Test revision | `207536fae2da9a95df3509aaac5f1950b41cd524` (stage-2 suite tree `6348b2e5…`, stage-1 suite tree `51241af5…`) |
| Specs and registers | stage-1.md `65497dea…` + stage-2.md `39aaf9d7…` · stage-1 register r2 (analyst@8e913edb) · stage-2 register r2 (analyst@88fb9fd2) + D2-18 + D2-19 |
| Tools | Python 3.12.3, pytest 9.1.1, httpx 0.28.1, Playwright 1.63.0, Chromium 153.0.8010.12, Docker 29.8.0 (WSL2), model claude-opus-5-5 |

## Results (events in `events/`)

| Event | Check | Outcome |
|---|---|---|
| 001 | Harness `--stage 2`, host mode (`checks/fskit-001-s2-adversary-1`) | **PASS.** Suite 1: 147/147. Suite 2: 35/35. 0 skipped, `claimed_stage 2`. The stage-3 probe fails as expected. `report.json` `9efdb06a…6100` |
| 002 | Adversary stage-1 suite on `stage-2/` (S2-904) | **PASS**, 325/325. The only supersession is `/me` compared as a superset (S1-090). |
| 003 | Adversary stage-2 suite, full (`c1-run1/`) | **137/139.** The 2 failures are F2-01 at 375 and 1280 px. Everything else passed: API, CONC, UI at both widths including XSS, overflow, refresh ordering, lost response and labels/focus, XC 1→2 in both D2-18 shapes, and the D2-13 byte-identical replays. 30 screenshots are in `c1-run1/shots/`. |
| 004 | F2-01 minimal repro (`repro_s2_027.py` / `.log`) | **FAIL, 3/3 deterministic.** After a refused over-remainder capture, the capture input resets from the typed `25.00` to the prefill `20.00`. There is no money effect. |
| 005 | `test_s2_conc` × 5 on fresh images (`c1-conc-r1..5/`) | **PASS**, 45/45, 0 intermittent |
| 006 | Inspection | **PASS.** S2-001 copy commit `327e7a4d:stage-2` == `347efba5`. No runtime URL, no polling, and no innerHTML, eval or document.write. No stage-3 code, no test detection. |

## What remains untested or only partly tested

1. **S2-030/031** (product quality): only the measurable proxies were checked. The available figure is the headline (by font size), the states differ, and screenshots were taken. The overall aesthetic judgement is the auditor's.
2. **S2-033 contrast:** not measured by me. The auditor measured 6.25–16.5:1 (interim 435bea17). Labels and the focus ring were checked on `/`, `/split` and `/authorizations` only.
3. **S2-034:** loading states are not tested, because responses are too fast to observe without throttling. Empty and error states were tested.
4. **S2-021:** latest-refresh-wins was tested with held fetch/XHR responses on `/` only, not on `/authorizations`.
5. **S2-024:** uncertain-write recovery was tested for payments only. The spec requires nothing more.
6. **S2-035:** XSS was checked in notes on the feed, requests and authorizations. Display names were not checked; by inspection, all output goes through `textContent`.
7. **S2-057 / D2-09:** the timing boundary uses TTL 2 s with a 0.5 s margin before the deadline. A capture exactly at the deadline is not tested.
8. **S2-070:** 5 repetitions of 9 CONC tests on one host. The Docker daemon is shared with the other seats, whose containers were running at the same time.
9. **S2-041…043:** tested under D2-18 routing (Playwright). No real network proxy was used.
10. **Scale:** 55 feed items at most.
11. **Hidden tests:** the shipped checks are a partial sample, and nothing here predicts the hidden suite.

## Usage

`fskit-001,2,adversary,f603ac21-88ea-434a-844e-bb621f8da63e,Claude Code,claude-opus-5-5,2026-09-28T21:45:00Z,2026-09-28T22:20:00Z,2100,unknown,unknown,unknown,unknown,,true,wall clock from shell and room timestamps (approximate to the minute),token counts are not exposed to this seat at run time`
