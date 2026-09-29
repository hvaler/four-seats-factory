'use strict';

// Stage-4 implementation tests: refunds, the correction floor and correction
// batches. Register IDs are noted per test; expected balances are hand-computed.

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

const enc = encodeURIComponent;
const me = async (t, qs = '') => (await api.get(`/me${qs}`, { token: t })).json;
const pay = async (t, to, amount, extra = {}) => (await api.post('/payments', { to_handle: to, amount, ...extra }, { token: t, key: key() })).json;
const refund = (t, pid, amount, k = key()) => api.post(`/payments/${pid}/refunds`, { amount }, { token: t, key: k });
const batch = (t, corrections, k = key()) => api.post('/correction-batches', { corrections }, { token: t, key: k });
const empty = () => fixture({ payments: [], requests: [] });

describe('refunds (S4-010..S4-023)', () => {
  test('a refund is a new payment back to the sender', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 1000, { note: 'dinner', visibility: 'private' });
    assert.equal(p.refund_of, null);
    const k = key();
    const r = await refund(t.bob, p.payment_id, 300, k);
    assert.equal(r.status, 201);
    assert.deepEqual([r.json.from_handle, r.json.to_handle, r.json.amount, r.json.refund_of, r.json.note, r.json.visibility],
      ['bob', 'ada', 300, p.payment_id, 'dinner', 'private']);
    assert.deepEqual([r.json.request_id, r.json.authorization_id, r.json.settlement_id], [null, null, null]);
    assert.deepEqual([(await me(t.ada)).balance, (await me(t.bob)).balance], [9300, 3200]);
    const again = await refund(t.bob, p.payment_id, 300, k);
    assert.deepEqual([again.status, again.text], [200, r.text]);
    const feed = (await api.get('/activity', { token: t.ada })).json.payments;
    assert.equal(feed.find((x) => x.payment_id === r.json.payment_id).refund_of, p.payment_id);
    assert.ok(!(await api.get('/activity', { token: t.cy })).json.payments.some((x) => x.payment_id === r.json.payment_id), 'private copied');
    const st = (await api.get('/statement', { token: t.bob })).json.entries;
    assert.deepEqual(st.map((e) => [e.payment.refund_of, e.delta]), [[null, 1000], [p.payment_id, -300]]);
    const revs = (await api.get(`/payments/${r.json.payment_id}/revisions`, { token: t.ada })).json.revisions;
    assert.equal(revs.length, 1);
    assert.equal(revs[0].correction_batch_id, null);
  });

  test('permissions, targets, limits and precedence (D4-01)', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 1000);
    const code = async (tok, pid, amount) => (await refund(tok, pid, amount)).json.error.code;
    assert.equal(await code(t.ada, p.payment_id, 1), 'forbidden');
    assert.equal(await code(t.cy, p.payment_id, 1), 'forbidden');
    assert.equal(await code(t.op, p.payment_id, 1), 'forbidden');
    assert.equal(await code(t.bob, 'p_nope', 1), 'not_found');
    for (const bad of [0, -1, 1000000001, 1.5, '5', true]) assert.equal(await code(t.bob, p.payment_id, bad), 'validation_failed', String(bad));
    assert.equal(await code(t.bob, 'p_nope', 0), 'validation_failed', 'amount before 404');
    assert.equal((await refund(t.bob, p.payment_id, 600)).status, 201);
    assert.equal(await code(t.bob, p.payment_id, 401), 'refund_exceeds_payment');
    assert.equal((await refund(t.bob, p.payment_id, 400)).status, 201, 'exactly the amount');
    const r = (await api.get('/activity', { token: t.bob })).json.payments.find((x) => x.refund_of === p.payment_id);
    assert.equal(await code(t.ada, r.payment_id, 1), 'invalid_refund_target');
    assert.equal((await api.post(`/payments/${p.payment_id}/refunds`, { amount: 1 }, { token: t.bob })).json.error.code, 'missing_idempotency_key');
    assert.equal((await api.post(`/payments/${p.payment_id}/refunds`, { amount: 1 }, { key: key() })).status, 401);
  });

  test('refunds use available funds and never reopen requests or holds (S4-016, S4-017)', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'cy', 500);
    await api.post('/authorizations', { to_handle: 'bob', amount: 400 }, { token: t.cy, key: key() });
    assert.equal((await refund(t.cy, p.payment_id, 101)).json.error.code, 'insufficient_funds', 'only 100 available');
    assert.equal((await refund(t.cy, p.payment_id, 100)).status, 201);
    const rq = (await api.post('/requests', { payer_handle: 'bob', amount: 50 }, { token: t.ada, key: key() })).json;
    const paid = (await api.post(`/requests/${rq.request_id}/pay`, {}, { token: t.bob, key: key() })).json;
    assert.equal((await refund(t.ada, paid.payment_id, 50)).status, 201);
    const rqs = (await api.get('/requests', { token: t.ada })).json.requests.find((x) => x.request_id === rq.request_id);
    assert.deepEqual([rqs.status, rqs.payment_id], ['paid', paid.payment_id]);
    const a = (await api.post('/authorizations', { to_handle: 'ada', amount: 200 }, { token: t.bob, key: key() })).json;
    const cap = (await api.post(`/authorizations/${a.authorization_id}/capture`, { amount: 80 }, { token: t.ada, key: key() })).json;
    assert.equal((await refund(t.ada, cap.payment_id, 80)).status, 201);
    const au = (await api.get('/authorizations', { token: t.bob })).json.authorizations.find((x) => x.authorization_id === a.authorization_id);
    assert.deepEqual([au.status, au.captured_amount, au.remaining_amount], ['captured', 80, 0]);
    assert.equal((await me(t.bob)).held, 0, 'the released hold is not restored');
  });

  test('concurrent refunds never exceed the payment (S4-023)', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 1000);
    const res = await Promise.all(Array.from({ length: 15 }, () => refund(t.bob, p.payment_id, 100)));
    assert.equal(res.filter((r) => r.status === 201).length, 10);
    assert.ok(res.every((r) => r.status === 201 || r.json.error.code === 'refund_exceeds_payment'));
    const k = key();
    const p2 = await pay(t.ada, 'bob', 50);
    const same = await Promise.all(Array.from({ length: 15 }, () => refund(t.bob, p2.payment_id, 10, k)));
    assert.deepEqual([same.filter((r) => r.status === 201).length, same.filter((r) => r.status === 200).length], [1, 14]);
    let sum = 0;
    for (const tok of Object.values(t)) sum += (await me(tok)).balance;
    assert.equal(sum, 12500);
  });
});

