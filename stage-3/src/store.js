'use strict';

// The whole service state lives in one in-memory object. Every mutation runs
// synchronously on the single event loop, so each operation (including a
// multi-transfer settlement) is atomic and no other request can observe it
// half-applied. Reset and import build a complete new state first and then
// swap it in with one assignment.
//
// Holds (stage 2): an open authorization reserves money on its payer. Expiry is
// derived from the clock whenever an authorization is looked at (sweep), so a
// hold is released at its deadline without any request or timer.

const crypto = require('node:crypto');
const { JNum, isObject } = require('./json');
const { invalid, malformed } = require('./errors');
const { hashPassword, isValidHash } = require('./password');
const ledger = require('./ledger');

const HANDLE_RE = /^[a-z0-9_]{1,20}$/;
const STATUSES = new Set(['pending', 'paid', 'declined', 'cancelled']);
const AUTH_STATUSES = new Set(['open', 'captured', 'voided', 'expired']);
const VISIBILITIES = new Set(['public', 'private']);
const MINOR_UNITS = new Set([0, 2, 3]);
const MAX_ID = 64;
const DEFAULT_TTL = 600;
const SCHEMA = 3;
const RFC3339 = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$/i;

function newState(currency = 'EUR', minorUnits = 2) {
  return {
    currency,
    minorUnits,
    ttlSeconds: DEFAULT_TTL,
    total: 0n,
    users: new Map(),
    byHandle: new Map(),
    byEmail: new Map(),
    tokens: new Map(),
    payments: [],
    paymentById: new Map(),
    requests: [],
    requestById: new Map(),
    authorizations: [],
    authById: new Map(),
    splits: new Map(),
    settlements: new Map(),
    operators: new Set(),
    idem: new Map(),
    snapshots: new Map(),
    seq: 0,
  };
}

let state = newState();

const current = () => state;
const replace = (next) => { state = next; };

// RFC 3339 with an explicit numeric offset and millisecond precision.
function timestamp(date = new Date()) {
  return date.toISOString().replace(/Z$/, '+00:00');
}

function newId(prefix, taken) {
  let id;
  do {
    id = prefix + crypto.randomBytes(12).toString('base64url');
  } while (taken.has(id));
  return id;
}

function newToken(s) {
  let token;
  do {
    token = crypto.randomBytes(32).toString('base64url');
  } while (s.tokens.has(token));
  return token;
}

function addUser(s, user) {
  user.openAuths = new Set();
  user.payments = [];
  user.authsOut = [];
  if (user.opening === undefined) user.opening = 0n;
  s.users.set(user.id, user);
  s.byHandle.set(user.handle, user);
  s.byEmail.set(user.email, user);
}

// Every payment has an immutable revision history; revision 1 is the original
// amount with effective_at = recorded_at = created_at.
function revision(number, amount, effectiveAt, recordedAt, reason) {
  return {
    revision: number,
    amount,
    effectiveAt,
    effNs: ledger.ns(effectiveAt),
    recordedAt,
    recNs: ledger.ns(recordedAt),
    reason,
  };
}

// Stamps a revision with the next write sequence number (snapshot watermark).
function stamp(s, rev) {
  if (rev.seq === undefined) rev.seq = (s.seq += 1);
  else if (rev.seq > s.seq) s.seq = rev.seq;
  return rev;
}

function addPayment(s, payment) {
  payment.createdNs = ledger.ns(payment.createdAt);
  if (!payment.revisions) payment.revisions = [revision(1, payment.amount, payment.createdAt, payment.createdAt, '')];
  for (const rev of payment.revisions) stamp(s, rev);
  s.payments.push(payment);
  s.paymentById.set(payment.id, payment);
  s.users.get(payment.fromId).payments.push(payment);
  s.users.get(payment.toId).payments.push(payment);
}

function addRequest(s, request) {
  s.requests.push(request);
  s.requestById.set(request.id, request);
}

