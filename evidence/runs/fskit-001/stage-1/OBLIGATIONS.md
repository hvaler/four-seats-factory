# Obligation register — fskit-001 · Stage 1 (ACTIVE)

Run: fskit-001 · Track: pocketful · Active stage: 1 · Register owner: analyst (hugo.valer/analyst-thgs)
Kickoff checkout: C:\nexus\dev\dark-factory-wearedevs @ 803560d2a678ace1414465c098eb0ab5380ffade (verified with `git rev-parse HEAD`)
Spec: pocketful/spec/stage-1.md · SHA-256 65497dea09a8b432598c71662320cf66c3550e183cfd76e2d7f97318e0d30aa4 · 25082 bytes (Windows CRLF working-tree file; LF-normalised SHA-256 f5e4c644076cf5b480c072bc17a966f3b3e229272c44b301d333763be2c438a6; git blob dd44280488c44a920dbba08b3ce6e8f6ffe9e45a at 803560d2)
Other specs as read at dispatch (not active): stage-2 39aaf9d7…6e54 · stage-3 2255d3f2…6e54c · stage-4 1894b002…df1 (full hashes in STAGE-REGISTER.md)
Register revision: r1 (2026-09-28, before the adversary challenge). Rows are only ever added or re-stated in later revisions. Nothing is deleted.

Owners: **I** = implementer (production), **A** = adversary (independent challenge tests), **U** = auditor (reproduction and verdict). Every row is built by I, challenged by A and reproduced by U. "Method" names the acceptance method: `API` means black-box HTTP tests against a clean container of the frozen candidate; `CONC` means concurrent HTTP tests; `XC` means two independent containers; `HARN` means the official harness; `INSP` means inspection of the delivered files.

States: OPEN → CLAIMED → CHALLENGED → REPRODUCED → ACCEPTED | REJECTED | BLOCKED. All rows start OPEN.

## Invariants (§1)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-001 | §1 item 1 | The sum of all wallet balances always equals the total seeded by the last reset (or carried by the last import) | Every operation, including concurrent requests, retries, failures and settlements | CONC: sum over every user's GET /me after mixed concurrent load = seeded total | OPEN |
| S1-002 | §1 item 2 | No wallet balance is ever negative, including transiently | Concurrent payments, pays and settlements from one wallet whose total exceeds its balance | CONC: fire N concurrent debits whose total is greater than the balance; the successes never exceed the balance, the final balance is ≥0, every other response is 409 insufficient_funds and none is 5xx | OPEN |
| S1-003 | §1 item 3 | A payment request moves money at most once | Concurrent pay calls with different keys, pay racing cancel or decline, replays | CONC: exactly one payment per request; balances moved once | OPEN |
| S1-004 | §1, §4 | Money moves only between existing wallets; no deposit, top-up or withdrawal surface | — | INSP/API: no such endpoints are implemented | OPEN |

## Delivery and runtime (§2, §3)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-010 | §2 | stage-1/ contains a Dockerfile, the source, locked dependencies where supported, and a RUN.md whose command builds and starts the service with no manual setup | The folder builds with no reference to sibling folders; no symlinks, no submodules, no nested .git | INSP + a clean build following RUN.md exactly | OPEN |
| S1-011 | §2 | One image runs alone with `-e PORT=<port>` and a port mapping; all runtime dependencies, initialization and seed data are inside that container; Compose is not used | — | HARN + manual docker run | OPEN |
| S1-012 | §2 | No outbound network at runtime (fonts, scripts and similar assets included) | Isolated mode: internal network | HARN --mode isolated passes | OPEN |
| S1-013 | §2 table | Operates within 2 vCPU and 2 GiB; first healthy response within 60 s; up to 50 requests in flight; each request answered within 5 s (reset within 10 s); disk is ephemeral | Load with 50 in flight | CONC timing + HARN isolated | OPEN |
| S1-014 | §3.1 | Listens on 0.0.0.0 on $PORT, default 8080 | PORT unset → 8080 | API with PORT set and unset | OPEN |
| S1-015 | §3.2 | GET /health → 200 {"status":"ok"} once the service and its store can serve | Non-200 is allowed before ready; ≤60 s | API | OPEN |
| S1-016 | §3.3 | POST /_test/reset with a fixture → 204; replaces ALL state; afterwards only the fixture is visible; repeatable; needs no auth; must be enabled in the delivered image | Old tokens, keys, payments and requests are gone after reset | API: reset twice, old token → 401, old key reusable | OPEN |
| S1-017 | §3.4 | Requests and responses are application/json; charset=utf-8 | Every response, including errors | API header check | OPEN |
| S1-018 | §3.4 | Timestamps are RFC 3339 with an explicit offset | created_at, committed_at | API regex | OPEN |
| S1-019 | §3.4 | Unknown body fields and unknown query parameters are ignored, never an error | Every endpoint | API | OPEN |
| S1-020 | §3.4 | IDs are opaque strings of at most 64 characters | Generated ids; fixture ids are echoed | API length check | OPEN |

