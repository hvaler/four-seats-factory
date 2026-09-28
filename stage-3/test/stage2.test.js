'use strict';

// Stage-2 implementation tests: holds, captures, voids, expiry, negotiation,
// the stage-1 upgrade path and the UI shell. Register IDs are noted per test.

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

const soon = (ms) => new Date(Date.now() + ms).toISOString().replace('Z', '+00:00');
const me = async (t) => (await api.get('/me', { token: t })).json;
const authorize = (t, body, k = key()) => api.post('/authorizations', body, { token: t, key: k });
const capture = (t, id, body, k = key()) => api.post(`/authorizations/${id}/capture`, body, { token: t, key: k });

describe('holds and /me (S2-050, S2-052, S2-059)', () => {
  test('an authorization holds money without moving it', async () => {
    const t = await seed(api);
    const a = await authorize(t.ada, { to_handle: 'bob', amount: 2000, note: 'deposit', visibility: 'private' });
    assert.equal(a.status, 201);
    assert.equal(a.json.status, 'open');
    assert.equal(a.json.captured_amount, 0);
    assert.equal(a.json.remaining_amount, 2000);
    assert.deepEqual(a.json.payment_ids, []);
    assert.equal(a.json.payment_id, null);
    assert.equal(Date.parse(a.json.expires_at) - Date.parse(a.json.created_at), 600000);
    const m = await me(t.ada);
    assert.deepEqual([m.balance, m.total, m.available, m.held], [10000, 10000, 8000, 2000]);
    assert.equal((await api.get('/activity', { token: t.ada })).json.payments.length, 1, 'not a feed item');
  });

  test('held money cannot fund payments, holds, request payments or settlements (S1-092/112/196 superseded)', async () => {
    const t = await seed(api);
    await authorize(t.bob, { to_handle: 'ada', amount: 2000 });
    assert.equal((await api.post('/payments', { to_handle: 'cy', amount: 501 }, { token: t.bob, key: key() })).json.error.code, 'insufficient_funds');
    assert.equal((await authorize(t.bob, { to_handle: 'cy', amount: 501 })).json.error.code, 'insufficient_funds');
    const s = await api.post('/settlements', { transfers: [{ from_handle: 'bob', to_handle: 'cy', amount: 501 }] }, { token: t.op, key: key() });
    assert.equal(s.json.error.code, 'insufficient_funds');
    assert.equal((await api.post('/payments', { to_handle: 'cy', amount: 500 }, { token: t.bob, key: key() })).status, 201);
    const rq = await api.post('/requests', { payer_handle: 'bob', amount: 1, note: '' }, { token: t.ada, key: key() });
    assert.equal((await api.post(`/requests/${rq.json.request_id}/pay`, {}, { token: t.bob, key: key() })).json.error.code, 'insufficient_funds');
  });

  test('authorization validation (S2-059)', async () => {
    const t = await seed(api);
    const code = async (b) => (await authorize(t.ada, b)).json.error.code;
    assert.equal(await code({ to_handle: 'ada', amount: 1 }), 'self_payment');
    assert.equal(await code({ to_handle: 'ghost', amount: 1 }), 'not_found');
    assert.equal(await code({ to_handle: 'bob', amount: 0 }), 'validation_failed');
    assert.equal(await code({ to_handle: 'bob', amount: 1, visibility: 'x' }), 'validation_failed');
    assert.equal(await code({ to_handle: 'bob', amount: 10001 }), 'insufficient_funds');
    assert.equal((await api.post('/authorizations', { to_handle: 'bob', amount: 1 }, { token: t.ada })).json.error.code, 'missing_idempotency_key');
  });
});

