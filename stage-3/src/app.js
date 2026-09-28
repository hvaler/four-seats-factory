'use strict';

// HTTP API handlers (spec §3, §6–§11). Every write handler runs synchronously
// from idempotency resolution to commit: there is no await between reading the
// state and mutating it, so concurrent requests are serialised by the event
// loop and each operation is atomic.

const store = require('./store');
const { JNum, parse, isObject, canonical, stringify } = require('./json');
const { ApiError, malformed, invalid, notFound, forbidden, unauthenticated, conflict } = require('./errors');
const { hashPassword, verifyPassword, dummyHash } = require('./password');
const ui = require('./ui');
const ledger = require('./ledger');
const crypto = require('node:crypto');

const MAX_AMOUNT = 1000000000n;
const MAX_NOTE = 200;
const MAX_KEY = 255;
const MIN_PASSWORD = 8;
const MAX_TRANSFERS = 32;

const codePoints = (s) => {
  let n = 0;
  for (const _ of s) n += 1; // eslint-disable-line no-unused-vars
  return n;
};

const reply = (status, body) => ({ status, text: stringify(body) });

// ---------------------------------------------------------------------------
// Request helpers

const JSON_WS = /^[ \t\r\n]*$/;

// The body as a JSON object. An unparseable body, or any value other than an
// object, is 400 malformed_request (§5).
function bodyObject(ctx, { emptyIsObject = false } = {}) {
  if (ctx.bodyText === null) throw malformed('the body is not valid UTF-8 JSON');
  if (emptyIsObject && JSON_WS.test(ctx.bodyText)) return {};
  let value;
  try {
    value = parse(ctx.bodyText);
  } catch {
    throw malformed('the body is not valid JSON');
  }
  if (!isObject(value)) throw malformed('the body must be a JSON object');
  return value;
}

const BEARER = /^Bearer +(\S+) *$/i;

function authenticate(ctx) {
  const header = ctx.headers.authorization;
  const m = typeof header === 'string' ? BEARER.exec(header) : null;
  if (!m) throw unauthenticated('a bearer token is required');
  const s = store.current();
  const userId = s.tokens.get(m[1]);
  const user = userId === undefined ? undefined : s.users.get(userId);
  if (!user) throw unauthenticated('unknown token');
  return user;
}

// §7: resolve the Idempotency-Key before any field validation. Returns either
// { replay } with the stored original response, or { commit } to store the
// successful response of a first use. Only 201 outcomes claim a key.
function idempotency(ctx, user, body) {
  const key = ctx.headers['idempotency-key'];
  if (key === undefined || key === '') {
    throw new ApiError(400, 'missing_idempotency_key', 'the Idempotency-Key header is required');
  }
  if (codePoints(key) > MAX_KEY) throw invalid(`Idempotency-Key must be 1 to ${MAX_KEY} characters`);
  const s = store.current();
  const k = store.idemKey(user.id, ctx.method, ctx.path, key);
  const canon = canonical(body);
  const record = s.idem.get(k);
  if (record) {
    if (record.canon !== canon) {
      throw conflict('idempotency_key_reuse', 'this Idempotency-Key was already used with a different body');
    }
    return { replay: { status: 200, text: record.response } };
  }
  return {
    commit(body201) {
      const text = stringify(body201);
      s.idem.set(k, { userId: user.id, method: ctx.method, path: ctx.path, key, canon, response: text });
      return { status: 201, text };
    },
  };
}

// Phase 1 of body validation (D-18): wrong JSON types are 400.
function typeString(body, field) {
  const v = body[field];
  if (v !== undefined && typeof v !== 'string') throw malformed(`${field} must be a string`);
}

// Phase 2 (D-18): field rules are 422.
function required(body, field) {
  if (body[field] === undefined) throw invalid(`${field} is required`);
  return body[field];
}

function ruleAmount(v, field = 'amount') {
  if (v === undefined) throw invalid(`${field} is required`);
  const n = v instanceof JNum ? v.toBigInt() : null;
  if (n === null || n < 1n || n > MAX_AMOUNT) {
    throw invalid(`${field} must be an integer from 1 to ${MAX_AMOUNT}`);
  }
  return n;
}

function ruleNote(v) {
  if (v === undefined) return '';
  if (typeof v !== 'string') throw invalid('note must be a string');
  if (codePoints(v) > MAX_NOTE) throw invalid(`note must be at most ${MAX_NOTE} characters`);
  return v;
}

function ruleVisibility(v) {
  if (v === undefined) return 'public';
  if (v !== 'public' && v !== 'private') throw invalid('visibility must be public or private');
  return v;
}

