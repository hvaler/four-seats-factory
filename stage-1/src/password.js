'use strict';

const crypto = require('node:crypto');

// scrypt (RFC 7914) with a per-password random salt. N=2^12, r=8, p=1 costs about
// 4 MiB and a few tens of milliseconds per hash. The cost is bounded by the
// stage limits: 50 concurrent logins must each finish within 5 s on 2 vCPU.
const PARAMS = { N: 4096, r: 8, p: 1, maxmem: 64 * 1024 * 1024 };
const KEYLEN = 32;

function derive(password, salt, params) {
  return new Promise((resolve, reject) => {
    crypto.scrypt(password, salt, KEYLEN, params, (err, key) => (err ? reject(err) : resolve(key)));
  });
}

async function hashPassword(password) {
  const salt = crypto.randomBytes(16);
  const key = await derive(password, salt, PARAMS);
  return `scrypt$${PARAMS.N}$${PARAMS.r}$${PARAMS.p}$${salt.toString('base64')}$${key.toString('base64')}`;
}

const HASH_RE = /^scrypt\$(\d+)\$(\d+)\$(\d+)\$([A-Za-z0-9+/=]+)\$([A-Za-z0-9+/=]+)$/;

function isValidHash(stored) {
  const m = typeof stored === 'string' && HASH_RE.exec(stored);
  if (!m) return false;
  const N = Number(m[1]);
  return N >= 2 && (N & (N - 1)) === 0 && N <= 1 << 20 && Number(m[2]) >= 1 && Number(m[2]) <= 32
    && Number(m[3]) >= 1 && Number(m[3]) <= 16;
}

async function verifyPassword(password, stored) {
  if (!isValidHash(stored)) return false;
  const [, N, r, p, salt, key] = HASH_RE.exec(stored);
  const expected = Buffer.from(key, 'base64');
  const actual = await derive(password, Buffer.from(salt, 'base64'),
    { N: Number(N), r: Number(r), p: Number(p), maxmem: PARAMS.maxmem });
  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}

// A hash of a random secret, used to spend the same time on an unknown email.
let dummy = null;
async function dummyHash() {
  if (!dummy) dummy = await hashPassword(crypto.randomBytes(16).toString('hex'));
  return dummy;
}

module.exports = { hashPassword, verifyPassword, isValidHash, dummyHash };
