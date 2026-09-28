# Obligation register — fskit-001 · Stage 3 (ACTIVE) · revision r2 (the r2 section is at the end)

Run: fskit-001 · Track: pocketful · Active stage: 3 · Register owner: analyst (hugo.valer/analyst-thgs)
Kickoff: C:\nexus\dev\dark-factory-wearedevs @ 803560d2a678ace1414465c098eb0ab5380ffade
Specs in force (cumulative), all re-read in full at the start of stage 3:
- stage-1.md: CRLF 65497dea…0aa4 · LF f5e4c644…38a6
- stage-2.md: CRLF 39aaf9d7…b13f · LF 699fcdd4…af12
- stage-3.md: CRLF 2255d3f2181c22dc6eac6919bf7712197d812248bd9de8a7e59260ede6056e54 · LF 70a428536fdc834dc77538ed78168dfd448d2000c91fa2c002e2d7cfd98ebf94 · git blob db2dbabc57fb4fe2ec9255b7fe1f2f37d15d6d59
Accepted bases:
- stage 1: beeaec72, tree 347efba5 (verdict 72be202b)
- stage 2: 68583038, tree a8e6178d (verdict 4ced8436)
- main after the evidence merges: 095cb06c0350c2279c838595eb463ecc3f85c77b

Method codes as before (API, CONC, XC, HARN, INSP, UI). All rows start OPEN. I = implementer, A = adversary, U = auditor.

## 0. Cumulative rule

Every stage-1 row (S1-*, stage-1 register r2) and every stage-2 row (S2-*, stage-2 register r3, including D2-18 and D2-19), together with their decisions, remains in force for stage-3/ unless section 1 supersedes it. The stage-1 and stage-2 suites and the stage-2 browser rows must still pass against stage-3/. Browser evidence at 375 and 1280 px is required again (dispatch: "For Stages 2-4, inspect the real UI").

## 1. Earlier rows superseded or extended by stage 3

| Row | Stage-3 change | Source (stage-3.md) |
|---|---|---|
| S1-044 / S1-047 / D-11 / D-32 | Seeded payments may supply `created_at`. If omitted, it is the reset time, earlier than any later API payment. A seeded `created_at` in the future → 422 with no change. The fixture `balance` is still the balance after all seeded payments; loading them never changes it | Payment timestamps |
| S2-054 / D2-12 | Seeded open holds are created at reset unless `created_at` is supplied. Seeded closed holds need not reconstruct a prior lifecycle | Historical holds |
| S1-090 / S2-052 | GET /me accepts the optional `as_of` and `known_at`. Without temporal params it returns the existing fields with the current corrected values | GET /me as of |
| S1-150 | /activity keeps its ordering by `created_at` and shows the ORIGINAL payment. Correction records are never feed items | Corrections ¶ |
| S1-074 / S1-079 | Original payments and every original idempotent response stay unchanged after corrections | Corrections ¶ |
| S2-058 / S2-069 | Every authorization representation adds `closed_at` (null while open; the event time when closed) | Historical holds |
| S1-170…178, S2-040 | stage-3/ accepts unchanged exports from the ACCEPTED stage-1 AND stage-2 services. The ledger imports and accounts for authorizations and captures. The export stays at format_version 1 (D2-01) | Settlement history ¶2 |
| S1-900 / S2-900 | stage-3/ implements stages 1–3 only, with no stage-4 behaviour (refunds, batch corrections). The stage-4 probe is expected not to pass its whole suite | dispatch |

## 2. Delivery

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S3-001 | dispatch §1 | stage-3/ is a full copy of the ACCEPTED stage-2 tree a8e6178d (no nested .git), extended only inside stage-3/. stage-1/ stays at 347efba5 and stage-2/ at a8e6178d | INSP: `git diff <copy-commit>:stage-3 a8e6178d` is empty | OPEN |
| S3-002 | cumulative | Dockerfile, RUN.md and locked dependencies in stage-3/; no runtime outbound fetch; all stage-2 UI obligations still hold | INSP + HARN isolated + UI | OPEN |

