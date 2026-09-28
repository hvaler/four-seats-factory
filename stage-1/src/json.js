'use strict';

// Exact JSON handling. Numbers are kept as their source text (JNum) so that
// integral forms such as 1000.0 and 1e3 are recognised exactly and no value is
// ever rounded through a binary float.

const MAX_EXP = 1000;

class JNum {
  constructor(raw) {
    this.raw = raw;
    const m = /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(raw);
    if (!m) throw new Error(`not a JSON number: ${raw}`);
    const frac = m[3] || '';
    let digits = (m[2] + frac).replace(/^0+/, '');
    let exp = (m[4] ? Number(m[4]) : 0) - frac.length;
    if (digits === '') {
      digits = '0';
      exp = 0;
    } else {
      const trimmed = digits.replace(/0+$/, '');
      exp += digits.length - trimmed.length;
      digits = trimmed;
    }
    this.neg = m[1] === '-' && digits !== '0';
    this.digits = digits;
    this.exp = exp;
  }

  isIntegral() {
    return this.exp >= 0;
  }

  // The exact integer value, or null when the value is not integral or too
  // large to be meaningful here.
  toBigInt() {
    if (!this.isIntegral() || this.digits.length + this.exp > MAX_EXP) return null;
    const v = BigInt(this.digits) * 10n ** BigInt(this.exp);
    return this.neg ? -v : v;
  }

  canon() {
    return `${this.neg ? '-' : ''}${this.digits}e${this.exp}`;
  }
}

class JsonSyntaxError extends Error {}

function parse(text) {
  try {
    return JSON.parse(text, (key, value, context) =>
      typeof value === 'number' ? new JNum(context.source) : value);
  } catch (err) {
    throw new JsonSyntaxError(err.message);
  }
}

function isObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v) && !(v instanceof JNum);
}

// A canonical text for a parsed JSON value: equal JSON values (key order,
// whitespace and numeric spelling aside) give equal texts.
function canonical(v) {
  if (v === null) return 'n';
  if (v === true) return 't';
  if (v === false) return 'f';
  if (typeof v === 'string') return JSON.stringify(v);
  if (v instanceof JNum) return `#${v.canon()}`;
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`;
  const keys = Object.keys(v).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`;
}

// Serialise a response value. BigInt is written as an exact JSON integer.
function stringify(v) {
  if (v === null || v === undefined) return 'null';
  switch (typeof v) {
    case 'bigint': return v.toString();
    case 'string': return JSON.stringify(v);
    case 'number': return Number.isFinite(v) ? String(v) : 'null';
    case 'boolean': return v ? 'true' : 'false';
    default: break;
  }
  if (v instanceof JNum) return v.raw;
  if (Array.isArray(v)) return `[${v.map(stringify).join(',')}]`;
  const parts = [];
  for (const k of Object.keys(v)) {
    if (v[k] !== undefined) parts.push(`${JSON.stringify(k)}:${stringify(v[k])}`);
  }
  return `{${parts.join(',')}}`;
}

module.exports = { JNum, JsonSyntaxError, parse, isObject, canonical, stringify };