// Integer query parameter written as plain decimal digits (§5).
function intParam(query, name, dflt, min, max) {
  if (!query.has(name)) return dflt;
  const raw = query.get(name);
  if (!/^[0-9]+$/.test(raw)) throw invalid(`${name} must be written as decimal digits`);
  const n = Number(raw);
  if (n < min || n > max) throw invalid(`${name} is out of range`);
  return n;
}

function page(query) {
  return {
    limit: intParam(query, 'limit', 50, 1, 200),
    offset: intParam(query, 'offset', 0, 0, Infinity),
  };
}

// Newest first (items are stored in creation order), then limit/offset.
function newestFirst(items, keep, { limit, offset }) {
  const out = [];
  let seen = 0;
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (!keep(items[i])) continue;
    if (seen >= offset && out.length < limit) out.push(items[i]);
    seen += 1;
    if (out.length === limit && seen > offset + limit) break;
  }
  return { items: out, hasMore: seen > offset + out.length };
}

// ---------------------------------------------------------------------------
// Representations

function paymentView(s, p) {
  return {
    payment_id: p.id,
    from_user_id: p.fromId,
    from_handle: s.users.get(p.fromId).handle,
    to_user_id: p.toId,
    to_handle: s.users.get(p.toId).handle,
    amount: p.amount,
    currency: s.currency,
    note: p.note,
    visibility: p.visibility,
    request_id: p.requestId,
    settlement_id: p.settlementId,
    authorization_id: p.authorizationId,
    created_at: p.createdAt,
  };
}

function authorizationView(s, a) {
  store.sweep(s, a);
  return {
    authorization_id: a.id,
    from_user_id: a.fromId,
    from_handle: s.users.get(a.fromId).handle,
    to_user_id: a.toId,
    to_handle: s.users.get(a.toId).handle,
    amount: a.amount,
    captured_amount: a.captured,
    remaining_amount: store.remaining(a),
    currency: s.currency,
    note: a.note,
    visibility: a.visibility,
    status: a.status,
    expires_at: a.expiresAt,
    payment_id: a.paymentIds.length ? a.paymentIds[a.paymentIds.length - 1] : null,
    payment_ids: a.paymentIds,
    created_at: a.createdAt,
    closed_at: a.closedAt,
  };
}

function requestView(s, r) {
  return {
    request_id: r.id,
    requester_id: r.requesterId,
    requester_handle: s.users.get(r.requesterId).handle,
    payer_id: r.payerId,
    payer_handle: s.users.get(r.payerId).handle,
    amount: r.amount,
    currency: s.currency,
    note: r.note,
    status: r.status,
    payment_id: r.paymentId,
    created_at: r.createdAt,
  };
}

// Records a payment. Balances are moved by the caller.
function recordPayment(s, fields) {
  const payment = {
    id: store.newId('p_', s.paymentById),
    requestId: null,
    settlementId: null,
    authorizationId: null,
    ...fields,
  };
  store.addPayment(s, payment);
  return payment;
}

function newRequest(s, fields) {
  const request = {
    id: store.newId('rq_', s.requestById),
    status: 'pending',
    paymentId: null,
    ...fields,
  };
  store.addRequest(s, request);
  return request;
}

// ---------------------------------------------------------------------------
// Test control (§3.2, §3.3, §10)

function health() {
  return reply(200, { status: 'ok' });
}

async function reset(ctx) {
  const next = await store.stateFromFixture(bodyObject(ctx));
  store.replace(next);
  return { status: 204 };
}

function exportState() {
  return reply(200, { track: 'pocketful', format_version: 1, state: store.exportState(store.current()) });
}

function importState(ctx) {
  store.replace(store.stateFromExport(bodyObject(ctx)));
  return { status: 204 };
}

// ---------------------------------------------------------------------------
// Authentication (§6)

const EMAIL = /^[^@\s]+@[^@\s]+$/u;

// §4: local part, lowercased, every code point outside [a-z0-9_] becomes "_",
// truncated to 20 characters.
function deriveHandle(email) {
  const local = email.slice(0, email.indexOf('@')).toLowerCase();
  let out = '';
  for (const ch of local) out += /^[a-z0-9_]$/.test(ch) ? ch : '_';
  return out.slice(0, 20);
}

async function signup(ctx) {
  const body = bodyObject(ctx);
  for (const f of ['email', 'password', 'display_name']) typeString(body, f);
  const email = required(body, 'email');
  const password = required(body, 'password');
  const displayName = required(body, 'display_name');
  if (!EMAIL.test(email)) throw invalid('email must be of the form local@domain');
  if (codePoints(password) < MIN_PASSWORD) throw invalid(`password must be at least ${MIN_PASSWORD} characters`);
  if (displayName === '') throw invalid('display_name must not be empty');
  const handle = deriveHandle(email);

  const checkFree = (s) => {
    if (s.byEmail.has(email)) throw conflict('email_taken', 'that email is already registered');
    if (s.byHandle.has(handle)) throw conflict('handle_taken', 'the handle derived from that email is taken');
  };
  checkFree(store.current());
  const pwHash = await hashPassword(password);

  // Re-check after the asynchronous hash, then insert synchronously.
  const s = store.current();
  checkFree(s);
  const user = { id: store.newId('u_', s.users), email, pwHash, displayName, handle, balance: 0n };
  store.addUser(s, user);
  const token = store.newToken(s);
  s.tokens.set(token, user.id);
  return reply(201, { user_id: user.id, display_name: user.displayName, token });
}