## Model and fixture (§4)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-030 | §4 | One currency, declared by the fixture (currency, minor_units ∈ {0,2,3}); every amount is an integer count of minor units; responses echo `currency` | EUR 2, JPY 0, BHD 3 | API with all three | OPEN |
| S1-031 | §4 | An API amount is valid when its numeric value is integral: 1000, 1000.0 and 1e3 are the same valid amount | Non-integral (1000.5) → 422; booleans and strings → 422 (§5) | API on every amount field (payments, requests, splits, settlement entries) | OPEN |
| S1-032 | §4 | A handle is unique across the service, matches ^[a-z0-9_]{1,20}$ and never changes | — | API | OPEN |
| S1-033 | §4 | A signup handle is derived from the email: take the local part, lowercase it, map every char outside [a-z0-9_] to `_`, truncate to 20 | e.g. "Ann.Lee+x@…" → "ann_lee_x"; a local part longer than 20; non-ASCII chars → `_` | API: GET /me handle after signup | OPEN |
| S1-034 | §4 | A new user has balance 0 and can immediately receive money and be asked for money | — | API | OPEN |
| S1-035 | §4 | A payment moves money from one wallet to another immediately and atomically; it is sent directly or created by paying a request | — | API | OPEN |
| S1-036 | §4 | A request's lifecycle: pending → exactly one of paid, declined or cancelled. Only the payer pays or declines; only the requester cancels | Terminal states never change | API | OPEN |
| S1-037 | §4 | A request may exceed the payer's balance: creation succeeds, the request stays pending, paying while short → 409 insufficient_funds with no change, and it becomes payable once funds arrive | — | API: create > balance, pay → 409, fund, pay → 201 | OPEN |
| S1-038 | §4 | Visibility belongs to the payment and is chosen by the payer when money moves; a request has no visibility and never appears in anyone's feed | — | API | OPEN |
| S1-039 | §4, §8 | Feed contract: GET /activity returns payments only. A payment appears for caller X **iff** visibility=public OR X is the sender OR X is the receiver. No other rule | Private payment: visible to both parties, hidden from third parties; the operator gets no extra visibility (§11) | API with 3+ users | OPEN |
| S1-040 | §4 | GET /requests returns only requests where the caller is requester or payer | Third parties never see them | API | OPEN |
| S1-041 | §4 | A split is not a feed item; its requests are visible only to their two parties | — | API | OPEN |
| S1-042 | §4 | Visibility is one value, seen identically by both parties and by everyone else | — | API compare representations | OPEN |
| S1-043 | §4 | Amount ≤ 1000000000 on any single request; no balance leaves ±2^53; arithmetic is exact (no floats and no rounding error) | Large seeded balances near 2^53; minor_units 0/3 | API | OPEN |
| S1-044 | §4 fixture | Reset accepts the fixture format: currency, minor_units, users (id, email, password, display_name, handle, balance), payments (id, from_user_id, to_user_id, amount, note, visibility), requests (id, requester_id, payer_id, amount, note, status), settlement_operator_ids (§11, default []) | Seeded requests in any status; seeded payments appear in the feed with their ids; the fields a seeded record lacks (created_at, request_id, settlement_id, payment_id) get sane values | API: seeded ids are readable through /activity and /requests | OPEN |
| S1-045 | §4 | Seeded users can log in immediately with their password | — | API | OPEN |
| S1-046 | §4 | A seeded balance is final (after seeded payments); seeded payments are NOT replayed against balances | — | API: /me = fixture balance | OPEN |
| S1-047 | §4 | A fixture balance < 0 → reset returns 422 validation_failed and changes nothing (the previous state survives) | — | API: good reset, bad reset, previous state still intact | OPEN |

