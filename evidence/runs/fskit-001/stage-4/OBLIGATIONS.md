# Obligation register — fskit-001 · Stage 4 (ACTIVE) · revision r1

Run: fskit-001 · Track: pocketful · Active stage: 4 (the final stage) · Register owner: analyst (hugo.valer/analyst-thgs)

Kickoff: C:\nexus\dev\dark-factory-wearedevs @ 803560d2a678ace1414465c098eb0ab5380ffade

Specs in force (cumulative), all re-read in full at the start of stage 4:
- stage-1.md LF f5e4c644…38a6
- stage-2.md LF 699fcdd4…af12
- stage-3.md LF 70a42853…bf94
- stage-4.md CRLF 1894b002f8827fd36623df4ecf3deb204e20d7fafbbfa671894a114db80e6df1 · LF ff79140fc43818909ee473cd24488604f245b3ce480d04c1862f359dde8e9a48 · git blob 19e76a0372e8ca83dbb817368876ae6dd057a8a0

Accepted bases:
- stage 1: beeaec72 / tree 347efba5
- stage 2: 68583038 / tree a8e6178d
- stage 3: 51a0bdd1 / tree f586c499 (verdict 11dbc577)
- main after the evidence merges: 4ce1c4430b4d54b2a287fe8a6d12f1b659b00d78

Method codes as before. All rows start OPEN. I = implementer, A = adversary, U = auditor.

## 0. Cumulative rule

Every stage-1, stage-2 and stage-3 row and decision stays in force for stage-4/ unless section 1 supersedes it:
- stage-1 register r2;
- stage-2 register r3, including D2-18 and D2-19;
- stage-3 register r2, including D3-17 … D3-21.

Suites 1–3, the stage-2 browser rows at 375/1280 px, and the earlier upgrade guarantees must still pass against stage-4/. Stage 4 has no next-stage probe.

## 1. Earlier rows superseded or extended by stage 4

| Row | Stage-4 change | Source (stage-4.md) |
|---|---|---|
| S1-070 / S2 / S3 idempotent paths | Ten idempotent write paths: stage 1's five, authorizations and captures, corrections, **refunds** and **correction batches**. The same §7 rules apply independently to each | intro |
| S1-091 etc. (payment representation) | Every payment representation adds `refund_of` (null for non-refunds; the target payment id for a refund) | Refunds ¶2 |
| S3-070 / D3-05 (settlement members immutable to single corrections) | Single-payment corrections still reject settlement members (422 linked_payment_immutable), but **batch corrections** by an operator may correct settlement members, provided the batch includes every member | Batch ¶1 |
| S3-071 / D3-05 (captures immutable) | Captures and **refund payments** cannot be corrected, singly or in a batch: 422 linked_payment_immutable | Refunds ¶3, Batch ¶1 |
| S3-043 / S3-049 | A correction can't reduce a payment below its already-refunded amount → 422 refund_exceeds_payment. Correction debits are checked against **available** funds | Refunds ¶3 |
| S3-044 / S3-052 | Revisions created by a batch also expose `correction_batch_id` (D4-05: null on other revisions) | Batch ¶3 |
| S1-170…178, S2-040, S3-071 | stage-4/ accepts unchanged exports from the ACCEPTED stage-1, 2 AND 3 services, keeping settlement membership, corrections and snapshots (a stage-3 snapshot token pages identically after a 3→4 import) | Batch ¶4 |
| S3-900 | There is no next-stage probe for stage 4 | dispatch |

## 2. Delivery

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S4-001 | dispatch §1 | stage-4/ is a full copy of the ACCEPTED stage-3 tree f586c499 (no nested .git), extended only inside stage-4/. stage-1/, stage-2/ and stage-3/ stay at 347efba5, a8e6178d and f586c499 | INSP: `git diff <copy-commit>:stage-4 f586c499` is empty | OPEN |
| S4-002 | cumulative | Dockerfile, RUN.md and locked dependencies; no runtime outbound fetch; the stage-2 UI still works (browser evidence at 375/1280) | INSP + HARN isolated + UI | OPEN |

## 3. Refunds

