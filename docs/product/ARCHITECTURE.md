# Architecture of the service

> Written by the operator **after** the run, by reading the accepted code in `stage-4/`
> (`181947069`). It describes what the implementer built; it is not output of the band, and nothing
> here changed the product. Where a design choice has a name in the band's register (`D2-14`,
> `D3-21`…), that name is given so it can be looked up in `evidence/`.

## In one picture

```
browser ──HTTP──▶ node:http server ──▶ router ──▶ handler ──▶ state (one object, in memory)
                  server.js            app.js     app.js       store.js · ledger.js
                                                     │
                                          json.js (exact numbers) · password.js (scrypt)
                                          ui.js  (HTML shell + static assets from the image)
```

One Node.js 22 process, one container, **no dependencies**: `package-lock.json` lists none, and the
code uses only the standard library (`node:http`, `node:crypto`, `node:fs`). The image is
`node:22-alpine` pinned by digest and runs as the unprivileged `node` user. Nothing is fetched at run
time, which is what lets the service start in an isolated container with no outbound network.

About 2,400 lines of server code in `stage-4/src/`:

| File | Lines | What it does |
|---|---:|---|
| `server.js` | 82 | HTTP server, body reading, strict UTF-8, security headers |
| `app.js` | 1,133 | Routes, request handlers, validation, idempotency |
| `store.js` | 788 | The state object, reset / export / import, holds |
| `ledger.js` | 201 | Historical views, instants, overdraft checks |
| `json.js` | 94 | A JSON parser that never rounds a number |
| `password.js` | 49 | scrypt hashing |
| `ui.js` | 35 | Serves the browser UI from the image |
| `errors.js` | 18 | The error type every handler throws |

## Request path

`server.js` reads the body (capped at 64 MiB) and decodes it as **strict** UTF-8: invalid bytes are
rejected rather than replaced. It hands a small context — method, path, query, headers, body text —
to `app.handle`.

The router is a single ordered table of `[method, pattern, handler]` rows. A path that matches with
the wrong method returns **405**, an unknown path **404**, so the two are never confused. Every
failure is an `ApiError` rendered as `{"error": {"code", "message"}}`; anything unexpected becomes a
500 with code `internal_error` and is logged, never leaked.

`/requests` and `/authorizations` are shared by the API and the UI: the server chooses HTML or JSON
from the `Accept` header's quality values (`D2-14`). Every other screen is UI only.

## Money is exact

**Amounts are integers in minor units, held as `BigInt`**, in a single currency whose `minor_units`
is 0, 2 or 3. They never pass through a binary floating-point number.

That starts at the parser. `json.js` keeps every number as **its source text** (`JNum`) and decides
exactly whether it is integral, so `1000`, `1000.0` and `1e3` are the same amount and `1000.5` is
rejected, with no rounding in between. A boolean or a string where an amount belongs is a validation
error, not a coercion. Amounts are bounded (`1` to `1,000,000,000`), and exports write them as decimal
strings.

## Every write is atomic

The whole state lives in **one in-memory object**. Every write handler runs **synchronously from
idempotency resolution to commit** — there is no `await` between reading the state and mutating it —
so concurrent requests are serialised by the event loop, and no request can observe another one
half-applied. A settlement that moves money between several wallets commits all members together or
none.

Reset and import build a complete new state first and swap it in with one assignment.

State does not survive a restart. The specification allows that, and the service says so rather than
pretending otherwise.

## Idempotency

Eleven write handlers in stage 4 require an `Idempotency-Key` (1 to 255 characters). The key is
scoped to **(user, method, path, key)** and resolved **before** any field validation:

- same key, same body → the **original response**, replayed with `200`, byte for byte;
- same key, different body → `409 idempotency_key_reuse`;
- bodies are compared in **canonical form**, so key order and whitespace do not make a retry look
  like a different request;
- **only a successful `201` claims a key.** A first attempt that fails leaves the key unused, so the
  client can retry it once the cause is fixed.

The replay was verified live for these docs: `POST /payments` with key `demo-pay-1` returned `201`,
and the identical retry returned `200` with an identical body. See [`FEATURES.md`](FEATURES.md).

## Passwords

