'use strict';

const http = require('node:http');
const { handle } = require('./app');

const MAX_BODY = 64 * 1024 * 1024;
const CONTENT_TYPE = 'application/json; charset=utf-8';
const decoder = new TextDecoder('utf-8', { fatal: true });

function send(res, result) {
  if (result.status === 204) {
    res.writeHead(204, { 'Content-Type': CONTENT_TYPE });
    res.end();
    return;
  }
  const payload = Buffer.from(result.text, 'utf8');
  res.writeHead(result.status, { 'Content-Type': CONTENT_TYPE, 'Content-Length': payload.length });
  res.end(payload);
}

function onRequest(req, res) {
  const chunks = [];
  let size = 0;
  req.on('data', (chunk) => {
    size += chunk.length;
    if (size <= MAX_BODY) chunks.push(chunk);
  });
  req.on('error', () => res.destroy());
  req.on('end', async () => {
    let bodyText = null;
    if (size <= MAX_BODY) {
      try {
        bodyText = decoder.decode(Buffer.concat(chunks));
      } catch {
        bodyText = null;
      }
    }
    const url = req.url || '/';
    const q = url.indexOf('?');
    const ctx = {
      method: req.method,
      path: q < 0 ? url : url.slice(0, q),
      query: new URLSearchParams(q < 0 ? '' : url.slice(q + 1)),
      headers: req.headers,
      bodyText,
    };
    let result;
    try {
      result = await handle(ctx);
    } catch (err) {
      console.error(err);
      result = { status: 500, text: '{"error":{"code":"internal_error","message":"internal error"}}' };
    }
    send(res, result);
  });
}

function createServer() {
  const server = http.createServer(onRequest);
  server.keepAliveTimeout = 65000;
  return server;
}

if (require.main === module) {
  const port = Number(process.env.PORT) || 8080;
  const server = createServer();
  server.listen(port, '0.0.0.0', () => console.log(`pocketful stage-1 listening on 0.0.0.0:${port}`));
  const stop = () => {
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 2000).unref();
  };
  process.on('SIGTERM', stop);
  process.on('SIGINT', stop);
}

module.exports = { createServer };