describe('captures (S2-061..S2-067, S2-072, S2-073)', () => {
  test('default final capture releases the remainder at once', async () => {
    const t = await seed(api);
    const a = (await authorize(t.ada, { to_handle: 'bob', amount: 2000, note: 'n', visibility: 'private' })).json;
    const c = await capture(t.bob, a.authorization_id, { amount: 1500 });
    assert.equal(c.status, 201);
    assert.equal(c.json.authorization_id, a.authorization_id);
    assert.equal(c.json.request_id, null);
    assert.equal(c.json.amount, 1500);
    assert.equal(c.json.note, 'n');
    assert.equal(c.json.visibility, 'private');
    assert.equal(c.json.from_handle, 'ada');
    const m = await me(t.ada);
    assert.deepEqual([m.total, m.available, m.held], [8500, 8500, 0]);
    const list = (await api.get('/authorizations', { token: t.ada })).json;
    const got = list.authorizations[0];
    assert.deepEqual([got.status, got.captured_amount, got.remaining_amount, got.payment_id], ['captured', 1500, 0, c.json.payment_id]);
    assert.equal((await capture(t.bob, a.authorization_id, {})).json.error.code, 'authorization_not_open');
    assert.ok((await api.get('/activity', { token: t.bob })).json.payments.some((p) => p.payment_id === c.json.payment_id));
  });

  test('non-final captures accumulate up to the remainder', async () => {
    const t = await seed(api);
    const a = (await authorize(t.ada, { to_handle: 'bob', amount: 2000 })).json;
    const id = a.authorization_id;
    assert.equal((await capture(t.bob, id, { amount: 700, final: false })).status, 201);
    assert.equal((await capture(t.bob, id, { amount: 1301, final: false })).json.error.code, 'capture_exceeds_authorization');
    const c2 = await capture(t.bob, id, { amount: 700, final: false });
    let got = (await api.get('/authorizations', { token: t.bob })).json.authorizations[0];
    assert.deepEqual([got.status, got.captured_amount, got.remaining_amount], ['open', 1400, 600]);
    assert.equal((await me(t.ada)).held, 600);
    const c3 = await capture(t.bob, id, { final: false });
    assert.equal(c3.json.amount, 600, 'omitted amount = remainder');
    got = (await api.get('/authorizations', { token: t.bob })).json.authorizations[0];
    assert.deepEqual([got.status, got.captured_amount, got.remaining_amount], ['captured', 2000, 0]);
    assert.equal(got.payment_ids.length, 3);
    assert.equal(got.payment_ids[1], c2.json.payment_id);
    assert.equal(got.payment_id, c3.json.payment_id);
  });

  test('a capture spends its own reservation even when available is 0 (S2-072)', async () => {
    const t = await seed(api);
    const a = (await authorize(t.bob, { to_handle: 'cy', amount: 2500 })).json;
    assert.equal((await me(t.bob)).available, 0);
    assert.equal((await capture(t.cy, a.authorization_id, {})).status, 201);
    const m = await me(t.bob);
    assert.deepEqual([m.total, m.available, m.held], [0, 0, 0]);
  });

  test('precedence, permissions and replays (D2-02, S2-073)', async () => {
    const t = await seed(api);
    const a = (await authorize(t.ada, { to_handle: 'bob', amount: 100 })).json;
    const id = a.authorization_id;
    assert.equal((await capture(t.bob, id, { final: 'no' })).status, 400);
    assert.equal((await capture(t.bob, id, { amount: 0 })).json.error.code, 'validation_failed');
    assert.equal((await capture(t.bob, 'a_nope', {})).status, 404);
    assert.equal((await capture(t.ada, id, {})).status, 403);
    assert.equal((await capture(t.cy, id, {})).status, 403);
    const k = key();
    const first = await capture(t.bob, id, { amount: 40 }, k);
    assert.equal(first.status, 201);
    const again = await capture(t.bob, id, { amount: 40 }, k);
    assert.equal(again.status, 200);
    assert.equal(again.text, first.text);
    assert.equal((await capture(t.bob, id, { amount: 999 }, k)).json.error.code, 'idempotency_key_reuse');
    assert.equal((await capture(t.bob, id, {}, k)).status, 409);
    assert.equal((await me(t.bob)).total, 2540, 'moved once');
    const ak = key();
    const created = await authorize(t.ada, { to_handle: 'bob', amount: 5 }, ak);
    await api.call('POST', `/authorizations/${created.json.authorization_id}/void`, { token: t.ada });
    const replay = await authorize(t.ada, { to_handle: 'bob', amount: 5 }, ak);
    assert.equal(replay.status, 200);
    assert.equal(replay.json.status, 'open', 'original body');
  });

  test('concurrent captures never exceed the authorization (S2-051)', async () => {
    const t = await seed(api);
    const a = (await authorize(t.ada, { to_handle: 'bob', amount: 1000 })).json;
    const res = await Promise.all(Array.from({ length: 20 }, () => capture(t.bob, a.authorization_id, { amount: 100, final: false })));
    assert.equal(res.filter((r) => r.status === 201).length, 10);
    assert.ok(res.every((r) => r.status < 500));
    const m = await me(t.ada);
    assert.deepEqual([m.total, m.held], [9000, 0]);
  });
});

