# Pocketful — stage 2

Wallet screens in the browser, plus the stage-1 JSON API extended with payment
authorizations (holds), captures, voids and expiry. It runs as one container
with no outbound network access at run time; every UI asset is served from the
image.

## Build and run

From this folder (`stage-2/`):

```sh
docker build -t pocketful-stage-2 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-stage-2
```

Then open <http://localhost:8080/>. The service listens on `0.0.0.0:$PORT`
(default `8080`), and `GET /health` returns `200 {"status":"ok"}` within a second
of start. No manual setup, seed data, volume or second container is needed. Load
state with `POST /_test/reset`, then sign in at `/login` as a seeded user, or
create an account at `/signup`.

To run under the stage limits:

```sh
docker run --rm --cpus 2 --memory 2g -e PORT=8080 -p 8080:8080 pocketful-stage-2
```

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
- **Upgrade:** `POST /_test/import` accepts this service's exports and the
  stage-1 service's exports. The latter import with no holds and the default
  TTL of 600 s.
- **Passwords:** scrypt (N=2^12, r=8, p=1, 16-byte random salt).

## Layout

| Path | Contents |
|---|---|
| `src/server.js` | HTTP server, body reading, response writing |
| `src/app.js` | routing, content negotiation and every API handler |
| `src/store.js` | state model, holds and expiry, fixture reset, export/import |
| `src/ui.js` | serves the UI shell and static assets |
| `src/ui/` | `index.html`, `app.js`, `app.css`, `icon.svg` |
| `src/json.js` | exact JSON number parsing, canonical form, serialisation |
| `src/password.js` | scrypt hashing and verification |
| `test/` | implementation tests (`node --test`) |
