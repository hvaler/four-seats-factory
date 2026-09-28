'use strict';

// HTTP API handlers (spec §3, §6–§11). Every write handler runs synchronously
// from idempotency resolution to commit: there is no await between reading the
// state and mutating it, so concurrent requests are serialised by the event
// loop and each operation is atomic.

const store = require('./store');
const { JNum, parse, isObject, canonical, stringify } = require('./json');
const { ApiError, malformed, invalid, notFound, forbidden, unauthenticated, conflict } = require('./errors');
const { hashPassword, verifyPassword, dummyHash } = require('./password');

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
    created_at: p.createdAt,
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

function me(ctx) {
  const user = authenticate(ctx);
  const s = store.current();
  return reply(200, {
    user_id: user.id,
    display_name: user.displayName,
    handle: user.handle,
    balance: user.balance,
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
  if (user.balance < amount) throw conflict('insufficient_funds', 'your balance is below the amount');

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
  if (user.balance < request.amount) throw conflict('insufficient_funds', 'your balance is below the amount');

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
  const { items, hasMore } = newestFirst(s.payments, keep, paging);
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
    if (wallet.balance + delta < 0n) throw conflict('insufficient_funds', 'the settlement is not affordable');
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
// Routing

const ROUTES = [
  ['GET', /^\/health$/, health],
  ['POST', /^\/_test\/reset$/, reset],
  ['GET', /^\/_test\/export$/, exportState],
  ['POST', /^\/_test\/import$/, importState],
  ['POST', /^\/auth\/signup$/, signup],
  ['POST', /^\/auth\/login$/, login],
  ['GET', /^\/me$/, me],
  ['POST', /^\/payments$/, createPayment],
  ['POST', /^\/requests$/, createRequest],
  ['GET', /^\/requests$/, listRequests],
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
