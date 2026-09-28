# Pocketful — stage 1

A JSON HTTP service for wallets, payments, payment requests, bill splits and
atomic net settlements (stage-1 specification). It runs as one container with
no outbound network access at run time.

## Build and run

From this folder (`stage-1/`):

```sh
docker build -t pocketful-stage-1 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-stage-1
```

The service listens on `0.0.0.0:$PORT` (default `8080`). `GET /health` returns
`200 {"status":"ok"}` within a second of start. No manual setup, seed data,
volume or second container is needed; load state with `POST /_test/reset`.

To run under the stage limits:

```sh
docker run --rm --cpus 2 --memory 2g -e PORT=8080 -p 8080:8080 pocketful-stage-1
```

## Implementation tests

These need Node.js 22 or later on the host. They use no dependencies.

```sh
npm test                                   # starts the service in-process
BASE_URL=http://127.0.0.1:8080 npm test    # against a running container
```

## Design

- **Runtime:** Node.js 22 (`node:22-alpine`, pinned by digest) using only the
  standard library (`node:http`, `node:crypto`). `package-lock.json` locks the
  (empty) dependency set.
- **State:** held in memory in one process, and lost on restart, as the spec
  allows. Each write runs synchronously from idempotency-key resolution to
  commit, so the event loop serialises every money movement. A payment, a
  request payment and a whole settlement are each applied in one step that no
  other request can interleave with. So balances never go negative, even
  transiently, the seeded total is conserved and a request is paid at most once.
- **Reset and import** build a complete replacement state first and then swap
  it in with a single assignment. A rejected fixture or import changes nothing.
- **Money:** every amount and balance is an exact integer (`BigInt`). JSON
  numbers are read from their source text, so `1000`, `1000.0` and `1e3` are
  the same amount, while `1000.00000000000001` is not an integer.
- **Idempotency:** each key is scoped to (user, method, path, key). A successful
  first use stores the canonical request body and the exact response bytes.
  Replays return those bytes with status 200.
- **Passwords:** stored as scrypt hashes (N=2^12, r=8, p=1, 16-byte random
  salt). Plaintext is never stored.
- **Export/import:** `GET /_test/export` returns `{track, format_version: 1,
  state}`. The state carries users with password hashes, tokens, payments,
  requests, splits, settlements, operators and idempotency records. Exports
  contain credentials and must be handled as private test artifacts.

## Layout

| Path | Contents |
|---|---|
| `src/server.js` | HTTP server, body reading, response writing |
| `src/app.js` | routing and every endpoint handler |
| `src/store.js` | state model, fixture reset, export/import validation |
| `src/json.js` | exact JSON number parsing, canonical form, serialisation |
| `src/password.js` | scrypt hashing and verification |
| `test/` | implementation tests (`node --test`) |