## 3. Payment timestamps

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S3-010 | Payment timestamps ¶1 | Every payment's `created_at` is an RFC 3339 instant with an offset marking when it moved money, and every endpoint that returns a payment includes it. /activity still orders by it | API | OPEN |
| S3-011 | ¶2 | A seeded `created_at` is accepted and used verbatim. If omitted → the reset time (earlier than later API payments). A future seeded `created_at` → reset 422 with no change | API | OPEN |
| S3-012 | ¶3 | Loading seeded payments with `created_at` does not change the fixture balance | API | OPEN |

## 4. GET /me as of an instant

| ID | Source | Obligation | Boundary | Method → expected | State |
|---|---|---|---|---|---|
| S3-020 | GET /me ¶1 | `as_of` is optional and must be RFC 3339 with an offset. A naive local time, a bare date or an empty value → 422 | `2026-09-24T13:20:00` (no offset), `2026-09-24`, `as_of=` | API | OPEN |
| S3-021 | ¶2 | With `as_of`, balance = the balance after every payment of the caller effective at or before as_of, and before every later one. A payment made exactly at `as_of` counts (inclusive) | Payment at exactly as_of | API | OPEN |
| S3-022 | ¶2 bullets | as_of ≥ the latest payment → the current balance. as_of before the earliest payment → the opening balance. The response echoes `as_of` exactly as given (same string, offset preserved) | `+02:00` offset input | API | OPEN |
| S3-023 | Historical holds | With as_of/known_at, all four money fields describe the SAME view: balance = total, available = total − held, and held = the historical open holds at as_of under known_at. Without as_of, the request's start instant is used | — | API | OPEN |

## 5. GET /statement

| ID | Source | Obligation | Boundary | Method → expected | State |
|---|---|---|---|---|---|
| S3-030 | Statement ¶1 | from and to are optional: `from` defaults to the wallet's opening and `to` to now. limit and offset are exactly as in GET /requests (422 rules and plain-digit integers) | — | API | OPEN |
| S3-031 | ¶2 | Returns the caller's sent and received payments in the half-open window [from, to), oldest first, as {opening_balance, entries:[{payment, delta, balance_after, revision, effective_at, recorded_at}], closing_balance, has_more, snapshot} | A payment exactly at `from` is included; exactly at `to` it is excluded | API | OPEN |
| S3-032 | req. 1 + corrections ¶ | Ordered by the selected effective_at ascending, then payment id ascending for ties | Equal instants | API | OPEN |
| S3-033 | req. 2 | opening_balance = the balance immediately before `from`; closing_balance = the balance immediately before `to` | — | API | OPEN |
| S3-034 | req. 3 | opening_balance + the sum of ALL deltas in the full window = closing_balance. A sent payment has a negative delta and a received one a positive delta | — | API | OPEN |
| S3-035 | req. 4 | Pagination never changes an entry's balance_after or the window's opening and closing balances; they describe the full window regardless of limit and offset | Page 2 values = the values in a single full page | API | OPEN |
| S3-036 | ¶ after req. | Only payments the caller sent or received appear; feed visibility does not apply (the caller's private payments appear; others' public payments do not) | — | API | OPEN |

## 6. Effective time, recorded time and corrections