async function login(ctx) {
  const body = bodyObject(ctx);
  for (const f of ['email', 'password']) typeString(body, f);
  const email = required(body, 'email');
  const password = required(body, 'password');
  const user = store.current().byEmail.get(email);
  const ok = await verifyPassword(password, user ? user.pwHash : await dummyHash());
  const s = store.current();
  // The state may have been reset or imported while the hash was computed.
  if (!user || !ok || s.users.get(user.id) !== user) throw unauthenticated('wrong email or password');
  const token = store.newToken(s);
  s.tokens.set(token, user.id);
  return reply(200, { user_id: user.id, display_name: user.displayName, token });
}

// ---------------------------------------------------------------------------
// Wallet API (§8)

// An optional RFC 3339 instant query parameter (stage 3): present-but-invalid
// or empty is 422. Returns { text, ns } or null when absent.
function instantParam(query, name) {
  if (!query.has(name)) return null;
  const text = query.get(name);
  const value = ledger.parseInstant(text);
  if (value === null) throw invalid(`${name} must be an RFC 3339 instant with an offset`);
  return { text, ns: value };
}

function me(ctx) {
  const user = authenticate(ctx);
  const s = store.current();
  const asOf = instantParam(ctx.query, 'as_of');
  const knownAt = instantParam(ctx.query, 'known_at');
  if (asOf || knownAt) {
    const A = asOf ? asOf.ns : ctx.startNs;
    const K = knownAt ? knownAt.ns : ctx.startNs;
    const total = ledger.totalAt(user, A, K);
    const heldThen = ledger.heldAt(s, user, A, K);
    return reply(200, {
      user_id: user.id,
      display_name: user.displayName,
      handle: user.handle,
      balance: total,
      total,
      available: total - heldThen,
      held: heldThen,
      currency: s.currency,
      minor_units: s.minorUnits,
      as_of: asOf ? asOf.text : undefined,
      known_at: knownAt ? knownAt.text : undefined,
    });
  }
  const holds = store.held(s, user);
  return reply(200, {
    user_id: user.id,
    display_name: user.displayName,
    handle: user.handle,
    balance: user.balance,
    total: user.balance,
    available: user.balance - holds,
    held: holds,
    currency: s.currency,
    minor_units: s.minorUnits,
  });
}

function createPayment(ctx) {
  const user = authenticate(ctx);
  const body = bodyObject(ctx);
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  typeString(body, 'to_handle');
  const toHandle = required(body, 'to_handle');
  const amount = ruleAmount(body.amount);
  const note = ruleNote(body.note);
  const visibility = ruleVisibility(body.visibility);
  if (toHandle === user.handle) throw new ApiError(422, 'self_payment', 'you cannot pay yourself');
  const s = store.current();
  const to = s.byHandle.get(toHandle);
  if (!to) throw notFound('no user has that handle');
  if (store.available(s, user) < amount) throw conflict('insufficient_funds', 'your available balance is below the amount');

  user.balance -= amount;
  to.balance += amount;
  const payment = recordPayment(s, {
    fromId: user.id, toId: to.id, amount, note, visibility, createdAt: store.timestamp(),
  });
  return idem.commit(paymentView(s, payment));
}

function createRequest(ctx) {
  const user = authenticate(ctx);
  const body = bodyObject(ctx);
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  typeString(body, 'payer_handle');
  const payerHandle = required(body, 'payer_handle');
  const amount = ruleAmount(body.amount);
  const note = ruleNote(body.note);
  if (payerHandle === user.handle) throw new ApiError(422, 'self_request', 'you cannot request money from yourself');
  const s = store.current();
  const payer = s.byHandle.get(payerHandle);
  if (!payer) throw notFound('no user has that handle');

  // The payer's balance is deliberately not checked (§8).
  const request = newRequest(s, {
    requesterId: user.id, payerId: payer.id, amount, note, createdAt: store.timestamp(),
  });
  return idem.commit(requestView(s, request));
}

function findRequest(ctx) {
  const request = store.current().requestById.get(ctx.params[0]);
  if (!request) throw notFound('no such request');
  return request;
}