function addAuthorization(s, auth) {
  auth.createdNs = ledger.ns(auth.createdAt);
  auth.expiresNs = ledger.ns(auth.expiresAt);
  if (auth.closedAt === undefined) auth.closedAt = null;
  auth.closedNs = auth.closedAt === null ? null : ledger.ns(auth.closedAt);
  if (auth.lifecycle === undefined) auth.lifecycle = true;
  if (auth.createHold === undefined) auth.createHold = auth.amount;
  s.authorizations.push(auth);
  s.authById.set(auth.id, auth);
  s.users.get(auth.fromId).authsOut.push(auth);
  if (auth.status === 'open') s.users.get(auth.fromId).openAuths.add(auth);
}

// ---------------------------------------------------------------------------
// Holds

// Brings an authorization's status up to date with the clock: an open
// authorization at or past its deadline is expired and releases its remainder.
function sweep(s, auth, now = Date.now()) {
  if (auth.status === 'open' && now >= auth.expiresMs) {
    auth.status = 'expired';
    auth.closedAt = auth.expiresAt;
    auth.closedNs = auth.expiresNs;
    s.users.get(auth.fromId).openAuths.delete(auth);
  }
  return auth;
}

// Releases an open hold with a final status (captured or voided) at an event time.
function close(s, auth, status, at) {
  auth.status = status;
  auth.closedAt = at;
  auth.closedNs = ledger.ns(at);
  s.users.get(auth.fromId).openAuths.delete(auth);
}

const remaining = (auth) => (auth.status === 'open' ? auth.amount - auth.captured : 0n);

function held(s, user, now = Date.now()) {
  let sum = 0n;
  for (const auth of [...user.openAuths]) {
    sweep(s, auth, now);
    sum += remaining(auth);
  }
  return sum;
}

const available = (s, user, now = Date.now()) => user.balance - held(s, user, now);

function idemKey(userId, method, path, key) {
  return JSON.stringify([userId, method, path, key]);
}

// ---------------------------------------------------------------------------
// Validation helpers shared by reset and import. Every failure is a 422.

function need(cond, what) {
  if (!cond) throw invalid(what);
}

function id(v, what) {
  need(typeof v === 'string' && v.length >= 1 && v.length <= MAX_ID, `${what} must be a string id of 1..${MAX_ID} characters`);
  return v;
}

function str(v, what) {
  need(typeof v === 'string', `${what} must be a string`);
  return v;
}

function optStr(v, what, dflt) {
  if (v === undefined) return dflt;
  return str(v, what);
}

function nullableId(v, what) {
  if (v === undefined || v === null) return null;
  return id(v, what);
}

function arr(v, what, dflt) {
  if (v === undefined && dflt !== undefined) return dflt;
  need(Array.isArray(v), `${what} must be an array`);
  return v;
}

function obj(v, what) {
  need(isObject(v), `${what} must be an object`);
  return v;
}

// A JSON number with an integral value, as an exact BigInt.
function jint(v, what) {
  const n = v instanceof JNum ? v.toBigInt() : null;
  need(n !== null, `${what} must be an integer`);
  return n;
}

// An exact integer written as a decimal string (the export format).
function sint(v, what) {
  need(typeof v === 'string' && /^-?\d{1,40}$/.test(v), `${what} must be an integer string`);
  return BigInt(v);
}

function visibility(v, what) {
  const out = v === undefined ? 'public' : v;
  need(VISIBILITIES.has(out), `${what} must be public or private`);
  return out;
}

function status(v, what) {
  need(STATUSES.has(v), `${what} must be one of ${[...STATUSES].join(', ')}`);
  return v;
}

function authStatus(v, what) {
  need(AUTH_STATUSES.has(v), `${what} must be one of ${[...AUTH_STATUSES].join(', ')}`);
  return v;
}

function rfc3339(v, what) {
  need(typeof v === 'string' && RFC3339.test(v) && !Number.isNaN(Date.parse(v)), `${what} must be an RFC 3339 timestamp`);
  return v;
}

