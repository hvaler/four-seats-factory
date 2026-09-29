'use strict';

// Stage-3 implementation tests: payment timestamps, historical /me, statements,
// corrections with revisions, known_at, snapshots and historical holds.
// Expected balances are computed by hand from the fixtures below.

const { test, before, after, describe } = require('node:test');
const assert = require('node:assert/strict');
const { start, client, fixture, seed, key } = require('./helpers');

let srv;
let api;
before(async () => {
  srv = await start();
  api = client(srv.base);
});
after(async () => srv.close());

const T = (s) => `2026-01-0${s}T00:00:00+00:00`;       // fixed seeded instants
const enc = encodeURIComponent;
const me = async (t, qs = '') => (await api.get(`/me${qs}`, { token: t })).json;
const correct = (t, pid, body, k = key()) => api.post(`/payments/${pid}/corrections`, body, { token: t, key: k });
const iso = (ms) => new Date(ms).toISOString().replace('Z', '+00:00');

// Seeded history, oldest first, with ending balances ada 10000, bob 2500, cy 500:
//   p_a  day 1  ada -> bob  1000
//   p_b  day 2  bob -> cy    300 (private)
//   p_c  day 3  ada -> cy    200
// Openings: ada 11200, bob 1800, cy 0; total 13000.
function history() {
  const fx = fixture({
    payments: [
      { id: 'p_a', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 1000, created_at: T(1) },
      { id: 'p_b', from_user_id: 'u_bob', to_user_id: 'u_cy', amount: 300, created_at: T(2), visibility: 'private' },
      { id: 'p_c', from_user_id: 'u_ada', to_user_id: 'u_cy', amount: 200, created_at: T(3) },
    ],
    requests: [],
  });
  fx.users[2].balance = 500;
  return fx;
}

describe('timestamps and /me as_of (S3-010..S3-023, S3-041)', () => {
  test('seeded created_at, openings and inclusive as_of', async () => {
    const t = await seed(api, history());
    assert.equal((await me(t.ada, `?as_of=${enc('2025-12-31T00:00:00+00:00')}`)).balance, 11200, 'opening');
    assert.equal((await me(t.ada, `?as_of=${enc(T(1))}`)).balance, 10200, 'inclusive at exactly as_of');
    const m = await me(t.ada, `?as_of=${enc('2026-01-02T01:00:00+01:00')}`);
    assert.equal(m.balance, 10200);
    assert.equal(m.as_of, '2026-01-02T01:00:00+01:00', 'echoed exactly');
    assert.equal((await me(t.ada, `?as_of=${enc('2099-01-01T00:00:00Z')}`)).balance, 10000, 'future = current');
    assert.equal((await me(t.cy, `?as_of=${enc(T(2))}`)).balance, 300);
    const feed = (await api.get('/activity', { token: t.ada })).json.payments.map((p) => p.payment_id);
    assert.deepEqual(feed.slice(0, 2), ['p_c', 'p_a'], 'activity newest first by created_at');
    assert.equal((await me(t.ada)).balance, 10000);
  });

  test('bad instants and future seeded times are 422', async () => {
    const t = await seed(api);
    for (const v of ['2026-09-24T13:20:00', '2026-09-24', '', 'yesterday', '2026-02-30T00:00:00Z', '2026-09-24T13:20:00 00:00']) {
      assert.equal((await api.get(`/me?as_of=${enc(v)}`, { token: t.ada })).status, 422, v);
      assert.equal((await api.get(`/statement?from=${enc(v)}`, { token: t.ada })).status, 422, v);
    }
    const fx = fixture({ payments: [{ id: 'p_f', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 1, created_at: '2099-01-01T00:00:00Z' }] });
    assert.equal((await api.post('/_test/reset', fx)).status, 422);
    assert.equal((await me(t.ada)).balance, 10000, 'unchanged');
  });
});