function payRequest(ctx) {
  const user = authenticate(ctx);
  const body = bodyObject(ctx, { emptyIsObject: true });
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  const visibility = ruleVisibility(body.visibility);
  const s = store.current();
  const request = findRequest(ctx);
  if (request.payerId !== user.id) throw forbidden('only the payer may pay this request');
  if (request.status !== 'pending') throw conflict('request_not_pending', `the request is ${request.status}`);
  if (store.available(s, user) < request.amount) throw conflict('insufficient_funds', 'your available balance is below the amount');

  const requester = s.users.get(request.requesterId);
  user.balance -= request.amount;
  requester.balance += request.amount;
  const payment = recordPayment(s, {
    fromId: user.id,
    toId: requester.id,
    amount: request.amount,
    note: request.note,
    visibility,
    requestId: request.id,
    createdAt: store.timestamp(),
  });
  request.status = 'paid';
  request.paymentId = payment.id;
  return idem.commit(paymentView(s, payment));
}

// decline and cancel take no idempotency key and ignore any body (§8, D-20).
function closeRequest(ctx, { actor, target }) {
  const user = authenticate(ctx);
  const request = findRequest(ctx);
  const party = actor === 'payer' ? request.payerId : request.requesterId;
  if (party !== user.id) throw forbidden(`only the ${actor} may do this`);
  if (request.status === 'pending') request.status = target;
  else if (request.status !== target) throw conflict('request_not_pending', `the request is ${request.status}`);
  return reply(200, requestView(store.current(), request));
}

const declineRequest = (ctx) => closeRequest(ctx, { actor: 'payer', target: 'declined' });
const cancelRequest = (ctx) => closeRequest(ctx, { actor: 'requester', target: 'cancelled' });

const DIRECTIONS = new Set(['incoming', 'outgoing']);
const STATUSES = new Set(['pending', 'paid', 'declined', 'cancelled']);

function listRequests(ctx) {
  const user = authenticate(ctx);
  const q = ctx.query;
  const direction = q.has('direction') ? q.get('direction') : null;
  if (direction !== null && !DIRECTIONS.has(direction)) throw invalid('direction must be incoming or outgoing');
  const status = q.has('status') ? q.get('status') : null;
  if (status !== null && !STATUSES.has(status)) throw invalid('unknown status');
  const paging = page(q);

  const s = store.current();
  const keep = (r) => {
    const incoming = r.payerId === user.id;
    const outgoing = r.requesterId === user.id;
    if (direction === 'incoming' ? !incoming : direction === 'outgoing' ? !outgoing : !(incoming || outgoing)) return false;
    return status === null || r.status === status;
  };
  const { items, hasMore } = newestFirst(s.requests, keep, paging);
  return reply(200, { requests: items.map((r) => requestView(s, r)), has_more: hasMore });
}

function createSplit(ctx) {
  const user = authenticate(ctx);
  const body = bodyObject(ctx);
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  const listed = body.participant_handles;
  if (listed !== undefined && (!Array.isArray(listed) || listed.some((h) => typeof h !== 'string'))) {
    throw malformed('participant_handles must be an array of strings');
  }
  const amount = ruleAmount(body.amount);
  if (listed === undefined) throw invalid('participant_handles is required');
  if (listed.length === 0) throw invalid('participant_handles must not be empty');
  if (new Set(listed).size !== listed.length) throw invalid('participant_handles contains a duplicate');
  const note = ruleNote(body.note);
  const s = store.current();
  const participants = listed.map((h) => s.byHandle.get(h));
  if (participants.some((p) => !p)) throw notFound('no user has one of those handles');

  // §9: equal shares; the remainder goes to the first participants in order.
  const n = BigInt(listed.length);
  const base = amount / n;
  const remainder = amount % n;
  const createdAt = store.timestamp();
  const shares = listed.map((handle, i) => ({ handle, amount: base + (BigInt(i) < remainder ? 1n : 0n) }));
  const requests = [];
  participants.forEach((p, i) => {
    if (p.id === user.id) return;
    requests.push(newRequest(s, {
      requesterId: user.id, payerId: p.id, amount: shares[i].amount, note, createdAt,
    }));
  });
  const split = {
    id: store.newId('sp_', s.splits),
    ownerId: user.id,
    amount,
    note,
    shares,
    requestIds: requests.map((r) => r.id),
    createdAt,
  };
  s.splits.set(split.id, split);
  return idem.commit({
    split_id: split.id,
    amount,
    currency: s.currency,
    note,
    shares,
    requests: requests.map((r) => requestView(s, r)),
    created_at: createdAt,
  });
}