## Errors and validation (§5)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-050 | §5 | Every 4xx/5xx body is {"error":{"code":…,"message":…}} with the specified status and code | Includes 404 on unknown routes and 405s | API | OPEN |
| S1-051 | §5 | 400 malformed_request: the body does not parse, or a field has the wrong JSON type (other than the special fields) | Non-object top-level body; wrong-typed to_handle, payer_handle, participant_handles, email, password or display_name | API | OPEN |
| S1-052 | §5 | 400 missing_idempotency_key: a required header is absent or empty | — | API on all 5 paths | OPEN |
| S1-053 | §5 | 401 unauthenticated: missing, malformed or unknown bearer token | "Bearer" with no token, the wrong scheme, a random token | API on every authenticated endpoint | OPEN |
| S1-054 | §5 | 422 validation_failed: a required field or query param is missing, or a value of the right type is invalid or out of range | — | API | OPEN |
| S1-055 | §5 | Endpoint field-rule precedence: an invalid amount (including strings and booleans), a non-string note (including null), and any visibility other than public/private → 422 validation_failed, never 400. Omitting an optional field selects its default | amount "100", true, null, 1.5, 0, -1, 1000000001; note null, 5; visibility "PUBLIC", null, 1 | API on every endpoint taking them | OPEN |
| S1-056 | §5 | An integer query param must be plain decimal digits: 1e9, 4.0 and +4 → 422 whatever their value | limit, offset | API | OPEN |
| S1-057 | §5 | Shared ranges: Idempotency-Key 1..255 chars (>255 → 422); limit 1..200; offset ≥0; otherwise 422 | Key of exactly 255 is OK and 256 → 422; limit 0/201 → 422; offset -1 → 422 | API | OPEN |
| S1-058 | §5 | No request produces a 5xx, including under concurrent load | Garbage input, 50 in flight | CONC + fuzz | OPEN |

## Authentication (§6)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-060 | §6 | POST /auth/signup {email,password,display_name} → 201 {user_id, display_name, token}; the user gets a derived handle and balance 0 | No handle field in the body | API | OPEN |
| S1-061 | §6 | POST /auth/login {email,password} → 200 {user_id, display_name, token} | Seeded and signed-up users | API | OPEN |
| S1-062 | §6 | Signup, email already registered → 409 email_taken | — | API | OPEN |
| S1-063 | §6 | Signup, password shorter than 8 chars → 422 validation_failed | Exactly 8 is OK | API | OPEN |
| S1-064 | §6 | Signup, email not of the form local@domain → 422 validation_failed | "", "a", "a@", "@b", "a@b@c"? | API | OPEN |
| S1-065 | §6 | Login with a wrong password or unknown email → 401 unauthenticated | — | API | OPEN |
| S1-066 | §6 | Signup whose derived handle is taken → 409 handle_taken, and no account is created (a later login with that email fails) | — | API | OPEN |
| S1-067 | §6 | Every endpoint except /health, /_test/reset, /_test/export, /_test/import, /auth/signup and /auth/login needs `Authorization: Bearer <token>` | — | API | OPEN |
| S1-068 | §6 | Tokens do not expire; an account may hold several valid tokens and concurrent sessions | Login twice; both tokens work | API | OPEN |
| S1-069 | §6 | Passwords are stored with bcrypt, scrypt, Argon2 or an equivalent, never in plaintext (seeded passwords included) | — | INSP source + export contains no plaintext password | OPEN |

