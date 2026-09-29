'use strict';

// Implementation tests, written from the stage-1 specification. Obligation IDs
// from the fskit-001 register are noted per test.

const { test, before, after, describe } = require('node:test');
const assert = require('node:assert/strict');
const { start, client, fixture, seed, key, PASSWORD } = require('./helpers');

let srv;
let api;
before(async () => {
  srv = await start();
  api = client(srv.base);
});
after(async () => srv.close());

const total = async (tokens) => {
  let sum = 0;
  for (const t of Object.values(tokens)) sum += (await api.get('/me', { token: t })).json.balance;
  return sum;
};

describe('runtime contract', () => {
  test('health, content type and error envelope (S1-015, S1-017, S1-050)', async () => {
    const h = await api.get('/health');
    assert.equal(h.status, 200);
    assert.deepEqual(h.json, { status: 'ok' });
    assert.equal(h.contentType, 'application/json; charset=utf-8');
    const nf = await api.get('/nope');
    assert.equal(nf.status, 404);
    assert.equal(nf.json.error.code, 'not_found');
    assert.equal(typeof nf.json.error.message, 'string');
    const wrong = await api.call('DELETE', '/payments');
    assert.equal(wrong.status, 405);
    assert.ok(wrong.json.error.code);
  });

  test('reset replaces state; negative balance is 422 and keeps state (S1-016, S1-047)', async () => {
    const tokens = await seed(api);
    const bad = fixture();
    bad.users[0].balance = -1;
    const r = await api.post('/_test/reset', bad);
    assert.equal(r.status, 422);
    assert.equal(r.json.error.code, 'validation_failed');
    assert.equal((await api.get('/me', { token: tokens.ada })).json.balance, 10000);
    await seed(api);
    assert.equal((await api.get('/me', { token: tokens.ada })).status, 401, 'old token invalid after reset');
    assert.equal((await api.post('/_test/reset', '{nope')).status, 400);
    const mu = fixture({ minor_units: 1 });
    assert.equal((await api.post('/_test/reset', mu)).status, 422);
  });

  test('timestamps carry an explicit offset (S1-018)', async () => {
    const tokens = await seed(api);
    const r = await api.post('/payments', { to_handle: 'bob', amount: 1 }, { token: tokens.ada, key: key() });
    assert.match(r.json.created_at, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?([+-]\d\d:\d\d|Z)$/);
  });
});

describe('authentication (§6)', () => {
  test('signup derives the handle, starts at 0, logs in (S1-033, S1-034, S1-060, S1-061)', async () => {
    await seed(api);
    const r = await api.post('/auth/signup', { email: 'Zoë.K+x@mail.test', password: '12345678', display_name: 'Zoe' });
    assert.equal(r.status, 201);
    assert.equal(r.json.display_name, 'Zoe');
    const me = await api.get('/me', { token: r.json.token });
    assert.equal(me.json.handle, 'zo__k_x');
    assert.equal(me.json.balance, 0);
    const long = await api.post('/auth/signup', { email: 'abcdefghijklmnopqrstuvwxyz@x.io', password: '12345678', display_name: 'L' });
    assert.equal((await api.get('/me', { token: long.json.token })).json.handle, 'abcdefghijklmnopqrst');
    const login = await api.post('/auth/login', { email: 'Zoë.K+x@mail.test', password: '12345678' });
    assert.equal(login.status, 200);
    assert.equal(login.json.user_id, r.json.user_id);
  });

  test('signup errors (S1-062..S1-066)', async () => {
    await seed(api);
    const ok = { password: '12345678', display_name: 'X' };
    assert.equal((await api.post('/auth/signup', { ...ok, email: 'ada@example.com' })).json.error.code, 'email_taken');
    const ht = await api.post('/auth/signup', { ...ok, email: 'ada@other.test' });
    assert.equal(ht.status, 409);
    assert.equal(ht.json.error.code, 'handle_taken');
    assert.equal((await api.post('/auth/login', { email: 'ada@other.test', password: '12345678' })).status, 401);
    assert.equal((await api.post('/auth/signup', { ...ok, email: 'new@x.io', password: '1234567' })).status, 422);
    for (const email of ['', 'a', 'a@', '@b', 'a@b@c', 'a b@c']) {
      assert.equal((await api.post('/auth/signup', { ...ok, email })).status, 422, email);
    }
    assert.equal((await api.post('/auth/signup', { ...ok, email: 5 })).status, 400);
    assert.equal((await api.post('/auth/signup', { password: '12345678' })).status, 422);
  });

  test('login and tokens (S1-053, S1-065, S1-068)', async () => {
    await seed(api);
    assert.equal((await api.post('/auth/login', { email: 'ada@example.com', password: 'wrong pass' })).status, 401);
    assert.equal((await api.post('/auth/login', { email: 'zz@example.com', password: PASSWORD })).status, 401);
    const a = await api.post('/auth/login', { email: 'ada@example.com', password: PASSWORD });
    const b = await api.post('/auth/login', { email: 'ada@example.com', password: PASSWORD });
    assert.notEqual(a.json.token, b.json.token);
    assert.equal((await api.get('/me', { token: a.json.token })).status, 200);
    assert.equal((await api.get('/me', { token: b.json.token })).status, 200);
    for (const authorization of ['', 'Bearer', 'Bearer ', 'Basic abc', 'Bearer nope']) {
      const r = await api.get('/me', { headers: { authorization } });
      assert.equal(r.status, 401, authorization);
      assert.equal(r.json.error.code, 'unauthenticated');
    }
    assert.equal((await api.post('/requests/rq_404/pay', {})).status, 401, '401 precedes 404');
  });
});

