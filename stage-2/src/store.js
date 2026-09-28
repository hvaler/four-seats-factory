'use strict';

// The whole service state lives in one in-memory object. Every mutation runs
// synchronously on the single event loop, so each operation (including a
// multi-transfer settlement) is atomic and no other request can observe it
// half-applied. Reset and import build a complete new state first and then
// swap it in with one assignment.

const crypto = require('node:crypto');
const { JNum, isObject } = require('./json');
const { invalid, malformed } = require('./errors');
const { hashPassword, isValidHash } = require('./password');

const HANDLE_RE = /^[a-z0-9_]{1,20}$/;
const STATUSES = new Set(['pending', 'paid', 'declined', 'cancelled']);
const VISIBILITIES = new Set(['public', 'private']);
const MINOR_UNITS = new Set([0, 2, 3]);
const MAX_ID = 64;

function newState(currency = 'EUR', minorUnits = 2) {
  return {
    currency,
    minorUnits,
    total: 0n,
    users: new Map(),
    byHandle: new Map(),
    byEmail: new Map(),
    tokens: new Map(),
    payments: [],
    paymentById: new Map(),
    requests: [],
    requestById: new Map(),
    splits: new Map(),
    settlements: new Map(),
    operators: new Set(),
    idem: new Map(),
  };
}

let state = newState();

const current = () => state;
const replace = (next) => { state = next; };

// RFC 3339 with an explicit numeric offset.
function timestamp(date = new Date()) {
  return date.toISOString().replace(/\.\d{3}Z$/, '+00:00');
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
  s.users.set(user.id, user);
  s.byHandle.set(user.handle, user);
  s.byEmail.set(user.email, user);
}

function addPayment(s, payment) {
  s.payments.push(payment);
  s.paymentById.set(payment.id, payment);
}

function addRequest(s, request) {
  s.requests.push(request);
  s.requestById.set(request.id, request);
}

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

function unique(map, key, what) {
  need(!map.has(key), `duplicate ${what}: ${key}`);
}

// ---------------------------------------------------------------------------
// Reset (§3.3, §4, §11)

async function stateFromFixture(fx) {
  if (!isObject(fx)) throw malformed('the fixture must be a JSON object');
  const currency = str(fx.currency, 'currency');
  need(currency.length > 0, 'currency must not be empty');
  const minorUnits = Number(jint(fx.minor_units, 'minor_units'));
  need(MINOR_UNITS.has(minorUnits), 'minor_units must be 0, 2 or 3');

  const s = newState(currency, minorUnits);
  const created = timestamp();
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
      createdAt: created,
    };
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
// decimal strings so they survive any JSON tooling exactly.

function exportState(s) {
  return {
    currency: s.currency,
    minor_units: s.minorUnits,
    total: s.total.toString(),
    users: [...s.users.values()].map((u) => ({
      id: u.id,
      email: u.email,
      password_hash: u.pwHash,
      display_name: u.displayName,
      handle: u.handle,
      balance: u.balance.toString(),
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
      created_at: p.createdAt,
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
  };
}

function stateFromExport(doc) {
  if (!isObject(doc)) throw malformed('the import body must be a JSON object');
  need(doc.track === 'pocketful', 'track must be "pocketful"');
  need(doc.format_version instanceof JNum && doc.format_version.toBigInt() === 1n, 'format_version must be 1');
  const st = obj(doc.state, 'state');

  const currency = str(st.currency, 'state.currency');
  need(currency.length > 0, 'state.currency must not be empty');
  const minorUnits = Number(jint(st.minor_units, 'state.minor_units'));
  need(MINOR_UNITS.has(minorUnits), 'state.minor_units must be 0, 2 or 3');
  const s = newState(currency, minorUnits);
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
      createdAt: ts(p.created_at, 'payment created_at'),
    };
    need(s.users.has(payment.fromId) && s.users.has(payment.toId), 'payment refers to an unknown user');
    need(payment.amount >= 1n, 'payment amount must be positive');
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

  return s;
}

module.exports = {
  HANDLE_RE,
  current,
  replace,
  timestamp,
  newId,
  newToken,
  addUser,
  addPayment,
  addRequest,
  idemKey,
  stateFromFixture,
  exportState,
  stateFromExport,
};
