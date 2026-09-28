# fskit-001 · Stage 2 · Adversary verification bundle, candidate 2 (repair cycle 1)

This is a challenge result, not a verdict. **No open finding.** F2-01 is fixed, and its original failing evidence (events 003, 004, 007) is preserved.

## Revisions

| Item | Value |
|---|---|
| Candidate | `68583038e7ea52429b062af0f775d3cbfd96b7c3` · `stage-2` tree `a8e6178d7b9d5ba4dde4999e78730fa99ff80fe2` · `stage-1` tree `347efba5…c478` (the accepted tree, unchanged). Its parents are `59ca569d` → `f1f0847d`. |
| Review clone | `clones\adversary-s2-2` (fresh, detached, clean). Stage-1 source: `clones\adversary-s1-1` at `beeaec72` |
| Test revision | `bdb21efc6e3ccdbc952f3f6bc24b56313e7a1266` (stage-2 suite v3, tree `c8d96109…`; stage-1 suite tree `51241af5…`) |
| Registers | stage-1 r2 (analyst@8e913edb) · stage-2 r3 (analyst@b8eb2f0a: r2 + D2-18 + D2-19) |
| Tools | as in BUNDLE-c1 (Python 3.12.3, pytest 9.1.1, httpx 0.28.1, Playwright 1.63.0, Chromium 153.0.8010.12, Docker 29.8.0) |

## Results

| Event | Check | Outcome |
|---|---|---|
| 009 | Harness `--stage 2`, host mode (`checks/fskit-001-s2-adversary-2`) | **PASS.** 147/147 + 35/35, 0 skipped, claimed 2. The stage-3 probe fails as expected. `report.json` `c0b55f86…9b55` |
| 010 | Stage-1 suite on `stage-2/` (S2-904) | **PASS**, 325/325 |
| 011 | Stage-2 suite v3, full (`c2-run1/`) | **PASS**, 148/148 at 375 and 1280 px. This includes the original F2-01 assertion, the v2 D2-19 regression, display-name XSS, latest-refresh on `/authorizations`, the deadline captures (sent 1.7, 55.1 and 252.7 ms after `expires_at` → 409 `authorization_expired`), and XC 1→2 in both D2-18 shapes. |
| 012 | `test_s2_conc` × 5 on fresh images (`c2-conc-r1..5/`) | **PASS**, 45/45, 0 intermittent |
| 013 | Repair diff inspection | **PASS.** Only `src/ui/app.js` (+17/−4: a per-authorization draft, cleared only on a successful capture) plus a regression test and RUN.md changed. No server or API change. |

## What remains untested or only partly tested

These are unchanged from BUNDLE-c1, except that items 6 (display names) and 7 (the deadline) are now covered:
- S2-030/031 by proxies and screenshots only;
- contrast not measured by me;
- loading states not observed;
- uncertain-write recovery for payments only;
- 55 feed items at most;
- 5 CONC repetitions on a shared daemon;
- the upgrade tested through D2-18 routing, not a real proxy;
- the hidden tests are unknown.

A note on the fix: a capture whose response is lost is handled like a refused one (the draft is kept and an error is shown). The spec requires uncertain-state handling only for payments, so this is not a finding.

## Usage

`fskit-001,2,adversary,f603ac21-88ea-434a-844e-bb621f8da63e,Claude Code,claude-opus-5-5,2026-09-28T22:18:30Z,2026-09-28T22:31:00Z,750,unknown,unknown,unknown,unknown,,true,wall clock from shell timestamps (approximate to the minute),token counts are not exposed to this seat at run time`