describe('statements (S3-030..S3-036, S3-060..S3-064)', () => {
  test('window, ordering, running balances and pagination invariance', async () => {
    const t = await seed(api, history());
    const full = (await api.get('/statement', { token: t.ada })).json;
    assert.equal(full.opening_balance, 11200);
    assert.deepEqual(full.entries.map((e) => [e.payment.payment_id, e.delta, e.balance_after]), [['p_a', -1000, 10200], ['p_c', -200, 10000]]);
    assert.equal(full.closing_balance, 10000);
    assert.equal(full.entries[0].revision, 1);
    assert.equal(full.entries[0].effective_at, T(1));
    assert.equal(typeof full.snapshot, 'string');
    const win = (await api.get(`/statement?from=${enc(T(1))}&to=${enc(T(3))}`, { token: t.ada })).json;
    assert.deepEqual(win.entries.map((e) => e.payment.payment_id), ['p_a'], 'from included, to excluded');
    assert.deepEqual([win.opening_balance, win.closing_balance], [11200, 10200]);
    const p2 = (await api.get('/statement?limit=1&offset=1', { token: t.ada })).json;
    assert.deepEqual([p2.opening_balance, p2.entries[0].balance_after, p2.closing_balance, p2.has_more], [11200, 10000, 10000, false]);
    const bob = (await api.get('/statement', { token: t.bob })).json;
    assert.deepEqual(bob.entries.map((e) => e.payment.payment_id), ['p_a', 'p_b'], 'own private payment, not others');
    assert.equal((await api.get(`/statement?from=${enc(T(3))}&to=${enc(T(1))}`, { token: t.ada })).status, 422);
  });

  test('snapshots page a frozen result', async () => {
    const t = await seed(api, history());
    const first = (await api.get('/statement?limit=1', { token: t.ada })).json;
    await api.post('/payments', { to_handle: 'bob', amount: 5 }, { token: t.ada, key: key() });
    await correct(t.ada, 'p_a', { expected_revision: 1, amount: 900, effective_at: T(1), reason: 'fix' });
    const page2 = (await api.get(`/statement?snapshot=${enc(first.snapshot)}&limit=1&offset=1`, { token: t.ada })).json;
    assert.deepEqual([page2.opening_balance, page2.closing_balance, page2.entries[0].payment.payment_id, page2.has_more], [11200, 10000, 'p_c', false]);
    const past = (await api.get(`/statement?snapshot=${enc(first.snapshot)}&offset=9`, { token: t.ada })).json;
    assert.deepEqual([past.entries.length, past.has_more], [0, false]);
    assert.equal((await api.get(`/statement?snapshot=${enc(first.snapshot)}&from=${enc(T(1))}`, { token: t.ada })).status, 422);
    assert.equal((await api.get(`/statement?snapshot=${enc(first.snapshot)}`, { token: t.bob })).status, 404);
    assert.equal((await api.get('/statement?snapshot=nope', { token: t.ada })).status, 404);
    const t2 = await seed(api, history());
    assert.equal((await api.get(`/statement?snapshot=${enc(first.snapshot)}`, { token: t2.ada })).status, 404, 'reset clears');
  });
});

