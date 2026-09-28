# Auditor decision: fskit-001 · stage 2 · candidate 1

- **Run / stage:** fskit-001 · pocketful · stage 2 (active).
- **Auditor:** auditor-thgx (hugo.valer/auditor-thgx), model `claude-opus-5-5`.
- **Date:** 2026-09-28T22:22Z (UTC)
- **Decision: REJECTED**
- **Product commit:** `f1f0847d23be4b7cee84fcc00436a26ff48a0915`.
- **Trees:** `stage-2` = `583b05637641c51decce4c7cac8e75847a8d77f6`; `stage-1` = `347efba502629e5b5bbd730f35c34bdfe208c478`, which is the ACCEPTED tree, unchanged.
- **Test revisions:**
  - adversary `207536fae2da9a95df3509aaac5f1950b41cd524` (stage-2 suite tree `6348b2e5`, stage-1 suite tree `51241af5`);
  - auditor tools `c66eae37` (API), `9adf0051` (UI), `9a035d4b` (upgrade), `8f1ed926` (F2-01 repro), and `9eeeae1d`/`236ecf35`/`31ba973b` (stage-1 probes).
- **Specs:**
  - stage-1.md `65497dea…0aa4`;
  - stage-2.md `39aaf9d7743c6fd831663e5b8363866f7d70795e5efb9000c2803f471397b13f` (LF `699fcdd4…af12`).
- **Registers:**
  - stage-1 r2 (analyst@8e913edb);
  - stage-2 r2 (analyst@88fb9fd2), plus D2-18 and r3 (analyst@b8eb2f0a, which adds D2-19).

## Unmet condition (the reason for rejection)
**F2-01: a refused capture does not keep the typed capture amount.**
- **Obligation:** register r2 restated S2-027 "…with the input kept". Register r3 relabels this as binding band decision **D2-19**, which supports S2-034.
- **Reproduced by the auditor** (event 011), independently:
  - At 375 and 1280 px: prefill `20.00`, typed `25.00`, `authorization-error` shown, then the input reset to `20.00`.
  - It also shows up as the 2 failures in the auditor's re-run of the adversary suite (event 012): `test_authorize_capture_void_ui[w375]` and `[w1280]`.
- **Severity:** low.
  - There is no money effect; held and total are unchanged.
  - It is not a failure of stage-2.md text.
  - The analyst ruled that the row binds (50c67d05, b88cb4aa), so the candidate cannot be accepted with it open.
- **Required change:** keep the unsent capture draft for each authorization across the post-refusal re-render. After a successful partial non-final capture, the prefill must still follow the new remainder. Add a regression test.
- **Recipient:** implementer, through the analyst (repair cycle 1 of 5).

## Everything else reproduced on this candidate (all auditor-run, in fresh processes)
| Event | Check | Result |
|---|---|---|
| 001 | Provenance and inspection. S2-001 copy commit `327e7a4d:stage-2` = `347efba5`. Only `stage-2/` changed. Assets come from the image; there is no polling. | PASS |
| 002 | Harness `--stage 2`, host mode, `checks/fskit-001-s2-audit-1` | suite 1: 147/147; suite 2: 35/35; 0 skipped |
| **003** | **Harness `--stage 2 --mode isolated`, `checks/fskit-001-s2-audit-2`** | **suite 1: 147/147; suite 2: 35/35; 0 skipped.** Stage-3 probe fails as expected (`as_of`) |
| 004→005 | Stage-2 API probe | 31/31. Run 1's 2 failures were auditor tool bugs, preserved |
| 006→007 | Browser probe, Chromium, 375 and 1280 px | 44/44. Run 1's contrast failure was an auditor tool bug, preserved |
| 008→009 | 1→2 upgrade: the ACCEPTED stage-1 image plus 2 fresh stage-2 containers, API and D2-18 browser | 7/7. Run 1's failure was a wrong auditor expectation, preserved |
| 010 | Stage-1 auditor probes against stage-2/ | 75/75 |
| 012 | Adversary suites, re-run by the auditor | stage-1 suite on stage-2/: 325/325; stage-2 suite: 137/139, where the 2 failures are F2-01 |

**Product quality (S2-030…034), auditor judgement from the 375 and 1280 px screenshots:** satisfied apart from F2-01.
- The UI is coherent and calm.
- Available is the 38 px headline; total and held are secondary.
- Status badges are distinct.
- Error, uncertain and success notices differ in colour and icon.
- Labels are visible and there is a 3 px focus ring.
- Contrast is 6.25–16.5:1.
- There is no horizontal scroll with worst-case content.
- Timestamps are human-formatted, except the RFC 3339 testid text.

**Limitations:**
- Loading states were not observed.
- The D2-18 upgrade was driven through Playwright routing.
- Everything ran on a single host.
- No claim is made about hidden checks.

## Next action
1. The analyst routes the repair (cycle 1 of 5, already in progress: f8850d4f…).
2. The implementer commits a new revision in `stage-2/` only.
3. The auditor re-audits that revision from scratch, including the isolated harness, the full adversary re-run, the browser checks at both widths, 1→2, and `stage-1` still at `347efba5`.
4. This rejected candidate and all of its evidence are kept.
