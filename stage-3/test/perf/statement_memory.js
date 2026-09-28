'use strict';

// Memory probe for statement snapshots (F3-A01): seeds 500 payments, then makes
// READS statement reads with 20 in flight against a running service and fails
// on any non-200 response or connection error. Run it against a container
// started with --cpus 2 --memory 2g and watch the container's memory:
//
//   node test/perf/statement_memory.js http://127.0.0.1:8080 [reads]
//
// It resets the service state.

const base = process.argv[2] || 'http://127.0.0.1:8080';
const READS = Number(process.argv[3] || 20000);
const IN_FLIGHT = 20;

async function call(method, path, body, headers = {}) {
  const res = await fetch(base + path, {
    method,
    headers: { 'content-type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, json: text ? JSON.parse(text) : null };
}

(async () => {
  await call('POST', '/_test/reset', {
    currency: 'EUR',
    minor_units: 2,
    users: [
      { id: 'u_a', email: 'a@x.io', password: 'correct horse', display_name: 'A', handle: 'a', balance: 100000000 },
      { id: 'u_b', email: 'b@x.io', password: 'correct horse', display_name: 'B', handle: 'b', balance: 0 },
    ],
  });
  const { token } = (await call('POST', '/auth/login', { email: 'a@x.io', password: 'correct horse' })).json;
  const auth = { authorization: `Bearer ${token}` };
  for (let i = 0; i < 500; i += 1) {
    await call('POST', '/payments', { to_handle: 'b', amount: 1, note: `payment ${i}` }, { ...auth, 'idempotency-key': `seed-${i}` });
  }
  const started = Date.now();
  let done = 0;
  while (done < READS) {
    const batch = Math.min(IN_FLIGHT, READS - done);
    const results = await Promise.all(Array.from({ length: batch }, () => call('GET', '/statement?limit=1', undefined, auth)));
    for (const r of results) {
      if (r.status !== 200) throw new Error(`statement read ${done} returned ${r.status}`);
    }
    done += batch;
    if (done % 5000 === 0) console.log(`${done} reads`);
  }
  const health = await call('GET', '/health');
  console.log(`PASS ${done} statement reads in ${((Date.now() - started) / 1000).toFixed(1)} s; health ${health.status}`);
})().catch((err) => {
  console.error(`FAIL ${err.message}`);
  process.exit(1);
});