describe('corrections (S3-040..S3-055)', () => {
  test('a decrease moves money back, keeps receipts and appends a revision', async () => {
    const t = await seed(api, history());
    const k = key();
    const c = await correct(t.ada, 'p_a', { expected_revision: 1, amount: 400, effective_at: T(1), reason: 'corrected amount' }, k);
    assert.equal(c.status, 201);
    assert.deepEqual([c.json.payment_id, c.json.revision, c.json.amount, c.json.effective_at, c.json.reason], ['p_a', 2, 400, T(1), 'corrected amount']);
    assert.deepEqual([(await me(t.ada)).balance, (await me(t.bob)).balance], [10600, 1900]);
    const feed = (await api.get('/activity', { token: t.ada })).json.payments.find((p) => p.payment_id === 'p_a');
    assert.equal(feed.amount, 1000, 'feed keeps the original');
    const st = (await api.get('/statement', { token: t.ada })).json;
    assert.deepEqual([st.entries[0].payment.amount, st.entries[0].delta, st.entries[0].revision], [400, -400, 2]);
    assert.equal(st.opening_balance, 11200, 'opening unchanged');
    const revs = (await api.get('/payments/p_a/revisions', { token: t.bob })).json.revisions;
    assert.deepEqual(revs.map((r) => [r.revision, r.amount, r.reason]), [[1, 1000, ''], [2, 400, 'corrected amount']]);
    assert.equal(revs[0].effective_at, revs[0].recorded_at);
    assert.equal((await api.get('/payments/p_a/revisions', { token: t.cy })).status, 404);
    assert.equal((await api.get('/payments/p_a/revisions')).status, 401);
    const again = await correct(t.ada, 'p_a', { expected_revision: 1, amount: 400, effective_at: T(1), reason: 'corrected amount' }, k);
    assert.deepEqual([again.status, again.text], [200, c.text]);
    assert.equal((await correct(t.ada, 'p_a', { expected_revision: 1, amount: 401, effective_at: T(1), reason: 'x' }, k)).status, 409);
    assert.equal((await correct(t.ada, 'p_a', { expected_revision: 1, amount: 300, effective_at: T(1), reason: 'x' })).json.error.code, 'stale_revision');
  });

  test('validation, permissions and precedence (D3-01, D3-02)', async () => {
    const t = await seed(api, history());
    const ok = { expected_revision: 1, amount: 100, effective_at: T(1), reason: 'r' };
    const code = async (b, tok = t.ada, pid = 'p_a') => (await correct(tok, pid, b)).json.error.code;
    for (const bad of [{ ...ok, expected_revision: 0 }, { ...ok, expected_revision: '1' }, { ...ok, amount: -1 }, { ...ok, amount: 1000000001 },
      { ...ok, reason: '' }, { ...ok, reason: 'x'.repeat(201) }, { ...ok, effective_at: '2099-01-01T00:00:00Z' }, { ...ok, effective_at: '2026-01-01T00:00:00' },
      { amount: 1, effective_at: T(1), reason: 'r' }]) {
      assert.equal(await code(bad), 'validation_failed', JSON.stringify(bad));
    }
    assert.equal(await code({ ...ok, expected_revision: '1' }, t.ada, 'p_nope'), 'validation_failed', 'fields before 404');
    assert.equal(await code(ok, t.ada, 'p_nope'), 'not_found');
    assert.equal(await code(ok, t.bob), 'forbidden');
    const raw = await api.post('/payments/p_a/corrections', '{"expected_revision":1.0,"amount":1e2,"effective_at":"'+T(1)+'","reason":"r"}', { token: t.ada, key: key() });
    assert.equal(raw.status, 201, 'integral forms 1.0 and 1e2 accepted');
  });

  test('insufficient funds and historical overdraft (S3-049, S3-083)', async () => {
    const t = await seed(api, history());
    // Raising p_b (bob -> cy) to 3000 debits bob 2700 now, but bob holds 2500.
    assert.equal((await correct(t.bob, 'p_b', { expected_revision: 1, amount: 3000, effective_at: T(2), reason: 'r' })).json.error.code, 'insufficient_funds');
    // Raising it to 2800 debits bob 2500: affordable now, and bob had 2800 on day 1.
    const ok = await correct(t.bob, 'p_b', { expected_revision: 1, amount: 2800, effective_at: T(2), reason: 'r' });
    assert.equal(ok.status, 201);
    // Time move (R3-02): cy now spends its 3000; backdating that payment to before cy's
    // income (day 2) would make cy negative in the past.
    const out = await api.post('/payments', { to_handle: 'ada', amount: 3000, note: '' }, { token: t.cy, key: key() });
    assert.equal(out.status, 201, 'cy had 3000');
    const code = (await correct(t.cy, out.json.payment_id, { expected_revision: 1, amount: 3000, effective_at: '2025-12-31T00:00:00+00:00', reason: 'backdate' })).json.error.code;
    assert.equal(code, 'historical_overdraft');
    assert.equal((await api.get(`/payments/${out.json.payment_id}/revisions`, { token: t.cy })).json.revisions.length, 1, 'nothing appended');
  });

  test('holds make historical available negative (S3-083 holds case)', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    const pay = await api.post('/payments', { to_handle: 'cy', amount: 1000 }, { token: t.ada, key: key() });
    const a = await api.post('/authorizations', { to_handle: 'ada', amount: 800 }, { token: t.cy, key: key() });
    await api.call('POST', `/authorizations/${a.json.authorization_id}/void`, { token: t.cy });
    const r = await correct(t.ada, pay.json.payment_id, { expected_revision: 1, amount: 100, effective_at: pay.json.created_at, reason: 'r' });
    assert.equal(r.json.error.code, 'historical_overdraft');
    const list = (await api.get('/authorizations', { token: t.cy })).json.authorizations[0];
    assert.equal(typeof list.closed_at, 'string');
  });

  test('linked payments are immutable (S3-056, S3-070/071)', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    const st = await api.post('/settlements', { transfers: [{ from_handle: 'ada', to_handle: 'bob', amount: 10 }] }, { token: t.op, key: key() });
    const member = st.json.payments[0];
    const c1 = await correct(t.ada, member.payment_id, { expected_revision: 1, amount: 5, effective_at: member.created_at, reason: 'r' });
    assert.equal(c1.json.error.code, 'linked_payment_immutable');
    const a = await api.post('/authorizations', { to_handle: 'bob', amount: 50 }, { token: t.ada, key: key() });
    const cap = await api.post(`/authorizations/${a.json.authorization_id}/capture`, {}, { token: t.bob, key: key() });
    const c2 = await correct(t.ada, cap.json.payment_id, { expected_revision: 1, amount: 5, effective_at: cap.json.created_at, reason: 'r' });
    assert.equal(c2.json.error.code, 'linked_payment_immutable');
    const s = (await api.get('/statement', { token: t.bob })).json.entries;
    assert.equal(s.filter((e) => e.payment.payment_id === cap.json.payment_id).length, 1);
    assert.equal(s.find((e) => e.payment.payment_id === member.payment_id).effective_at, st.json.committed_at);
  });

  test('known_at selects revisions and conservation holds in every view (S3-050, S3-053)', async () => {
    const t = await seed(api, history());
    const before_ = iso(Date.now() - 1);
    await new Promise((r) => setTimeout(r, 5));
    const c = (await correct(t.ada, 'p_a', { expected_revision: 1, amount: 0, effective_at: T(1), reason: 'reverse' })).json;
    const old = await me(t.ada, `?known_at=${enc(before_)}`);
    assert.equal(old.balance, 10000, 'revision 1 view');
    assert.equal(old.known_at, before_);
    assert.equal((await me(t.ada, `?known_at=${enc(c.recorded_at)}`)).balance, 11000, 'exactly at recorded_at selects it');
    const early = await api.get(`/statement?known_at=${enc('2025-01-01T00:00:00Z')}`, { token: t.ada });
    assert.equal(early.json.entries.length, 0, 'nothing known yet');
    const zero = (await api.get('/statement', { token: t.ada })).json.entries.find((e) => e.payment.payment_id === 'p_a');
    assert.deepEqual([zero.delta, zero.payment.amount], [0, 0], 'zero revision still an entry');
    const grid = ['2025-12-31T00:00:00Z', T(1), T(2), T(3), before_, c.recorded_at, '2099-01-01T00:00:00Z'];
    for (const A of grid) {
      for (const K of grid) {
        let sum = 0;
        for (const tok of Object.values(t)) sum += (await me(tok, `?as_of=${enc(A)}&known_at=${enc(K)}`)).balance;
        assert.equal(sum, 13000, `${A} / ${K}`);
      }
    }
  });

  test('recorded times strictly increase; concurrent same-revision corrections (S3-045, S3-065)', async () => {
    const t = await seed(api, history());
    const res = await Promise.all(Array.from({ length: 10 }, (_, i) =>
      correct(t.ada, 'p_c', { expected_revision: 1, amount: 100 + i, effective_at: T(3), reason: 'r' })));
    assert.equal(res.filter((r) => r.status === 201).length, 1);
    assert.equal(res.filter((r) => r.json && r.json.error && r.json.error.code === 'stale_revision').length, 9);
    let rev = 2;
    for (let i = 0; i < 5; i += 1) {
      const r = await correct(t.ada, 'p_c', { expected_revision: rev, amount: 50 + i, effective_at: T(3), reason: 'r' });
      assert.equal(r.status, 201);
      rev += 1;
    }
    const revs = (await api.get('/payments/p_c/revisions', { token: t.ada })).json.revisions;
    for (let i = 1; i < revs.length; i += 1) {
      assert.ok(revs[i].recorded_at > revs[i - 1].recorded_at, 'string order');
      assert.ok(Date.parse(revs[i].recorded_at) > Date.parse(revs[i - 1].recorded_at), 'instant order');
    }
  });
});