describe('payments (§8)', () => {
  test('happy path, defaults and atomic movement (S1-091, S1-097)', async () => {
    const t = await seed(api);
    const r = await api.post('/payments', { to_handle: 'bob', amount: 1500 }, { token: t.ada, key: key() });
    assert.equal(r.status, 201);
    assert.equal(r.json.note, '');
    assert.equal(r.json.visibility, 'public');
    assert.equal(r.json.request_id, null);
    assert.equal(r.json.settlement_id, null);
    assert.equal(r.json.currency, 'EUR');
    assert.equal(r.json.from_handle, 'ada');
    assert.equal(r.json.to_user_id, 'u_bob');
    assert.equal((await api.get('/me', { token: t.ada })).json.balance, 8500);
    assert.equal((await api.get('/me', { token: t.bob })).json.balance, 4000);
  });

  test('integral numeric forms are one amount; others are 422 (S1-031, S1-055, D-31)', async () => {
    const t = await seed(api);
    for (const amount of ['1e3', '1000.0', '10E2', '100000e-2']) {
      const r = await api.post('/payments', `{"to_handle":"bob","amount":${amount}}`, { token: t.ada, key: key() });
      assert.equal(r.status, 201, amount);
      assert.equal(r.json.amount, 1000);
    }
    for (const amount of ['"100"', 'true', 'null', '1.5', '0', '-1', '1000000001', '1000.00000000000001', '[1]', '{}']) {
      const r = await api.post('/payments', `{"to_handle":"bob","amount":${amount}}`, { token: t.ada, key: key() });
      assert.equal(r.status, 422, amount);
      assert.equal(r.json.error.code, 'validation_failed');
    }
  });

  test('payment errors and their order (S1-092..S1-096, D-03)', async () => {
    const t = await seed(api);
    const post = (body) => api.post('/payments', body, { token: t.bob, key: key() });
    assert.equal((await post({ to_handle: 'ada', amount: 2501 })).json.error.code, 'insufficient_funds');
    assert.equal((await post({ to_handle: 'ada', amount: 2500 })).status, 201, 'balance == amount is fine');
    assert.equal((await post({ to_handle: 'bob', amount: 1 })).json.error.code, 'self_payment');
    assert.equal((await post({ to_handle: 'nobody', amount: 1 })).status, 404);
    assert.equal((await post({ to_handle: 'Bob', amount: 1 })).status, 404);
    assert.equal((await post({ to_handle: 5, amount: 1 })).status, 400);
    assert.equal((await post({ amount: 1 })).status, 422);
    assert.equal((await post({ to_handle: 'ada', amount: 1, note: null })).status, 422);
    assert.equal((await post({ to_handle: 'ada', amount: 1, note: 'x'.repeat(201) })).status, 422);
    assert.equal((await post({ to_handle: 'ada', amount: 1, visibility: 'PUBLIC' })).status, 422);
    assert.equal((await post({ to_handle: 'nobody', amount: 0 })).status, 422, 'field rules before 404');
    assert.equal((await api.post('/payments', '[1]', { token: t.bob, key: key() })).status, 400);
    assert.equal((await api.post('/payments', '{', { token: t.bob, key: key() })).status, 400);
  });

  test('note round-trips verbatim; 200 code points allowed (S1-095, S1-098)', async () => {
    const t = await seed(api);
    for (const note of ['  spaced  ', 'é vs é', '🍝🍝', '<b>&amp;</b>', 'nul\u0000byte', '😀'.repeat(200)]) {
      const r = await api.post('/payments', { to_handle: 'bob', amount: 1, note }, { token: t.ada, key: key() });
      assert.equal(r.status, 201);
      assert.equal(r.json.note, note);
    }
  });
});

