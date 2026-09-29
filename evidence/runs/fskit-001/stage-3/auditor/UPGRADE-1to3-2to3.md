# Upgrade pairs 1→3 and 2→3: auditor reproduction (fskit-001)

This is the input for UPGRADE-REPORT pairs **1→3** and **2→3**.

| Field | 1→3 | 2→3 |
|---|---|---|
| Source | ACCEPTED stage-1 `beeaec72` (tree `347efba5`), image `sha256:cfb657fd…` | ACCEPTED stage-2 `68583038` (tree `a8e6178d`), image `sha256:eb155dc9…` |
| Target | ACCEPTED stage-3 `51a0bdd1` (tree `f586c499`), image `sha256:9d61adde…` | same |
| Containers | fresh `s1u` → fresh `t13` | fresh `s2u` → fresh `t23` |
| Tool / runs | `s3_upgrade_probe.py` @ `9abeae23`. Candidate 1: events 006→007. Candidate 2: event 016 | same |
| Result | **PASS** | **PASS** |

**What was populated in both sources:**
- users, including an operator;
- a completed private payment (K1);
- a pending request;
- a two-member settlement;
- a lost-response payment (K2);
- a failed key.

**Added in the stage-2 source only:**
- an open hold, with its authorize receipt;
- a partially captured open hold, with its capture receipt;
- a fully captured hold;
- a voided hold.

**What was verified on the target after import:**
- **Credentials:** old tokens work, and destination credentials are removed.
- **Balances:** preserved.
- **Replays:** all source receipts replay 200 with **byte-identical** bodies (D2-13): the payment, the lost payment and the settlement, plus on 2→3 the authorize and the capture.
- **Conservation and openings:** the total is conserved now and at the opening (15000). The `/statement` opening is 10000 (the imported balance minus the imported net), the deltas reconcile to the current balance, and the entry counts are exact (3 for 1→3, 4 for 2→3).
- **Imported payment:**
  - revision 1 is at `created_at`;
  - it can be corrected (201).
- **Imported settlement member:**
  - revision 1 is at `committed_at`;
  - a correction gives 422 `linked_payment_immutable`.
- **Imported pending request:** payable.
- **2→3 holds:**
  - the open hold has `closed_at` null;
  - the partial hold has remaining 200;
  - held is 600;
  - the captured hold has `closed_at` equal to its capture payment's `created_at`;
  - the voided hold has `closed_at` at the import time (D3-18, a decision);
  - the imported capture gives 422 on correction;
  - the imported open hold can be captured, after which held is 200;
  - captures appear exactly once each in the statement.

**Privacy:** export bodies were held in memory only. Only their SHA-256 is recorded.