describe('void and expiry (S2-057, S2-065, S2-068, D2-08)', () => {
  test('void releases; repeat is 200; captured is 409; only the payer', async () => {
    const t = await seed(api);
    const a = (await authorize(t.ada, { to_handle: 'bob', amount: 300 })).json;
    const id = a.authorization_id;
    await capture(t.bob, id, { amount: 100, final: false });
    assert.equal((await api.call('POST', `/authorizations/${id}/void`, { token: t.bob })).status, 403);
    assert.equal((await api.call('POST', `/authorizations/${id}/void`, { token: t.cy })).status, 403);
    const v = await api.call('POST', `/authorizations/${id}/void`, { token: t.ada });
    assert.deepEqual([v.status, v.json.status, v.json.captured_amount, v.json.remaining_amount, v.json.payment_ids.length], [200, 'voided', 100, 0, 1]);
    assert.equal((await api.call('POST', `/authorizations/${id}/void`, { token: t.ada })).status, 200);
    assert.equal((await capture(t.bob, id, {})).json.error.code, 'authorization_not_open');
    assert.deepEqual([(await me(t.ada)).held, (await me(t.ada)).total], [0, 9900]);
    const b = (await authorize(t.ada, { to_handle: 'bob', amount: 5 })).json;
    await capture(t.bob, b.authorization_id, {});
    assert.equal((await api.call('POST', `/authorizations/${b.authorization_id}/void`, { token: t.ada })).json.error.code, 'authorization_not_open');
  });

  test('holds expire by the clock with no request at the deadline', async () => {
    const fx = fixture({ authorization_ttl_seconds: 1 });
    const t = await seed(api, fx);
    const a = (await authorize(t.ada, { to_handle: 'bob', amount: 400 })).json;
    assert.equal(Date.parse(a.expires_at) - Date.parse(a.created_at), 1000);
    await new Promise((r) => setTimeout(r, 1200));
    assert.equal((await me(t.ada)).available, 10000);
    const list = (await api.get('/authorizations?status=expired', { token: t.ada })).json.authorizations;
    assert.equal(list[0].status, 'expired');
    assert.equal((await api.get('/authorizations?status=open', { token: t.ada })).json.authorizations.length, 0);
    assert.equal((await capture(t.bob, a.authorization_id, {})).json.error.code, 'authorization_expired');
    assert.equal((await api.call('POST', `/authorizations/${a.authorization_id}/void`, { token: t.ada })).json.error.code, 'authorization_not_open');
  });

  test('seeded holds: available derived, expired ones hold nothing, excess is 422 (S2-054..S2-056)', async () => {
    const auths = [
      { id: 'a_1', from_user_id: 'u_bob', to_user_id: 'u_ada', amount: 2000, status: 'open', expires_at: soon(3600e3) },
      { id: 'a_2', from_user_id: 'u_bob', to_user_id: 'u_ada', amount: 500, status: 'open', expires_at: soon(-3600e3) },
      { id: 'a_3', from_user_id: 'u_bob', to_user_id: 'u_ada', amount: 500, status: 'open', expires_at: soon(3600e3) },
    ];
    const t = await seed(api, fixture({ authorizations: auths }));
    const m = await me(t.bob);
    assert.deepEqual([m.total, m.held, m.available], [2500, 2500, 0], 'equal to balance is allowed');
    const exp = (await api.get('/authorizations?status=expired', { token: t.bob })).json.authorizations;
    assert.deepEqual(exp.map((a) => a.authorization_id), ['a_2']);
    const over = fixture({ authorizations: [...auths, { id: 'a_4', from_user_id: 'u_bob', to_user_id: 'u_ada', amount: 1, status: 'open', expires_at: soon(3600e3) }] });
    assert.equal((await api.post('/_test/reset', over)).status, 422);
    for (const ttl of [0, -1, 1.5, '600', true, null]) {
      assert.equal((await api.post('/_test/reset', fixture({ authorization_ttl_seconds: ttl }))).status, 422, String(ttl));
    }
    assert.equal((await me(t.bob)).held, 2500, 'failed resets change nothing');
  });
});