describe('idempotency (§7)', () => {
  test('replay, conflict, other path, failed reuse (S1-072..S1-077)', async () => {
    const t = await seed(api);
    const k = key();
    const first = await api.post('/payments', { to_handle: 'bob', amount: 100 }, { token: t.ada, key: k });
    assert.equal(first.status, 201);
    const again = await api.post('/payments', '{ "amount": 1e2,\n "to_handle": "bob" }', { token: t.ada, key: k });
    assert.equal(again.status, 200);
    assert.deepEqual(again.json, first.json);
    assert.equal((await api.get('/me', { token: t.ada })).json.balance, 9900, 'replay moved nothing');
    const diff = await api.post('/payments', { to_handle: 'bob', amount: 101 }, { token: t.ada, key: k });
    assert.equal(diff.json.error.code, 'idempotency_key_reuse');
    const extra = await api.post('/payments', { to_handle: 'bob', amount: 100, x: 1 }, { token: t.ada, key: k });
    assert.equal(extra.status, 409, 'unknown fields are part of the body (D-26)');
    const invalidBody = await api.post('/payments', { to_handle: 'nobody', amount: -5 }, { token: t.ada, key: k });
    assert.equal(invalidBody.json.error.code, 'idempotency_key_reuse', 'claimed key before validation');
    const otherPath = await api.post('/requests', { payer_handle: 'bob', amount: 100 }, { token: t.ada, key: k });
    assert.equal(otherPath.status, 201);
    const otherUser = await api.post('/payments', { to_handle: 'ada', amount: 100 }, { token: t.bob, key: k });
    assert.equal(otherUser.status, 201);

    const f = key();
    assert.equal((await api.post('/payments', { to_handle: 'bob', amount: 999999 }, { token: t.ada, key: f })).status, 409);
    assert.equal((await api.post('/payments', { to_handle: 'bob', amount: 1 }, { token: t.ada, key: f })).status, 201);
  });

  test('key header rules (S1-052, S1-057)', async () => {
    const t = await seed(api);
    const body = { to_handle: 'bob', amount: 1 };
    const none = await api.post('/payments', body, { token: t.ada });
    assert.equal(none.json.error.code, 'missing_idempotency_key');
    assert.equal((await api.post('/payments', body, { token: t.ada, key: '' })).json.error.code, 'missing_idempotency_key');
    assert.equal((await api.post('/payments', body, { token: t.ada, key: 'k'.repeat(255) })).status, 201);
    assert.equal((await api.post('/payments', body, { token: t.ada, key: 'k'.repeat(256) })).status, 422);
    for (const [path, b] of [['/requests', { payer_handle: 'bob', amount: 1 }], ['/requests/rq_1/pay', {}],
      ['/splits', { amount: 1, participant_handles: ['bob'] }]]) {
      assert.equal((await api.post(path, b, { token: t.ada })).json.error.code, 'missing_idempotency_key', path);
    }
    assert.equal((await api.post('/settlements', { transfers: [] }, { token: t.op })).json.error.code, 'missing_idempotency_key');
  });

  test('concurrent identical writes: exactly one 201 (S1-078)', async () => {
    const t = await seed(api);
    const k = key();
    const results = await Promise.all(Array.from({ length: 20 }, () =>
      api.post('/payments', { to_handle: 'bob', amount: 10 }, { token: t.ada, key: k })));
    assert.equal(results.filter((r) => r.status === 201).length, 1);
    assert.equal(results.filter((r) => r.status === 200).length, 19);
    for (const r of results) assert.deepEqual(r.json, results[0].json);
    assert.equal((await api.get('/me', { token: t.ada })).json.balance, 9990);
  });
});