function unique(map, key, what) {
  need(!map.has(key), `duplicate ${what}: ${key}`);
}

function setOpenings(s) {
  for (const user of s.users.values()) {
    user.opening = user.balance;
    for (const p of user.payments) user.opening += p.fromId === user.id ? p.amount : -p.amount;
  }
}

// ---------------------------------------------------------------------------
// Reset (§3.3, §4, §11; stage 2 Model)

async function stateFromFixture(fx) {
  if (!isObject(fx)) throw malformed('the fixture must be a JSON object');
  const currency = str(fx.currency, 'currency');
  need(currency.length > 0, 'currency must not be empty');
  const minorUnits = Number(jint(fx.minor_units, 'minor_units'));
  need(MINOR_UNITS.has(minorUnits), 'minor_units must be 0, 2 or 3');

  const s = newState(currency, minorUnits);
  if (fx.authorization_ttl_seconds !== undefined) {
    const ttl = jint(fx.authorization_ttl_seconds, 'authorization_ttl_seconds');
    need(ttl >= 1n && ttl <= 10n ** 12n, 'authorization_ttl_seconds must be a positive integer');
    s.ttlSeconds = Number(ttl);
  }
  const now = Date.now();
  const created = timestamp(new Date(now));
  const passwords = [];

  arr(fx.users, 'users').forEach((raw, i) => {
    const u = obj(raw, `users[${i}]`);
    const user = {
      id: id(u.id, `users[${i}].id`),
      email: str(u.email, `users[${i}].email`),
      pwHash: null,
      displayName: str(u.display_name, `users[${i}].display_name`),
      handle: str(u.handle, `users[${i}].handle`),
      balance: jint(u.balance, `users[${i}].balance`),
    };
    const password = str(u.password, `users[${i}].password`);
    need(HANDLE_RE.test(user.handle), `users[${i}].handle does not match ^[a-z0-9_]{1,20}$`);
    need(user.balance >= 0n, `users[${i}].balance must not be negative`);
    unique(s.users, user.id, 'user id');
    unique(s.byHandle, user.handle, 'handle');
    unique(s.byEmail, user.email, 'email');
    addUser(s, user);
    s.total += user.balance;
    passwords.push([user, password]);
  });

  arr(fx.payments, 'payments', []).forEach((raw, i) => {
    const p = obj(raw, `payments[${i}]`);
    const payment = {
      id: id(p.id, `payments[${i}].id`),
      fromId: id(p.from_user_id, `payments[${i}].from_user_id`),
      toId: id(p.to_user_id, `payments[${i}].to_user_id`),
      amount: jint(p.amount, `payments[${i}].amount`),
      note: optStr(p.note, `payments[${i}].note`, ''),
      visibility: visibility(p.visibility, `payments[${i}].visibility`),
      requestId: nullableId(p.request_id, `payments[${i}].request_id`),
      settlementId: nullableId(p.settlement_id, `payments[${i}].settlement_id`),
      authorizationId: nullableId(p.authorization_id, `payments[${i}].authorization_id`),
      createdAt: p.created_at === undefined ? created : rfc3339(p.created_at, `payments[${i}].created_at`),
    };
    need(ledger.ns(payment.createdAt) <= ledger.msToNs(now), `payments[${i}].created_at is in the future`);
    need(s.users.has(payment.fromId) && s.users.has(payment.toId), `payments[${i}] refers to an unknown user`);
    need(payment.fromId !== payment.toId, `payments[${i}] must be between two different users`);
    need(payment.amount >= 1n, `payments[${i}].amount must be positive`);
    unique(s.paymentById, payment.id, 'payment id');
    addPayment(s, payment);
  });

  arr(fx.requests, 'requests', []).forEach((raw, i) => {
    const r = obj(raw, `requests[${i}]`);
    const request = {
      id: id(r.id, `requests[${i}].id`),
      requesterId: id(r.requester_id, `requests[${i}].requester_id`),
      payerId: id(r.payer_id, `requests[${i}].payer_id`),
      amount: jint(r.amount, `requests[${i}].amount`),
      note: optStr(r.note, `requests[${i}].note`, ''),
      status: r.status === undefined ? 'pending' : status(r.status, `requests[${i}].status`),
      paymentId: nullableId(r.payment_id, `requests[${i}].payment_id`),
      createdAt: created,
    };
    need(s.users.has(request.requesterId) && s.users.has(request.payerId), `requests[${i}] refers to an unknown user`);
    need(request.requesterId !== request.payerId, `requests[${i}] must be between two different users`);
    need(request.amount >= 1n, `requests[${i}].amount must be positive`);
    unique(s.requestById, request.id, 'request id');
    addRequest(s, request);
  });

  arr(fx.authorizations, 'authorizations', []).forEach((raw, i) => {
    const a = obj(raw, `authorizations[${i}]`);
    const what = `authorizations[${i}]`;
    const expiresAt = rfc3339(a.expires_at, `${what}.expires_at`);
    const auth = {
      id: id(a.id, `${what}.id`),
      fromId: id(a.from_user_id, `${what}.from_user_id`),
      toId: id(a.to_user_id, `${what}.to_user_id`),
      amount: jint(a.amount, `${what}.amount`),
      captured: 0n,
      note: optStr(a.note, `${what}.note`, ''),
      visibility: visibility(a.visibility, `${what}.visibility`),
      status: a.status === undefined ? 'open' : authStatus(a.status, `${what}.status`),
      expiresAt,
      expiresMs: Date.parse(expiresAt),
      paymentIds: [],
      createdAt: a.created_at === undefined ? created : rfc3339(a.created_at, `${what}.created_at`),
    };
    need(ledger.ns(auth.createdAt) <= ledger.msToNs(now), `${what}.created_at is in the future`);
    need(s.users.has(auth.fromId) && s.users.has(auth.toId), `${what} refers to an unknown user`);
    need(auth.fromId !== auth.toId, `${what} must be between two different users`);
    need(auth.amount >= 1n && auth.amount <= 1000000000n, `${what}.amount must be from 1 to 1000000000`);
    if (a.captured_amount !== undefined) auth.captured = jint(a.captured_amount, `${what}.captured_amount`);
    else if (auth.status === 'captured') auth.captured = auth.amount;
    need(auth.captured >= 0n && auth.captured <= auth.amount, `${what}.captured_amount is out of range`);
    need(auth.status !== 'open' || auth.captured < auth.amount, `${what} is open with nothing left to capture`);
    if (a.payment_id !== undefined && a.payment_id !== null) auth.paymentIds.push(id(a.payment_id, `${what}.payment_id`));
    // D3-17: only a seeded open hold that can still be open after its creation
    // has a history; seeded closed holds have none.
    auth.createHold = auth.amount - auth.captured;
    auth.lifecycle = auth.status === 'open' && Date.parse(auth.expiresAt) > Date.parse(auth.createdAt);
    if (auth.status === 'expired') auth.closedAt = auth.expiresAt;
    else if (auth.status === 'captured' || auth.status === 'voided') auth.closedAt = auth.createdAt;
    unique(s.authById, auth.id, 'authorization id');
    addAuthorization(s, auth);
    sweep(s, auth, now);
  });

  // Opening balance = seeded ending balance minus the net of the original seeded payments.
  setOpenings(s);

  // The seeded unexpired open holds must fit inside each payer's balance.
  for (const user of s.users.values()) {
    need(held(s, user, now) <= user.balance, `the open holds of ${user.id} exceed its balance`);
  }

  arr(fx.settlement_operator_ids, 'settlement_operator_ids', []).forEach((v, i) => {
    const uid = id(v, `settlement_operator_ids[${i}]`);
    need(s.users.has(uid), `settlement_operator_ids[${i}] is not a user`);
    s.operators.add(uid);
  });

  await Promise.all(passwords.map(async ([user, password]) => {
    user.pwHash = await hashPassword(password);
  }));
  return s;
}