function activity(ctx) {
  const user = authenticate(ctx);
  const paging = page(ctx.query);
  const s = store.current();
  // §4 feed contract: public, or the caller is the sender or the receiver.
  const keep = (p) => p.visibility === 'public' || p.fromId === user.id || p.toId === user.id;
  const ordered = s.payments.filter(keep).sort((x, y) => (x.createdNs < y.createdNs ? -1 : x.createdNs > y.createdNs ? 1 : 0));
  const { items, hasMore } = newestFirst(ordered, () => true, paging);
  return reply(200, { payments: items.map((p) => paymentView(s, p)), has_more: hasMore });
}

// §11 atomic net settlement.
function createSettlement(ctx) {
  const user = authenticate(ctx);
  if (!store.current().operators.has(user.id)) throw forbidden('only a settlement operator may do this');
  const body = bodyObject(ctx);
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  // Batch shape (D-28).
  const transfers = body.transfers;
  if (!Array.isArray(transfers) || transfers.length < 1 || transfers.length > MAX_TRANSFERS) {
    throw invalid(`transfers must be an array of 1 to ${MAX_TRANSFERS} entries`);
  }
  transfers.forEach((t, i) => {
    if (!isObject(t) || typeof t.from_handle !== 'string' || typeof t.to_handle !== 'string') {
      throw invalid(`transfers[${i}] must be an object with string from_handle and to_handle`);
    }
  });

  // Entries in input order, each checked as a payment; the first invalid one decides.
  const s = store.current();
  const entries = transfers.map((t, i) => {
    const amount = ruleAmount(t.amount, `transfers[${i}].amount`);
    const note = ruleNote(t.note);
    const visibility = ruleVisibility(t.visibility);
    if (t.from_handle === t.to_handle) throw new ApiError(422, 'self_payment', `transfers[${i}] is a self-transfer`);
    const from = s.byHandle.get(t.from_handle);
    const to = s.byHandle.get(t.to_handle);
    if (!from || !to) throw notFound(`transfers[${i}] names an unknown handle`);
    return { from, to, amount, note, visibility };
  });

  // Affordable iff every wallet's final net balance is nonnegative.
  const net = new Map();
  for (const e of entries) {
    net.set(e.from, (net.get(e.from) || 0n) - e.amount);
    net.set(e.to, (net.get(e.to) || 0n) + e.amount);
  }
  for (const [wallet, delta] of net) {
    if (store.available(s, wallet) + delta < 0n) throw conflict('insufficient_funds', 'the settlement is not affordable');
  }

  // Commit every movement together.
  const committedAt = store.timestamp();
  const settlementId = store.newId('st_', s.settlements);
  for (const [wallet, delta] of net) wallet.balance += delta;
  const payments = entries.map((e) => recordPayment(s, {
    fromId: e.from.id,
    toId: e.to.id,
    amount: e.amount,
    note: e.note,
    visibility: e.visibility,
    settlementId,
    createdAt: committedAt,
  }));
  s.settlements.set(settlementId, {
    id: settlementId, operatorId: user.id, committedAt, paymentIds: payments.map((p) => p.id),
  });
  return idem.commit({
    settlement_id: settlementId,
    committed_at: committedAt,
    payments: payments.map((p) => paymentView(s, p)),
  });
}

// ---------------------------------------------------------------------------
// Authorizations and captures (stage 2)

function createAuthorization(ctx) {
  const user = authenticate(ctx);
  const body = bodyObject(ctx);
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  typeString(body, 'to_handle');
  const toHandle = required(body, 'to_handle');
  const amount = ruleAmount(body.amount);
  const note = ruleNote(body.note);
  const visibility = ruleVisibility(body.visibility);
  if (toHandle === user.handle) throw new ApiError(422, 'self_payment', 'you cannot authorize a payment to yourself');
  const s = store.current();
  const to = s.byHandle.get(toHandle);
  if (!to) throw notFound('no user has that handle');
  const now = Date.now();
  if (store.available(s, user, now) < amount) {
    throw conflict('insufficient_funds', 'your available balance is below the amount');
  }

  const createdAt = store.timestamp(new Date(now));
  const expiresMs = now + s.ttlSeconds * 1000;
  const auth = {
    id: store.newId('a_', s.authById),
    fromId: user.id,
    toId: to.id,
    amount,
    captured: 0n,
    note,
    visibility,
    status: 'open',
    expiresAt: store.timestamp(new Date(expiresMs)),
    expiresMs,
    paymentIds: [],
    createdAt,
  };
  store.addAuthorization(s, auth);
  return idem.commit(authorizationView(s, auth));
}

function findAuthorization(ctx) {
  const auth = store.current().authById.get(ctx.params[0]);
  if (!auth) throw notFound('no such authorization');
  return auth;
}