| ID | Source | Obligation | Boundary / error | Method → expected | State |
|---|---|---|---|---|---|
| S3-040 | Effective ¶1 | Every payment has a revision history. Revision 1 = the original amount, with effective_at = recorded_at = created_at (for seeded payments, the supplied created_at or the reset time) | — | API | OPEN |
| S3-041 | Effective ¶1 | Opening balances = seeded ending balances minus the net effect of the ORIGINAL seeded payments. Corrections never change opening balances. New accounts open at 0 | — | API | OPEN |
| S3-042 | Corrections ¶1 | POST /payments/{payment_id}/corrections requires an idempotency key and the original sender. No token → 401; an authenticated non-sender (including the receiver) → 403; an unknown payment → 404 | — | API | OPEN |
| S3-043 | ¶2 | All fields are required: expected_revision is a positive integer; amount is an integer 0..1000000000 (0 reverses the whole payment); reason is a string of 1..200 characters; effective_at is an RFC 3339 instant with offset, not later than now. Invalid → 422 validation_failed | A missing field; amount -1 or 1000000001; reason "" or 201 chars; a future effective_at; no offset | API | OPEN |
| S3-044 | ¶2 | A correction changes neither the parties nor the visibility. It appends an IMMUTABLE revision and returns 201 {payment_id, revision, amount, effective_at, recorded_at (server-assigned), reason} | — | API | OPEN |
| S3-045 | ¶2 | A payment's recorded times strictly increase across its revisions | Rapid successive corrections | API/CONC | OPEN |
| S3-046 | ¶2 | A stale expected_revision → 409 stale_revision | — | API | OPEN |
| S3-047 | ¶2 | A successful replay returns that ORIGINAL revision with 200, even after newer revisions. The same key with a different body → 409 idempotency_key_reuse | — | API | OPEN |
| S3-048 | ¶3 | The difference from the previous amount moves between the same two wallets in the same atomic step: an increase debits the original sender, a decrease debits the original receiver | — | API | OPEN |
| S3-049 | ¶3 | A currently unaffordable debit → 409 insufficient_funds (current available, stage 2). Otherwise, if any user's corrected balance is negative at any effective-time boundary → 409 historical_overdraft, where a boundary includes the combined effect of all movements at that instant. Either failure preserves balances, revision history, statements and idempotency state (the key stays unclaimed) | Backdated increase that the receiver spent earlier | API | OPEN |
| S3-050 | ¶3 | The sum of balances equals the seeded total in EVERY historical view (any as_of and known_at) | — | API | OPEN |
| S3-051 | ¶4 | The original payment and every original idempotent response stay unchanged. /activity keeps showing the original payment, and correction records are not feed payments | — | API | OPEN |
| S3-052 | ¶4 | GET /payments/{payment_id}/revisions → {"revisions":[…]} in revision order, including revision 1 (reason ""). Only the two parties may read it; a third party → 404, even for a public payment; no token → 401 | — | API | OPEN |
| S3-053 | known_at ¶ | GET /me and GET /statement accept an optional known_at (RFC 3339 with offset). For each payment, the latest revision recorded AT OR BEFORE known_at is selected; if none was recorded yet, the payment contributes nothing. Omitting it means everything known when the read begins. The selected revisions then apply by their EFFECTIVE times. as_of stays inclusive and the statement window half-open. Both instants may be in the future. An invalid or empty instant → 422. A supplied known_at is echoed exactly | known_at before a payment existed | API | OPEN |
| S3-054 | ordering ¶ | Statement entries order by the selected effective_at, then payment id. Each entry keeps payment, delta and balance_after, and adds the selected revision, effective_at and recorded_at. `payment.amount` is the SELECTED amount. A zero-amount revision still appears as an entry with delta 0. No correction is counted alongside the revision it replaces. With no corrections and no known_at, the previous behaviour is unchanged | — | API | OPEN |

## 7. Stable statement pagination

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S3-060 | Stable ¶1 | Every first GET /statement response returns an opaque `snapshot` token freezing the caller's selected revisions, window, balances, entries and the default `to` at that read | API | OPEN |
| S3-061 | ¶1 | `GET /statement?snapshot=<token>&limit&offset` pages that exact result, even after later payments or corrections | API | OPEN |
| S3-062 | ¶1 | Only limit and offset may accompany a snapshot: from, to or known_at with it → 422. Other unrecognized params stay ignored | API | OPEN |
| S3-063 | ¶1 | An unknown token, another user's token or a token from before the reset → 404. Tokens last until reset (container restarts need not be survived) | API | OPEN |
| S3-064 | ¶1 | Paging changes neither balances nor entries; the final partial page and offsets past the end report has_more correctly | API | OPEN |
| S3-065 | ¶2 | A correction may move a payment into or out of a statement window. Existing snapshots stay unchanged during concurrent payments or corrections. Concurrent corrections with the same expected_revision cannot both succeed (exactly one 201; the others 409 stale_revision) | CONC | OPEN |

