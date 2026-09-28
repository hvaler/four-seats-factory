# Upgrade pair 1→2: auditor reproduction (fskit-001)

This is the input for UPGRADE-REPORT pair **1→2**. The analyst owns the consolidated UPGRADE-REPORT.md.

| Field | Value |
|---|---|
| Source | ACCEPTED stage-1 `beeaec72`, tree `347efba5`. Image `sha256:cfb657fd…3583`, built `--no-cache` by the auditor from `clones\auditor-s1-1` |
| Target | ACCEPTED stage-2 `68583038`, tree `a8e6178d`. Image `sha256:eb155dc9…cf97`, built `--no-cache` by the auditor from `clones\auditor-s2-2` |
| Containers | 3 fresh ones per run: `s1u` (source), `s2a` (UI origin, and the API target of part A), `s2b` (fresh target, used for the browser switch). All `--cpus 2 --memory 2g` |
| Tool | `tools/s2_upgrade_probe.py` @ `9a035d4b` |
| Runs | candidate 1: event 009 (7/7), after a tool-expectation fix in 008. Candidate 2: event 017 (7/7) |
| Result | **PASS on the accepted target** |

## What was populated in the source (stage 1)
- Users, including a settlement operator.
- A completed private payment receipt (key K1).
- A pending request.
- A two-member settlement receipt.
- A "lost-response" payment (K2): it committed on the source, but the client kept only the key and body.
- A failed-key attempt (409).
- For the browser half: a UI-driven pay whose response was aborted after it committed on stage 1.

## What was verified on the target after import
Receipts and identities:
- Old bearer tokens still work, and a destination-only token returns 401.
- Balances are preserved, with `total = balance = available` and `held = 0`.
- Stage-1 K1 payment, K2 payment and settlement replays return 200 with the **original bytes**. They have no `authorization_id`, per D2-13.
- Reusing K1 with a different body gives 409, and the failed key is reusable (201).
- The pending stage-1 request can be paid (201, with `authorization_id: null`).
- The feed carries `authorization_id` on every item, and it has 2 settlement members with one settlement id.
- The sum of totals is conserved (15000).

Browser (D2-18), at 375 and 1280 px:
- A session signed in against stage-1 data stays signed in after the import (same token, no reload).
- The pay whose response was lost is retried with the same key and body, recovers the original receipt, and moves the money once. The shown balance equals the target balance.
- The stage-1 pending request is paid from `/requests`.

## Privacy
Export bodies were held in memory only. Only their SHA-256 is recorded, in `upgrade-results.json`. No tokens or password hashes are written to evidence.