function captureAuthorization(ctx) {
  const user = authenticate(ctx);
  const body = bodyObject(ctx, { emptyIsObject: true });
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  // D2-02: types, amount rules, 404, 403, not_open, expired, exceeds.
  if (body.final !== undefined && typeof body.final !== 'boolean') throw malformed('final must be a boolean');
  let amount = null;
  if (body.amount !== undefined) {
    amount = body.amount instanceof JNum ? body.amount.toBigInt() : null;
    if (amount === null || amount < 1n) throw invalid('amount must be a positive integer');
  }
  const final = body.final !== false;
  const s = store.current();
  const auth = findAuthorization(ctx);
  if (auth.toId !== user.id) throw forbidden('only the receiver may capture this authorization');
  const now = Date.now();
  if (auth.status === 'captured' || auth.status === 'voided') {
    throw conflict('authorization_not_open', `the authorization is ${auth.status}`);
  }
  store.sweep(s, auth, now);
  if (auth.status === 'expired') throw conflict('authorization_expired', 'the authorization has expired');
  const rest = store.remaining(auth);
  if (amount === null) amount = rest;
  if (amount > rest) {
    throw new ApiError(422, 'capture_exceeds_authorization', 'the amount is above what remains authorized');
  }

  // The hold covers the capture, so the payer's total always suffices.
  const payer = s.users.get(auth.fromId);
  payer.balance -= amount;
  user.balance += amount;
  const payment = recordPayment(s, {
    fromId: payer.id,
    toId: user.id,
    amount,
    note: auth.note,
    visibility: auth.visibility,
    authorizationId: auth.id,
    createdAt: store.timestamp(new Date(now)),
  });
  auth.captured += amount;
  auth.paymentIds.push(payment.id);
  if (final || auth.captured === auth.amount) store.close(s, auth, 'captured', payment.createdAt);
  return idem.commit(paymentView(s, payment));
}

// Payer only, no idempotency key, body ignored (like decline).
function voidAuthorization(ctx) {
  const user = authenticate(ctx);
  const s = store.current();
  const auth = findAuthorization(ctx);
  if (auth.fromId !== user.id) throw forbidden('only the payer may void this authorization');
  store.sweep(s, auth);
  if (auth.status === 'open') store.close(s, auth, 'voided', store.timestamp());
  else if (auth.status !== 'voided') throw conflict('authorization_not_open', `the authorization is ${auth.status}`);
  return reply(200, authorizationView(s, auth));
}

function listAuthorizations(ctx) {
  const user = authenticate(ctx);
  const q = ctx.query;
  const direction = q.has('direction') ? q.get('direction') : null;
  if (direction !== null && !DIRECTIONS.has(direction)) throw invalid('direction must be incoming or outgoing');
  const status = q.has('status') ? q.get('status') : null;
  if (status !== null && !store.AUTH_STATUSES.has(status)) throw invalid('unknown status');
  const paging = page(q);

  const s = store.current();
  const now = Date.now();
  const keep = (a) => {
    const outgoing = a.fromId === user.id;
    const incoming = a.toId === user.id;
    if (direction === 'incoming' ? !incoming : direction === 'outgoing' ? !outgoing : !(incoming || outgoing)) return false;
    return status === null || store.sweep(s, a, now).status === status;
  };
  const { items, hasMore } = newestFirst(s.authorizations, keep, paging);
  return reply(200, { authorizations: items.map((a) => authorizationView(s, a)), has_more: hasMore });
}

// ---------------------------------------------------------------------------
// Statements, corrections and revisions (stage 3)

// The statement of a user over [from, to) under known_at: every payment they
// sent or received with its selected revision effective in the window, ordered
// by effective_at then payment id (code-unit order), with running balances.
function buildStatement(s, user, fromNs, toNs, K, seqMax = Infinity) {
  const moves = ledger.paymentEvents(user, K, null, seqMax)
    .sort((x, y) => (x.t < y.t ? -1 : x.t > y.t ? 1 : x.payment.id < y.payment.id ? -1 : x.payment.id > y.payment.id ? 1 : 0));
  let balance = user.opening;
  for (const m of moves) if (fromNs !== null && m.t < fromNs) balance += m.delta;
  const opening = balance;
  const entries = [];
  for (const m of moves) {
    if ((fromNs !== null && m.t < fromNs) || m.t >= toNs) continue;
    balance += m.delta;
    entries.push({
      payment: { ...paymentView(s, m.payment), amount: m.revision.amount },
      delta: m.delta,
      balance_after: balance,
      revision: m.revision.revision,
      effective_at: m.revision.effectiveAt,
      recorded_at: m.revision.recordedAt,
    });
  }
  return { opening_balance: opening, entries, closing_balance: balance };
}

function statementPage(result, paging, token, extra) {
  const entries = result.entries.slice(paging.offset, paging.offset + paging.limit);
  return reply(200, {
    ...extra,
    opening_balance: result.opening_balance,
    entries,
    closing_balance: result.closing_balance,
    has_more: paging.offset + entries.length < result.entries.length,
    snapshot: token,
  });
}