| ID | Source | Obligation | Boundary / error | Method → expected | State |
|---|---|---|---|---|---|
| S4-010 | Refunds ¶1 | `POST /payments/{payment_id}/refunds` with body {"amount": n} requires an idempotency key (400 missing, §7) and a bearer token (401) | — | API | OPEN |
| S4-011 | ¶1 | Only the original receiver may refund; anyone else (the sender, a third party, an operator) → 403 forbidden; an unknown payment → 404 | — | API | OPEN |
| S4-012 | ¶1 | Allowed targets: a direct payment, a request payment or a capture. A settlement member is also allowed (Batch ¶4). A refund as target → 422 invalid_refund_target | — | API | OPEN |
| S4-013 | ¶1 | An invalid amount (below 1, above 1e9, non-integral, a string, a boolean; §4/§5) → 422 validation_failed | — | API | OPEN |
| S4-014 | ¶1 | Cumulative refunds may not exceed the payment's CURRENT CORRECTED amount → 422 refund_exceeds_payment. Refunds up to exactly that amount are OK | Refund, then partial refunds summing exactly; a correction that lowers the payment, then a refund above the new amount | API | OPEN |
| S4-015 | ¶2 | A refund is a NEW payment in the opposite direction (from = the original receiver, to = the original sender) with refund_of = the target id, request_id null, authorization_id null, settlement_id null (D4-02), and the original note and visibility. 201 with that payment; a replay returns 200 with the original body | — | API | OPEN |
| S4-016 | ¶2 | It moves existing money out of the receiver's **available** funds, atomically, or fails with 409 insufficient_funds (held funds can't pay a refund) | Receiver with total ≥ amount but available < amount | API | OPEN |
| S4-017 | ¶2 | Refunds never reopen a request or authorization and never restore a released hold. Request status, authorization status, captured_amount and remaining_amount are unchanged | Refund a request payment; refund a capture | API | OPEN |
| S4-018 | ¶2 | Every other payment carries refund_of: null (a new field on every payment representation) | — | API | OPEN |
| S4-019 | ¶2 + stage-1 feed | A refund payment appears in /activity by the ordinary visibility rule (its visibility is copied from the target), and in statements as a money movement (a revision-1 payment with its own created_at) | — | API | OPEN |
| S4-020 | ¶3 | Captures and refund payments can't be corrected: 422 linked_payment_immutable | — | API | OPEN |
| S4-021 | ¶3 | A correction (single or batch) can't reduce a payment's amount below its already-refunded total → 422 refund_exceeds_payment | Reducing to exactly the refunded total is OK | API | OPEN |
| S4-022 | ¶3 | Correction debits are checked against the debited party's available funds (insufficient_funds) | — | API | OPEN |
| S4-023 | §1 invariants | Concurrent refunds of one payment never exceed its corrected amount in total, and never make available negative; conservation holds | — | CONC | OPEN |

## 4. Batch corrections

| ID | Source | Obligation | Boundary / error | Method → expected | State |
|---|---|---|---|---|---|
| S4-030 | Batch ¶1 | POST /correction-batches requires a settlement operator and an idempotency key, with the same 401/403 rules as settlements (no token → 401; a non-operator → 403 forbidden) | — | API | OPEN |
| S4-031 | ¶2 | `corrections` holds 1..32 objects with DISTINCT payment_ids, else 422 validation_failed. Each item has the ordinary correction fields (payment_id, expected_revision, amount, effective_at, reason) and ordinary validation. Unknown fields are ignored | 0 or 33 items; a duplicate payment_id | API | OPEN |
| S4-032 | ¶2 | An unknown payment → 404; a stale expected revision → 409 stale_revision | — | API | OPEN |
| S4-033 | ¶2 | The operator may correct ordinary, request and settlement payments, whoever the parties are. Captures and refunds stay immutable (422 linked_payment_immutable) | An operator who is party to none of the payments | API | OPEN |
| S4-034 | ¶2 | Correcting any settlement member requires including EVERY member of that settlement, else 422 incomplete_settlement | Two settlements; one complete and one partial | API | OPEN |
| S4-035 | ¶2 | Members of one settlement must have identical effective instants (offset spellings may differ, e.g. `12:00:00+00:00` ≡ `14:00:00+02:00`), else 422 validation_failed | — | API | OPEN |
| S4-036 | ¶2 | Single-payment corrections stay available for non-members (and still reject members with linked_payment_immutable) | — | API | OPEN |
| S4-037 | ¶3 | Error precedence: item errors in input order → settlement completeness → resulting current available funds (insufficient_funds) → historical total and available at every effective/event boundary (historical_overdraft). Codes: linked_payment_immutable, refund_exceeds_payment, insufficient_funds, historical_overdraft | Item 1 has a stale revision and item 2 is unknown → 409 stale_revision; the reverse → 404 | API | OPEN |
| S4-038 | ¶3 | Affordability comes from the COMBINED effect of all proposed revisions: a batch where one correction alone would overdraw but the combination does not → 201 | — | API | OPEN |
| S4-039 | ¶3 | A rejected batch leaves history, balances and idempotency records unchanged (the key stays unclaimed; no partial revision) | — | API | OPEN |
| S4-040 | ¶4 | 201 {correction_batch_id, recorded_at, revisions:[… in input order]}. All new revisions share recorded_at, strictly later than the previous recorded_at of every member; each revision exposes correction_batch_id | — | API | OPEN |
| S4-041 | ¶4 | effective_at can't be later than now (422) | — | API | OPEN |
| S4-042 | ¶4 | Original payments and receipts never change: original payment and settlement retries return their original bodies (byte-identical) | Replay of settlement receipt after a batch reverses it | API | OPEN |
| S4-043 | ¶4 | New statements reflect the new revisions; earlier snapshot tokens keep paging their frozen entries | — | API | OPEN |
| S4-044 | ¶4 | A replay returns the original batch response with 200; the same key with a different body → 409 idempotency_key_reuse; claimed-key precedence (S1-080) | — | API | OPEN |
| S4-045 | ¶5 | A settlement payment may be refunded under the ordinary refund rules; refunds never change settlement membership (the refund has settlement_id null; the member keeps its settlement_id; the batch completeness set is unchanged) | — | API | OPEN |
| S4-046 | ¶5 | Concurrent corrections that share ANY expected payment revision can't both succeed (single vs batch, or batch vs batch, overlapping on one payment): at most one 201, the others 409 stale_revision | Overlapping batches | CONC | OPEN |
| S4-047 | ¶3 + §1 | Batch history keeps conservation in every historical view and never makes total or available negative at any boundary (the historical_overdraft rule, D3-11/D3-21) | — | API/CONC | OPEN |