## 8. Settlements, captures and upgrade

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S3-070 | Settlement ¶1 | Stage-1 settlements keep their original receipts and privacy rules. Each member's revision 1 uses the shared committed_at as effective_at and recorded_at. A correction of a settlement member → 422 linked_payment_immutable | API | OPEN |
| S3-071 | Settlement ¶2 | stage-3/ accepts exports from the ACCEPTED stage-1 AND stage-2 services. The ledger imports and accounts for authorizations and captures. Captures are immutable linked payments: a correction of a capture → 422 linked_payment_immutable | XC (1→3, 2→3) | OPEN |
| S3-072 | dispatch §3 | Upgrades 1→3 and 2→3 run on two separate containers from populated exports, preserving original receipts, retry identities and sessions, and exercise the imported state: historical /me and /statement over imported history, corrections of imported payments, and captures of imported holds. UPGRADE-REPORT pairs 1→3 and 2→3 | XC | OPEN |

## 9. Historical holds

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S3-080 | Holds ¶1 | A hold starts when the authorization is created. A non-final capture reduces it at capture time. A final capture, a void or an expiry releases the remainder at that event's time, and expiry takes effect at expires_at | API (as_of before and after each event) | OPEN |
| S3-081 | Holds ¶1 | Events other than clock expiry are known at their server-assigned event time. Once the creation is known, the expiry deadline is known too. For queries beyond now, an open hold expires at its deadline. Without as_of, the instant the request began is used | API (known_at around the events; as_of in the future) | OPEN |
| S3-082 | Holds ¶1 | Authorizations expose `closed_at`: null while open, the event time once closed (expires_at for expiry) | API | OPEN |
| S3-083 | Holds ¶2 | Historical total follows the effective/recorded rules. A correction is rejected with 409 historical_overdraft if it makes EITHER total OR available negative at any past effective or event boundary under the latest known revisions. A currently unaffordable debit still takes precedence as insufficient_funds | API | OPEN |
| S3-084 | Holds ¶2 | GET /statement contains money movements only: authorization, release and expiry are not payments. Captures appear exactly once, with their links. Old snapshots stay unchanged after any lifecycle action or correction | API | OPEN |
| S3-085 | Stage 2 concurrency + stage 3 | Concurrent corrections, payments, captures and statement reads stay linearizable. Every invariant (conservation in every view, non-negative total and available) holds at every read | CONC | OPEN |

## 10. Process

| ID | Obligation | Method | State |
|---|---|---|---|
| S3-900 | Harness `--stage 3` (suites 1–3 plus the stage-4 probe, which is expected not to pass whole) by A and U on clean clones; U's final run in isolated mode | HARN | OPEN |
| S3-901 | UI regression evidence at 375 and 1280 px by A and U (the stage-2 UI rows still apply) | UI | OPEN |
| S3-902 | UPGRADE-REPORT pairs 1→3 and 2→3, reproduced by U | XC | OPEN |
| S3-903 | Evidence records under evidence/runs/fskit-001/stage-3 | INSP | OPEN |
| S3-904 | The stage-1 and stage-2 adversary suites re-run against stage-3/ (with superseded assertions adapted in a recorded test revision, nothing else weakened) | A suite | OPEN |

## Ambiguities and decisions (NOT source requirements)