describe('requests (§8)', () => {
  test('request above balance, pay short, fund, pay, replay (S1-037, S1-102, S1-110, S1-113)', async () => {
    const t = await seed(api);
    const rq = await api.post('/requests', { payer_handle: 'cy', amount: 700, note: 'lunch' }, { token: t.bob, key: key() });
    assert.equal(rq.status, 201);
    assert.equal(rq.json.status, 'pending');
    assert.equal(rq.json.payment_id, null);
    assert.equal(rq.json.requester_handle, 'bob');
    const id = rq.json.request_id;
    assert.equal((await api.post(`/requests/${id}/pay`, {}, { token: t.cy, key: key() })).json.error.code, 'insufficient_funds');
    await api.post('/payments', { to_handle: 'cy', amount: 700 }, { token: t.ada, key: key() });
    const k = key();
    const paid = await api.post(`/requests/${id}/pay`, { visibility: 'private' }, { token: t.cy, key: k });
    assert.equal(paid.status, 201);
    assert.equal(paid.json.request_id, id);
    assert.equal(paid.json.visibility, 'private');
    assert.equal(paid.json.note, 'lunch');
    assert.equal(paid.json.from_handle, 'cy');
    const replay = await api.post(`/requests/${id}/pay`, { visibility: 'private' }, { token: t.cy, key: k });
    assert.equal(replay.status, 200);
    assert.deepEqual(replay.json, paid.json);
    assert.equal((await api.post(`/requests/${id}/pay`, {}, { token: t.cy, key: k })).status, 409);
    assert.equal((await api.post(`/requests/${id}/pay`, {}, { token: t.cy, key: key() })).json.error.code, 'request_not_pending');
    const list = await api.get('/requests?status=paid', { token: t.bob });
    assert.equal(list.json.requests[0].payment_id, paid.json.payment_id);
  });

  test('pay permissions and empty body (S1-111, S1-112, D-20)', async () => {
    const t = await seed(api);
    assert.equal((await api.post('/requests/rq_1/pay', {}, { token: t.bob, key: key() })).status, 403);
    assert.equal((await api.post('/requests/rq_1/pay', {}, { token: t.cy, key: key() })).status, 403);
    assert.equal((await api.post('/requests/rq_x/pay', {}, { token: t.ada, key: key() })).status, 404);
    const k = key();
    const paid = await api.call('POST', '/requests/rq_1/pay', { token: t.ada, key: k });
    assert.equal(paid.status, 201);
    assert.equal((await api.post('/requests/rq_1/pay', {}, { token: t.ada, key: k })).status, 200);
    assert.equal((await api.post('/requests/rq_1/pay', { visibility: 'public' }, { token: t.ada, key: k })).status, 409);
  });

  test('decline and cancel state machine (S1-120, S1-121, S1-206)', async () => {
    const t = await seed(api);
    const mk = async () => (await api.post('/requests', { payer_handle: 'ada', amount: 5 }, { token: t.bob, key: key() })).json.request_id;
    const a = await mk();
    assert.equal((await api.call('POST', `/requests/${a}/decline`, { token: t.bob })).status, 403);
    const d1 = await api.call('POST', `/requests/${a}/decline`, { token: t.ada });
    assert.equal(d1.status, 200);
    assert.equal(d1.json.status, 'declined');
    assert.equal((await api.post(`/requests/${a}/decline`, 'garbage', { token: t.ada })).status, 200);
    assert.equal((await api.call('POST', `/requests/${a}/cancel`, { token: t.bob })).json.error.code, 'request_not_pending');
    const b = await mk();
    assert.equal((await api.call('POST', `/requests/${b}/cancel`, { token: t.ada })).status, 403);
    assert.equal((await api.call('POST', `/requests/${b}/cancel`, { token: t.bob })).json.status, 'cancelled');
    assert.equal((await api.call('POST', `/requests/${b}/cancel`, { token: t.bob })).status, 200);
    assert.equal((await api.call('POST', `/requests/${b}/decline`, { token: t.ada })).status, 409);
    assert.equal((await api.post(`/requests/${b}/pay`, {}, { token: t.ada, key: key() })).json.error.code, 'request_not_pending');
    assert.equal((await api.call('POST', '/requests/nope/cancel', { token: t.bob })).status, 404);
  });

  test('listing, filters and paging (S1-130..S1-132)', async () => {
    const t = await seed(api);
    for (let i = 0; i < 5; i += 1) await api.post('/requests', { payer_handle: 'bob', amount: i + 1 }, { token: t.ada, key: key() });
    const all = await api.get('/requests', { token: t.ada });
    assert.equal(all.json.requests.length, 6);
    assert.equal(all.json.requests[0].amount, 5, 'newest first');
    assert.equal(all.json.requests[5].request_id, 'rq_1', 'seeded is oldest');
    assert.equal((await api.get('/requests?direction=incoming', { token: t.ada })).json.requests.length, 1);
    assert.equal((await api.get('/requests?direction=outgoing&status=pending', { token: t.ada })).json.requests.length, 5);
    const p = await api.get('/requests?limit=2&offset=4', { token: t.ada });
    assert.deepEqual([p.json.requests.length, p.json.has_more], [2, false]);
    const q = await api.get('/requests?limit=2&offset=3&extra=1', { token: t.ada });
    assert.equal(q.json.has_more, true);
    assert.deepEqual((await api.get('/requests?offset=99', { token: t.ada })).json, { requests: [], has_more: false });
    assert.equal((await api.get('/requests?limit=01', { token: t.ada })).status, 200);
    assert.equal((await api.get('/requests', { token: t.cy })).json.requests.length, 0, 'third party sees none');
    for (const qs of ['limit=0', 'limit=201', 'limit=1e1', 'limit=4.0', 'limit=%2B4', 'offset=-1', 'direction=up', 'status=', 'status=done']) {
      assert.equal((await api.get(`/requests?${qs}`, { token: t.ada })).status, 422, qs);
    }
  });
});