## Idempotency (§7) — applies independently to POST /payments, /requests, /requests/{id}/pay, /splits, /settlements

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-070 | §7 | Exactly these five paths require the key; decline and cancel do not | — | API | OPEN |
| S1-071 | §7 | A key is scoped to the authenticated user; two users with the same key do not interact | — | API | OPEN |
| S1-072 | §7 | A replay is the same user + method + path + body. The same key and body on a different path is a new request and succeeds normally | e.g. the same key on /payments then on /requests; pay on rq_1 vs rq_2 | API | OPEN |
| S1-073 | §7 | First use → the normal 201 | — | API | OPEN |
| S1-074 | §7 | Replay → 200 with a body identical (as a JSON value) to the original, including ids and created_at | — | API | OPEN |
| S1-075 | §7 | Same key with a different body → 409 idempotency_key_reuse | — | API | OPEN |
| S1-076 | §7 | A key whose original request failed with any 4xx is treated as a first use (it stays reusable) | After 409 insufficient_funds, 422 or 404 on the key, reuse it with a valid or different body → 201 | API | OPEN |
| S1-077 | §7 | "Same body" means the same JSON value after parsing; key order and whitespace do not matter | See decision D-06 on numeric forms | API | OPEN |
| S1-078 | §7 | Concurrent identical requests with an unused key: exactly one 201, the others 200 with the same body; the effect happens once | 10–20 concurrent, on each of the 5 paths | CONC | OPEN |
| S1-079 | §7 | A successful replay returns the original response even after the resource changed (a request later paid or cancelled, balances changed) and makes no further state change | — | API | OPEN |
| S1-080 | §7 | Once the body has parsed as a JSON object and the caller is authenticated, an already-claimed key is resolved BEFORE field validation and current-resource checks: a successful key replayed with an invalid body → 409 idempotency_key_reuse | Invalid amount, unknown handle, or a request that is no longer pending | API | OPEN |

## API (§8)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-090 | §8 GET /me | Returns {user_id, display_name, handle, balance, currency, minor_units} | Needs auth | API | OPEN |
| S1-091 | §8 POST /payments | Body {to_handle, amount, note?="", visibility?="public"} → 201 payment {payment_id, from_user_id, from_handle, to_user_id, to_handle, amount, currency, note, visibility, request_id:null, settlement_id:null (§11), created_at} | — | API | OPEN |
| S1-092 | §8 POST /payments | Caller's balance < amount → 409 insufficient_funds | balance == amount is OK | API | OPEN |
| S1-093 | §8 POST /payments | amount <1, >1000000000 or not integral → 422 | Boundaries 1 and 1000000000 are OK | API | OPEN |
| S1-094 | §8 POST /payments | to_handle is the caller's own handle → 422 self_payment | — | API | OPEN |
| S1-095 | §8 POST /payments | note >200 chars → 422; visibility not public/private → 422 | Exactly 200 is OK (see D-07 on counting) | API | OPEN |
| S1-096 | §8 POST /payments | No user has that handle → 404 not_found | — | API | OPEN |
| S1-097 | §8 POST /payments | Debit and credit are one atomic step; a failed payment leaves no trace (no balance change, no feed item) | — | API/CONC | OPEN |
| S1-098 | §8 POST /payments | note is stored and returned verbatim: no trim, escape or normalisation; Unicode and emoji round-trip byte for byte | Leading/trailing spaces, NFC vs NFD, emoji, "<b>", "\u0000"? | API | OPEN |
| S1-100 | §8 POST /requests | Body {payer_handle, amount, note?} → 201 request {request_id, requester_id, requester_handle, payer_id, payer_handle, amount, currency, note, status:"pending", payment_id:null, created_at}; the caller is the requester | — | API | OPEN |
| S1-101 | §8 POST /requests | amount invalid → 422; payer_handle is the caller's own → 422 self_request; note >200 → 422; unknown handle → 404 | — | API | OPEN |
| S1-102 | §8 POST /requests | The payer's balance is NOT checked | amount > payer balance → 201 pending | API | OPEN |
| S1-110 | §8 pay | Only the payer may pay. Body {visibility?="public"} → 201 payment exactly as POST /payments returns one, with request_id set; the request becomes paid and carries payment_id | from = payer, to = requester, amount = the request's amount, note = the request's note (D-10) | API | OPEN |
| S1-111 | §8 pay | `{}` and `{"visibility":"public"}` are different bodies: a key reused across them → 409 idempotency_key_reuse | — | API | OPEN |
| S1-112 | §8 pay | Request not pending → 409 request_not_pending; payer short → 409 insufficient_funds; caller not the payer → 403 forbidden; unknown request → 404 | — | API | OPEN |
| S1-113 | §8 pay | Replaying a successful pay returns 200 with the original payment body even though the request is now paid; no additional money, never 409 request_not_pending | — | API | OPEN |
| S1-120 | §8 decline | Payer only, no key → 200 request status declined; declining an already-declined request → 200 current state; paid/cancelled → 409 request_not_pending; not the payer → 403; unknown → 404 | — | API | OPEN |
| S1-121 | §8 cancel | Requester only, no key → 200 request status cancelled; cancelling an already-cancelled request → 200; paid/declined → 409 request_not_pending; not the requester → 403; unknown → 404 | — | API | OPEN |
| S1-130 | §8 GET /requests | Only the caller's requests (requester or payer), newest first by created_at | — | API | OPEN |
| S1-131 | §8 GET /requests | direction ∈ {incoming (caller is payer), outgoing (caller is requester)} or absent = both; status ∈ {pending, paid, declined, cancelled} or absent = all; unknown values → 422 | Empty-string value (D-13) | API | OPEN |
| S1-132 | §8 GET /requests | limit default 50 (1..200), offset default 0 (≥0), out of range → 422; has_more is true iff items exist beyond the last one returned; response {requests:[…], has_more} | Exact page boundary: has_more false | API | OPEN |
| S1-140 | §8 POST /splits | Body {amount, participant_handles, note?} → 201 {split_id, amount, currency, note, shares:[{handle, amount}] (every participant including the caller, in the given order, summing to amount), requests:[…] (every participant except the caller, same order), created_at} | The caller may be omitted from the list; each request has the caller as requester and the share as amount | API | OPEN |
| S1-141 | §8 POST /splits | amount invalid → 422; participant_handles empty or with a duplicate → 422; note >200 → 422; any handle unknown → 404 | — | API | OPEN |
| S1-142 | §8 POST /splits | A split whose only participant is the caller is valid: one share, zero requests, "requests": [] | — | API | OPEN |
| S1-143 | §8/§9 splits | A share of 0 is legal and still produces a (pending) request for that participant | amount 1 across 3 → 1,0,0 | API | OPEN |
| S1-144 | §8 splits | A split checks nobody's balance; creation is atomic (all its requests or none) | — | API | OPEN |
| S1-150 | §8 GET /activity | Payments visible by S1-039, newest first by created_at; {payments:[…], has_more}; limit/offset exactly as in GET /requests | The order within one second is unspecified | API | OPEN |