`scrypt` (RFC 7914) with a random salt per password, `N=2^12, r=8, p=1` — about 4 MiB and a few tens
of milliseconds per hash. The cost is set by a stage limit rather than by taste: fifty concurrent
logins must each finish within five seconds on two vCPUs. For an unknown email, login still verifies
the password against a dummy hash, so a missing account costs the same scrypt work as an existing
one.

## Holds expire without a timer

An open authorization **reserves** money on its payer, so `/me` reports `balance`, `available` and
`held` separately. Expiry is derived from the clock **whenever an authorization is looked at** (a
*sweep*), so a hold is released at its deadline with no background job and no request needed to
trigger it. Partial captures reduce the hold; the last capture, a void or expiry releases the rest.

## History, corrections and statements (stage 3)

Every payment has an **immutable revision history**. Revision 1 is the original, with
`effective_at = recorded_at = created_at`. A correction never edits a revision: it appends the next
one, and it must name the revision it expects to replace (`expected_revision`), so two concurrent
corrections cannot both win — the second gets `409 stale_revision`.

Historical views take two instants: `as_of` (when it happened) and `known_at` (what was known at the
time). Every instant is a strict RFC 3339 timestamp with an explicit offset, compared as a **`BigInt`
count of nanoseconds** since the epoch, so fractional seconds of any precision compare exactly.

A correction may not make any balance negative at a past instant (`409 historical_overdraft`). When a
past boundary was **already** negative, the band's decision `D3-21` is to accept a correction that
does not make it more negative. That is an interpretation of the stage-3 text and is flagged as such
in [`FACTORY.md`](../../FACTORY.md).

### Statement snapshots, and the crash they caused

`GET /statement` returns a page plus a **snapshot token**, so later pages come from the same frozen
view even while new payments arrive. The first stage-3 candidate stored each snapshot as a copy of the
whole statement; under sustained reads it ran out of heap after 4,761 reads and lost all state
(`F3-A01`).

The accepted design stores a snapshot as **(window, known_at, write watermark)** — constant size per
token. Every revision carries a monotonically increasing write sequence number, and revisions are
immutable, so each page is **re-derived** from history with everything above the watermark ignored.
After the repair the auditor ran 20,000 reads at 39.7 MiB.

Tokens are kept in a `Map` and never deleted. Space per token is constant, but the total grows with
the number of tokens issued; that is an open item, listed in `FACTORY.md`. The specification requires
earlier tokens to keep working, so any fix must be a more compact representation, not expiry.

## Refunds and correction batches (stage 4)

A **refund** is a new payment from the original receiver back to the sender, linked by `refund_of`.
Only the receiver may refund; a refund cannot itself be refunded; and refunds are bounded by the
payment's **current** amount — including after corrections — so a payment cannot be corrected below
what has already been refunded.

A **correction batch** applies up to 32 corrections to distinct payments **atomically**, and only a
settlement operator may submit one. Captures and refunds are immutable and cannot be corrected.
**Every check runs before anything is applied**: each item's expected revision and refund floor;
affordability, computed on the **net** change per wallet across the whole batch; and historical
overdraft for every wallet the batch touches. Only then are balances moved and revisions appended,
all stamped with one shared `recorded_at`.

## The browser UI (stages 2–4)

One HTML shell for every screen, plus `app.js`, `app.css` and an icon, **read from the image at start
up**. Pages are served with a strict Content-Security-Policy (`default-src 'self'`, no inline script,
`frame-ancestors 'none'`) and `X-Content-Type-Options: nosniff`. The session token lives in
`localStorage`, so a signed-in browser survives a reload.

Screens: sign-in and sign-up; the wallet (available, total and held, pay, request, reserve, and the
activity feed); requests, incoming and outgoing; split a bill; and holds, with capture and release.
The harness exercises them at 375 px and 1280 px. [Screenshots](FEATURES.md#screens).

## Between stages

Each `stage-N/` is a complete, self-contained copy of the service: it builds alone and shares no code
with its siblings. `GET /_test/export` and `POST /_test/import` move a populated state between
containers. The auditor verified all six upgrade pairs — 1→2, 1→3, 2→3, 1→4, 2→4, 3→4 — in fresh,
separate containers with real exports, and recorded byte-identical receipts after the move
([`UPGRADE-REPORT.md`](../../evidence/runs/fskit-001/UPGRADE-REPORT.md)).