describe('splits (§8, §9)', () => {
  test('share arithmetic and remainder order (S1-160, S1-161)', async () => {
    const t = await seed(api);
    const cases = [[1000, [334, 333, 333]], [1, [1, 0, 0]], [10, [4, 3, 3]], [999, [333, 333, 333]]];
    for (const [amount, expected] of cases) {
      const r = await api.post('/splits', { amount, participant_handles: ['ada', 'bob', 'cy'] }, { token: t.ada, key: key() });
      assert.equal(r.status, 201);
      assert.deepEqual(r.json.shares.map((s) => s.amount), expected);
      assert.deepEqual(r.json.requests.map((q) => [q.payer_handle, q.amount]), [['bob', expected[1]], ['cy', expected[2]]]);
    }
    const big = await api.post('/splits', { amount: 1000000000, participant_handles: ['ada', 'bob', 'cy', 'op', 'bob2'].slice(0, 4) }, { token: t.ada, key: key() });
    assert.equal(big.json.shares.reduce((a, s) => a + s.amount, 0), 1000000000);
    const rev = await api.post('/splits', { amount: 10, participant_handles: ['cy', 'bob', 'ada'] }, { token: t.ada, key: key() });
    assert.deepEqual(rev.json.shares, [{ handle: 'cy', amount: 4 }, { handle: 'bob', amount: 3 }, { handle: 'ada', amount: 3 }]);
  });

  test('caller omitted, caller only, zero share payable (S1-140, S1-142, S1-143, S1-145)', async () => {
    const t = await seed(api);
    const omitted = await api.post('/splits', { amount: 5, participant_handles: ['bob', 'cy'], note: 'n' }, { token: t.ada, key: key() });
    assert.deepEqual(omitted.json.shares.map((s) => s.handle), ['bob', 'cy']);
    assert.equal(omitted.json.requests.length, 2);
    assert.equal(omitted.json.requests[0].note, 'n');
    const solo = await api.post('/splits', { amount: 5, participant_handles: ['ada'] }, { token: t.ada, key: key() });
    assert.deepEqual(solo.json.requests, []);
    assert.deepEqual(solo.json.shares, [{ handle: 'ada', amount: 5 }]);
    const zero = await api.post('/splits', { amount: 1, participant_handles: ['ada', 'cy'] }, { token: t.ada, key: key() });
    const zr = zero.json.requests[0];
    assert.equal(zr.amount, 0);
    const pay = await api.post(`/requests/${zr.request_id}/pay`, {}, { token: t.cy, key: key() });
    assert.equal(pay.status, 201);
    assert.equal(pay.json.amount, 0);
  });

  test('split errors (S1-141)', async () => {
    const t = await seed(api);
    const post = (b) => api.post('/splits', b, { token: t.ada, key: key() });
    assert.equal((await post({ amount: 5, participant_handles: [] })).status, 422);
    assert.equal((await post({ amount: 5, participant_handles: ['bob', 'bob'] })).status, 422);
    assert.equal((await post({ amount: 0, participant_handles: ['bob'] })).status, 422);
    assert.equal((await post({ amount: 5, participant_handles: ['bob'], note: 'x'.repeat(201) })).status, 422);
    assert.equal((await post({ amount: 5, participant_handles: ['bob', 'ghost'] })).status, 404);
    assert.equal((await post({ amount: 5, participant_handles: 'bob' })).status, 400);
    assert.equal((await post({ amount: 5, participant_handles: [1] })).status, 400);
    assert.equal((await api.get('/requests', { token: t.bob })).json.requests.length, 1, 'failed splits create nothing');
  });
});

