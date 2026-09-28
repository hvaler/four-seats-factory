'use strict';

// Starts the service in-process on a random port and offers a tiny HTTP client.
// Set BASE_URL to run the same tests against an already running container.

const { createServer } = require('../src/server');

async function start() {
  if (process.env.BASE_URL) return { base: process.env.BASE_URL, close: async () => {} };
  const server = createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    base: `http://127.0.0.1:${server.address().port}`,
    close: () => new Promise((resolve) => {
      server.closeAllConnections();
      server.close(resolve);
    }),
  };
}

function client(base) {
  async function call(method, path, { body, token, key, headers = {} } = {}) {
    const h = { ...headers };
    if (body !== undefined) h['content-type'] = 'application/json';
    if (token) h.authorization = `Bearer ${token}`;
    if (key !== undefined) h['idempotency-key'] = key;
    const res = await fetch(base + path, {
      method,
      headers: h,
      body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
    });
    const text = await res.text();
    return {
      status: res.status,
      text,
      json: text && /json/.test(res.headers.get('content-type') || '') ? JSON.parse(text) : null,
      contentType: res.headers.get('content-type'),
    };
  }
  return {
    call,
    get: (path, opts) => call('GET', path, opts),
    post: (path, body, opts = {}) => call('POST', path, { ...opts, body }),
  };
}

const PASSWORD = 'correct horse';

function fixture(overrides = {}) {
  return {
    currency: 'EUR',
    minor_units: 2,
    users: [
      { id: 'u_ada', email: 'ada@example.com', password: PASSWORD, display_name: 'Ada', handle: 'ada', balance: 10000 },
      { id: 'u_bob', email: 'bob@example.com', password: PASSWORD, display_name: 'Bob', handle: 'bob', balance: 2500 },
      { id: 'u_cy', email: 'cy@example.com', password: PASSWORD, display_name: 'Cy', handle: 'cy', balance: 0 },
      { id: 'u_op', email: 'op@example.com', password: PASSWORD, display_name: 'Op', handle: 'op', balance: 0 },
    ],
    payments: [
      { id: 'p_1', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 500, note: 'coffee', visibility: 'public' },
    ],
    requests: [
      { id: 'rq_1', requester_id: 'u_bob', payer_id: 'u_ada', amount: 1200, note: 'taxi', status: 'pending' },
    ],
    settlement_operator_ids: ['u_op'],
    ...overrides,
  };
}

// Reset to a fixture and log everyone in. Returns { tokens: {handle: token} }.
async function seed(api, fx = fixture()) {
  const r = await api.post('/_test/reset', fx);
  if (r.status !== 204) throw new Error(`reset failed: ${r.status} ${r.text}`);
  const tokens = {};
  await Promise.all(fx.users.map(async (u) => {
    const login = await api.post('/auth/login', { email: u.email, password: u.password });
    tokens[u.handle] = login.json.token;
  }));
  return tokens;
}

let n = 0;
const key = () => `k-${process.pid}-${Date.now()}-${(n += 1)}`;

module.exports = { start, client, fixture, seed, key, PASSWORD };