// ---------------------------------------------------------------------------
// Export and import (§10). The state object is opaque to callers; amounts are
// decimal strings so they survive any JSON tooling exactly. A stage-1 export
// (no schema marker) imports with no authorizations and the default TTL.

function exportState(s) {
  return {
    schema: SCHEMA,
    currency: s.currency,
    minor_units: s.minorUnits,
    authorization_ttl_seconds: s.ttlSeconds,
    total: s.total.toString(),
    users: [...s.users.values()].map((u) => ({
      id: u.id,
      email: u.email,
      password_hash: u.pwHash,
      display_name: u.displayName,
      handle: u.handle,
      balance: u.balance.toString(),
      opening: u.opening.toString(),
    })),
    tokens: [...s.tokens].map(([token, userId]) => ({ token, user_id: userId })),
    settlement_operator_ids: [...s.operators],
    payments: s.payments.map((p) => ({
      id: p.id,
      from_user_id: p.fromId,
      to_user_id: p.toId,
      amount: p.amount.toString(),
      note: p.note,
      visibility: p.visibility,
      request_id: p.requestId,
      settlement_id: p.settlementId,
      authorization_id: p.authorizationId,
      created_at: p.createdAt,
      revisions: p.revisions.map((v) => ({
        revision: v.revision,
        amount: v.amount.toString(),
        effective_at: v.effectiveAt,
        recorded_at: v.recordedAt,
        reason: v.reason,
        seq: v.seq,
      })),
    })),
    requests: s.requests.map((r) => ({
      id: r.id,
      requester_id: r.requesterId,
      payer_id: r.payerId,
      amount: r.amount.toString(),
      note: r.note,
      status: r.status,
      payment_id: r.paymentId,
      created_at: r.createdAt,
    })),
    authorizations: s.authorizations.map((a) => ({
      id: a.id,
      from_user_id: a.fromId,
      to_user_id: a.toId,
      amount: a.amount.toString(),
      captured_amount: a.captured.toString(),
      note: a.note,
      visibility: a.visibility,
      status: a.status,
      expires_at: a.expiresAt,
      payment_ids: a.paymentIds,
      created_at: a.createdAt,
      closed_at: a.closedAt,
      create_hold: a.createHold.toString(),
      lifecycle: a.lifecycle,
    })),
    splits: [...s.splits.values()].map((sp) => ({
      id: sp.id,
      owner_id: sp.ownerId,
      amount: sp.amount.toString(),
      note: sp.note,
      shares: sp.shares.map((sh) => ({ handle: sh.handle, amount: sh.amount.toString() })),
      request_ids: sp.requestIds,
      created_at: sp.createdAt,
    })),
    settlements: [...s.settlements.values()].map((st) => ({
      id: st.id,
      operator_id: st.operatorId,
      committed_at: st.committedAt,
      payment_ids: st.paymentIds,
    })),
    idempotency: [...s.idem.values()].map((r) => ({
      user_id: r.userId,
      method: r.method,
      path: r.path,
      key: r.key,
      body: r.canon,
      response: r.response,
    })),
    seq: s.seq,
    snapshots: [...s.snapshots].map(([token, snap]) => ({
      token,
      user_id: snap.userId,
      from_ns: snap.fromNs === null ? null : snap.fromNs.toString(),
      to_ns: snap.toNs.toString(),
      known_ns: snap.knownNs.toString(),
      known_at: snap.knownAt,
      seq_max: snap.seqMax,
    })),
  };
}

