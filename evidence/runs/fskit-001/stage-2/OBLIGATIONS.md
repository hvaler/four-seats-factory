# Obligation register — fskit-001 · Stage 2 (ACTIVE) · revision r2 (the r2 section is at the end)

Run: fskit-001 · Track: pocketful · Active stage: 2 · Register owner: analyst (hugo.valer/analyst-thgs)
Kickoff: C:\nexus\dev\dark-factory-wearedevs @ 803560d2a678ace1414465c098eb0ab5380ffade
Specs in force (cumulative): stage-1.md (CRLF SHA-256 65497dea09a8b432598c71662320cf66c3550e183cfd76e2d7f97318e0d30aa4, LF f5e4c644076cf5b480c072bc17a966f3b3e229272c44b301d333763be2c438a6) + stage-2.md (CRLF SHA-256 39aaf9d7743c6fd831663e5b8363866f7d70795e5efb9000c2803f471397b13f, LF 699fcdd4b410754242945dde50e15d3470160d11b43b84314c042ed26317af12, git blob bc4acc5a5e8c5af04ccd8540e2005625854fa1b7). Both were re-read in full at the start of stage 2.
Accepted base: stage 1 ACCEPTED at beeaec72ff53fa75469c5f09236a786632f21fd8, stage-1 tree 347efba502629e5b5bbd730f35c34bdfe208c478 (verdict 72be202b). main after the evidence merges: 527d87589b0b6f994cb79da4593bac6e626f6a3c.

Owners and method codes as in the stage-1 register: I = implementer, A = adversary, U = auditor. `API`, `CONC`, `XC` (two independent containers), `HARN`, `INSP`, plus `UI` (a real browser, e.g. Playwright/Chromium, run by A and U themselves) at **375 px and ≥1280 px** widths. All rows start OPEN.

## 0. Cumulative rule

**Every stage-1 obligation S1-001 … S1-206 and S1-900 … S1-903 (stage-1 register r2), and every stage-1 decision (D-01 … D-32 as revised), remains in force for stage-2/, except where section 1 below explicitly supersedes it.** The stage-1 suite must still pass against stage-2/. Stage-1 obligations are re-verified on stage-2/, not inherited from the stage-1 verdict.

## 1. Stage-1 rows superseded or extended by stage 2

| Row | Stage-2 change | Source (stage-2.md) |
|---|---|---|
| S1-001 | The sum of all wallet `total` values equals the seeded total; holds move no money | Authorizations inv. 1 |
| S1-002 | `available = total − held` is never negative; held funds cannot fund new payments, authorizations or settlement net debits; captures may spend their own reservation | inv. 2 |
| S1-070 | Seven idempotent paths: the stage-1 five + POST /authorizations + POST /authorizations/{id}/capture; void has no key | API changes |
| S1-090 | GET /me adds `total` (== `balance`), `available` and `held` | GET /me |
| S1-091 / S1-110 / S1-198 / S1-199 | Every payment representation adds `authorization_id` (null unless created by a capture); request_id and settlement_id semantics unchanged | capture |
| S1-092 / S1-112 / S1-196 | insufficient_funds is evaluated against `available` (payments, pay, settlement final net) | API changes |
| S1-044 / S1-047 | The fixture adds `authorization_ttl_seconds` (default 600; if supplied, a positive integer, else 422) and `authorizations` (optional; omission = []); the sum of seeded unexpired open holds > the user's balance → 422, no change | Model |
| S1-050 / D-25 | `/`, `/requests`, `/split`, `/signup`, `/login` and `/authorizations` now serve HTML for `Accept: text/html` | Routes |
| S1-170 … S1-178, S1-202 | Export/import also carries authorizations (status, captures, expiry), the TTL, and every stage-2 idempotency record; format stays `track:"pocketful", format_version:1` (D2-01) | Existing clients |
| S1-900 | stage-2/ implements stages 1–2 only; no stage-3 behaviour (corrections, historical views, statements); the stage-3 probe is expected not to pass its whole suite | dispatch |

