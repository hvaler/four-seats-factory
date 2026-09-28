# Pocketful — stage 3

Wallet screens in the browser and the JSON API for payments, requests, splits,
settlements and payment authorizations, extended with historical balances,
paginated statements with snapshot tokens, and payment corrections with an
immutable revision history. It runs as one container
with no outbound network access at run time; every UI asset is served from the
image.

## Build and run

From this folder (`stage-3/`):

```sh
docker build -t pocketful-stage-3 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-stage-3
```

Then open <http://localhost:8080/>. The service listens on `0.0.0.0:$PORT`
(default `8080`), and `GET /health` returns `200 {"status":"ok"}` within a second
of start. No manual setup, seed data, volume or second container is needed. Load
state with `POST /_test/reset`, then sign in at `/login` as a seeded user, or
create an account at `/signup`.

To run under the stage limits:

```sh
docker run --rm --cpus 2 --memory 2g -e PORT=8080 -p 8080:8080 pocketful-stage-3
```

## History API (stage 3)

| Endpoint | Purpose |
|---|---|
| `GET /me?as_of=&known_at=` | Balance, total, available and held as they stood at `as_of` (inclusive), using what was known at `known_at` |
| `GET /statement?from=&to=&known_at=&limit=&offset=` | The caller's payments in `[from, to)` by effective time, with running balances and a `snapshot` token |
| `GET /statement?snapshot=&limit=&offset=` | Pages the frozen result of an earlier statement read |
| `POST /payments/{id}/corrections` | Appends a revision (new amount and effective time); the difference moves between the same two wallets |
| `GET /payments/{id}/revisions` | The payment's revision history, for its two parties |

## Screens

| Route | Screen |
|---|---|
| `/` | Available balance (headline), total and held, pay form, request form, reserve (authorize) form, activity feed |
| `/requests` | Incoming and outgoing requests, with pay, decline and cancel |
| `/split` | Split form with a live share preview |
| `/authorizations` | Holds you made or can collect, with collect (capture) and release (void), plus the reserve form |
| `/signup`, `/login` | Account screens |

`/requests` and `/authorizations` are shared with the API. A `GET` whose Accept
header lists `text/html` (at a quality no lower than `application/json`) gets
the page; anything else gets JSON.

## Implementation tests

These need Node.js 22 or later on the host. They use no dependencies.

```sh
npm test                                   # starts the service in-process
BASE_URL=http://127.0.0.1:8080 npm test    # against a running container
```

A browser regression test (Python 3.12+ with Playwright and Chromium) runs
against a running container and resets its state:

```sh
python test/browser/capture_draft_test.py http://127.0.0.1:8080
```

## Design

- **Runtime:** Node.js 22 (`node:22-alpine`, pinned by digest) using only the
  standard library. `package-lock.json` locks the (empty) dependency set. The UI
  is plain JavaScript and CSS with system fonts, so there is no build step.
- **State:** held in memory in one process, and lost on restart, as the spec
  allows. Each write runs synchronously from idempotency-key resolution to
  commit, so the event loop serialises every money movement. Concurrent
  requests therefore behave like some serial order.
- **Holds:** each open authorization reserves its uncaptured remainder on the
  payer. `available = total − held`, and every `insufficient_funds` check
  (payments, request payments, settlement final nets, new authorizations) uses
  `available`. Expiry is derived from the clock whenever a hold is read or
  written, so a hold is released at `expires_at` with no timer and no request at
  the deadline. A capture spends its own reservation.
- **Money:** every amount and balance is an exact integer (`BigInt`). JSON
  numbers are read from their source text. The UI converts typed decimals to
  minor units exactly and rejects extra decimal places instead of rounding.
- **Idempotency:** seven write paths, each keyed by (user, method, path, key). A
  replay returns the stored original response bytes with 200.
- **Browser:** the session token is kept in `localStorage`, so a signed-in
  browser survives an export/import upgrade. Each form keeps its
  (Idempotency-Key, body) pair while its fields are unchanged, so a
  resubmission or a retry after a lost response never pays twice. Reads are
  versioned so the latest refresh wins. All user text is inserted as text, and a
  Content-Security-Policy allows only same-origin assets.
- **History:** every payment keeps immutable revisions (revision 1 is the
  original, effective and recorded at `created_at`). A view selects, per
  payment, the latest revision recorded by `known_at` and applies it at its
  effective time; holds contribute creation, capture and release events. All
  instants are compared at nanosecond resolution. A correction is refused with
  `historical_overdraft` if it would make total or available negative at any
  past boundary where the existing history is not already that low.
- **Upgrade:** `POST /_test/import` accepts this service's exports and the
  stage-1 service's exports. Stage-1 and stage-2 exports import
  with revision 1 for every payment and openings derived from the imported
  balances; a stage-2 voided hold, whose void time was not recorded, releases
  at the import time.
- **Passwords:** scrypt (N=2^12, r=8, p=1, 16-byte random salt).

## Layout

| Path | Contents |
|---|---|
| `src/server.js` | HTTP server, body reading, response writing |
| `src/app.js` | routing, content negotiation and every API handler |
| `src/store.js` | state model, holds and expiry, fixture reset, export/import |
| `src/ledger.js` | instants, revision selection, historical balances and holds, overdraft check |
| `src/ui.js` | serves the UI shell and static assets |
| `src/ui/` | `index.html`, `app.js`, `app.css`, `icon.svg` |
| `src/json.js` | exact JSON number parsing, canonical form, serialisation |
| `src/password.js` | scrypt hashing and verification |
| `test/` | implementation tests (`node --test`) |