function stateFromExport(doc) {
  if (!isObject(doc)) throw malformed('the import body must be a JSON object');
  need(doc.track === 'pocketful', 'track must be "pocketful"');
  need(doc.format_version instanceof JNum && doc.format_version.toBigInt() === 1n, 'format_version must be 1');
  const st = obj(doc.state, 'state');

  const schema = st.schema === undefined ? 1n : jint(st.schema, 'state.schema');
  need(schema >= 1n && schema <= 3n, 'state.schema is not supported');
  const currency = str(st.currency, 'state.currency');
  need(currency.length > 0, 'state.currency must not be empty');
  const minorUnits = Number(jint(st.minor_units, 'state.minor_units'));
  need(MINOR_UNITS.has(minorUnits), 'state.minor_units must be 0, 2 or 3');
  const s = newState(currency, minorUnits);
  if (schema >= 2n) {
    const ttl = jint(st.authorization_ttl_seconds, 'state.authorization_ttl_seconds');
    need(ttl >= 1n && ttl <= 10n ** 12n, 'state.authorization_ttl_seconds must be positive');
    s.ttlSeconds = Number(ttl);
  }
  const importedAt = timestamp();
  const ts = (v, what) => {
    need(typeof v === 'string' && !Number.isNaN(Date.parse(v)), `${what} must be a timestamp`);
    return v;
  };

  arr(st.users, 'state.users').forEach((u, i) => {
    obj(u, `state.users[${i}]`);
    const user = {
      id: id(u.id, 'user id'),
      email: str(u.email, 'user email'),
      pwHash: str(u.password_hash, 'user password_hash'),
      displayName: str(u.display_name, 'user display_name'),
      handle: str(u.handle, 'user handle'),
      balance: sint(u.balance, 'user balance'),
    };
    if (schema >= 3n) user.opening = sint(u.opening, 'user opening');
    need(isValidHash(user.pwHash), 'user password_hash is not a supported hash');
    need(HANDLE_RE.test(user.handle), 'user handle is invalid');
    need(user.balance >= 0n, 'user balance must not be negative');
    unique(s.users, user.id, 'user id');
    unique(s.byHandle, user.handle, 'handle');
    unique(s.byEmail, user.email, 'email');
    addUser(s, user);
    s.total += user.balance;
  });
  need(sint(st.total, 'state.total') === s.total, 'state.total does not match the balances');

  arr(st.tokens, 'state.tokens').forEach((t, i) => {
    obj(t, `state.tokens[${i}]`);
    const token = str(t.token, 'token');
    need(token.length > 0, 'token must not be empty');
    need(s.users.has(t.user_id), 'token refers to an unknown user');
    unique(s.tokens, token, 'token');
    s.tokens.set(token, t.user_id);
  });

  arr(st.settlement_operator_ids, 'state.settlement_operator_ids').forEach((uid) => {
    need(s.users.has(uid), 'operator is not a user');
    s.operators.add(uid);
  });

  arr(st.payments, 'state.payments').forEach((p, i) => {
    obj(p, `state.payments[${i}]`);
    const payment = {
      id: id(p.id, 'payment id'),
      fromId: id(p.from_user_id, 'payment from_user_id'),
      toId: id(p.to_user_id, 'payment to_user_id'),
      amount: sint(p.amount, 'payment amount'),
      note: str(p.note, 'payment note'),
      visibility: visibility(p.visibility, 'payment visibility'),
      requestId: nullableId(p.request_id, 'payment request_id'),
      settlementId: nullableId(p.settlement_id, 'payment settlement_id'),
      authorizationId: nullableId(p.authorization_id, 'payment authorization_id'),
      createdAt: ts(p.created_at, 'payment created_at'),
    };
    if (schema >= 3n) {
      payment.revisions = arr(p.revisions, 'payment revisions').map((v, n) => {
        obj(v, 'payment revision');
        need(v.revision instanceof JNum && v.revision.toBigInt() === BigInt(n + 1), 'payment revisions are out of order');
        const rev = revision(n + 1, sint(v.amount, 'revision amount'), ts(v.effective_at, 'revision effective_at'),
          ts(v.recorded_at, 'revision recorded_at'), str(v.reason, 'revision reason'));
        need(rev.amount >= 0n, 'revision amount must not be negative');
        if (v.seq !== undefined) rev.seq = Number(jint(v.seq, 'revision seq'));
        return rev;
      });
      need(payment.revisions.length >= 1, 'a payment needs revision 1');
    }
    need(s.users.has(payment.fromId) && s.users.has(payment.toId), 'payment refers to an unknown user');
    need(payment.amount >= 0n, 'payment amount must not be negative');
    unique(s.paymentById, payment.id, 'payment id');
    addPayment(s, payment);
  });

  arr(st.requests, 'state.requests').forEach((r, i) => {
    obj(r, `state.requests[${i}]`);
    const request = {
      id: id(r.id, 'request id'),
      requesterId: id(r.requester_id, 'request requester_id'),
      payerId: id(r.payer_id, 'request payer_id'),
      amount: sint(r.amount, 'request amount'),
      note: str(r.note, 'request note'),
      status: status(r.status, 'request status'),
      paymentId: nullableId(r.payment_id, 'request payment_id'),
      createdAt: ts(r.created_at, 'request created_at'),
    };
    need(s.users.has(request.requesterId) && s.users.has(request.payerId), 'request refers to an unknown user');
    need(request.amount >= 0n, 'request amount must not be negative');
    unique(s.requestById, request.id, 'request id');
    addRequest(s, request);
  });

  arr(st.authorizations, 'state.authorizations', []).forEach((a, i) => {
    obj(a, `state.authorizations[${i}]`);
    const expiresAt = ts(a.expires_at, 'authorization expires_at');
    const auth = {
      id: id(a.id, 'authorization id'),
      fromId: id(a.from_user_id, 'authorization from_user_id'),
      toId: id(a.to_user_id, 'authorization to_user_id'),
      amount: sint(a.amount, 'authorization amount'),
      captured: sint(a.captured_amount, 'authorization captured_amount'),
      note: str(a.note, 'authorization note'),
      visibility: visibility(a.visibility, 'authorization visibility'),
      status: authStatus(a.status, 'authorization status'),
      expiresAt,
      expiresMs: Date.parse(expiresAt),
      paymentIds: arr(a.payment_ids, 'authorization payment_ids').map((pid) => {
        need(s.paymentById.has(pid), 'authorization refers to an unknown payment');
        return pid;
      }),
      createdAt: ts(a.created_at, 'authorization created_at'),
    };
    if (schema >= 3n) {
      auth.closedAt = a.closed_at === null ? null : ts(a.closed_at, 'authorization closed_at');
      auth.createHold = sint(a.create_hold, 'authorization create_hold');
      need(typeof a.lifecycle === 'boolean', 'authorization lifecycle must be a boolean');
      auth.lifecycle = a.lifecycle;
    } else {
      // D3-13 / D3-18: a stage-2 export has no close times. A capture closes at
      // its last capture payment, an expiry at expires_at, and a void at the
      // import time, which never accepts a real overdraft.
      let capturedByPayments = 0n;
      for (const pid of auth.paymentIds) capturedByPayments += s.paymentById.get(pid).amount;
      auth.createHold = auth.amount - (auth.captured - capturedByPayments);
      const last = auth.paymentIds.length ? s.paymentById.get(auth.paymentIds[auth.paymentIds.length - 1]).createdAt : null;
      if (auth.status === 'captured') auth.closedAt = last || auth.createdAt;
      else if (auth.status === 'expired') auth.closedAt = auth.expiresAt;
      else if (auth.status === 'voided') auth.closedAt = importedAt;
      else auth.closedAt = null;
    }
    need(s.users.has(auth.fromId) && s.users.has(auth.toId), 'authorization refers to an unknown user');
    need(auth.amount >= 1n && auth.captured >= 0n && auth.captured <= auth.amount, 'authorization amounts are inconsistent');
    unique(s.authById, auth.id, 'authorization id');
    addAuthorization(s, auth);
  });
  for (const user of s.users.values()) {
    need(held(s, user) <= user.balance, 'open holds exceed a balance');
  }
  if (schema < 3n) setOpenings(s);

  arr(st.splits, 'state.splits').forEach((sp, i) => {
    obj(sp, `state.splits[${i}]`);
    const split = {
      id: id(sp.id, 'split id'),
      ownerId: id(sp.owner_id, 'split owner_id'),
      amount: sint(sp.amount, 'split amount'),
      note: str(sp.note, 'split note'),
      shares: arr(sp.shares, 'split shares').map((sh) => {
        obj(sh, 'split share');
        return { handle: str(sh.handle, 'share handle'), amount: sint(sh.amount, 'share amount') };
      }),
      requestIds: arr(sp.request_ids, 'split request_ids').map((rid) => {
        need(s.requestById.has(rid), 'split refers to an unknown request');
        return rid;
      }),
      createdAt: ts(sp.created_at, 'split created_at'),
    };
    need(s.users.has(split.ownerId), 'split refers to an unknown user');
    unique(s.splits, split.id, 'split id');
    s.splits.set(split.id, split);
  });

  arr(st.settlements, 'state.settlements').forEach((x, i) => {
    obj(x, `state.settlements[${i}]`);
    const settlement = {
      id: id(x.id, 'settlement id'),
      operatorId: id(x.operator_id, 'settlement operator_id'),
      committedAt: ts(x.committed_at, 'settlement committed_at'),
      paymentIds: arr(x.payment_ids, 'settlement payment_ids').map((pid) => {
        need(s.paymentById.has(pid), 'settlement refers to an unknown payment');
        return pid;
      }),
    };
    unique(s.settlements, settlement.id, 'settlement id');
    s.settlements.set(settlement.id, settlement);
  });

  arr(st.idempotency, 'state.idempotency').forEach((r, i) => {
    obj(r, `state.idempotency[${i}]`);
    const rec = {
      userId: id(r.user_id, 'idempotency user_id'),
      method: str(r.method, 'idempotency method'),
      path: str(r.path, 'idempotency path'),
      key: str(r.key, 'idempotency key'),
      canon: str(r.body, 'idempotency body'),
      response: str(r.response, 'idempotency response'),
    };
    need(s.users.has(rec.userId), 'idempotency record refers to an unknown user');
    const k = idemKey(rec.userId, rec.method, rec.path, rec.key);
    unique(s.idem, k, 'idempotency record');
    s.idem.set(k, rec);
  });

  if (st.seq !== undefined) {
    const seq = Number(jint(st.seq, 'state.seq'));
    if (seq > s.seq) s.seq = seq;
  }
  const nsOrNull = (v, what) => (v === null ? null : sint(v, what));
  arr(st.snapshots, 'state.snapshots', []).forEach((x, i) => {
    obj(x, `state.snapshots[${i}]`);
    const token = str(x.token, 'snapshot token');
    need(s.users.has(x.user_id), 'snapshot refers to an unknown user');
    unique(s.snapshots, token, 'snapshot token');
    s.snapshots.set(token, {
      userId: x.user_id,
      fromNs: nsOrNull(x.from_ns, 'snapshot from_ns'),
      toNs: sint(x.to_ns, 'snapshot to_ns'),
      knownNs: sint(x.known_ns, 'snapshot known_ns'),
      knownAt: x.known_at === null ? null : str(x.known_at, 'snapshot known_at'),
      seqMax: Number(jint(x.seq_max, 'snapshot seq_max')),
    });
  });

  return s;
}

module.exports = {
  HANDLE_RE,
  AUTH_STATUSES,
  current,
  replace,
  timestamp,
  newId,
  newToken,
  addUser,
  addPayment,
  addRequest,
  addAuthorization,
  revision,
  stamp,
  sweep,
  close,
  remaining,
  held,
  available,
  idemKey,
  stateFromFixture,
  exportState,
  stateFromExport,
};