function statement(ctx) {
  const user = authenticate(ctx);
  const q = ctx.query;
  const s = store.current();
  if (q.has('snapshot')) {
    if (q.has('from') || q.has('to') || q.has('known_at')) {
      throw invalid('only limit and offset may accompany a snapshot');
    }
    const token = q.get('snapshot');
    const snap = s.snapshots.get(token);
    if (!snap || snap.userId !== user.id) throw notFound('no such statement snapshot');
    const paging = page(q);
    const frozen = buildStatement(s, user, snap.fromNs, snap.toNs, snap.knownNs, snap.seqMax);
    return statementPage(JSON.parse(stringify(frozen)), paging, token, snap.knownAt !== null ? { known_at: snap.knownAt } : {});
  }
  const from = instantParam(q, 'from');
  const to = instantParam(q, 'to');
  const knownAt = instantParam(q, 'known_at');
  if (from && to && from.ns > to.ns) throw invalid('from must not be after to');
  const paging = page(q);
  // A snapshot is (window, known_at, write watermark): O(1) per token. Revisions
  // are immutable and every later write has a higher sequence number, so each
  // page re-derives exactly this result (F3-A01).
  const snap = {
    userId: user.id,
    fromNs: from ? from.ns : null,
    toNs: to ? to.ns : ctx.startNs,
    knownNs: knownAt ? knownAt.ns : ctx.startNs,
    knownAt: knownAt ? knownAt.text : null,
    seqMax: s.seq,
  };
  const result = buildStatement(s, user, snap.fromNs, snap.toNs, snap.knownNs, snap.seqMax);
  const extra = knownAt ? { known_at: knownAt.text } : {};
  const token = `st_${crypto.randomBytes(18).toString('base64url')}`;
  s.snapshots.set(token, snap);
  return statementPage(JSON.parse(stringify(result)), paging, token, extra);
}

function revisionView(p, v) {
  return {
    payment_id: p.id,
    revision: v.revision,
    amount: v.amount,
    effective_at: v.effectiveAt,
    recorded_at: v.recordedAt,
    reason: v.reason,
  };
}

// Field rules for a correction (D3-02: every invalid field, including a wrong
// JSON type, is 422).
function correctionFields(body, nowNs) {
  const rev = body.expected_revision instanceof JNum ? body.expected_revision.toBigInt() : null;
  if (rev === null || rev < 1n) throw invalid('expected_revision must be a positive integer');
  const amount = body.amount instanceof JNum ? body.amount.toBigInt() : null;
  if (amount === null || amount < 0n || amount > MAX_AMOUNT) throw invalid(`amount must be an integer from 0 to ${MAX_AMOUNT}`);
  const effNs = ledger.parseInstant(body.effective_at);
  if (effNs === null) throw invalid('effective_at must be an RFC 3339 instant with an offset');
  if (effNs > nowNs) throw invalid('effective_at must not be in the future');
  if (typeof body.reason !== 'string' || codePoints(body.reason) < 1 || codePoints(body.reason) > MAX_NOTE) {
    throw invalid(`reason must be 1 to ${MAX_NOTE} characters`);
  }
  return { expected: rev, amount, effectiveAt: body.effective_at, reason: body.reason };
}

function createCorrection(ctx) {
  const user = authenticate(ctx);
  const body = bodyObject(ctx);
  const idem = idempotency(ctx, user, body);
  if (idem.replay) return idem.replay;

  // D3-01: fields, 404, 403, linked, stale, insufficient, historical overdraft.
  const nowMs = Date.now();
  const nowNs = ledger.nowNs(nowMs);
  const f = correctionFields(body, nowNs);
  const s = store.current();
  const p = s.paymentById.get(ctx.params[0]);
  if (!p) throw notFound('no such payment');
  if (p.fromId !== user.id) throw forbidden('only the original sender may correct this payment');
  if (p.settlementId !== null || p.authorizationId !== null) {
    throw new ApiError(422, 'linked_payment_immutable', 'settlement members and captures cannot be corrected');
  }
  const current = ledger.currentRevision(p);
  if (f.expected !== BigInt(current.revision)) {
    throw conflict('stale_revision', `the current revision is ${current.revision}`);
  }
  const sender = s.users.get(p.fromId);
  const receiver = s.users.get(p.toId);
  const diff = f.amount - current.amount;
  const debtor = diff > 0n ? sender : receiver;
  const debit = diff > 0n ? diff : -diff;
  if (debit > 0n && store.available(s, debtor, nowMs) < debit) {
    throw conflict('insufficient_funds', 'the wallet to debit cannot afford the difference now');
  }

  // Recorded times strictly increase per payment, as instants and as strings.
  let recMs = nowMs;
  const lastRecMs = Number(current.recNs / ledger.NS_PER_MS);
  if (recMs <= lastRecMs) recMs = lastRecMs + 1;
  const proposed = store.revision(current.revision + 1, f.amount, f.effectiveAt, store.timestamp(new Date(recMs)), f.reason);
  if (ledger.overdraws(s, sender, p, proposed, nowNs) || ledger.overdraws(s, receiver, p, proposed, nowNs)) {
    throw conflict('historical_overdraft', 'the correction would make a balance negative at a past instant');
  }

  sender.balance -= diff;
  receiver.balance += diff;
  p.revisions.push(store.stamp(s, proposed));
  return idem.commit(revisionView(p, proposed));
}