## Money and rounding (§9)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-160 | §9 | Shares are whole minor units, sum exactly to amount and differ by ≤1; the remainder goes to the first participants in the given order | 1000/3 → 334,333,333; 1/3 → 1,0,0; 10/3 → 4,3,3; 999/3 → 333×3; 5/5 → 1×5; large amount 1000000000/7 | API | OPEN |
| S1-161 | §9 | A different order gives the extra unit to a different person; each split is independent of previous splits (no carried remainder) | — | API | OPEN |
| S1-162 | §9 | After any number of splits are paid in full, balances still sum to the seeded total | — | API/CONC | OPEN |

## Export and import (§10)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-170 | §10 | GET /_test/export (no auth) → 200 {track:"pocketful", format_version:1, state:{…}} | — | API | OPEN |
| S1-171 | §10 | POST /_test/import (no auth) takes the entire unchanged export object → 204 and atomically replaces all state | — | API | OPEN |
| S1-172 | §10 | No dependency on the source process, files, volume, port or network address: an export from container A imports into an independent container B | — | XC | OPEN |
| S1-173 | §10 | Import is replacement, not merge; repeating it restores the exported state without duplicating anything | Import twice → identical counts | API/XC | OPEN |
| S1-174 | §10 | Invalid JSON → 400 malformed_request; missing fields, wrong track, wrong format_version or an invalid state → 422 validation_failed, and the destination is unchanged | e.g. state missing, state not an object, track "tablekeeper", format_version 2 or "1" | API | OPEN |
| S1-175 | §10 | Export is an atomic, read-only snapshot; later source writes do not change it | Export during concurrent writes is internally consistent (sums match) | CONC | OPEN |
| S1-176 | §10 | Import preserves accounts and hashed-password login, existing bearer tokens, currency and minor_units, balances, payments, requests (with status and payment_id), settlement operator permissions and settlement membership, and all completed idempotent request bodies with their original responses; ids, timestamps and monetary records are neither regenerated nor replayed | After an A→B import: old tokens work on B, replays on B → 200 with the original body, a different body with the same key → 409, the old password logs in | XC | OPEN |
| S1-177 | §10 | Failed request keys stay reusable after import | — | XC | OPEN |
| S1-178 | §10 | Import removes all previous destination data and credentials (a destination-only token → 401 afterwards) | — | XC | OPEN |
| S1-179 | §10 | Reset clears all state, including imported state | — | API | OPEN |
| S1-180 | §10 | Test control calls complete within 10 s | Export and import of a populated state | API timing | OPEN |
| S1-181 | §10 | Exports are private test artifacts: snapshot contents and credentials stay out of public evidence, the repo and the room | — | INSP of evidence and commits | OPEN |