describe('activity feed (§4)', () => {
  test('visibility contract (S1-039, S1-041, S1-150, S1-191)', async () => {
    const t = await seed(api);
    const priv = await api.post('/payments', { to_handle: 'bob', amount: 1, visibility: 'private' }, { token: t.ada, key: key() });
    await api.post('/splits', { amount: 3, participant_handles: ['bob', 'cy'] }, { token: t.ada, key: key() });
    const ids = async (tok) => (await api.get('/activity', { token: tok })).json.payments.map((p) => p.payment_id);
    assert.ok((await ids(t.ada)).includes(priv.json.payment_id));
    assert.ok((await ids(t.bob)).includes(priv.json.payment_id));
    assert.ok(!(await ids(t.cy)).includes(priv.json.payment_id));
    assert.ok(!(await ids(t.op)).includes(priv.json.payment_id), 'operator gets no extra visibility');
    const cyFeed = await ids(t.cy);
    assert.deepEqual(cyFeed, ['p_1'], 'only public payments; no split or request items');
    const feed = await api.get('/activity?limit=1', { token: t.ada });
    assert.equal(feed.json.payments[0].payment_id, priv.json.payment_id);
    assert.equal(feed.json.has_more, true);
    assert.equal((await api.get('/activity?limit=300', { token: t.ada })).status, 422);
    assert.equal((await api.get('/requests', { token: t.op })).json.requests.length, 0);
  });
});