## 2. Delivery (stage 2)

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S2-001 | dispatch §1 | stage-2/ is a full copy of the ACCEPTED stage-1 tree 347efba5 (excluding nested .git), extended only inside stage-2/. stage-1/ remains byte-identical (tree 347efba5). No symlinks, submodules or references to sibling folders | INSP: `git rev-parse <c>:stage-1` == 347efba5; diff shows the first stage-2 commit == the copy | OPEN |
| S2-002 | §2 (st1) + st2 intro | Dockerfile, RUN.md and locked deps in stage-2/; all UI assets (JS, CSS, fonts) are served from the image with no runtime outbound fetch | INSP + HARN isolated (browser suite) | OPEN |

## 3. Routing and UI contract

| ID | Source | Obligation | Boundary | Method → expected | State |
|---|---|---|---|---|---|
| S2-010 | Routes table | `/`, `/requests`, `/split`, `/signup` and `/login` are reachable by URL (direct navigation), in server- or client-side rendering; other screens are reachable through the UI | Deep-link load of each route in a fresh browser | UI | OPEN |
| S2-011 | Routes | `/requests` and `/authorizations`: `Accept: text/html` → the UI; without that header → the JSON API (stage-1 behaviour for /requests) | GET /requests with Bearer and no Accept → JSON; with Accept text/html → HTML | API | OPEN |
| S2-012 | Signup/login table | testids: signup-email, signup-password, signup-display-name, signup-submit; login-email, login-password, login-submit; auth-error (present only when there is an error); current-user (visible on every screen when signed in; text contains the display name); current-handle (text is exactly the handle, no `@`, no other words); logout-button | Wrong password → auth-error; after logout, signed-out state | UI | OPEN |
| S2-013 | Balance/pay | testids: wallet-balance (text exactly the formatted amount; `data-amount` = minor units), pay-handle, pay-amount, pay-note, pay-visibility (a select with option values `public`/`private`), pay-submit, pay-error (on refusal, including insufficient funds), request-handle, request-amount, request-note, request-submit, request-error | — | UI | OPEN |
| S2-014 | Balance/pay | The pay form keeps its values after success. Re-submitting without changing a field sends NO new payment: wallet-balance falls once, the feed has one payment, pay-error is absent. Changing any field makes the next submit a new payment (new key). Retries follow §7 | Double-click / double submit | UI + API count | OPEN |
| S2-015 | Formatted amount | Formatted = decimal with exactly minor_units places, one space, the currency code (`100.00 EUR`, `1200 JPY`, `1.500 BHD`); no sign | minor_units 0/2/3 | UI | OPEN |
| S2-016 | Formatted amount | Decimal input → minor units: with mu=2, `15.00` and `15` → 1500 and `15.5` → 1550. Non-numeric input or more than minor_units decimals (`15.005`) shows the form's error element and sends NO request (no rounding). Applies to pay, request, split, authorize and capture inputs | mu=0: `15.0`? (D2-05); `-5`, `1e3`, `abc`, empty | UI + network log | OPEN |
| S2-017 | Activity | activity-list (children newest first in the DOM); activity-item-{payment_id} with data-visibility; activity-parties-{id} (text contains both handles); activity-amount-{id} (exactly formatted); activity-note-{id} (exactly the note, present even when empty); empty-activity shown instead of the list when nothing is visible | Feed contract as S1-039 (private visible to parties only) | UI | OPEN |
| S2-018 | Requests | incoming-list and outgoing-list; request-item-{id} with data-status; request-amount-{id} exactly formatted; request-pay-{id} and request-decline-{id} only on pending incoming; request-cancel-{id} only on pending outgoing; request-error on a refused pay, decline or cancel; empty-requests when both lists are empty | Paid/declined/cancelled items have no action buttons | UI | OPEN |
| S2-019 | Split | split-amount (decimal, same rule), split-handles (comma-separated, in order), split-note, split-submit, split-error; split-preview shows the §9 shares BEFORE posting, with one split-share-{handle} per participant (text exactly formatted); the preview and the submitted split have identical shares | 1000/3 in both orders; the caller included and omitted; whitespace around commas (D2-06) | UI + API | OPEN |
| S2-020 | Post-action refresh | After any successful action, the balance, feed and request lists on the same page show the new state without a manual reload; navigation waits for the write to succeed before refreshing | — | UI | OPEN |
| S2-021 | Competing clients | wallet-refresh on `/` refreshes the balance and feed without clearing the pay form; **latest refresh wins**: a delayed earlier read never overwrites a later refresh, even with out-of-order responses | Network-delay injection in the browser test | UI | OPEN |
| S2-022 | Competing clients | A payment refused because another client spent the balance → pay-error, the balance/feed refresh, and all pay inputs are preserved | — | UI | OPEN |
| S2-023 | Competing clients | A request cancelled elsewhere while its pay button is visible: clicking pay → request-error, and the request list refreshes so the stale pay button disappears | — | UI | OPEN |
| S2-024 | Uncertain outcome | A lost payment response (including after POST /payments committed) shows pay-uncertain (non-empty text), NOT pay-error; the unchanged form stays retryable with the **same key and body**; a successful retry removes pay-error and pay-uncertain, refreshes the balance and feed, and money moves exactly once. An unknown outcome is never shown as a confirmed rejection | Abort the response after commit (route interception) | UI + API | OPEN |
| S2-025 | No live sync | No background polling or live synchronisation is required; this browser refreshes only after its own action or an explicit refresh. The same refresh rules apply to available/held | — | INSP/UI | OPEN |
| S2-026 | UI authorizations | A new route /authorizations (HTML for text/html, JSON otherwise). testids: wallet-balance (formatted total; existing display and data-amount kept); wallet-available (formatted available, with data-amount; **the headline number**); wallet-held (formatted held, with data-amount; ABSENT when held = 0); authorize-handle/-amount/-note/-visibility/-submit (same input rules as pay); authorize-error (on refusal, including insufficient available) | — | UI | OPEN |
| S2-027 | UI authorizations | authorization-list (newest first in the DOM); authorization-item-{id} with data-status; authorization-amount-{id} (exactly the formatted authorized amount); authorization-captured-{id} (the formatted captured amount, present ONLY when status is captured); authorization-expires-{id} (text is the RFC 3339 expires_at); authorization-capture-amount-{id} (a decimal input pre-filled with the remaining amount, only on an incoming open authorization); authorization-capture-{id} (only on incoming open); authorization-void-{id} (only on outgoing open); authorization-error (a refused capture or void); empty-authorizations | Partial capture (final:false) leaves the item open with a reduced prefill | UI | OPEN |
| S2-028 | UI authorizations | The UI reflects seeded and newly created holds; available funds are shown as the spending balance, including immediately after a reset with open holds | — | UI | OPEN |