describe('negotiation, listing and UI shell (S2-010, S2-011, S2-069)', () => {
  test('shared routes serve HTML only to browsers', async () => {
    const t = await seed(api);
    const html = await api.get('/requests', { token: t.ada, headers: { accept: 'text/html,application/xhtml+xml,*/*;q=0.8' } });
    assert.match(html.contentType, /^text\/html/);
    for (const accept of [undefined, '*/*', 'application/json', 'application/json, text/html;q=0.5']) {
      const r = await api.get('/requests', { token: t.ada, headers: accept ? { accept } : {} });
      assert.match(r.contentType, /^application\/json/, String(accept));
      assert.ok(Array.isArray(r.json.requests));
    }
    const auths = await api.get('/authorizations', { token: t.ada });
    assert.deepEqual(Object.keys(auths.json), ['authorizations', 'has_more']);
    for (const route of ['/', '/split', '/signup', '/login', '/authorizations']) {
      const r = await api.get(route, { headers: { accept: 'text/html' } });
      assert.equal(r.status, 200, route);
      assert.match(r.text, /<script src="\/static\/app.js">/);
    }
    for (const asset of ['/static/app.js', '/static/app.css', '/static/icon.svg']) {
      assert.equal((await api.get(asset)).status, 200, asset);
    }
    assert.equal((await api.get('/static/nope.js')).status, 404);
  });

  test('every payment carries authorization_id (S1-091 superseded)', async () => {
    const t = await seed(api);
    const p = await api.post('/payments', { to_handle: 'bob', amount: 1 }, { token: t.ada, key: key() });
    assert.equal(p.json.authorization_id, null);
    const feed = (await api.get('/activity', { token: t.ada })).json.payments;
    assert.ok(feed.every((x) => 'authorization_id' in x));
  });
});

describe('export and import (S2-040, S2-074, D2-13)', () => {
  test('a stage-1 style export imports with no holds and TTL 600', async () => {
    const t = await seed(api);
    const k = key();
    const paid = await api.post('/payments', { to_handle: 'bob', amount: 10 }, { token: t.ada, key: k });
    const ex = (await api.get('/_test/export')).json;
    const st = ex.state;
    delete st.schema;
    delete st.authorizations;
    delete st.authorization_ttl_seconds;
    st.payments.forEach((p) => delete p.authorization_id);
    assert.equal((await api.post('/_test/import', ex)).status, 204);
    const m = await me(t.ada);
    assert.deepEqual([m.total, m.available, m.held], [9990, 9990, 0]);
    const replay = await api.post('/payments', { to_handle: 'bob', amount: 10 }, { token: t.ada, key: k });
    assert.equal(replay.status, 200);
    assert.equal(replay.text, paid.text, 'original bytes');
    const a = await authorize(t.ada, { to_handle: 'bob', amount: 5 });
    assert.equal(Date.parse(a.json.expires_at) - Date.parse(a.json.created_at), 600000);
  });

  test('a hold exported open and imported after its deadline reads expired', async () => {
    const t = await seed(api, fixture({ authorization_ttl_seconds: 1 }));
    await authorize(t.ada, { to_handle: 'bob', amount: 400 });
    const ex = await api.get('/_test/export');
    await new Promise((r) => setTimeout(r, 1100));
    assert.equal((await api.post('/_test/import', ex.text)).status, 204);
    assert.equal((await me(t.ada)).held, 0);
    assert.equal((await api.get('/authorizations', { token: t.ada })).json.authorizations[0].status, 'expired');
  });
});