describe('settlements (§11)', () => {
  const settle = (t, transfers, k = key()) => api.post('/settlements', { transfers }, { token: t.op, key: k });

  test('net affordability, membership and replay (S1-196, S1-198, S1-201, S1-205)', async () => {
    const t = await seed(api);
    // cy has 0: cy -> ada 100 is only affordable because bob -> cy 100 counts too.
    const k = key();
    const r = await settle(t, [
      { from_handle: 'cy', to_handle: 'ada', amount: 100 },
      { from_handle: 'bob', to_handle: 'cy', amount: 100, visibility: 'private', note: 'n' },
    ], k);
    assert.equal(r.status, 201);
    assert.equal(r.json.payments.length, 2);
    assert.equal(r.json.payments[0].from_handle, 'cy');
    for (const p of r.json.payments) {
      assert.equal(p.settlement_id, r.json.settlement_id);
      assert.equal(p.request_id, null);
      assert.equal(p.created_at, r.json.committed_at);
    }
    assert.equal(r.json.payments[1].visibility, 'private');
    assert.equal((await api.get('/me', { token: t.cy })).json.balance, 0);
    const replay = await settle(t, [
      { from_handle: 'cy', to_handle: 'ada', amount: 100 },
      { from_handle: 'bob', to_handle: 'cy', amount: 100, visibility: 'private', note: 'n' },
    ], k);
    assert.equal(replay.status, 200);
    assert.deepEqual(replay.json, r.json);
    assert.equal((await api.get('/me', { token: t.ada })).json.balance, 10100);
    const cycle = await settle(t, [{ from_handle: 'cy', to_handle: 'op', amount: 5 }, { from_handle: 'op', to_handle: 'cy', amount: 5 }]);
    assert.equal(cycle.status, 201, 'net-zero cycle between empty wallets');
    const many = Array.from({ length: 32 }, () => ({ from_handle: 'ada', to_handle: 'bob', amount: 1 }));
    assert.equal((await settle(t, many)).status, 201);
    assert.equal((await settle(t, [...many, many[0]])).status, 422);
  });

  test('all or nothing; failures claim no key (S1-196, S1-197)', async () => {
    const t = await seed(api);
    const before = await total(t);
    const k = key();
    const short = await settle(t, [{ from_handle: 'bob', to_handle: 'cy', amount: 2500 }, { from_handle: 'cy', to_handle: 'op', amount: 2501 }], k);
    assert.equal(short.json.error.code, 'insufficient_funds');
    assert.equal((await api.get('/me', { token: t.bob })).json.balance, 2500);
    assert.equal(await total(t), before);
    assert.equal((await settle(t, [{ from_handle: 'bob', to_handle: 'cy', amount: 1 }], k)).status, 201, 'key reusable after failure');
  });

  test('permission and precedence (S1-192..S1-195, D-28)', async () => {
    const t = await seed(api);
    assert.equal((await api.post('/settlements', { transfers: [] }, { key: key() })).status, 401);
    assert.equal((await api.post('/settlements', '{bad', { token: t.ada, key: key() })).status, 403);
    const code = async (transfers) => (await settle(t, transfers)).json.error.code;
    const bad = (x) => ({ from_handle: 'ada', to_handle: 'bob', amount: 1, ...x });
    assert.equal(await code([bad({ to_handle: 'ghost' }), bad({ to_handle: 'ada', from_handle: 'ada' })]), 'not_found');
    assert.equal(await code([bad({ to_handle: 'ada', from_handle: 'ada' }), bad({ to_handle: 'ghost' })]), 'self_payment');
    assert.equal(await code([bad({ to_handle: 'ghost' }), 'x']), 'validation_failed', 'batch shape first');
    assert.equal(await code([bad({ amount: 0 }), bad({ to_handle: 'ghost' })]), 'validation_failed');
    assert.equal(await code([bad({ to_handle: 'ghost' }), bad({ amount: 999999999 })]), 'not_found', 'entry errors before funds');
    assert.equal(await code([bad({ from_handle: 5 })]), 'validation_failed');
    assert.equal((await api.post('/settlements', {}, { token: t.op, key: key() })).status, 422);
    assert.equal((await api.post('/settlements', '{bad', { token: t.op, key: key() })).status, 400);
  });
});

