/* Pocketful browser client (stage 2). Plain JavaScript, no dependencies.
 *
 * - Every screen is a full page load of the same shell; the path picks the view.
 * - The session token lives in localStorage so a signed-in browser survives a
 *   server-side export/import upgrade without signing in again.
 * - All user-supplied text is inserted with textContent, never as HTML.
 * - Reads are versioned: a response is applied only if no later read of the
 *   same data has been started since ("latest refresh wins").
 * - Each write form keeps its (Idempotency-Key, body) pair in memory while its
 *   fields are unchanged, so resubmitting or retrying an uncertain outcome
 *   replays the same request and money moves at most once.
 */
(function () {
  'use strict';

  var TOKEN_KEY = 'pocketful.token';
  var root = document.getElementById('app');
  var path = location.pathname.replace(/\/+$/, '') || '/';

  // ------------------------------------------------------------------ utils

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'text') el.textContent = v;
        else if (k === 'class') el.className = v;
        else if (k === 'testid') el.setAttribute('data-testid', v);
        else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? '' : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i += 1) append(el, arguments[i]);
    return el;
  }

  function append(el, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(el, c); }); return; }
    el.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function newKey() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16);
    crypto.getRandomValues(b);
    return Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
  }

  var session = {
    token: null,
    get: function () { try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; } },
    set: function (t) { try { localStorage.setItem(TOKEN_KEY, t); } catch (e) { /* private mode */ } },
    clear: function () { try { localStorage.removeItem(TOKEN_KEY); } catch (e) { /* ignore */ } },
  };
  session.token = session.get();

  // Money: amounts are integer minor units. Formatting and parsing are exact.
  var money = { currency: '', mu: 2 };

  function fmt(minor) {
    var s = BigInt(minor).toString();
    var neg = s.charAt(0) === '-';
    if (neg) s = s.slice(1);
    if (money.mu > 0) {
      while (s.length <= money.mu) s = '0' + s;
      s = s.slice(0, s.length - money.mu) + '.' + s.slice(s.length - money.mu);
    }
    return (neg ? '-' : '') + s + ' ' + money.currency;
  }

  // The decimal a person would type for an amount, without the currency.
  function decimalOf(minor) {
    var t = fmt(minor);
    return t.slice(0, t.lastIndexOf(' '));
  }

  // "15", "15.5", "15.00" -> minor units (BigInt), or null when not a valid
  // decimal with at most minor_units places. Nothing is ever rounded.
  function parseAmount(text) {
    var t = String(text).trim();
    var re = money.mu === 0 ? /^\d+$/ : new RegExp('^\\d+(\\.\\d{1,' + money.mu + '})?$');
    if (!re.test(t)) return null;
    var parts = t.split('.');
    var frac = (parts[1] || '');
    while (frac.length < money.mu) frac += '0';
    return BigInt(parts[0] + frac);
  }

  var dateFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  function when(ts) {
    var d = new Date(ts);
    return isNaN(d.getTime()) ? '' : dateFmt.format(d);
  }

  // ------------------------------------------------------------------ API

  // Result kinds: ok | error (a definite refusal) | uncertain (no answer:
  // network failure, lost response or a server error).
  function api(method, url, opts) {
    opts = opts || {};
    var headers = { Accept: 'application/json' };
    if (session.token) headers.Authorization = 'Bearer ' + session.token;
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    if (opts.key) headers['Idempotency-Key'] = opts.key;
    return fetch(url, { method: method, headers: headers, body: opts.body, cache: 'no-store' })
      .then(function (res) {
        return res.text().then(function (text) {
          var data = null;
          try { data = text ? JSON.parse(text) : null; } catch (e) { data = undefined; }
          if (res.status >= 500 || data === undefined) return { kind: 'uncertain', status: res.status };
          if (!res.ok) {
            var err = (data && data.error) || {};
            return { kind: 'error', status: res.status, code: err.code, message: err.message };
          }
          return { kind: 'ok', status: res.status, data: data };
        });
      }, function () { return { kind: 'uncertain', status: 0 }; });
  }

  // JSON body text with exact integer amounts.
  function body(fields) {
    var parts = [];
    Object.keys(fields).forEach(function (k) {
      var v = fields[k];
      if (v === undefined) return;
      parts.push(JSON.stringify(k) + ':' + (typeof v === 'bigint' ? v.toString() : JSON.stringify(v)));
    });
    return '{' + parts.join(',') + '}';
  }

  var MESSAGES = {
    insufficient_funds: 'Not enough available funds for this amount.',
    self_payment: 'You can’t send money to yourself.',
    self_request: 'You can’t request money from yourself.',
    not_found: 'We couldn’t find anyone with that handle.',
    request_not_pending: 'This request is no longer pending. The list has been refreshed.',
    authorization_not_open: 'This hold is no longer open. The list has been refreshed.',
    authorization_expired: 'This hold has expired. The list has been refreshed.',
    capture_exceeds_authorization: 'That is more than the amount still held.',
    forbidden: 'You are not allowed to do that.',
    email_taken: 'That email is already registered. Try logging in instead.',
    handle_taken: 'The handle made from that email is already taken. Try another email.',
    unauthenticated: 'Wrong email or password.',
  };
  function explain(res, fallback) {
    if (res.kind === 'uncertain') return 'We couldn’t reach Pocketful. Please try again.';
    if (res.code === 'validation_failed') return res.message ? 'Please check the form: ' + res.message + '.' : fallback;
    return MESSAGES[res.code] || res.message || fallback;
  }

  // ------------------------------------------------------------------ shared views

  var me = null;
  var reads = {};           // latest read sequence per resource
  function beginRead(name) { reads[name] = (reads[name] || 0) + 1; return reads[name]; }
  function isLatest(name, seq) { return reads[name] === seq; }

  function notice(testid, kind, text) {
    return h('div', { class: 'notice notice-' + kind, testid: testid, role: kind === 'ok' ? 'status' : 'alert', text: text });
  }

  // A slot that holds at most one feedback element.
  function slot() {
    var el = h('div', { class: 'slot' });
    return {
      el: el,
      show: function (testid, kind, text) { clear(el); el.appendChild(notice(testid, kind, text)); },
      clear: function () { clear(el); },
    };
  }

  function field(label, input, hint) {
    var id = input.id || ('f-' + Math.random().toString(36).slice(2));
    input.id = id;
    return h('div', { class: 'field' }, h('label', { for: id, text: label }), input, hint ? h('span', { class: 'hint', text: hint }) : null);
  }

  function amountHint() {
    return money.mu === 0 ? 'Whole ' + money.currency + ', e.g. 1500' : 'In ' + money.currency + ', e.g. 15.' + '0'.repeat(money.mu);
  }

  function visibilitySelect(testid) {
    return h('select', { testid: testid },
      h('option', { value: 'public', text: 'Public — visible in everyone’s feed' }),
      h('option', { value: 'private', text: 'Private — only you and them' }));
  }

  // Wallet summary: available is the headline number.
  var wallet = { el: null, onRefresh: null };
  function walletCard() {
    wallet.el = h('section', { class: 'card wallet', 'aria-label': 'Wallet' }, h('p', { class: 'loading', text: 'Loading balance…' }));
    return wallet.el;
  }

  function renderWallet() {
    if (!wallet.el || !me) return;
    var total = me.total !== undefined ? me.total : me.balance;
    var held = me.held !== undefined ? me.held : 0;
    var available = me.available !== undefined ? me.available : total - held;
    clear(wallet.el);
    append(wallet.el, [
      h('div', { class: 'wallet-main' },
        h('div', { class: 'label', text: 'Available to spend' }),
        h('div', { class: 'wallet-available', testid: 'wallet-available', 'data-amount': String(available), text: fmt(available) })),
      h('div', { class: 'wallet-secondary' },
        h('div', null, h('div', { class: 'label', text: 'Total balance' }),
          h('div', { class: 'amt', testid: 'wallet-balance', 'data-amount': String(me.balance), text: fmt(me.balance) })),
        Number(held) !== 0 ? h('div', { class: 'wallet-held' }, h('div', { class: 'label', text: 'Held for payments' }),
          h('div', { class: 'amt', testid: 'wallet-held', 'data-amount': String(held), text: fmt(held) })) : null),
      h('button', { class: 'btn btn-ghost btn-sm', type: 'button', testid: 'wallet-refresh', onclick: function () { if (wallet.onRefresh) wallet.onRefresh(); } }, 'Refresh'),
    ]);
  }

  function loadMe() {
    var seq = beginRead('me');
    return api('GET', '/me').then(function (res) {
      if (!isLatest('me', seq)) return res;
      if (res.kind === 'ok') {
        me = res.data;
        money.currency = me.currency;
        money.mu = me.minor_units;
        renderWallet();
        renderWho();
      } else if (res.kind === 'error' && res.status === 401) {
        session.clear();
        session.token = null;
        location.replace('/login');
      }
      return res;
    });
  }

  // A write form's retry identity: the same body reuses the same key.
  function identity() {
    var current = null;
    return {
      keyFor: function (text) {
        if (!current || current.body !== text) current = { key: newKey(), body: text };
        return current.key;
      },
    };
  }

  function busy(button, on) {
    button.disabled = on;
    button.setAttribute('aria-busy', on ? 'true' : 'false');
  }

  // ------------------------------------------------------------------ chrome

  var whoEl = h('div', { class: 'who' });
  function renderWho() {
    clear(whoEl);
    if (!me) return;
    append(whoEl, [
      h('div', { class: 'who-text', testid: 'current-user' },
        h('span', { class: 'who-name', text: me.display_name }),
        h('span', { class: 'who-handle' }, '@', h('span', { testid: 'current-handle', text: me.handle }))),
      h('button', { class: 'btn btn-ghost btn-sm', type: 'button', testid: 'logout-button', onclick: logout }, 'Log out'),
    ]);
  }

  function logout() {
    session.clear();
    session.token = null;
    location.assign('/login');
  }

  function chrome(content, signedIn) {
    var links = signedIn
      ? [['/', 'Wallet'], ['/requests', 'Requests'], ['/split', 'Split a bill'], ['/authorizations', 'Holds']]
      : [['/login', 'Log in'], ['/signup', 'Sign up']];
    var nav = h('nav', { class: 'nav', 'aria-label': 'Main' }, links.map(function (l) {
      return h('a', { href: l[0], 'aria-current': l[0] === path ? 'page' : null, text: l[1] });
    }));
    clear(root);
    append(root, [
      h('header', { class: 'topbar' }, h('div', { class: 'topbar-inner' },
        h('a', { class: 'brand', href: '/' }, h('img', { src: '/static/icon.svg', alt: '' }), 'Pocketful'),
        nav, signedIn ? whoEl : null)),
      h('main', { id: 'main' }, content),
      h('footer', { class: 'footer', text: 'Pocketful · money moves only between Pocketful wallets' }),
    ]);
  }

  // ------------------------------------------------------------------ activity

  function activityCard() {
    var body_ = h('div', null, h('p', { class: 'loading', text: 'Loading activity…' }));
    var card = h('section', { class: 'card', 'aria-label': 'Activity' }, h('h2', null, 'Activity', h('span', { class: 'sub', text: 'newest first' })), body_);
    return {
      el: card,
      load: function () {
        var seq = beginRead('activity');
        return api('GET', '/activity?limit=100').then(function (res) {
          if (!isLatest('activity', seq) || res.kind !== 'ok') return;
          clear(body_);
          var items = res.data.payments;
          if (!items.length) {
            body_.appendChild(h('div', { class: 'empty', testid: 'empty-activity' },
              h('strong', { text: 'No activity yet' }), 'Payments you send, receive or can see will appear here.'));
            return;
          }
          body_.appendChild(h('ul', { class: 'list', testid: 'activity-list' }, items.map(activityItem)));
        });
      },
    };
  }

  function activityItem(p) {
    var mine = me && p.to_user_id === me.user_id;
    var sent = me && p.from_user_id === me.user_id;
    var kind = p.authorization_id ? 'Captured hold' : p.settlement_id ? 'Settlement' : p.request_id ? 'Request paid' : 'Payment';
    return h('li', { class: 'item ' + (mine ? 'dir-in' : 'dir-out'), testid: 'activity-item-' + p.payment_id, 'data-visibility': p.visibility },
      h('div', { class: 'item-main' },
        h('div', { class: 'item-title', testid: 'activity-parties-' + p.payment_id, text: '@' + p.from_handle + ' → @' + p.to_handle }),
        h('div', { class: 'item-note', testid: 'activity-note-' + p.payment_id, text: p.note }),
        h('div', { class: 'item-meta' },
          h('span', { text: sent ? 'You sent' : mine ? 'You received' : kind }),
          h('span', { class: 'badge badge-' + p.visibility, text: p.visibility }),
          h('span', { text: when(p.created_at) }))),
      h('div', { class: 'item-side' },
        h('div', { class: 'item-amount', testid: 'activity-amount-' + p.payment_id, text: fmt(p.amount) }),
        h('div', { class: 'small muted', text: mine ? 'in' : sent ? 'out' : '' })));
  }

  // ------------------------------------------------------------------ forms

  // A money form (pay, request, authorize). spec: prefix, fields, path, build.
  function moneyForm(spec) {
    var ids = identity();
    var inputs = {};
    var fb = slot();
    var inFlight = false;
    inputs.handle = h('input', { testid: spec.prefix + '-handle', autocomplete: 'off', autocapitalize: 'none', spellcheck: 'false', placeholder: 'their handle' });
    inputs.amount = h('input', { testid: spec.prefix + '-amount', inputmode: 'decimal', autocomplete: 'off', placeholder: money.mu ? '0.' + '0'.repeat(money.mu) : '0' });
    inputs.note = h('input', { testid: spec.prefix + '-note', maxlength: '200', autocomplete: 'off', placeholder: 'What’s it for?' });
    if (spec.visibility) inputs.visibility = visibilitySelect(spec.prefix + '-visibility');
    var submit = h('button', { class: 'btn', type: 'submit', testid: spec.prefix + '-submit', text: spec.action });

    var form = h('form', { class: 'form', novalidate: true, onsubmit: function (e) { e.preventDefault(); send(); } },
      h('div', { class: 'row row-2' }, field(spec.handleLabel, inputs.handle), field('Amount', inputs.amount, amountHint())),
      field('Note (optional)', inputs.note),
      inputs.visibility ? field('Who can see it', inputs.visibility) : null,
      h('div', { class: 'actions' }, submit),
      fb.el);

    function send() {
      if (inFlight) return;
      var amount = parseAmount(inputs.amount.value);
      if (amount === null) {
        inputs.amount.setAttribute('aria-invalid', 'true');
        fb.show(spec.prefix + '-error', 'error', money.mu === 0
          ? 'Enter a whole amount, like 1500.'
          : 'Enter an amount with up to ' + money.mu + ' decimal places, like 15.' + '0'.repeat(money.mu) + '.');
        return;
      }
      inputs.amount.removeAttribute('aria-invalid');
      var fields = {};
      fields[spec.handleField] = inputs.handle.value.trim();
      fields.amount = amount;
      fields.note = inputs.note.value;
      if (inputs.visibility) fields.visibility = inputs.visibility.value;
      var text = body(fields);
      var key = ids.keyFor(text);
      inFlight = true;
      busy(submit, true);
      api('POST', spec.path, { body: text, key: key }).then(function (res) {
        inFlight = false;
        busy(submit, false);
        if (res.kind === 'ok') fb.show(spec.prefix + '-success', 'ok', spec.done(res.data));
        else if (res.kind === 'uncertain' && spec.uncertain) fb.show(spec.prefix + '-uncertain', 'uncertain', spec.uncertain);
        else fb.show(spec.prefix + '-error', 'error', explain(res, spec.refused));
        spec.after(res);
      });
    }
    return { el: form, inputs: inputs };
  }

  // ------------------------------------------------------------------ screens

  function homeScreen() {
    var feed = activityCard();
    var refresh = function () { return Promise.all([loadMe(), feed.load()]); };
    wallet.onRefresh = refresh;

    var pay = moneyForm({
      prefix: 'pay', action: 'Send money', handleLabel: 'Pay to', handleField: 'to_handle', path: '/payments', visibility: true,
      refused: 'The payment was refused.',
      uncertain: 'We couldn’t confirm this payment. It may have gone through. Press “Send money” again to check — it will never be sent twice.',
      done: function (p) { return 'Sent ' + fmt(p.amount) + ' to @' + p.to_handle + '.'; },
      after: refresh,
    });
    var request = moneyForm({
      prefix: 'request', action: 'Request money', handleLabel: 'Ask', handleField: 'payer_handle', path: '/requests',
      refused: 'The request was refused.',
      done: function (r) { return 'Asked @' + r.payer_handle + ' for ' + fmt(r.amount) + '.'; },
      after: function (res) { if (res.kind === 'ok') refresh(); },
    });
    var authorize = authorizeForm(refresh);

    chrome(h('div', { class: 'stack' },
      walletCard(),
      h('div', { class: 'grid grid-2' },
        h('div', { class: 'stack' },
          h('section', { class: 'card', 'aria-label': 'Pay' }, h('h2', { text: 'Pay someone' }), pay.el),
          h('section', { class: 'card', 'aria-label': 'Request' }, h('h2', { text: 'Request money' }), request.el),
          h('section', { class: 'card', 'aria-label': 'Reserve' }, h('h2', null, 'Reserve money', h('span', { class: 'sub', text: 'they collect later' })), authorize.el)),
        feed.el)), true);
    renderWallet();
    refresh();
  }

  function authorizeForm(after) {
    return moneyForm({
      prefix: 'authorize', action: 'Reserve money', handleLabel: 'For', handleField: 'to_handle', path: '/authorizations', visibility: true,
      refused: 'The hold was refused.',
      done: function (a) { return 'Reserved ' + fmt(a.amount) + ' for @' + a.to_handle + '.'; },
      after: function (res) { if (res.kind === 'ok' || res.kind === 'error') after(); },
    });
  }

  function requestsScreen() {
    var fb = slot();
    var incoming = h('ul', { class: 'list', testid: 'incoming-list' });
    var outgoing = h('ul', { class: 'list', testid: 'outgoing-list' });
    var emptyBoth = h('div');
    var payKeys = identity();
    var loaded = false;

    function load() {
      var seq = beginRead('requests');
      return Promise.all([api('GET', '/requests?direction=incoming&limit=200'), api('GET', '/requests?direction=outgoing&limit=200')])
        .then(function (rs) {
          if (!isLatest('requests', seq) || rs[0].kind !== 'ok' || rs[1].kind !== 'ok') return;
          loaded = true;
          fill(incoming, rs[0].data.requests, true, 'Nobody has asked you for money.');
          fill(outgoing, rs[1].data.requests, false, 'You haven’t asked anyone for money.');
          clear(emptyBoth);
          if (!rs[0].data.requests.length && !rs[1].data.requests.length) {
            emptyBoth.appendChild(h('div', { class: 'empty', testid: 'empty-requests' },
              h('strong', { text: 'No requests yet' }), 'Ask someone for money from your wallet, or split a bill.'));
          }
        });
    }
    var refresh = function () { return Promise.all([loadMe(), load()]); };
    wallet.onRefresh = refresh;

    function fill(list, items, isIncoming, emptyText) {
      clear(list);
      if (!items.length) { list.appendChild(h('li', { class: 'muted small', text: emptyText })); return; }
      items.forEach(function (r) { list.appendChild(requestItem(r, isIncoming)); });
    }

    function act(button, method, url, opts, verb) {
      busy(button, true);
      fb.clear();
      api(method, url, opts).then(function (res) {
        busy(button, false);
        if (res.kind === 'ok') fb.show('request-success', 'ok', verb);
        else fb.show('request-error', 'error', explain(res, 'That action was refused.'));
        refresh();
      });
    }

    function requestItem(r, isIncoming) {
      var pending = r.status === 'pending';
      var actions = [];
      if (pending && isIncoming) {
        actions.push(h('button', { class: 'btn btn-sm', type: 'button', testid: 'request-pay-' + r.request_id, onclick: function (e) {
          var text = '{}';
          act(e.currentTarget, 'POST', '/requests/' + encodeURIComponent(r.request_id) + '/pay', { body: text, key: payKeys.keyFor(r.request_id + text) }, 'Paid ' + fmt(r.amount) + ' to @' + r.requester_handle + '.');
        } }, 'Pay ' + fmt(r.amount)));
        actions.push(h('button', { class: 'btn btn-danger btn-sm', type: 'button', testid: 'request-decline-' + r.request_id, onclick: function (e) {
          act(e.currentTarget, 'POST', '/requests/' + encodeURIComponent(r.request_id) + '/decline', {}, 'Request declined.');
        } }, 'Decline'));
      }
      if (pending && !isIncoming) {
        actions.push(h('button', { class: 'btn btn-ghost btn-sm', type: 'button', testid: 'request-cancel-' + r.request_id, onclick: function (e) {
          act(e.currentTarget, 'POST', '/requests/' + encodeURIComponent(r.request_id) + '/cancel', {}, 'Request cancelled.');
        } }, 'Cancel request'));
      }
      return h('li', { class: 'item ' + (isIncoming ? 'dir-out' : 'dir-in'), testid: 'request-item-' + r.request_id, 'data-status': r.status },
        h('div', { class: 'item-main' },
          h('div', { class: 'item-title', text: isIncoming ? '@' + r.requester_handle + ' asks you' : 'You asked @' + r.payer_handle }),
          h('div', { class: 'item-note', text: r.note }),
          h('div', { class: 'item-meta' }, h('span', { class: 'badge badge-' + r.status, text: r.status }), h('span', { text: when(r.created_at) }))),
        h('div', { class: 'item-side' }, h('div', { class: 'item-amount', testid: 'request-amount-' + r.request_id, text: fmt(r.amount) })),
        actions.length ? h('div', { class: 'item-actions' }, actions) : null);
    }

    chrome(h('div', { class: 'stack' },
      walletCard(),
      h('h1', { class: 'page-title', text: 'Requests' }),
      fb.el, emptyBoth,
      h('div', { class: 'grid grid-2' },
        h('section', { class: 'card', 'aria-label': 'Incoming requests' }, h('h2', null, 'Incoming', h('span', { class: 'sub', text: 'people asking you' })), incoming),
        h('section', { class: 'card', 'aria-label': 'Outgoing requests' }, h('h2', null, 'Outgoing', h('span', { class: 'sub', text: 'you asked' })), outgoing))), true);
    incoming.appendChild(h('li', { class: 'loading', text: 'Loading…' }));
    renderWallet();
    refresh();
    return loaded;
  }

  // §9: equal shares, the remainder to the first participants in order.
  function shares(amount, handles) {
    var n = BigInt(handles.length);
    var base = amount / n;
    var rem = amount % n;
    return handles.map(function (hd, i) { return { handle: hd, amount: base + (BigInt(i) < rem ? 1n : 0n) }; });
  }

  function splitScreen() {
    var ids = identity();
    var fb = slot();
    var amount = h('input', { testid: 'split-amount', inputmode: 'decimal', autocomplete: 'off', placeholder: money.mu ? '0.' + '0'.repeat(money.mu) : '0' });
    var handles = h('input', { testid: 'split-handles', autocomplete: 'off', autocapitalize: 'none', spellcheck: 'false', placeholder: 'ada, bob, cy' });
    var note = h('input', { testid: 'split-note', maxlength: '200', autocomplete: 'off', placeholder: 'Dinner, rent, tickets…' });
    var submit = h('button', { class: 'btn', type: 'submit', testid: 'split-submit', text: 'Split and send requests' });
    var preview = h('div', { class: 'preview', testid: 'split-preview', 'aria-live': 'polite' });
    var inFlight = false;

    function parseHandles() {
      var raw = handles.value.split(',').map(function (x) { return x.trim(); });
      if (raw.length === 1 && raw[0] === '') return [];
      return raw;
    }

    function renderPreview() {
      clear(preview);
      var a = parseAmount(amount.value);
      var list = parseHandles();
      if (a === null || !list.length) {
        preview.appendChild(h('p', { class: 'muted small', text: 'Enter an amount and at least one handle to see each share.' }));
        return;
      }
      if (list.indexOf('') !== -1) { preview.appendChild(h('p', { class: 'muted small', text: 'Remove the empty entry between commas.' })); return; }
      var seen = {};
      for (var i = 0; i < list.length; i += 1) {
        if (seen[list[i]]) { preview.appendChild(h('p', { class: 'muted small', text: '@' + list[i] + ' is listed twice.' })); return; }
        seen[list[i]] = true;
      }
      shares(a, list).forEach(function (s) {
        preview.appendChild(h('div', { class: 'share' },
          h('span', { class: 'who', text: '@' + s.handle + (me && s.handle === me.handle ? ' (you)' : '') }),
          h('span', { class: 'share-amt', testid: 'split-share-' + s.handle, text: fmt(s.amount) })));
      });
    }
    amount.addEventListener('input', renderPreview);
    handles.addEventListener('input', renderPreview);

    function send() {
      if (inFlight) return;
      var a = parseAmount(amount.value);
      if (a === null) {
        amount.setAttribute('aria-invalid', 'true');
        fb.show('split-error', 'error', 'Enter an amount with up to ' + money.mu + ' decimal places.');
        return;
      }
      amount.removeAttribute('aria-invalid');
      var list = parseHandles();
      if (!list.length || list.indexOf('') !== -1) {
        fb.show('split-error', 'error', 'List the handles to split between, separated by commas.');
        return;
      }
      var text = body({ amount: a, participant_handles: list, note: note.value });
      inFlight = true;
      busy(submit, true);
      api('POST', '/splits', { body: text, key: ids.keyFor(text) }).then(function (res) {
        inFlight = false;
        busy(submit, false);
        if (res.kind === 'ok') {
          var n = res.data.requests.length;
          fb.show('split-success', 'ok', 'Split ' + fmt(res.data.amount) + ' — ' + (n === 1 ? '1 request sent.' : n + ' requests sent.'));
        } else {
          fb.show('split-error', 'error', explain(res, 'The split was refused.'));
        }
        loadMe();
      });
    }

    var form = h('form', { class: 'form', novalidate: true, onsubmit: function (e) { e.preventDefault(); send(); } },
      h('div', { class: 'row row-2' }, field('Total amount', amount, amountHint()), field('Split between', handles, 'Handles separated by commas, in order. Include yourself to take a share.')),
      field('Note (optional)', note),
      h('div', null, h('h3', { class: 'small muted', text: 'Each person pays' }), preview),
      h('div', { class: 'actions' }, submit),
      fb.el);
    wallet.onRefresh = loadMe;
    chrome(h('div', { class: 'stack' },
      walletCard(),
      h('section', { class: 'card', 'aria-label': 'Split a bill' }, h('h2', { text: 'Split a bill you paid' }), form)), true);
    renderWallet();
    loadMe().then(renderPreview);
    renderPreview();
  }

  function authorizationsScreen() {
    var fb = slot();
    var listWrap = h('div', null, h('p', { class: 'loading', text: 'Loading holds…' }));
    var captureKeys = identity();

    function load() {
      var seq = beginRead('authorizations');
      return api('GET', '/authorizations?limit=200').then(function (res) {
        if (!isLatest('authorizations', seq) || res.kind !== 'ok') return;
        clear(listWrap);
        var items = res.data.authorizations;
        if (!items.length) {
          listWrap.appendChild(h('div', { class: 'empty', testid: 'empty-authorizations' },
            h('strong', { text: 'No holds' }), 'Reserve money for someone and they can collect it later.'));
          return;
        }
        listWrap.appendChild(h('ul', { class: 'list', testid: 'authorization-list' }, items.map(item)));
      });
    }
    var refresh = function () { return Promise.all([loadMe(), load()]); };
    wallet.onRefresh = refresh;

    function item(a) {
      var incoming = me && a.to_user_id === me.user_id;
      var open = a.status === 'open';
      var actions = [];
      if (open && incoming) {
        var amt = h('input', { testid: 'authorization-capture-amount-' + a.authorization_id, inputmode: 'decimal', autocomplete: 'off', value: decimalOf(a.remaining_amount) });
        var keep = h('input', { type: 'checkbox' });
        var btn = h('button', { class: 'btn btn-sm', type: 'button', testid: 'authorization-capture-' + a.authorization_id, text: 'Collect' });
        btn.addEventListener('click', function () {
          var value = parseAmount(amt.value);
          if (value === null) {
            amt.setAttribute('aria-invalid', 'true');
            fb.show('authorization-error', 'error', 'Enter an amount with up to ' + money.mu + ' decimal places.');
            return;
          }
          amt.removeAttribute('aria-invalid');
          var text = body({ amount: value, final: keep.checked ? false : undefined });
          busy(btn, true);
          fb.clear();
          api('POST', '/authorizations/' + encodeURIComponent(a.authorization_id) + '/capture', { body: text, key: captureKeys.keyFor(a.authorization_id + text) })
            .then(function (res) {
              busy(btn, false);
              if (res.kind === 'ok') fb.show('authorization-success', 'ok', 'Collected ' + fmt(res.data.amount) + ' from @' + a.from_handle + '.');
              else fb.show('authorization-error', 'error', explain(res, 'The capture was refused.'));
              refresh();
            });
        });
        actions.push(field('Amount to collect', amt), h('label', { class: 'check' }, keep, 'Keep the rest on hold'), btn);
      }
      if (open && !incoming) {
        actions.push(h('button', { class: 'btn btn-danger btn-sm', type: 'button', testid: 'authorization-void-' + a.authorization_id, onclick: function (e) {
          var b = e.currentTarget;
          busy(b, true);
          fb.clear();
          api('POST', '/authorizations/' + encodeURIComponent(a.authorization_id) + '/void').then(function (res) {
            busy(b, false);
            if (res.kind === 'ok') fb.show('authorization-success', 'ok', 'Hold released.');
            else fb.show('authorization-error', 'error', explain(res, 'The hold could not be released.'));
            refresh();
          });
        } }, 'Release hold'));
      }
      var progress = a.captured_amount > 0 && a.status !== 'captured'
        ? h('span', { text: 'Collected so far ' + fmt(a.captured_amount) }) : null;
      return h('li', { class: 'item ' + (incoming ? 'dir-in' : 'dir-out'), testid: 'authorization-item-' + a.authorization_id, 'data-status': a.status },
        h('div', { class: 'item-main' },
          h('div', { class: 'item-title', text: incoming ? '@' + a.from_handle + ' reserved for you' : 'You reserved for @' + a.to_handle }),
          h('div', { class: 'item-note', text: a.note }),
          h('div', { class: 'item-meta' },
            h('span', { class: 'badge badge-' + a.status, text: a.status }),
            h('span', { class: 'badge badge-' + a.visibility, text: a.visibility }),
            progress,
            h('span', null, (a.status === 'open' ? 'Expires ' : 'Expiry ') + when(a.expires_at) + ' · ',
              h('time', { class: 'mono', datetime: a.expires_at, testid: 'authorization-expires-' + a.authorization_id, text: a.expires_at })))),
        h('div', { class: 'item-side' },
          h('div', { class: 'item-amount', testid: 'authorization-amount-' + a.authorization_id, text: fmt(a.amount) }),
          a.status === 'captured' ? h('div', { class: 'small' }, 'Collected ', h('span', { testid: 'authorization-captured-' + a.authorization_id, text: fmt(a.captured_amount) })) : null,
          open ? h('div', { class: 'small muted', text: fmt(a.remaining_amount) + ' held' }) : null),
        actions.length ? h('div', { class: 'item-actions' }, actions) : null);
    }

    var authorize = authorizeForm(refresh);
    chrome(h('div', { class: 'stack' },
      walletCard(),
      h('div', { class: 'grid grid-2' },
        h('section', { class: 'card', 'aria-label': 'Reserve money' }, h('h2', null, 'Reserve money', h('span', { class: 'sub', text: 'they collect later' })), authorize.el),
        h('section', { class: 'card', 'aria-label': 'Holds' }, h('h2', null, 'Holds', h('span', { class: 'sub', text: 'newest first' })), fb.el, listWrap))), true);
    renderWallet();
    refresh();
  }

  function authScreen(kind) {
    var fb = slot();
    var isSignup = kind === 'signup';
    var email = h('input', { testid: kind + '-email', type: 'email', autocomplete: 'email', autocapitalize: 'none', spellcheck: 'false' });
    var password = h('input', { testid: kind + '-password', type: 'password', autocomplete: isSignup ? 'new-password' : 'current-password' });
    var name = isSignup ? h('input', { testid: 'signup-display-name', autocomplete: 'name' }) : null;
    var submit = h('button', { class: 'btn', type: 'submit', testid: kind + '-submit', text: isSignup ? 'Create account' : 'Log in' });
    var inFlight = false;

    function send() {
      if (inFlight) return;
      var fields = { email: email.value.trim(), password: password.value };
      if (isSignup) fields.display_name = name.value.trim();
      inFlight = true;
      busy(submit, true);
      fb.clear();
      api('POST', isSignup ? '/auth/signup' : '/auth/login', { body: JSON.stringify(fields) }).then(function (res) {
        inFlight = false;
        busy(submit, false);
        if (res.kind === 'ok') {
          session.set(res.data.token);
          session.token = res.data.token;
          location.assign('/');
          return;
        }
        var msg = res.code === 'validation_failed'
          ? (isSignup ? 'Use a valid email, a password of at least 8 characters and your name.' : 'Enter your email and password.')
          : explain(res, 'That didn’t work. Please try again.');
        fb.show('auth-error', 'error', msg);
      });
    }

    var form = h('form', { class: 'form', novalidate: true, onsubmit: function (e) { e.preventDefault(); send(); } },
      field('Email', email),
      isSignup ? field('Your name', name, 'Shown to people you pay') : null,
      field('Password', password, isSignup ? 'At least 8 characters' : null),
      h('div', { class: 'actions' }, submit),
      fb.el,
      h('p', { class: 'small muted' }, isSignup ? 'Already have an account? ' : 'New to Pocketful? ',
        h('a', { href: isSignup ? '/login' : '/signup', text: isSignup ? 'Log in' : 'Create an account' })));
    chrome(h('div', { class: 'auth-wrap card' },
      h('h1', { class: 'page-title', text: isSignup ? 'Create your wallet' : 'Welcome back' }), form), !!me);
  }

  function signedOutScreen() {
    chrome(h('div', { class: 'welcome card' },
      h('h1', { class: 'page-title', text: 'Pocketful' }),
      h('p', { text: 'Send money by handle, request it back, split bills and reserve money for later. Log in to see your wallet.' }),
      h('div', { class: 'actions', style: null },
        h('a', { class: 'btn', href: '/login', text: 'Log in' }),
        h('a', { class: 'btn btn-ghost', href: '/signup', text: 'Create an account' }))), false);
  }

  // ------------------------------------------------------------------ boot

  var screens = { '/': homeScreen, '/requests': requestsScreen, '/split': splitScreen, '/authorizations': authorizationsScreen };

  function boot() {
    if (path === '/login' || path === '/signup') {
      if (!session.token) { authScreen(path.slice(1)); return; }
      loadMe().then(function () { authScreen(path.slice(1)); renderWho(); });
      return;
    }
    if (!session.token) { signedOutScreen(); return; }
    // Money formatting needs the currency, so the first /me comes first.
    loadMe().then(function (res) {
      if (res.kind !== 'ok') {
        if (res.kind === 'uncertain') {
          chrome(h('div', { class: 'empty' }, h('strong', { text: 'Pocketful is unreachable' }), 'Check your connection and reload the page.'), false);
        }
        return;
      }
      (screens[path] || homeScreen)();
      renderWho();
    });
  }

  boot();
})();