function listRevisions(ctx) {
  const user = authenticate(ctx);
  const p = store.current().paymentById.get(ctx.params[0]);
  if (!p || (p.fromId !== user.id && p.toId !== user.id)) throw notFound('no such payment');
  return reply(200, { revisions: p.revisions.map((v) => revisionView(p, v)) });
}

// ---------------------------------------------------------------------------
// Browser UI (stage 2). /requests and /authorizations are shared with the API
// and negotiate on Accept (D2-14); the other screens are UI only.

function acceptQ(header, type) {
  let q = 0;
  for (const part of String(header || '').split(',')) {
    const [media, ...params] = part.trim().toLowerCase().split(';').map((x) => x.trim());
    if (media !== type) continue;
    const qp = params.find((p) => p.startsWith('q='));
    const v = qp ? Number(qp.slice(2)) : 1;
    if (Number.isFinite(v)) q = Math.max(q, v);
  }
  return q;
}

function wantsHtml(ctx) {
  const html = acceptQ(ctx.headers.accept, 'text/html');
  return html > 0 && html >= acceptQ(ctx.headers.accept, 'application/json');
}

const page_ = () => ui.page();
const negotiated = (api) => (ctx) => (wantsHtml(ctx) ? ui.page() : api(ctx));

// ---------------------------------------------------------------------------
// Routing

const ROUTES = [
  ['GET', /^\/$/, page_],
  ['GET', /^\/split$/, page_],
  ['GET', /^\/signup$/, page_],
  ['GET', /^\/login$/, page_],
  ['GET', /^\/static\/([a-z0-9.-]+)$/, (ctx) => ui.asset(ctx.params[0])],
  ['GET', /^\/authorizations$/, negotiated(listAuthorizations)],
  ['POST', /^\/authorizations$/, createAuthorization],
  ['POST', /^\/authorizations\/([^/]+)\/capture$/, captureAuthorization],
  ['POST', /^\/authorizations\/([^/]+)\/void$/, voidAuthorization],
  ['GET', /^\/health$/, health],
  ['POST', /^\/_test\/reset$/, reset],
  ['GET', /^\/_test\/export$/, exportState],
  ['POST', /^\/_test\/import$/, importState],
  ['POST', /^\/auth\/signup$/, signup],
  ['POST', /^\/auth\/login$/, login],
  ['GET', /^\/me$/, me],
  ['POST', /^\/payments$/, createPayment],
  ['POST', /^\/payments\/([^/]+)\/corrections$/, createCorrection],
  ['GET', /^\/payments\/([^/]+)\/revisions$/, listRevisions],
  ['GET', /^\/statement$/, statement],
  ['POST', /^\/requests$/, createRequest],
  ['GET', /^\/requests$/, negotiated(listRequests)],
  ['POST', /^\/requests\/([^/]+)\/pay$/, payRequest],
  ['POST', /^\/requests\/([^/]+)\/decline$/, declineRequest],
  ['POST', /^\/requests\/([^/]+)\/cancel$/, cancelRequest],
  ['POST', /^\/splits$/, createSplit],
  ['GET', /^\/activity$/, activity],
  ['POST', /^\/settlements$/, createSettlement],
];

function route(method, path) {
  let pathKnown = false;
  for (const [m, re, handler] of ROUTES) {
    const match = re.exec(path);
    if (!match) continue;
    pathKnown = true;
    if (m !== method) continue;
    let params;
    try {
      params = match.slice(1).map(decodeURIComponent);
    } catch {
      throw notFound('no such resource');
    }
    return { handler, params };
  }
  if (pathKnown) throw new ApiError(405, 'method_not_allowed', 'method not allowed on this path');
  throw notFound('no such route');
}

async function handle(ctx) {
  try {
    ctx.startNs = ledger.nowNs();
    const { handler, params } = route(ctx.method, ctx.path);
    ctx.params = params;
    return await handler(ctx);
  } catch (err) {
    if (err instanceof ApiError) return reply(err.status, { error: { code: err.code, message: err.message } });
    console.error(err);
    return reply(500, { error: { code: 'internal_error', message: 'internal error' } });
  }
}

module.exports = { handle, deriveHandle };