## 4. Product quality (graded as App; verified by inspection and the browser at both widths)

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S2-030 | Visual direction ¶1 | A coherent, presentation-ready consumer-finance look with a calm, trustworthy character; once holds exist, available is the most prominent monetary value, with total and held visibly secondary; payments, requests, splits and authorizations are easy to scan; status, direction, privacy and money movement are understandable without raw API data | UI screenshots at 375 px and 1280 px; U judges against this row | OPEN |
| S2-031 | ¶2 | A consistent visual system (typography, spacing, colour, controls, feedback); primary actions are obvious; the available, held, pending, loading, successful, refused and uncertain states are visually distinct; people, amounts and timestamps are formatted for people, with technical ids exposed only where useful | UI screenshots of each state | OPEN |
| S2-032 | ¶3 | Required flows are usable at 375 CSS px and at desktop widths with **no horizontal page scroll** (document scrollWidth ≤ viewport width) | UI measure scrollWidth on every route at both widths | OPEN |
| S2-033 | ¶3 | Inputs have visible labels; keyboard focus is apparent (a visible focus indicator); text and controls have sufficient contrast (WCAG AA 4.5:1 for body text as the band's measure, D2-07) | UI: tab through forms; contrast check | OPEN |
| S2-034 | ¶3 | Considered empty, loading and error states; navigation is consistent across all required routes | UI | OPEN |

## 5. Upgrade from stage 1 (existing clients)

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S2-040 | Existing clients | stage-2/ accepts an unchanged export produced by the ACCEPTED stage-1 service (tree 347efba5): accounts, tokens, balances, payments, requests, operators, settlements and idempotency records; holds default to none (available = total) | XC: populate a stage-1 container, export, import into an independent stage-2 container | OPEN |
| S2-041 | Existing clients | A browser signed in on stage 1 before the upgrade stays signed in afterwards (same token), with no reload or new screen required | UI + XC: import between browser requests | OPEN |
| S2-042 | Existing clients | Existing pending requests stay payable through the request screen after the import | UI + XC | OPEN |
| S2-043 | Existing clients | A payment whose response was lost before the export stays retryable after import with the same body and key; the UI recovers the original payment (200 replay) and refreshes the imported balance; the form and the pending retry identity survive the upgrade; money moves once | UI + XC | OPEN |
| S2-044 | dispatch §3 | Upgrade evidence uses populated exports, preserves original receipts and retry identities, and exercises the imported state; resetting to a fresh fixture is not a migration test. Snapshots and credentials stay private | U reproduces 1→2 in fresh containers; UPGRADE-REPORT pair 1→2 | OPEN |

## 6. Authorizations and captures (model + API)

| ID | Source | Obligation | Boundary / error | Method → expected | State |
|---|---|---|---|---|---|
| S2-050 | Authorizations ¶1 | An authorization places a hold on the payer: it reserves money and moves none; a capture moves money; a final capture releases the uncaptured rest; a non-final capture keeps the rest held; an open authorization expires on its own and releases its remainder | — | API | OPEN |
| S2-051 | inv. 3 | Cumulative captures ≤ the authorized amount; each idempotent capture moves money once; a closed hold cannot be captured again | Concurrent captures on one authorization | CONC | OPEN |
| S2-052 | GET /me | {user_id, display_name, handle, balance, total, available, held, currency, minor_units}; balance == total always; held = the sum of open holds; available = total − held ≥ 0; with no open holds, balance = total = available and held = 0, and every earlier behaviour is unchanged | — | API | OPEN |
| S2-053 | API changes | POST /payments stays an immediate transfer, with no intermediate hold or capture step; paying a request stays immediate; authorizing a request is out of scope; POST /splits is unchanged | — | API | OPEN |
| S2-054 | Model | Fixture authorizations: {id, from_user_id, to_user_id, amount, note, visibility, status ∈ open/captured/voided/expired, expires_at}; only open holds anything; available is derived (never seeded); seeded expiry times are absolute | A seeded open with past expires_at → expired, holding nothing | API | OPEN |
| S2-055 | Model | authorization_ttl_seconds applies to every API-created authorization; default 600; if supplied it must be a positive integer (else reset 422 with no change); expires_at = created_at + ttl | ttl 0, -1, 1.5, "600" → 422 | API | OPEN |
| S2-056 | Model | The sum of seeded **unexpired open** holds > the user's balance → reset 422, no change (expired or closed seeded holds don't count) | — | API | OPEN |
| S2-057 | Expiry | An authorization whose expires_at ≤ now is expired and holds nothing, with **no request needed at the deadline**: GET /authorizations shows status expired (never open) and GET /me's available includes the released remainder; status=expired filter matches, open does not | A short TTL (e.g. 2 s) via the fixture | API (sleep past expiry) | OPEN |
| S2-058 | POST /authorizations | Idempotency-Key required; the caller is the payer; body {to_handle, amount, note?="", visibility?="public"} → 201 {authorization_id, from_user_id, from_handle, to_user_id, to_handle, amount, captured_amount:0, currency, note, visibility, status:"open", expires_at, payment_id:null, payment_ids:[], remaining_amount (=amount), created_at} | — | API | OPEN |
| S2-059 | POST /authorizations | available < amount → 409 insufficient_funds; amount <1, >1e9 or non-integral → 422; to_handle == self → 422 self_payment; note >200 or bad visibility → 422; unknown handle → 404 | Held funds can't back a second authorization | API | OPEN |
| S2-060 | POST /authorizations | An open authorization is NOT a feed item and never appears in GET /activity | Nor voided or expired ones; only capture payments appear | API | OPEN |
| S2-061 | capture | Idempotency-Key required; only the receiver (to) may capture; body {amount?, final?}; amount defaults to the remaining amount; a replay needs the identical body ({} ≠ {"amount":2000} → 409 idempotency_key_reuse) | — | API | OPEN |
| S2-062 | capture | 201 returns a **payment** in exactly the POST /payments shape with authorization_id set and request_id null; payment amount = the captured amount; note and visibility copied from the authorization; it appears in the feed by the ordinary rule; money moves payer → receiver | — | API | OPEN |
| S2-063 | capture default | By default (final true): the authorization becomes captured, carries captured_amount and payment_id, and releases the uncaptured remainder in the same step (capture 1500 of 2000 → 500 returns to the payer's available at once); a second capture → 409 authorization_not_open | — | API | OPEN |
| S2-064 | extended capture | `final:false` with a remainder left → status stays open and further captures are allowed up to the remainder; capturing the entire remainder closes it even with final:false; a final capture closes it and releases any remainder; capture_exceeds_authorization compares with the REMAINING amount; an omitted amount = the remainder; captured_amount is cumulative; payment_id = the latest capture; payment_ids lists every capture in order; every authorization response includes remaining_amount (0 when closed) | 700 then 700 then 600 of 2000 | API | OPEN |
| S2-065 | extended capture | Void and expiry can close a partially captured authorization: they release only the remainder and preserve all capture records (captured_amount, payment_ids, payments) | — | API | OPEN |
| S2-066 | extended capture | "New fields do not change idempotency body equality": body equality stays the §7 JSON-value rule (D2-03) | — | API | OPEN |
| S2-067 | capture errors | Not open → 409 authorization_not_open; expires_at ≤ now → 409 authorization_expired; amount > remainder → 422 capture_exceeds_authorization; amount <1 or non-integral → 422 validation_failed; caller not the receiver (including a non-party) → 403; unknown → 404 | `final` non-boolean (D2-04) | API | OPEN |
| S2-068 | void | Only the payer; no idempotency key; 200 with the authorization, status voided, hold released; voiding a voided one → 200 with current state; captured or expired → 409 authorization_not_open; non-payer (including a non-party) → 403; unknown → 404 | A body is ignored (as for decline) | API | OPEN |
| S2-069 | GET /authorizations | Only authorizations where the caller is payer or receiver; newest first by created_at; direction outgoing (payer) / incoming (receiver) / absent; status one of the four or absent (clock-expired matches expired, never open); limit/offset/has_more exactly as GET /requests (422 on bad values) | — | API | OPEN |
| S2-070 | Concurrent ops | Concurrent requests produce the same results as some serial order (linearizable), and every invariant holds at every read: concurrent capture vs void vs expiry, authorization vs payment competing for available, settlement vs hold | — | CONC | OPEN |
| S2-071 | inv. 1–2 | Conservation of total and non-negative available under mixed concurrent authorizations, captures, voids, payments and settlements | — | CONC | OPEN |

## 7. Process (stage 2)

| ID | Obligation | Method | State |
|---|---|---|---|
| S2-900 | The official harness `--stage 2` runs suites 1 and 2 (and the stage-3 probe, expected not to pass whole) on clean clones by A and U; U's final run uses `--mode isolated` | HARN | OPEN |
| S2-901 | Browser evidence at mobile (375) and desktop widths recorded by A and U themselves, in addition to API results | UI | OPEN |
| S2-902 | UPGRADE-REPORT pair 1→2 with two separate containers, populated source, preserved receipts and retry identities | XC | OPEN |
| S2-903 | Evidence records under evidence/runs/fskit-001/stage-2 | INSP | OPEN |

## Ambiguities and decisions (NOT source requirements)

| ID | Ambiguity | Decision | Basis |
|---|---|---|---|
| D2-01 | Export format after stage 2 | Keep `track:"pocketful", format_version:1` (§10 says another version is 422, and stage-2 must accept stage-1 exports); the opaque state may carry an internal schema marker. Missing stage-2 parts in a stage-1 export mean an empty authorization list and TTL 600 | §10, Existing clients |
| D2-02 | Capture error precedence | 401 → 400 unparseable → 400 missing key → 422 key length → claimed-key resolution → 400 wrong types (`final` not boolean → 400) → 422 amount rules (<1, non-integral) → 404 unknown → 403 not the receiver → 409 authorization_expired (expires_at ≤ now, including seeded status expired) → 409 authorization_not_open (captured/voided) → 422 capture_exceeds_authorization | §5, §7, capture table |
| D2-03 | "New fields do not change idempotency body equality" | Body equality is still the whole-JSON-value rule (D-26): adding `final:true` explicitly makes a different body from omitting it (→ 409 on key reuse); the new response fields don't alter replayed originals | stage-2 capture ¶, D-26 |
| D2-04 | `final` of the wrong type | 400 malformed_request (a field of the wrong JSON type; not in the amount/note/visibility exception) | §5 |
| D2-05 | Decimal input edge cases in forms | Trim surrounding whitespace; accept digits with an optional `.` and at most minor_units decimal digits; for mu=0 only plain integers are accepted (`15.` and `15.0` are rejected); reject signs, exponents, thousands separators, empty; values <1 or >1e9 minor units go to the API, which answers 422 → form error | Formatted amount ¶ |
| D2-06 | split-handles parsing | Split on commas, trim whitespace around each handle, drop nothing else; an empty element → client error without sending (or server 422); the order is kept | Split table |
| D2-07 | "Sufficient contrast" measure | WCAG 2.x AA: 4.5:1 for normal text, 3:1 for large text and UI component boundaries | Visual ¶3 |
| D2-08 | Void on a clock-expired but status-open authorization | 409 authorization_not_open (treated as expired) | void ¶ |
| D2-09 | Authorization expiry vs capture racing at the deadline | An instant ≥ expires_at is expired; comparisons use server time at the moment the write commits | Expiry ¶ |
| D2-10 | How the UI keeps the pay retry identity | The page keeps (key, body) in memory while the form is unchanged; a changed field → a new key; nothing persists across a page reload (not required) | Uncertain ¶, Existing clients ¶ |
| D2-11 | Session storage in the browser | The token is stored client-side (e.g. localStorage) so a signed-in browser keeps working after an export/import upgrade without re-login; logout clears it | Existing clients ¶ |
| D2-12 | Seeded authorizations' created_at | Assigned at reset in fixture order (as D-11/D-32), with the absolute expires_at taken from the fixture; captured_amount for seeded captured authorizations = amount unless supplied | Model |


---

# Stage-2 register revision r2 (2026-09-28): additions, restatements and decisions

Sources:
- auditor coverage review 0751e812-c687-442e-8872-37d79ebe9157 (points B1–B9), answered in 640b688e;
- adversary R2 findings 919ff78e-79db-4483-9ccc-1fb268e28475 (R2-01 … R2-20);
- implementer readings I2-1 and I2-2 (5aab7ab3), accepted in 212d9f8e.

All r1 rows stay in force unless restated below. Every row is OPEN.

## New rows

| ID | Source | Obligation | Method → expected | Origin |
|---|---|---|---|---|
| S2-035 | "Text is exactly the note", S2-031 | Notes, display names and handles render as TEXT, never as HTML. An XSS payload (`<img src=x onerror=alert(1)>`, `</td><script>…`) appears verbatim in activity, request, split and authorization note elements, and no dialog opens and no element is injected | UI | R2-11 |
| S2-072 | inv. 2 "captures may spend the money reserved for them" | A payer with available 0 (total = held) can still be captured in full. A capture never raises insufficient_funds. After a partial FINAL capture, held falls by the full remainder, total by the captured amount, and the rest returns to available | API | B2, R2-04 |
| S2-073 | §7 on the two new paths | Replaying POST /authorizations after the authorization was captured, voided or expired → 200 with the original body (status open). Replaying a capture after a later void or expiry → 200 with the original payment, never not_open or expired. A claimed capture key with an invalid body (e.g. amount above the remainder) → 409 idempotency_key_reuse. A failed capture (4xx) leaves its key reusable | API | R2-05 |
| S2-074 | §10 + Expiry | A hold exported before its expires_at and imported (into another container) after it reads as expired and holds nothing | XC | B4 |
| S2-904 | Cumulative rule | Stage-1 suites on stage-2/: harness suite 1 (inside `--stage 2`) and the adversary's stage-1 suite re-run against stage-2/. A test superseded by a stage-2 change (e.g. the exact /me body) is adapted in a new, separately recorded test revision, with nothing else weakened | HARN + A suite | B9, R2-19 |

## Restated rows (supersede the r1 wording; the r1 text is kept above)

| ID | Restatement | Origin |
|---|---|---|
| S2-011 | Negotiation per D2-14 | B8, R2-03 |
| S2-012 | Signup errors (email_taken, handle_taken, short password) and a wrong login each show auth-error. A successful signup leaves the user signed in, with current-handle = the derived handle. Signed-out navigation to /, /requests, /split and /authorizations shows no user data and offers login/signup. Logout clears only the client session (tokens do not expire server-side, §6) | R2-14 |
| S2-014 | Includes a rapid double click where the second click lands before the first response: exactly one payment | R2-16 |
| S2-015 / S2-019 | No thousands grouping (`1234567.89 EUR`, `1000000000 JPY`). A zero share renders `0.00 EUR`. data-amount is the integer minor units | R2-12 |
| S2-020 | Also: after capture or void on /authorizations, wallet-available, wallet-held and the list refresh; after authorize on /, the wallet numbers refresh; after a split, /requests shows the new requests once navigated to. Navigation waits for the write to succeed | R2-17 |
| S2-027 | The capture prefill uses the decimal input form (`20.00`, not `2000`) and after a partial non-final capture shows the new remainder. Editing it above the remainder → authorization-error (server 422) with the input kept. authorization-captured-{id} is present ONLY when status = captured (absent for open-partial and expired-partial, while captured_amount remains in the API). The testid rule governs authorization-expires-{id} (exact RFC 3339); human-friendly formatting (S2-031) applies elsewhere | R2-13, R2-10, B7 |
| S2-030 / S2-031 | Measurable proxies, recorded by A and U: (a) the computed font-size/weight of wallet-available exceeds wallet-balance and wallet-held; (b) each request and authorization status differs in a computed style or a text badge; (c) error, uncertain and success feedback differ in colour or iconography; (d) no raw ISO timestamp or bare id text in feed rows (except authorization-expires). Plus screenshots of every route at 375 and 1280 px. The verdict on these rows stays with the auditor | R2-18 |
| S2-032 | Measured with worst-case content: a 200-character note with no spaces, 20-character handles, a display name of 60+ characters, the largest amounts, and 50+ feed items, at 375 px on every required route plus /authorizations | R2-15 |
| S2-055 | The created_at and expires_at strings differ by exactly the TTL. Observable expiry happens at expires_at (the status just before it is open, with a 0.5 s margin; 1 s after it, expired). Reset validation per D2-15 | R2-06, R2-07, R2-20 |
| S2-056 | Boundary: seeded unexpired open holds EQUAL to the balance → 204 with available 0 | R2-07 |
| S2-060 / S2-069 | Voided and expired authorizations never appear in /activity (only capture payments do). The operator gets no access to others' authorizations. The listing ignores the authorization's visibility (only the parties see it). The response shape is `{"authorizations":[…],"has_more":…}` | R2-08, B5 |
| S2-065 | payment_id stays the latest capture after a void or expiry; payment_ids keeps its order and never shrinks | R2-10 |
| S2-068 | "A captured or expired one is 409 authorization_not_open" on void is SPEC. Only the clock-expired-while-status-open case is decision D2-08 | B6 |
| S1-196 (superseded) | The settlement final net is evaluated against available: a wallet whose net debit is ≤ total but > available (it would eat into held) → 409 insufficient_funds, and nothing is committed | B3, R2-09 |
| S1-112 (superseded) | Paying a request with only held money → 409 insufficient_funds | R2-09 |
| S2-057 | Timing method: TTL = 2 s; the "after" check allows no margin 1 s past expires_at; the "before" check uses a 0.5 s margin; the host/container clock skew is recorded | R2-20 |

## Decisions added or revised in r2 (NOT source requirements)

| ID | Decision | Origin |
|---|---|---|
| D2-02 (revised) | Capture precedence: 401 → 400 unparseable → 400 missing key → 422 key length → claimed-key resolution → 400 wrong types (`final` not boolean) → 422 amount rules → 404 unknown → 403 not the receiver → **409 authorization_not_open for captured/voided, whatever the clock** → **409 authorization_expired for status expired (seeded, or open with expires_at ≤ now)** → 422 capture_exceeds_authorization | R2-01; replaces the r1 D2-02 |
| D2-13 | A replay returns the stored original response bytes unchanged, even when they lack newer fields: a stage-1 payment replayed on stage-2 has no authorization_id. Reads (/activity etc.) always include authorization_id. The XC test asserts replay body == the stage-1 original | B1, R2-02 |
| D2-14 | Negotiation on /requests and /authorizations: HTML only for **GET** when Accept explicitly lists `text/html` with q>0 and at a q not lower than `application/json`. `*/*`, a missing Accept and `application/json` → JSON. Every non-GET method → JSON whatever the Accept. `/`, `/split`, `/signup` and `/login` are UI-only and serve HTML regardless | B8, R2-03 (merged) |
| D2-15 | Reset validation for authorizations (extends D-24): an unknown from/to user, from = to, an amount outside 1..1e9 or non-integral, a status outside the four, a missing or unparseable expires_at or one without an offset, a duplicate id, or authorization_ttl_seconds of 0, -1, 1.5, "600", true or null → 422, and nothing changes | R2-07 |
| D2-16 | The authorize form appears on both `/` and `/authorizations`, one instance per page (never twice on the same page) | I2-1 |
| D2-17 | Stage-2 timestamps have millisecond precision in RFC 3339 with an explicit offset (`…T21:40:00.123+00:00`). Seeded and imported timestamps (including stage-1 export values) are preserved verbatim, never regenerated | I2-2 |

## Decision added after r2 (message 12a694af → analyst reply)

| ID | Decision | Origin |
|---|---|---|
| D2-18 | Browser scenario for S2-041…043: the stage-2 UI (document and assets) loads from the stage-2 origin; before the switch, its fetch/XHR data calls are routed to the ACCEPTED stage-1 container; the stage-1 state is exported and imported into an independent stage-2 container between browser requests; after the switch every call goes to stage 2, with no reload. Checks: the token still works; a stage-1 pending request can be paid from /requests; a pay whose response was lost after commit on stage 1, retried with the same key and body, gets the original stage-1 receipt (200, bytes per D2-13) and money moves once. The same checks also run with a stage-2→stage-2 switch after importing a stage-1 export. Consequences: the UI fetches its data from the JSON API (same origin); it tolerates stage-1 /me bodies (missing total/available → balance, missing held → 0) and payments without authorization_id | R2-21 |