| ID | Ambiguity | Decision | Basis |
|---|---|---|---|
| D3-01 | Correction precedence | 401 → 400 unparseable/non-object → 400 missing key → 422 key length → claimed-key resolution → 422 field validation (D3-02) → 404 unknown payment → 403 not the sender → 422 linked_payment_immutable → 409 stale_revision → 409 insufficient_funds (against current available) → 409 historical_overdraft | §5, §7, stage-3 corrections |
| D3-02 | Wrong JSON types in the correction body | "Invalid input is 422" is endpoint-specific, so any invalid correction field, including a wrong JSON type (e.g. expected_revision "1", reason 5, effective_at 0), → 422. Integral numeric forms (1.0, 1e0) are accepted for expected_revision and amount, as for amounts (§4) | stage-3 corrections ¶2, §5 precedence |
| D3-03 | A correction to the same amount as the current revision | Valid: it appends a revision, moves no money and returns 201 | ¶2 |
| D3-04 | Can effective_at precede the original created_at or the wallet's opening? | Yes, if not later than now. Validity is decided by the historical_overdraft rule | ¶2–3 |
| D3-05 | Which payments are correctable | Direct payments and request payments (including zero-amount ones). Settlement members and captures → 422 linked_payment_immutable | Settlement history |
| D3-06 | What /activity and the other payment representations show after a correction | The ORIGINAL payment body (amount of revision 1). Only statement entries show the selected amount. /me without params shows the current corrected balance | ¶4, known_at ¶ |
| D3-07 | known_at on /me without as_of | as_of = the request's start instant; the revisions come from known_at | known_at ¶ |
| D3-08 | from > to on /statement | 422 validation_failed. from == to → an empty window with opening = closing | Statement ¶ |
| D3-09 | as_of or other params with snapshot | Only from, to and known_at are forbidden (422); as_of and other unknown params are ignored | Stable ¶1 |
| D3-10 | Snapshot tokens and export/import | Snapshots are part of the exported state and stay valid after import; a reset invalidates them (404) | Stable ¶1, §10 |
| D3-11 | Boundaries for historical_overdraft | Every distinct effective_at of any revision affecting the user, every hold event time, and every created_at, evaluated under the latest known revisions including the proposed one; movements at the same instant are netted together first | ¶3, Holds ¶2 |
| D3-12 | Statement `payment` object | The payment representation with `amount` = the selected amount; every other field (created_at, note, visibility, ids, links) is the original | ordering ¶ |
| D3-13 | Upgrade from stage 1 or 2: revision history | Imported payments get revision 1 with effective_at = recorded_at = their created_at (settlement members: committed_at). Opening balance = the imported balance minus the net of the imported payments. Imported holds keep their created_at and their event times; lifecycle times missing in a stage-2 export (e.g. the void time) use the best recorded time available (the closed-state record time, or the import time) | Settlement history ¶2, Holds ¶2 |
| D3-14 | Historical balance view when known_at excludes a payment | The excluded payment contributes to neither party, so conservation still holds | S3-050 |
| D3-15 | Timestamp precision | Millisecond precision (D2-17). Instants in query params are parsed with any valid RFC 3339 fraction and compared exactly | D2-17 |
| D3-16 | The seeded authorization created_at field | Accepted if supplied (RFC 3339 with offset; a future one → 422); otherwise the reset time | Holds ¶2 |


---

# Stage-3 register revision r2 (2026-09-28): additions, restatements and decisions

Sources: auditor coverage review 90404c89-3acd-4738-90ac-d647d26943a9 (C1–C7), answered in 7b44ca24; adversary R3 findings 593f5bfd-c2a6-4e9d-8ef3-251d1673989c (R3-01 … R3-16); implementer reading I3-1 (51789bb2), accepted in 42638d32. All r1 rows stay in force unless restated. Every row is OPEN.

## New rows

| ID | Source | Obligation | Method → expected | Origin |
|---|---|---|---|---|
| S3-055 | Corrections ¶3 + known_at ¶ | The whole selected amount takes effect at the selected effective_at, not at the original created_at plus a delta. A same-amount revision with an earlier effective_at leaves current balances unchanged, but an as_of between the new and old instants shows the payment as already applied, and the statement entry moves (including into or out of a window) | API | R3-01 |
| S3-056 | C6 | Combined statement row: a settlement member appears at committed_at, once, with settlement_id; a capture appears once, at the capture time, with authorization_id; correcting either → 422 linked_payment_immutable | API | C6, R3-06 |
| S3-057 | S3-081 + known_at | as_of > expires_at > now → the open hold is released in the view at expires_at, even though no request occurred; a void recorded at t3 is invisible to known_at < t3 | API | R3-14 |
| S3-058 | D3-18 | After a 2→3 import, a stage-2 voided hold releases at the import time (tested as decision D3-18; historical available between the imported void and the import is not asserted as spec) | XC | C1 |

## Restated rows (the r1 text is kept above)