describe('historical holds (S3-080..S3-082, S3-057)', () => {
  test('hold created, partially captured and released in history', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    const a = (await api.post('/authorizations', { to_handle: 'bob', amount: 1000 }, { token: t.ada, key: key() })).json;
    assert.equal(a.closed_at, null);
    await new Promise((r) => setTimeout(r, 5));
    const c = (await api.post(`/authorizations/${a.authorization_id}/capture`, { amount: 300, final: false }, { token: t.bob, key: key() })).json;
    await new Promise((r) => setTimeout(r, 5));
    const v = (await api.call('POST', `/authorizations/${a.authorization_id}/void`, { token: t.ada })).json;
    const at = (x) => me(t.ada, `?as_of=${enc(x)}`);
    const pre = await at(iso(Date.parse(a.created_at) - 1));
    assert.deepEqual([pre.total, pre.held, pre.available], [10000, 0, 10000]);
    const open = await at(a.created_at);
    assert.deepEqual([open.total, open.held, open.available], [10000, 1000, 9000]);
    const part = await at(c.created_at);
    assert.deepEqual([part.total, part.held, part.available], [9700, 700, 9000]);
    const done = await at(v.closed_at);
    assert.deepEqual([done.total, done.held, done.available], [9700, 0, 9700]);
    const unknownVoid = await me(t.ada, `?as_of=${enc(v.closed_at)}&known_at=${enc(iso(Date.parse(v.closed_at) - 1))}`);
    assert.equal(unknownVoid.held, 700, 'a void is invisible before it is known');
  });

  test('an open hold expires at its deadline in future views', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [], authorization_ttl_seconds: 3600 }));
    const a = (await api.post('/authorizations', { to_handle: 'bob', amount: 400 }, { token: t.ada, key: key() })).json;
    assert.equal((await me(t.ada, `?as_of=${enc(iso(Date.parse(a.expires_at) - 1000))}`)).held, 400);
    assert.equal((await me(t.ada, `?as_of=${enc(a.expires_at)}`)).held, 0);
  });
});

describe('upgrade from a stage-2 export (S3-071, D3-13, D3-18)', () => {
  test('a schema-2 export imports with openings and revision 1 everywhere', async () => {
    const t = await seed(api, history());
    const k = key();
    const pay = await api.post('/payments', { to_handle: 'bob', amount: 10 }, { token: t.ada, key: k });
    const ex = (await api.get('/_test/export')).json;
    const st = ex.state;
    st.schema = 2;
    st.users.forEach((u) => delete u.opening);
    st.payments.forEach((p) => delete p.revisions);
    delete st.snapshots;
    st.authorizations.forEach((a) => { delete a.closed_at; delete a.create_hold; delete a.lifecycle; });
    assert.equal((await api.post('/_test/import', ex)).status, 204);
    assert.equal((await me(t.ada, `?as_of=${enc('2025-12-31T00:00:00Z')}`)).balance, 11200);
    const replay = await api.post('/payments', { to_handle: 'bob', amount: 10 }, { token: t.ada, key: k });
    assert.equal(replay.text, pay.text);
    const c = await correct(t.ada, pay.json.payment_id, { expected_revision: 1, amount: 5, effective_at: pay.json.created_at, reason: 'r' });
    assert.equal(c.status, 201);
  });
});