describe('corrections with refunds (S4-020..S4-022)', () => {
  test('corrections cannot go below the refunded total; refunds and captures are immutable', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 1000);
    const r = (await refund(t.bob, p.payment_id, 300)).json;
    const correct = (tok, pid, amount, rev = 1) => api.post(`/payments/${pid}/corrections`,
      { expected_revision: rev, amount, effective_at: p.created_at, reason: 'r' }, { token: tok, key: key() });
    assert.equal((await correct(t.ada, p.payment_id, 299)).json.error.code, 'refund_exceeds_payment');
    assert.equal((await correct(t.ada, p.payment_id, 300)).status, 201, 'exactly the refunded total');
    assert.equal((await refund(t.bob, p.payment_id, 1)).json.error.code, 'refund_exceeds_payment', 'limit is the corrected amount');
    assert.equal((await correct(t.bob, r.payment_id, 1)).json.error.code, 'linked_payment_immutable');
    assert.equal((await batch(t.op, [{ payment_id: r.payment_id, expected_revision: 1, amount: 1, effective_at: p.created_at, reason: 'r' }])).json.error.code, 'linked_payment_immutable');
  });

  test('a later backdated correction counts the refund in history (auditor E2)', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'cy', 1000);
    await refund(t.cy, p.payment_id, 300);
    await pay(t.cy, 'bob', 700);
    // cy now holds 0; lowering p to 300 would take 700 back from cy -> insufficient now.
    const r = await api.post(`/payments/${p.payment_id}/corrections`,
      { expected_revision: 1, amount: 300, effective_at: p.created_at, reason: 'r' }, { token: t.ada, key: key() });
    assert.equal(r.json.error.code, 'insufficient_funds');
    assert.equal((await me(t.cy, `?as_of=${enc(p.created_at)}`)).balance, 1000);
  });
});