## Atomic net settlements (§11)

| ID | Source | Obligation | Boundary / error case | Method → expected | State |
|---|---|---|---|---|---|
| S1-190 | §11 | The fixture may include settlement_operator_ids (default []); an operator may settle across any wallets | Absent field → nobody is an operator | API | OPEN |
| S1-191 | §11 | The operator permission grants no access to other users' requests or private activity items | Operator GET /activity and /requests and pay/decline/cancel of others' requests | API | OPEN |
| S1-192 | §11 | POST /settlements: no token → 401; authenticated non-operator → 403 forbidden; an idempotency key is required | — | API | OPEN |
| S1-193 | §11 | Body {transfers:[{from_handle, to_handle, amount, note?, visibility?}]} with 1..32 entries; each entry uses the ordinary payment amount, note and visibility rules (defaults "" and public); unknown fields are ignored | 0 or 33 entries → 422 | API | OPEN |
| S1-194 | §11 | Unknown handle → 404; self-transfer (from == to) → 422 self_payment; malformed batch shape → 422 validation_failed | transfers missing, not an array, an entry that is not an object (D-15) | API | OPEN |
| S1-195 | §11 | Entry errors take precedence in input order, before insufficient funds: the error reported is the one on the first invalid entry | Entry 1 has an unknown handle and entry 2 a self-transfer → 404; the reverse → 422 self_payment | API | OPEN |
| S1-196 | §11 | Affordable ⇔ every wallet's balance after ALL incoming and outgoing transfers is ≥0 (final net, not sequential); otherwise 409 insufficient_funds | A chain where an early transfer overdraws unless later credits count → must succeed; the net is short by 1 → 409 | API | OPEN |
| S1-197 | §11 | All movements commit together or none do; failed validation claims no key and creates no payment or revision | After a failure the key is reusable and balances are unchanged | API/CONC | OPEN |
| S1-198 | §11 | 201 {settlement_id, committed_at, payments:[…] in input order}; every member is an ordinary payment with settlement_id, request_id null and created_at == committed_at | — | API | OPEN |
| S1-199 | §11 | Non-member payments expose settlement_id null (every payment representation carries the field) | /payments, pay, /activity, seeded payments | API | OPEN |
| S1-200 | §11 | Members follow ordinary feed visibility (per-entry visibility); the response contains every member's receipt | Private member hidden from third parties and the operator | API | OPEN |
| S1-201 | §11 | Replays → 200 with the original complete response | — | API | OPEN |
| S1-202 | §11 | Reset and import preserve operator permissions, original payments, requests, settlement membership and retry responses | — | XC | OPEN |
| S1-203 | §11 + §1 | Concurrent settlements and payments never leave a balance negative and conserve the total | — | CONC | OPEN |

## Stage-boundary and process obligations (dispatch)

| ID | Source | Obligation | Method → expected | State |
|---|---|---|---|---|
| S1-900 | dispatch, guide | stage-1/ implements stage 1 only: no stage-2+ behaviour (browser UI, holds, authorizations and so on). The stage-2 probe is expected not to pass its whole suite; nothing is added or removed to manipulate it | HARN next-stage probe fails; INSP | OPEN |
| S1-901 | dispatch | Built from the spec, with no code that detects tests or fixture examples; the harness is unmodified | INSP | OPEN |
| S1-902 | dispatch | Official `harness run --stage 1` by the adversary and the auditor on their own clean clones; the auditor's final run uses `--mode isolated`; report.json and logs are read (skips, uncollected tests and startup failures ≠ pass); `claimed stage: 1` | HARN | OPEN |
| S1-903 | dispatch | Evidence records under evidence/runs/fskit-001/stage-1 link obligation, product revision, test revision, command, env, outcome and artifact checksum | INSP | OPEN |