describe('export and import (§10)', () => {
  test('round trip keeps tokens, receipts and retries; import replaces (S1-170..S1-178)', async () => {
    const t = await seed(api);
    const k = key();
    const pay = await api.post('/payments', { to_handle: 'bob', amount: 10 }, { token: t.ada, key: k });
    const failedKey = key();
    await api.post('/payments', { to_handle: 'bob', amount: 10 ** 9 }, { token: t.ada, key: failedKey });
    const ex = await api.get('/_test/export');
    assert.equal(ex.status, 200);
    assert.equal(ex.json.track, 'pocketful');
    assert.equal(ex.json.format_version, 1);
    assert.ok(!ex.text.includes(PASSWORD), 'no plaintext password');

    await api.post('/payments', { to_handle: 'bob', amount: 20 }, { token: t.ada, key: key() });
    const signed = await api.post('/auth/signup', { email: 'dest@x.io', password: '12345678', display_name: 'D' });
    assert.equal((await api.post('/_test/import', ex.text)).status, 204);
    assert.equal((await api.get('/me', { token: signed.json.token })).status, 401, 'destination credentials removed');
    assert.equal((await api.get('/me', { token: t.ada })).json.balance, 9990, 'old token and exported balance');
    const replay = await api.post('/payments', { to_handle: 'bob', amount: 10 }, { token: t.ada, key: k });
    assert.equal(replay.status, 200);
    assert.deepEqual(replay.json, pay.json);
    assert.equal((await api.post('/payments', { to_handle: 'bob', amount: 11 }, { token: t.ada, key: k })).status, 409);
    assert.equal((await api.post('/payments', { to_handle: 'bob', amount: 1 }, { token: t.ada, key: failedKey })).status, 201);
    assert.equal((await api.post('/auth/login', { email: 'ada@example.com', password: PASSWORD })).status, 200);

    assert.equal((await api.post('/_test/import', ex.text)).status, 204);
    assert.equal((await api.post('/_test/import', ex.text)).status, 204);
    assert.equal((await api.get('/activity', { token: t.ada })).json.payments.length, 2, 'no duplication');
  });

  test('invalid imports are rejected without change (S1-174)', async () => {
    const t = await seed(api);
    const ex = (await api.get('/_test/export')).json;
    const variants = [
      { ...ex, track: 'tablekeeper' },
      { ...ex, format_version: 2 },
      { ...ex, format_version: '1' },
      { track: 'pocketful', format_version: 1 },
      { ...ex, state: [] },
      { ...ex, state: { ...ex.state, users: 'x' } },
    ];
    for (const v of variants) assert.equal((await api.post('/_test/import', v)).status, 422);
    assert.equal((await api.post('/_test/import', '{')).status, 400);
    assert.equal((await api.get('/me', { token: t.ada })).json.balance, 10000);
  });
});

describe('invariants under concurrency (§1)', () => {
  test('no overspend, conservation, request paid at most once (S1-001..S1-003, S1-203)', async () => {
    const t = await seed(api);
    const before = await total(t);
    const debits = Array.from({ length: 40 }, (_, i) =>
      api.post('/payments', { to_handle: i % 2 ? 'cy' : 'ada', amount: 100 }, { token: t.bob, key: key() }));
    const settles = Array.from({ length: 10 }, () =>
      api.post('/settlements', { transfers: [{ from_handle: 'bob', to_handle: 'op', amount: 100 }] }, { token: t.op, key: key() }));
    const pays = Array.from({ length: 10 }, () => api.post('/requests/rq_1/pay', {}, { token: t.ada, key: key() }));
    const res = await Promise.all([...debits, ...settles, ...pays]);
    assert.ok(res.every((r) => r.status < 500));
    const ok = res.slice(0, 50).filter((r) => r.status === 201).length;
    const failed = res.slice(0, 50).filter((r) => r.status === 409 && r.json.error.code === 'insufficient_funds').length;
    assert.equal(ok + failed, 50);
    assert.equal(res.slice(50).filter((r) => r.status === 201).length, 1, 'request paid once');
    // bob starts with 2500 and receives the 1200 request payment once.
    const bob = (await api.get('/me', { token: t.bob })).json.balance;
    assert.ok(ok >= 25 && ok <= 37, `successful debits ${ok}`);
    assert.equal(bob, 2500 + 1200 - 100 * ok);
    assert.ok(bob >= 0);
    assert.equal(await total(t), before);
  });
});
