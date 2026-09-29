'use strict';

// Serves the browser UI: one HTML shell for every screen plus its static
// assets, all read from the image at start-up (no runtime fetches).

const fs = require('node:fs');
const path = require('node:path');
const { notFound } = require('./errors');

const DIR = path.join(__dirname, 'ui');
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
};

const files = new Map();
for (const name of fs.readdirSync(DIR)) {
  const type = TYPES[path.extname(name)];
  if (type) files.set(name, { type, text: fs.readFileSync(path.join(DIR, name), 'utf8') });
}

function page() {
  const f = files.get('index.html');
  return { status: 200, text: f.text, type: f.type, cache: 'no-store' };
}

function asset(name) {
  const f = name !== 'index.html' && files.get(name);
  if (!f) throw notFound('no such asset');
  return { status: 200, text: f.text, type: f.type, cache: 'no-cache' };
}

module.exports = { page, asset };