## Ambiguities and reasoned decisions (NOT source requirements)

| ID | Ambiguity | Decision (default for implementer; adversary may challenge) | Spec basis |
|---|---|---|---|
| D-01 | Git identity: every seat shares one OS git config | Each seat commits with its own identity: `git -c user.name="<role>-<suffix>" -c user.email="<role>-<suffix>@fskit-001.band.invalid" commit …` (e.g. implementer-thgt). No amend, rebase or squash | Guide "Configure Git names and emails for each seat" |
| D-02 | Order of checks for a write | 1) route/method; 2) auth → 401; 3) body parses as a JSON object, else 400 malformed_request; 4) for idempotent paths: key absent/empty → 400 missing_idempotency_key, key >255 → 422; 5) claimed-key resolution (replay → 200, different body → 409); 6) field types → 400 / field rules → 422, in body-field order as listed in the spec table; 7) resource existence/visibility → 404; 8) permission → 403; 9) state (request_not_pending) → 409; 10) funds → 409 insufficient_funds. Exception: POST /settlements checks operator (403) right after auth | §5, §7 last paragraph, §11 |
| D-03 | Payments: which of self_payment / not_found / insufficient comes first | 422 field rules (amount, note, visibility) → 422 self_payment → 404 not_found → 409 insufficient_funds. Same idea for requests (self_request) | §5 "422 unless endpoint specifies", §11 "before insufficient funds" |
| D-04 | A pay/decline/cancel by an authenticated user who is neither party | 403 forbidden (the endpoint rule "caller is not the payer/requester" overrides the generic "not visible" 404). An unknown id is 404 for everyone | §8 tables |
| D-05 | A handle string that does not match the handle regex (e.g. "Bob", "") in to_handle, payer_handle, participant_handles or from/to_handle | 404 not_found (no user has that handle), not 422. A missing field → 422; a non-string → 400 | §8 "No user has that handle" |
| D-06 | Idempotency body equality for numerically equal forms (1000 vs 1000.0 vs 1e3) | Parsed JSON values are compared with numbers by exact numeric value, so 1000 ≡ 1000.0 ≡ 1e3 (the same value) | §4 "represent the same valid amount", §7 "same JSON value" |
| D-07 | note length unit | Unicode code points (not bytes, not UTF-16 units) | §8 "200 characters" |
| D-08 | Email uniqueness/login case | Emails compared case-insensitively (trimmed? no: verbatim except for case) for email_taken and login | §6 |
| D-09 | Signup missing or empty display_name | Missing → 422; a non-string → 400; an empty string → 422 | §5 required field |
| D-10 | The note of a payment created by paying a request | Copies the request's note; visibility from the pay body | §8 pay "exactly as POST /payments" |
| D-11 | created_at for seeded payments/requests (absent from the fixture) | Assigned at reset time, strictly ordered by fixture order (earlier fixture index = older) so newest-first is deterministic | §4 fixture |
| D-12 | Seeded paid requests: payment_id | Null unless the fixture supplies one; accept an optional payment_id if present | §4 fixture |
| D-13 | An empty query value (?status=) | Treated as present and invalid → 422 | §8 GET /requests |
| D-14 | Concurrent same-key requests with DIFFERENT bodies | One is processed as the first use; the others, once it completes, get 409 idempotency_key_reuse if it succeeded, or are treated as a first use if it failed with a 4xx. Never a 5xx and never a double effect | §7 |
| D-15 | Settlement "malformed batch shape" vs the §5 wrong-type 400 | transfers missing, not an array, empty, >32 entries, or an entry not an object → 422 validation_failed. A wrong-typed entry field follows the payment rules (amount/note/visibility → 422; a non-string handle → 422 as batch shape) | §11 |
| D-16 | Payment/pay "insufficient funds" when balance == amount | Allowed (balance becomes 0) | §1 nonnegative |
| D-17 | Actual model id recording | Each seat records its own actual runtime model id and usage; analyst runs as claude-opus-5-5 (per its runtime), while run-config.json lists claude-opus-5; the discrepancy is recorded, not resolved by assumption | dispatch "Record actual model IDs" |
