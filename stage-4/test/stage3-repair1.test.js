'use strict';

// Regression tests for stage-3 repair 1:
// F3-01  a closed hold seen through an earlier known_at still expires at its deadline;
// F3-A01 statement snapshots are constant-size and page an unchanged result.

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
const iso = (ms) => new Date(ms).toISOString().replace('Z', '+00:00');
const nowIso = () => iso(Date.now());
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const view = async (t, asOf, knownAt) => {
  const qs = `?as_of=${enc(asOf)}${knownAt ? `&known_at=${enc(knownAt)}` : ''}`;
  const m = (await api.get(`/me${qs}`, { token: t })).json;
  return [m.held, m.available];
};

async function holdThen(close) {
  const t = await seed(api, fixture({ payments: [], requests: [] }));
  const a = (await api.post('/authorizations', { to_handle: 'bob', amount: 1000 }, { token: t.ada, key: key() })).json;
  await pause(15);
  const K = nowIso();
  await pause(15);
  const closed = await close(t, a.authorization_id);
  return { t, a, K, closed };
}

describe('F3-01: expiry deadline in views that do not yet know the close', () => {
  const cases = {
    void: (t, id) => api.call('POST', `/authorizations/${id}/void`, { token: t.ada }),
    'final capture': (t, id) => api.post(`/authorizations/${id}/capture`, { amount: 300 }, { token: t.bob, key: key() }),
  };
  for (const [name, close] of Object.entries(cases)) {
    test(`hold closed by a ${name}`, async () => {
      const { t, a, K } = await holdThen(close);
      const e = Date.parse(a.expires_at);
      assert.deepEqual(await view(t.ada, iso(e - 1), K), [1000, 9000], 'A: close unknown, before the deadline');
      assert.deepEqual(await view(t.ada, iso(e + 1), K), [0, 10000], 'B: close unknown, after the deadline');
      assert.deepEqual(await view(t.ada, '2099-01-01T00:00:00+00:00', K), [0, 10000], 'C: far future');
      const [held] = await view(t.ada, '2099-01-01T00:00:00+00:00');
      assert.equal(held, 0, 'D: everything known');
    });
  }

  test('a partial non-final capture known at K keeps the rest until the deadline', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    const a = (await api.post('/authorizations', { to_handle: 'bob', amount: 1000 }, { token: t.ada, key: key() })).json;
    await pause(15);
    await api.post(`/authorizations/${a.authorization_id}/capture`, { amount: 400, final: false }, { token: t.bob, key: key() });
    await pause(15);
    const K = nowIso();
    await pause(15);
    await api.call('POST', `/authorizations/${a.authorization_id}/void`, { token: t.ada });
    const e = Date.parse(a.expires_at);
    assert.deepEqual(await view(t.ada, iso(e - 1), K), [600, 9000], 'capture known, void unknown');
    assert.deepEqual(await view(t.ada, iso(e + 1), K), [0, 9600], 'remainder expires at the deadline');
  });

  test('a close known at K releases before the deadline', async () => {
    const { t, a, closed } = await holdThen(cases.void);
    const closedAt = closed.json.closed_at;
    assert.deepEqual(await view(t.ada, iso(Date.parse(closedAt) - 1), closedAt), [1000, 9000]);
    assert.deepEqual(await view(t.ada, closedAt, closedAt), [0, 10000]);
    assert.ok(Date.parse(closedAt) < Date.parse(a.expires_at));
  });

  test('historical_overdraft agrees with the historical hold view (D3-11)', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    const pay = (await api.post('/payments', { to_handle: 'cy', amount: 1000 }, { token: t.ada, key: key() })).json;
    await pause(15);
    const a = (await api.post('/authorizations', { to_handle: 'ada', amount: 800 }, { token: t.cy, key: key() })).json;
    await pause(15);
    await api.call('POST', `/authorizations/${a.authorization_id}/void`, { token: t.cy });
    // During the hold, cy's view is total 1000, held 800, available 200.
    assert.deepEqual(await view(t.cy, a.created_at), [800, 200]);
    const correct = (amount) => api.post(`/payments/${pay.payment_id}/corrections`,
      { expected_revision: 1, amount, effective_at: pay.created_at, reason: 'r' }, { token: t.ada, key: key() });
    assert.equal((await correct(799)).json.error.code, 'historical_overdraft', 'available would be -1 during the hold');
    const ok = await correct(800);
    assert.equal(ok.status, 201, 'available reaches exactly 0 during the hold');
    assert.deepEqual(await view(t.cy, a.created_at), [800, 0]);
  });
});