## 5. Upgrades

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S4-050 | Batch ¶5 | stage-4/ accepts exports from the ACCEPTED stage-1, stage-2 and stage-3 services, keeping settlement membership, corrections (revision histories) and snapshots. Imported state is exercised: sessions, byte-identical replays, statements and a stage-3 snapshot token paging identically, refunds of imported payments and captures, and batch corrections of imported settlements | XC 1→4, 2→4, 3→4 | OPEN |
| S4-051 | dispatch §3 | Upgrades are run by A and reproduced by U in two separate containers per pair, from populated exports; receipts and retry identities are preserved; UPGRADE-REPORT pairs 1→4, 2→4 and 3→4 | XC | OPEN |

## 6. Process and final verification

| ID | Obligation | Method | State |
|---|---|---|---|
| S4-900 | Harness `--stage 4` (suites 1–4, with no next-stage probe) by A and U on clean clones; U's final run in isolated mode | HARN | OPEN |
| S4-901 | UI regression evidence at 375 and 1280 px by A and U | UI | OPEN |
| S4-902 | The stage-1, 2 and 3 adversary suites re-run against stage-4/ (superset adaptations only, in recorded test revisions) | A suite | OPEN |
| S4-903 | **Final all-stage verification (dispatch):** after stage 4 is accepted, U makes a fresh clone of the submission candidate and runs `harness run --all --mode isolated --out …/fskit-001-all-final-<n>`. U verifies each stage's RUN.md independently, the required UI, and all six upgrade pairs against the final accepted trees; earlier evidence is reused only if the exact trees are unchanged and its provenance is complete. U captures the final four-folder claims and tree hashes | HARN + INSP | OPEN |

## Ambiguities and decisions (NOT source requirements)

| ID | Ambiguity | Decision | Basis |
|---|---|---|---|
| D4-01 | Refund precedence | 401 → 400 unparseable → 400 missing key → 422 key length → claimed-key resolution → 422 amount validation → 404 unknown → 403 not the receiver → 422 invalid_refund_target (the target is a refund) → 422 refund_exceeds_payment → 409 insufficient_funds | §5, §7, D-02 pattern |
| D4-02 | settlement_id / authorization_id / request_id of a refund payment | All null. A refund is never a settlement member and never a capture, so refunds of refunds are blocked by refund_of, not by these links | Refunds ¶2, Batch ¶5 |
| D4-03 | "Current corrected amount" for the refund limit | The amount of the payment's latest revision (all revisions known now), regardless of effective time | Refunds ¶1 |
| D4-04 | Can a refund target have a zero current amount? | Yes, but any amount ≥ 1 then exceeds it → 422 refund_exceeds_payment | ¶1 |
| D4-05 | correction_batch_id on non-batch revisions | Present and null on revision 1 and on single corrections; set on batch revisions (both in the batch response and in /revisions) | Batch ¶4 |
| D4-06 | Batch precedence within item errors | Validate items in input order. Each item runs its checks in D3-01 order (422 fields → 404 → 422 linked_payment_immutable → 409 stale_revision → 422 refund_exceeds_payment), and the first failing item decides. The batch-shape checks (not an array, 0 or >32, a non-object item, duplicate payment_ids) → 422 before any item. Then: settlement completeness (422 incomplete_settlement), then identical member instants (422 validation_failed), then combined current available (409 insufficient_funds), then combined historical (409 historical_overdraft) | Batch ¶2–3 |
| D4-07 | The batch's recorded_at when the members' previous recorded_at values differ | One shared recorded_at strictly greater than the maximum previous recorded_at of all members and than the server clock, with the D3-15 ms bump | ¶4 |
| D4-08 | The operator reading /revisions of payments they corrected but are not party to | Still only the two parties can read /revisions (S3-052); the operator sees the batch response | stage-3 ¶4 |
| D4-09 | Refund of a capture and the authorization's history | The refund is an ordinary new payment; the authorization's captured_amount and payment_ids are unchanged, and a closed hold stays closed | Refunds ¶2 |
| D4-10 | Batch correction including a non-member ordinary payment together with settlements | Allowed: the batch can mix non-members and complete settlements | Batch ¶2 |
| D4-11 | Refund feed visibility | Copied from the target payment | Refunds ¶2 |