describe('correction batches (S4-030..S4-047)', () => {
  const item = (p, extra = {}) => ({ payment_id: p.payment_id, expected_revision: 1, amount: 0, effective_at: p.created_at, reason: 'reversal', ...extra });

  async function settled(t) {
    const st = (await api.post('/settlements', { transfers: [
      { from_handle: 'ada', to_handle: 'bob', amount: 100 },
      { from_handle: 'ada', to_handle: 'cy', amount: 50 },
    ] }, { token: t.op, key: key() })).json;
    return st;
  }

  test('an operator reverses a whole settlement atomically', async () => {
    const t = await seed(api, empty());
    const stKey = key();
    const stRaw = await api.post('/settlements', { transfers: [{ from_handle: 'ada', to_handle: 'bob', amount: 100 }, { from_handle: 'ada', to_handle: 'cy', amount: 50 }] }, { token: t.op, key: stKey });
    const [m1, m2] = stRaw.json.payments;
    const k = key();
    const b = await batch(t.op, [item(m1), item(m2, { effective_at: m1.created_at.replace('+00:00', 'Z') })], k);
    assert.equal(b.status, 201);
    assert.equal(b.json.revisions.length, 2);
    assert.ok(b.json.revisions.every((r) => r.correction_batch_id === b.json.correction_batch_id && r.recorded_at === b.json.recorded_at && r.revision === 2));
    assert.deepEqual([(await me(t.ada)).balance, (await me(t.bob)).balance, (await me(t.cy)).balance], [10000, 2500, 0]);
    const replay = await batch(t.op, [item(m1), item(m2, { effective_at: m1.created_at.replace('+00:00', 'Z') })], k);
    assert.deepEqual([replay.status, replay.text], [200, b.text]);
    const stAgain = await api.post('/settlements', { transfers: [{ from_handle: 'ada', to_handle: 'bob', amount: 100 }, { from_handle: 'ada', to_handle: 'cy', amount: 50 }] }, { token: t.op, key: stKey });
    assert.deepEqual([stAgain.status, stAgain.text], [200, stRaw.text], 'settlement receipt unchanged');
    const revs = (await api.get(`/payments/${m1.payment_id}/revisions`, { token: t.bob })).json.revisions;
    assert.deepEqual(revs.map((r) => r.correction_batch_id), [null, b.json.correction_batch_id]);
    assert.equal((await api.get(`/payments/${m1.payment_id}/revisions`, { token: t.op })).status, 404, 'operator is not a party');
  });

  test('shape, completeness, instants and precedence (D4-06)', async () => {
    const t = await seed(api, empty());
    const st = await settled(t);
    const [m1, m2] = st.payments;
    const p = await pay(t.ada, 'bob', 10);
    const code = async (items) => (await batch(t.op, items)).json.error.code;
    assert.equal((await batch(t.ada, [item(p)])).status, 403);
    assert.equal((await api.post('/correction-batches', { corrections: [item(p)] }, { key: key() })).status, 401);
    assert.equal(await code([]), 'validation_failed');
    assert.equal(await code(Array.from({ length: 33 }, () => item(p))), 'validation_failed');
    assert.equal(await code([item(p), item(p)]), 'validation_failed');
    assert.equal(await code([item(m1)]), 'incomplete_settlement');
    assert.equal(await code([item(m1), item(m2, { effective_at: '2020-01-01T00:00:00+00:00' })]), 'validation_failed');
    assert.equal(await code([item(p, { expected_revision: 2 }), { ...item(p), payment_id: 'p_nope' }]), 'stale_revision');
    assert.equal(await code([{ ...item(p), payment_id: 'p_nope' }, item(p, { expected_revision: 2 })]), 'not_found');
    assert.equal(await code([item(p, { amount: -1 }), { ...item(p), payment_id: 'p_nope' }]), 'validation_failed');
    assert.equal(await code([item(p), item(m1)]), 'incomplete_settlement', 'mixing is fine, completeness still applies');
    assert.equal((await batch(t.op, [item(p), item(m1), item(m2), { ...item(p), x: 1, payment_id: 'zz' }].slice(0, 3))).status, 201, 'non-member plus complete settlement');
  });

  test('combined affordability and rejected batches leave no trace (S4-038, S4-039)', async () => {
    const t = await seed(api, empty());
    const toCy = await pay(t.ada, 'cy', 500);
    const fromCy = await pay(t.cy, 'bob', 500);
    // cy has 0. Lowering toCy alone debits cy 500 now -> insufficient; raising fromCy... instead
    // lowering both by the same amount nets cy to zero change.
    const alone = await batch(t.op, [item(toCy, { amount: 200 })]);
    assert.equal(alone.json.error.code, 'insufficient_funds');
    const k = key();
    const both = await batch(t.op, [item(toCy, { amount: 200 }), item(fromCy, { amount: 200 })], k);
    assert.equal(both.status, 201, 'combined effect is affordable');
    assert.deepEqual([(await me(t.ada)).balance, (await me(t.bob)).balance, (await me(t.cy)).balance], [9800, 2700, 0]);
    const rejected = await batch(t.op, [item(toCy, { expected_revision: 2, amount: 100 })], k);
    assert.equal(rejected.status, 409, 'same key, different body');
    const failKey = key();
    assert.equal((await batch(t.op, [item(toCy, { expected_revision: 1 })], failKey)).json.error.code, 'stale_revision');
    assert.equal((await batch(t.op, [item(toCy, { expected_revision: 2, amount: 200 })], failKey)).status, 201, 'failed key stays reusable');
  });

  test('historical overdraft through the combined batch', async () => {
    const t = await seed(api, empty());
    const inc = await pay(t.ada, 'cy', 500);
    const out = await pay(t.cy, 'bob', 500);
    // Moving cy's outgoing payment before its income overdraws cy in the past.
    const r = await batch(t.op, [item(out, { amount: 500, effective_at: '2020-01-01T00:00:00+00:00' }), item(inc, { amount: 500 })]);
    assert.equal(r.json.error.code, 'historical_overdraft');
    assert.equal((await api.get(`/payments/${out.payment_id}/revisions`, { token: t.cy })).json.revisions.length, 1);
  });

  test('overlapping concurrent corrections: one wins (S4-046)', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 100);
    const q = await pay(t.ada, 'cy', 100);
    const jobs = [
      ...Array.from({ length: 5 }, () => batch(t.op, [item(p, { amount: 90 }), item(q, { amount: 90 })])),
      ...Array.from({ length: 5 }, () => api.post(`/payments/${p.payment_id}/corrections`, { expected_revision: 1, amount: 80, effective_at: p.created_at, reason: 'r' }, { token: t.ada, key: key() })),
    ];
    const res = await Promise.all(jobs);
    assert.equal(res.filter((r) => r.status === 201).length, 1);
    assert.ok(res.every((r) => r.status === 201 || r.json.error.code === 'stale_revision'));
    const same = key();
    const ids = await Promise.all(Array.from({ length: 15 }, () => batch(t.op, [item(q, { expected_revision: (res[0].status === 201 && res[0].json.revisions) ? 2 : 1, amount: 70 })], same)));
    assert.ok(ids.filter((r) => r.status === 201).length <= 1);
    assert.ok(ids.every((r) => r.status < 500));
  });

  test('snapshots keep paging frozen entries after a batch (S4-043)', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 100);
    const first = await api.get('/statement', { token: t.ada });
    await batch(t.op, [item(p)]);
    assert.equal((await api.get(`/statement?snapshot=${enc(first.json.snapshot)}`, { token: t.ada })).text, first.text);
    const now = (await api.get('/statement', { token: t.ada })).json.entries[0];
    assert.deepEqual([now.revision, now.payment.amount], [2, 0]);
  });
});

