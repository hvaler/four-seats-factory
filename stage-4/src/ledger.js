'use strict';

// Historical views (stage 3). Every instant is compared as a BigInt count of
// nanoseconds since the epoch, so query instants with any RFC 3339 fraction
// are compared exactly with stored times.
//
// A view is (as_of A, known_at K):
// - payments: for each payment select its latest revision recorded at or
//   before K; that revision's amount applies at its effective time (<= A).
// - holds: an authorization contributes events (creation +hold, capture
//   -amount, release of the remainder at final capture / void / expiry). An
//   event counts when its time <= A and it is known by K. Clock expiry is known
//   as soon as the creation is.

const NS_PER_MS = 1000000n;

const RFC3339 = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:([Zz])|([+-])(\d{2}):(\d{2}))$/;

function daysIn(y, m) {
  return [31, (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
}

// A strict RFC 3339 instant with an explicit offset, as BigInt nanoseconds, or
// null when the text is not one.
function parseInstant(text) {
  if (typeof text !== 'string') return null;
  const m = RFC3339.exec(text);
  if (!m) return null;
  const [y, mo, d, h, mi, se] = m.slice(1, 7).map(Number);
  if (mo < 1 || mo > 12 || d < 1 || d > daysIn(y, mo) || h > 23 || mi > 59 || se > 59) return null;
  let offsetMin = 0;
  if (!m[8]) {
    const oh = Number(m[10]);
    const om = Number(m[11]);
    if (oh > 23 || om > 59) return null;
    offsetMin = (m[9] === '-' ? -1 : 1) * (oh * 60 + om);
  }
  const date = new Date(Date.UTC(2000, mo - 1, d, h, mi, se));
  date.setUTCFullYear(y);
  const ms = date.getTime() - offsetMin * 60000;
  const frac = (m[7] || '').padEnd(9, '0').slice(0, 9);
  return BigInt(ms) * NS_PER_MS + BigInt(frac);
}

// Nanoseconds of a stored timestamp (always valid RFC 3339 by construction).
function ns(text) {
  const v = parseInstant(text);
  return v === null ? BigInt(Date.parse(text)) * NS_PER_MS : v;
}

// The end of the current millisecond: stored times have millisecond precision,
// so everything already recorded is at or before it.
const nowNs = (ms = Date.now()) => (BigInt(ms) + 1n) * NS_PER_MS - 1n;
const msToNs = (ms) => BigInt(ms) * NS_PER_MS;

// The latest revision of a payment recorded at or before K (null: none yet).
// A snapshot also passes the sequence watermark of its read, so anything
// recorded after that read is excluded even within the same millisecond.
function selectedRevision(p, K, seqMax = Infinity) {
  let chosen = null;
  for (const rev of p.revisions) {
    if (rev.recNs <= K && rev.seq <= seqMax) chosen = rev;
    else break;
  }
  return chosen;
}

const currentRevision = (p) => p.revisions[p.revisions.length - 1];

// Payment movements for a user under known_at K, with optional overrides
// (Map payment -> revision) used to evaluate proposed corrections.
function paymentEvents(user, K, overrides, seqMax = Infinity) {
  const out = [];
  for (const p of user.payments) {
    const rev = overrides && overrides.has(p) ? overrides.get(p) : selectedRevision(p, K, seqMax);
    if (!rev) continue;
    const sign = p.fromId === user.id ? -1n : 1n;
    out.push({ t: rev.effNs, delta: sign * rev.amount, payment: p, revision: rev });
  }
  return out;
}

// Hold events for the authorizations a user made.
function holdEvents(s, user) {
  const out = [];
  for (const a of user.authsOut) {
    if (!a.lifecycle || a.createHold <= 0n) continue;
    out.push({ t: a.createdNs, known: a.createdNs, delta: a.createHold });
    let left = a.createHold;
    for (const pid of a.paymentIds) {
      const p = s.paymentById.get(pid);
      if (!p) continue;
      const take = p.amount < left ? p.amount : left;
      left -= take;
      if (take > 0n) out.push({ t: p.createdNs, known: p.createdNs, delta: -take });
    }
    if (left <= 0n) continue;
    if (a.status === 'captured' || a.status === 'voided') {
      if (a.closedNs !== null) out.push({ t: a.closedNs, known: a.closedNs, delta: -left });
    } else {
      // open or expired: the remainder is released at the deadline, which is
      // known as soon as the creation is.
      out.push({ t: a.expiresNs, known: a.createdNs, delta: -left });
    }
  }
  return out;
}

function totalAt(user, A, K) {
  let total = user.opening;
  for (const e of paymentEvents(user, K)) if (e.t <= A) total += e.delta;
  return total;
}

// Held amount of one authorization in the view (A, K). The hold exists from
// its creation (if known by K); captures known by K reduce it; it is released
// at a close event known by K, or at expires_at, whichever comes first. The
// deadline is known as soon as the creation is (F3-01).
function authHeldAt(s, a, A, K) {
  if (!a.lifecycle || a.createHold <= 0n) return 0n;
  if (a.createdNs > A || a.createdNs > K) return 0n;
  if (a.expiresNs <= A) return 0n;
  if (a.closedNs !== null && (a.status === 'captured' || a.status === 'voided') && a.closedNs <= A && a.closedNs <= K) return 0n;
  let left = a.createHold;
  for (const pid of a.paymentIds) {
    const p = s.paymentById.get(pid);
    if (!p || p.createdNs > A || p.createdNs > K) continue;
    left -= p.amount < left ? p.amount : left;
  }
  return left;
}

function heldAt(s, user, A, K) {
  let held = 0n;
  for (const a of user.authsOut) held += authHeldAt(s, a, A, K);
  return held;
}

// Evaluates (total, available) at every boundary of a user's history, with
// all movements at one instant netted together. Returns a Map t -> {total, available}.
function boundaries(s, user, overrides) {
  const events = [
    ...paymentEvents(user, Infinity, overrides).map((e) => ({ t: e.t, dt: e.delta, dh: 0n })),
    ...holdEvents(s, user).map((e) => ({ t: e.t, dt: 0n, dh: e.delta })),
  ].sort((x, y) => (x.t < y.t ? -1 : x.t > y.t ? 1 : 0));
  const out = [];
  let total = user.opening;
  let held = 0n;
  for (let i = 0; i < events.length;) {
    const t = events[i].t;
    while (i < events.length && events[i].t === t) {
      total += events[i].dt;
      held += events[i].dh;
      i += 1;
    }
    out.push({ t, total, available: total - held });
  }
  return out;
}

// Value of a step function (from boundaries()) at instant t.
function valueAt(steps, opening, t) {
  let v = { total: opening, available: opening };
  for (const b of steps) {
    if (b.t <= t) v = b;
    else break;
  }
  return v;
}

// D3-21. True when replacing current revisions with the proposed ones (Map payment -> revision) would make a
// user's total or available negative at some boundary where it is not already
// at least that negative under the current history (so imprecise imported
// history can never block an unrelated correction).
function overdraws(s, user, overrides, nowNs) {
  const before = boundaries(s, user, null);
  const after = boundaries(s, user, overrides);
  for (const b of after) {
    if (b.t > nowNs) break; // D3-11: past boundaries only
    if (b.total >= 0n && b.available >= 0n) continue;
    const was = valueAt(before, user.opening, b.t);
    if ((b.total < 0n && b.total < was.total) || (b.available < 0n && b.available < was.available)) return true;
  }
  return false;
}

module.exports = {
  NS_PER_MS,
  parseInstant,
  ns,
  nowNs,
  msToNs,
  selectedRevision,
  currentRevision,
  paymentEvents,
  holdEvents,
  totalAt,
  heldAt,
  authHeldAt,
  overdraws,
};