describe('F3-A01: snapshots are constant-size and frozen', () => {
  test('a snapshot pages the same result after later writes of every kind', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    const p1 = (await api.post('/payments', { to_handle: 'bob', amount: 100 }, { token: t.ada, key: key() })).json;
    const auth = (await api.post('/authorizations', { to_handle: 'ada', amount: 200 }, { token: t.bob, key: key() })).json;
    const first = await api.get('/statement?limit=10', { token: t.ada });
    const token = first.json.snapshot;
    const expected = { ...first.json };

    // Same-millisecond and later writes: payments, a backdated correction, a capture, a void, an expiry.
    await api.post('/payments', { to_handle: 'bob', amount: 7 }, { token: t.ada, key: key() });
    await api.post(`/payments/${p1.payment_id}/corrections`,
      { expected_revision: 1, amount: 50, effective_at: '2020-01-01T00:00:00+00:00', reason: 'backdate' }, { token: t.ada, key: key() });
    await api.post(`/authorizations/${auth.authorization_id}/capture`, { amount: 20, final: false }, { token: t.ada, key: key() });
    const other = (await api.post('/authorizations', { to_handle: 'ada', amount: 5 }, { token: t.bob, key: key() })).json;
    await api.call('POST', `/authorizations/${other.authorization_id}/void`, { token: t.bob });
    await api.call('POST', `/authorizations/${auth.authorization_id}/void`, { token: t.bob });

    const again = await api.get(`/statement?snapshot=${enc(token)}&limit=10`, { token: t.ada });
    assert.equal(again.text, first.text, 'byte-identical page');
    const live = (await api.get('/statement', { token: t.ada })).json;
    assert.notDeepEqual(live.entries.map((e) => e.payment.amount), expected.entries.map((e) => e.payment.amount), 'the live view did change');
    const p2 = await api.get(`/statement?snapshot=${enc(token)}&limit=1&offset=1`, { token: t.ada });
    assert.deepEqual(p2.json.entries, expected.entries.slice(1, 2));
    assert.equal(p2.json.has_more, false);
  });

  test('a snapshot survives export and import', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    await api.post('/payments', { to_handle: 'bob', amount: 3 }, { token: t.ada, key: key() });
    const first = await api.get('/statement', { token: t.ada });
    const ex = await api.get('/_test/export');
    await api.post('/payments', { to_handle: 'bob', amount: 4 }, { token: t.ada, key: key() });
    assert.equal((await api.post('/_test/import', ex.text)).status, 204);
    await api.post('/payments', { to_handle: 'bob', amount: 5 }, { token: t.ada, key: key() });
    const again = await api.get(`/statement?snapshot=${enc(first.json.snapshot)}`, { token: t.ada });
    assert.equal(again.text, first.text);
  });

  test('the stored snapshot holds no entries', async () => {
    const t = await seed(api, fixture({ payments: [], requests: [] }));
    for (let i = 0; i < 30; i += 1) await api.post('/payments', { to_handle: 'bob', amount: 1, note: 'x'.repeat(200) }, { token: t.ada, key: key() });
    await api.get('/statement', { token: t.ada });
    const snaps = (await api.get('/_test/export')).json.state.snapshots;
    assert.equal(snaps.length, 1);
    assert.ok(JSON.stringify(snaps[0]).length < 400, `snapshot record is ${JSON.stringify(snaps[0]).length} bytes`);
  });
});