describe('upgrade (S4-050)', () => {
  test('a schema-3 export imports with revisions, snapshots and null refund links', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 100);
    await api.post(`/payments/${p.payment_id}/corrections`, { expected_revision: 1, amount: 60, effective_at: p.created_at, reason: 'r' }, { token: t.ada, key: key() });
    const first = await api.get('/statement', { token: t.ada });
    const ex = (await api.get('/_test/export')).json;
    ex.state.schema = 3;
    ex.state.payments.forEach((x) => { delete x.refund_of; x.revisions.forEach((v) => delete v.correction_batch_id); });
    assert.equal((await api.post('/_test/import', ex)).status, 204);
    assert.equal((await api.get(`/statement?snapshot=${enc(first.json.snapshot)}`, { token: t.ada })).text, first.text);
    const revs = (await api.get(`/payments/${p.payment_id}/revisions`, { token: t.bob })).json.revisions;
    assert.deepEqual(revs.map((r) => [r.amount, r.correction_batch_id]), [[100, null], [60, null]]);
    assert.equal((await refund(t.bob, p.payment_id, 60)).status, 201);
    assert.equal((await refund(t.bob, p.payment_id, 1)).json.error.code, 'refund_exceeds_payment');
  });
});

describe('register r2 cases', () => {
  const item = (p, extra = {}) => ({ payment_id: p.payment_id, expected_revision: 1, amount: 0, effective_at: p.created_at, reason: 'r', ...extra });

  test('refunded settlement members: floor, refund not a member (S4-021, S4-045)', async () => {
    const t = await seed(api, empty());
    const st = (await api.post('/settlements', { transfers: [{ from_handle: 'ada', to_handle: 'bob', amount: 100 }, { from_handle: 'ada', to_handle: 'cy', amount: 50 }] }, { token: t.op, key: key() })).json;
    const [m1, m2] = st.payments;
    const r = (await refund(t.bob, m1.payment_id, 30)).json;
    assert.equal(r.settlement_id, null);
    assert.equal((await batch(t.op, [item(m1), item(m2)])).json.error.code, 'refund_exceeds_payment');
    assert.equal((await batch(t.op, [item(m1), item(m2), item(r, { amount: 1 })])).json.error.code, 'refund_exceeds_payment', 'first failing item decides');
    assert.equal((await batch(t.op, [item(m1, { amount: 30 }), item(m2), item(r, { amount: 1 })])).json.error.code, 'linked_payment_immutable');
    assert.equal((await batch(t.op, [item(m1, { amount: 30 }), item(m2)])).status, 201);
  });

  test('recorded_at increases across batches and single corrections; no partial known_at view (S4-040, S4-043)', async () => {
    const t = await seed(api, empty());
    const p = await pay(t.ada, 'bob', 100);
    const q = await pay(t.ada, 'cy', 100);
    const b1 = (await batch(t.op, [item(p, { amount: 90 }), item(q, { amount: 90 })])).json;
    const single = (await api.post(`/payments/${p.payment_id}/corrections`, { expected_revision: 2, amount: 80, effective_at: p.created_at, reason: 'r' }, { token: t.ada, key: key() })).json;
    const other = await pay(t.ada, 'bob', 5);
    const b2 = (await batch(t.op, [item(other)])).json;
    assert.ok(Date.parse(single.recorded_at) > Date.parse(b1.recorded_at));
    assert.ok(Date.parse(b2.recorded_at) > Date.parse(single.recorded_at));
    const before_ = new Date(Date.parse(b1.recorded_at) - 1).toISOString().replace('Z', '+00:00');
    const view = (await api.get(`/statement?known_at=${enc(before_)}`, { token: t.ada })).json.entries;
    assert.deepEqual(view.filter((e) => e.payment.payment_id !== other.payment_id).map((e) => e.revision), [1, 1], 'every member pre-batch');
  });

  test('a capture can be refunded while its authorization stays open (D4-09)', async () => {
    const t = await seed(api, empty());
    const a = (await api.post('/authorizations', { to_handle: 'bob', amount: 500 }, { token: t.ada, key: key() })).json;
    const cap = (await api.post(`/authorizations/${a.authorization_id}/capture`, { amount: 200, final: false }, { token: t.bob, key: key() })).json;
    assert.equal((await refund(t.bob, cap.payment_id, 200)).status, 201);
    const au = (await api.get('/authorizations', { token: t.ada })).json.authorizations[0];
    assert.deepEqual([au.status, au.remaining_amount, (await me(t.ada)).held], ['open', 300, 300]);
  });
});