| ID | Restatement | Origin |
|---|---|---|
| S3-021 / S3-031 / S3-053 | Exact-instant boundaries, using the server's own returned strings: a correction whose effective_at equals as_of counts; effective_at equal to the statement `to` → excluded; equal to `from` → included; a known_at exactly equal to a recorded_at selects that revision | R3-04 |
| S3-030 | An invalid or empty `from` or `to` (a naive time, a bare date, empty) → 422, as for as_of | C2 |
| S3-041 | Named case: a user with only seeded payments that lack created_at (reset time), followed by API payments. A default `from` includes the seeded entries, and opening = seeded balance − the net of the seeded payments | R3-11 |
| S3-045 | Returned recorded_at strings strictly increase per payment, both as instants and as strings, even for two corrections within one millisecond | R3-13 |
| S3-049 | Adds the time-move case: A has 0; B pays A 500 at t1; A pays C 500 at t2; correcting A→C to an effective_at < t1 (same amount) → 409 historical_overdraft | R3-02 |
| S3-050 | Method: the sum over all users of /me?as_of=T&known_at=K equals the seeded total over a T×K grid (before any payment, each effective instant, each recorded_at, between them, and the future), after corrections that move amounts and times | R3-05 |
| S3-051 / D3-05 | Correcting a request payment leaves the request's status and payment_id and the original pay receipt unchanged; both parties' revisions reads work; a zero-amount request payment corrected upward debits the payer, with insufficient_funds judged against the payer's available | C4, R3-06 |
| S3-052 | Every /revisions entry has the correction-response shape {payment_id, revision, amount, effective_at, recorded_at, reason}; revision 1 has reason "" and effective_at = recorded_at = created_at; a failed correction or a replay appends nothing | C3, R3-07 |
| S3-053 / D3-14 | Boundary: with known_at between a payment's creation and a later correction, both parties' views show revision 1 only; with known_at before the creation, the payment is absent for BOTH parties | C5 |
| S3-054 / D3-06 / D3-12 | **Expected by design, not an inconsistency:** after a correction, /activity (and every other payment representation) shows revision 1's amount, while a statement entry's payment.amount shows the selected revision's amount | R3-08 |
| S3-072 / D2-13 | Stage-1 and stage-2 receipts replay byte-identical after 1→3 and 2→3, even though stage 3 adds fields such as closed_at. Source exports contain no snapshot tokens | C7 |
| S3-083 | Names the holds-only case: B receives 1000 at t1, authorizes 800 at t2 and voids at t3; correcting the t1 payment down to 100 effective t1 → 409 historical_overdraft, because historical available in [t2, t3) is negative, while current available is fine | R3-03 |
| S3-904 | The stage-2 suite on stage-3/ may need superset adaptations (for example, closed_at on authorizations), made in a separate test revision | R3-16 |

## Decisions added or revised in r2 (NOT source requirements)

| ID | Decision | Origin |
|---|---|---|
| D3-03 (extended) | A same-amount revision is valid and moves no money now, but may change history by moving effective_at (S3-055) | R3-01 |
| D3-11 (clarified) | historical_overdraft is evaluated at PAST boundaries only (instants ≤ now): every distinct effective_at, including both the proposed and the replaced revision's effective_at, every hold event time and every created_at. Movements at one instant are netted together first. Future expiries are not boundaries | R3-12 |
| D3-17 | A seeded open hold whose expires_at is at or before its created_at (the default reset time) produces no hold events, so it never held anything in history. Seeded closed holds produce no historical hold events either. closed_at: a seeded expired hold uses expires_at, and a seeded captured or voided hold uses its created_at | I3-1 |
| D3-18 | 2→3 import: a stage-2 export records no void time, so a stage-2 voided hold releases at the IMPORT time. This errs on the safe side for money, because it never accepts a real overdraft, at the cost of possibly rejecting a legitimate backdated correction. Captures on imported holds release at their capture payment's created_at, and expiries at expires_at. Recorded as a known limitation of 2→3 imports | C1 |
| D3-19 | Statement tie order "payment id ascending" = plain code-unit (byte) lexicographic order of the id string | R3-09 |
| D3-20 | Query instants: only the percent-decoded value is used. A decoded space where the offset should be (an unencoded `+`) is not RFC 3339 → 422. The echo returns the decoded string exactly. The suites send `%2B`; the literal `+` is tested only as this decision | R3-10 |
