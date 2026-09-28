#!/usr/bin/env python3
"""Auditor-owned stage-2 browser probes (fskit-001). Playwright (async) + Chromium, run by the auditor.
Keys: S2-010, S2-012..S2-028, S2-030..S2-034 (evidence screenshots), S2-032 scrollWidth, S2-033 focus/contrast.
Synthetic data only. Screenshots contain synthetic handles only (no tokens).

usage: s2_ui_probe.py --base URL --out-dir DIR
"""
import argparse, asyncio, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, k
from playwright.async_api import async_playwright

RESULTS = []
WIDTHS = [(375, 800), (1280, 800)]
PW = {"aa": "pw-aa-12345"}


def rec(ob, name, ok, detail):
    RESULTS.append({"obligation": ob, "probe": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + ob + " " + name + " :: " + json.dumps(detail, default=str)[:300], flush=True)


def fixture(mu=2, cur="EUR", holds=True):
    f = ap.fixture([("aa", 10000 if mu else 100), ("bb", 2500), ("cc", 0)], cur=cur, mu=mu)
    f["payments"] = [{"id": "p_seed1", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 500 if mu else 5,
                      "note": "coffee", "visibility": "public"}]
    f["requests"] = [{"id": "rq_seed1", "requester_id": "u_bb", "payer_id": "u_aa", "amount": 1200 if mu else 12,
                      "note": "taxi", "status": "pending"}]
    if holds:
        f["authorizations"] = [{"id": "a_seed1", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 2000 if mu else 20,
                                "note": "deposit", "visibility": "public", "status": "open",
                                "expires_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + 7200))}]
    return f


def fmt(minor, mu, cur):
    if mu == 0:
        return "%d %s" % (minor, cur)
    s = str(minor).rjust(mu + 1, "0")
    return "%s.%s %s" % (s[:-mu], s[-mu:], cur)


async def login_ui(page, base, h="aa"):
    await page.goto(base + "/login")
    await page.fill("[data-testid=login-email]", h + "@audit.invalid")
    await page.fill("[data-testid=login-password]", PW.get(h, "pw-%s-12345" % h))
    await page.click("[data-testid=login-submit]")
    await page.wait_for_selector("[data-testid=current-user]", timeout=8000)


async def tid(page, t, timeout=5000):
    return page.locator("[data-testid='%s']" % t)


async def visible(page, t, timeout=4000):
    try:
        await page.wait_for_selector("[data-testid='%s']" % t, state="visible", timeout=timeout)
        return True
    except Exception:
        return False


async def gone(page, t, timeout=4000):
    try:
        await page.wait_for_selector("[data-testid='%s']" % t, state="detached", timeout=timeout)
        return True
    except Exception:
        return await page.locator("[data-testid='%s']" % t).count() == 0 or not await page.locator("[data-testid='%s']" % t).first.is_visible()


async def text(page, t):
    return (await page.locator("[data-testid='%s']" % t).first.inner_text()).strip()


async def api_balance(tok):
    return call("GET", "/me", token=tok)[1]


async def routes_and_layout(ctx, base, out, w, h):
    page = await ctx.new_page()
    res = {}
    # signed-out routes
    for r, anchor in (("/signup", "signup-submit"), ("/login", "login-submit")):
        await page.goto(base + r)
        ok = await visible(page, anchor)
        sw = await page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        await page.screenshot(path=os.path.join(out, "w%d-%s.png" % (w, r.strip("/") or "root")), full_page=True)
        res[r] = {"anchor": ok, "scroll": sw}
    await login_ui(page, base)
    for r, anchor in (("/", "pay-submit"), ("/requests", "incoming-list"), ("/split", "split-submit"), ("/authorizations", "authorization-list")):
        await page.goto(base + r)
        ok = await visible(page, anchor)
        cu = await visible(page, "current-user")
        sw = await page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        await page.screenshot(path=os.path.join(out, "w%d-%s.png" % (w, r.strip("/") or "root")), full_page=True)
        res[r] = {"anchor": ok, "current_user": cu, "scroll": sw}
    all_ok = all(v["anchor"] and v["scroll"][0] <= v["scroll"][1] and v.get("current_user", True) for v in res.values())
    rec("S2-010/S2-032/S2-012", "direct navigation, current-user on every signed-in screen, no horizontal scroll @%d" % w, all_ok, res)
    # focus visibility on pay-submit
    await page.goto(base + "/")
    await page.wait_for_selector("[data-testid=pay-submit]")
    before = await page.evaluate("""() => { const e=document.querySelector('[data-testid=pay-submit]'); const s=getComputedStyle(e); return [s.outlineStyle,s.outlineWidth,s.boxShadow]; }""")
    await page.focus("[data-testid=pay-handle]")
    await page.keyboard.press("Tab")
    for _ in range(6):
        act = await page.evaluate("document.activeElement && document.activeElement.getAttribute('data-testid')")
        if act == "pay-submit":
            break
        await page.keyboard.press("Tab")
    after = await page.evaluate("""() => { const e=document.activeElement; const s=getComputedStyle(e); return [e.getAttribute('data-testid'), s.outlineStyle, s.outlineWidth, s.boxShadow]; }""")
    await page.screenshot(path=os.path.join(out, "w%d-focus.png" % w))
    focus_ok = after[0] == "pay-submit" and ((after[1] not in ("none", "") and after[2] not in ("0px",)) or after[3] not in ("none", before[2]))
    rec("S2-033", "keyboard reaches pay-submit with a visible focus indicator @%d" % w, focus_ok, {"before": before, "after": after})
    labels = await page.evaluate("""() => ['pay-handle','pay-amount','pay-note','request-handle','request-amount','authorize-handle','authorize-amount'].map(t => {
        const e=document.querySelector(`[data-testid="${t}"]`); if(!e) return [t,null];
        const lab = (e.labels && e.labels.length && e.labels[0].innerText.trim()) || (e.id && document.querySelector(`label[for="${e.id}"]`)?.innerText.trim()) || e.getAttribute('aria-label');
        const vis = e.labels && e.labels.length ? e.labels[0].getBoundingClientRect().height > 0 : false;
        return [t, lab, vis]; })""")
    rec("S2-033", "inputs have visible labels @%d" % w, all(l[1] and l[2] for l in labels), {"labels": labels})
    contrast = await page.evaluate("""() => {
      function rgb(s){const m=s.match(/[\\d.]+/g).map(Number);return m;}
      function lum(c){const a=c.slice(0,3).map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)});return 0.2126*a[0]+0.7152*a[1]+0.0722*a[2];}
      function bg(e){while(e){const c=rgb(getComputedStyle(e).backgroundColor);if(c.length<4||c[3]>0.5)return c;e=e.parentElement;}return [255,255,255,1];}
      const out=[];
      for (const t of ['wallet-available','wallet-balance','pay-submit','current-user','activity-list']) {
        const e=document.querySelector(`[data-testid="${t}"]`); if(!e) continue;
        const f=rgb(getComputedStyle(e).color), b=bg(e); const L1=lum(f),L2=lum(b);
        out.push([t,(Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05)]);
      } return out; }""")
    rec("S2-033/D2-07", "sampled text contrast >= 4.5:1 @%d" % w, contrast and all(c[1] >= 4.5 for c in contrast), {"ratios": [[c[0], round(c[1], 2)] for c in contrast]})
    await page.close()


async def wallet_and_forms(ctx, base, out, w):
    page = await ctx.new_page()
    ta = ap.login("aa")
    await login_ui(page, base)
    await page.goto(base + "/")
    await page.wait_for_selector("[data-testid=wallet-available]")
    wb, wa, wh = (await text(page, "wallet-balance")), (await text(page, "wallet-available")), (await text(page, "wallet-held"))
    da = await page.get_attribute("[data-testid=wallet-available]", "data-amount")
    db = await page.get_attribute("[data-testid=wallet-balance]", "data-amount")
    dh = await page.get_attribute("[data-testid=wallet-held]", "data-amount")
    hdr = await page.evaluate("""() => ['wallet-available','wallet-balance','wallet-held'].map(t=>parseFloat(getComputedStyle(document.querySelector(`[data-testid="${t}"]`)).fontSize))""")
    rec("S2-013/S2-015/S2-026/S2-028", "wallet total/available/held formatted, data-amount, available is headline @%d" % w,
        (wb, wa, wh, db, da, dh) == ("100.00 EUR", "80.00 EUR", "20.00 EUR", "10000", "8000", "2000") and hdr[0] > hdr[1] and hdr[0] > hdr[2],
        {"text": [wb, wa, wh], "data": [db, da, dh], "font_px": hdr})
    # activity
    feed_ok = await visible(page, "activity-item-p_seed1")
    note = await text(page, "activity-note-p_seed1") if feed_ok else None
    amt = await text(page, "activity-amount-p_seed1") if feed_ok else None
    par = await text(page, "activity-parties-p_seed1") if feed_ok else ""
    vis = await page.get_attribute("[data-testid=activity-item-p_seed1]", "data-visibility") if feed_ok else None
    rec("S2-017", "activity item testids @%d" % w, feed_ok and note == "coffee" and amt == "5.00 EUR" and "aa" in par and "bb" in par and vis == "public",
        {"note": note, "amt": amt, "parties": par, "vis": vis})
    # decimal rules with network log
    posts = []
    page.on("request", lambda r: posts.append((r.method, r.url, r.post_data)) if r.method == "POST" and "/payments" in r.url else None)
    bad = {}
    for v in ["15.005", "abc", "-5", "1e3", ""]:
        n0 = len(posts)
        await page.fill("[data-testid=pay-handle]", "bb")
        await page.fill("[data-testid=pay-amount]", v)
        await page.click("[data-testid=pay-submit]")
        err = await visible(page, "pay-error", 2500)
        await page.wait_for_timeout(300)
        bad[v] = {"error": err, "posted": len(posts) - n0}
    rec("S2-016", "invalid decimals show pay-error and send no request @%d" % w, all(x["error"] and x["posted"] == 0 for x in bad.values()), bad)
    await page.fill("[data-testid=pay-handle]", "bb")
    await page.fill("[data-testid=pay-amount]", "15.5")
    await page.fill("[data-testid=pay-note]", "ui-%d" % w)
    n0 = len(posts)
    b0 = (await api_balance(ta))["total"]
    await page.click("[data-testid=pay-submit]")
    await page.wait_for_timeout(1200)
    body = json.loads(posts[n0][2]) if len(posts) > n0 else None
    await page.click("[data-testid=pay-submit]")
    await page.wait_for_timeout(1200)
    b1 = (await api_balance(ta))["total"]
    kept = await page.input_value("[data-testid=pay-amount]")
    errp = await page.locator("[data-testid=pay-error]").count()
    shown = await text(page, "wallet-balance")
    rec("S2-016/S2-014/S2-020", "15.5 -> 1550; double submit moves money once; form kept; page refreshed @%d" % w,
        body and body.get("amount") == 1550 and b0 - b1 == 1550 and kept == "15.5" and errp == 0 and shown == fmt(b1, 2, "EUR"),
        {"body_amount": (body or {}).get("amount"), "debit": b0 - b1, "kept": kept, "shown": shown})
    await page.screenshot(path=os.path.join(out, "w%d-after-pay.png" % w), full_page=True)
    # refused by competing client: spend everything elsewhere, then submit a changed form
    avail = (await api_balance(ta))["available"]
    call("POST", "/payments", {"to_handle": "cc", "amount": avail}, token=ta, key=k())
    await page.fill("[data-testid=pay-amount]", "1")
    await page.fill("[data-testid=pay-note]", "refused")
    await page.click("[data-testid=pay-submit]")
    err = await visible(page, "pay-error", 4000)
    await page.wait_for_timeout(600)
    vals = [await page.input_value("[data-testid=%s]" % t) for t in ("pay-handle", "pay-amount", "pay-note")]
    av_shown = await page.get_attribute("[data-testid=wallet-available]", "data-amount")
    await page.screenshot(path=os.path.join(out, "w%d-refused.png" % w), full_page=True)
    rec("S2-022", "refused payment: pay-error, inputs kept, balance refreshed @%d" % w, err and vals == ["bb", "1", "refused"] and av_shown == "0",
        {"err": err, "vals": vals, "available_shown": av_shown})
    await page.close()


async def latest_refresh_wins(ctx, base, w):
    page = await ctx.new_page()
    ta = ap.login("aa")
    await login_ui(page, base)
    await page.goto(base + "/")
    await page.wait_for_selector("[data-testid=wallet-refresh]")
    await page.fill("[data-testid=pay-note]", "keepme")
    state = {"delay": True, "seen": 0}

    async def handler(route):
        req = route.request
        if req.method == "GET" and req.resource_type in ("fetch", "xhr") and state["delay"]:
            state["seen"] += 1
            resp = await route.fetch()           # read NOW (old state)
            await asyncio.sleep(2.5)            # deliver LATE
            await route.fulfill(response=resp)
        else:
            await route.continue_()
    await page.route("**/*", handler)
    await page.click("[data-testid=wallet-refresh]")           # refresh #1, delayed with stale data
    await page.wait_for_timeout(400)
    call("POST", "/payments", {"to_handle": "bb", "amount": 111}, token=ta, key=k())
    state["delay"] = False
    await page.click("[data-testid=wallet-refresh]")           # refresh #2, fast with new data
    await page.wait_for_timeout(4000)
    shown = await page.get_attribute("[data-testid=wallet-balance]", "data-amount")
    truth = (await api_balance(ta))["total"]
    note = await page.input_value("[data-testid=pay-note]")
    await page.unroute("**/*")
    rec("S2-021", "latest refresh wins over a delayed earlier read; pay form not cleared @%d" % w,
        state["seen"] >= 1 and shown == str(truth) and note == "keepme", {"delayed_reads": state["seen"], "shown": shown, "truth": truth, "note": note})
    await page.close()


async def lost_response(ctx, base, out, w):
    page = await ctx.new_page()
    ta = ap.login("aa")
    await login_ui(page, base)
    await page.goto(base + "/")
    await page.wait_for_selector("[data-testid=pay-submit]")
    seen = []

    async def handler(route):
        req = route.request
        if req.method == "POST" and "/payments" in req.url:
            seen.append((req.headers.get("idempotency-key"), req.post_data))
            if len(seen) == 1:
                await route.fetch()          # the server commits
                await route.abort("connectionreset")   # the response is lost
                return
        await route.continue_()
    await page.route("**/*", handler)
    b0 = (await api_balance(ta))["total"]
    await page.fill("[data-testid=pay-handle]", "bb")
    await page.fill("[data-testid=pay-amount]", "2.34")
    await page.fill("[data-testid=pay-note]", "lost-%d" % w)
    await page.click("[data-testid=pay-submit]")
    unc = await visible(page, "pay-uncertain", 5000)
    unc_txt = await text(page, "pay-uncertain") if unc else ""
    perr = await page.locator("[data-testid=pay-error]").count()
    await page.screenshot(path=os.path.join(out, "w%d-uncertain.png" % w), full_page=True)
    b_mid = (await api_balance(ta))["total"]
    await page.click("[data-testid=pay-submit]")
    g1 = await gone(page, "pay-uncertain", 5000)
    await page.wait_for_timeout(800)
    b1 = (await api_balance(ta))["total"]
    perr2 = await page.locator("[data-testid=pay-error]").count()
    shown = await page.get_attribute("[data-testid=wallet-balance]", "data-amount")
    same = len(seen) >= 2 and seen[0] == seen[1]
    await page.unroute("**/*")
    rec("S2-024", "lost response after commit: pay-uncertain, retry same key+body, money once, cleared @%d" % w,
        unc and unc_txt and perr == 0 and b0 - b_mid == 234 and same and g1 and perr2 == 0 and b0 - b1 == 234 and shown == str(b1),
        {"uncertain": unc, "pay_error_first": perr, "committed": b0 - b_mid, "same_key_body": same, "retries": len(seen), "final_debit": b0 - b1, "shown": shown})
    await page.close()


async def requests_screen(ctx, base, out, w):
    page = await ctx.new_page()
    ta, tb = ap.login("aa"), ap.login("bb")
    s, r1, _ = call("POST", "/requests", {"payer_handle": "aa", "amount": 300, "note": "stale"}, token=tb, key=k())
    s, r2, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 400, "note": "out"}, token=ta, key=k())
    await login_ui(page, base)
    await page.goto(base + "/requests")
    await page.wait_for_selector("[data-testid=incoming-list]")
    i1, i2 = r1["request_id"], r2["request_id"]
    btns = {t: await page.locator("[data-testid='%s']" % t).count() for t in
            ("request-pay-" + i1, "request-decline-" + i1, "request-cancel-" + i1, "request-cancel-" + i2, "request-pay-" + i2)}
    st = await page.get_attribute("[data-testid='request-item-%s']" % i1, "data-status")
    am = await text(page, "request-amount-" + i1)
    rec("S2-018", "request buttons only where allowed; status and amount @%d" % w,
        btns == {"request-pay-" + i1: 1, "request-decline-" + i1: 1, "request-cancel-" + i1: 0, "request-cancel-" + i2: 1, "request-pay-" + i2: 0}
        and st == "pending" and am == "3.00 EUR", {"buttons": btns, "status": st, "amount": am})
    call("POST", "/requests/%s/cancel" % i1, None, token=tb)      # cancelled elsewhere
    await page.click("[data-testid='request-pay-%s']" % i1)
    err = await visible(page, "request-error", 4000)
    stale_gone = await gone(page, "request-pay-" + i1, 4000)
    await page.screenshot(path=os.path.join(out, "w%d-requests-stale.png" % w), full_page=True)
    rec("S2-023", "stale pay after cancel elsewhere -> request-error, button disappears @%d" % w, err and stale_gone, {"err": err, "gone": stale_gone})
    await page.click("[data-testid='request-cancel-%s']" % i2)
    await page.wait_for_timeout(1000)
    st2 = await page.get_attribute("[data-testid='request-item-%s']" % i2, "data-status")
    rec("S2-018/S2-020", "cancel from UI updates status without reload @%d" % w, st2 == "cancelled", {"status": st2})
    await page.close()


async def split_screen(ctx, base, w):
    page = await ctx.new_page()
    await login_ui(page, base)
    await page.goto(base + "/split")
    await page.fill("[data-testid=split-amount]", "10")
    await page.fill("[data-testid=split-handles]", "bb, aa ,cc")
    await page.wait_for_timeout(500)
    ok_prev = await visible(page, "split-preview")
    shares = {h: (await text(page, "split-share-" + h)) if await page.locator("[data-testid=split-share-%s]" % h).count() else None for h in ("bb", "aa", "cc")}
    posted = []
    page.on("request", lambda r: posted.append(r.post_data) if r.method == "POST" and r.url.endswith("/splits") else None)
    await page.click("[data-testid=split-submit]")
    await page.wait_for_timeout(1200)
    body = json.loads(posted[0]) if posted else {}
    rec("S2-019", "split preview = server rule, submitted order kept @%d" % w,
        ok_prev and shares == {"bb": "3.34 EUR", "aa": "3.33 EUR", "cc": "3.33 EUR"} and body.get("amount") == 1000 and body.get("participant_handles") == ["bb", "aa", "cc"],
        {"shares": shares, "body": body})
    await page.close()


async def authorizations_screen(ctx, base, out, w):
    page = await ctx.new_page()
    ta, tb = ap.login("aa"), ap.login("bb")
    await login_ui(page, base)
    await page.goto(base + "/")
    await page.fill("[data-testid=authorize-handle]", "bb")
    await page.fill("[data-testid=authorize-amount]", "3.00")
    await page.click("[data-testid=authorize-submit]")
    await page.wait_for_timeout(1200)
    held = await page.get_attribute("[data-testid=wallet-held]", "data-amount")
    await page.fill("[data-testid=authorize-amount]", "999999")
    await page.click("[data-testid=authorize-submit]")
    aerr = await visible(page, "authorize-error", 4000)
    await page.goto(base + "/authorizations")
    await page.wait_for_selector("[data-testid=authorization-list]")
    items = await page.eval_on_selector_all("[data-testid^=authorization-item-]", "els => els.map(e => [e.getAttribute('data-testid'), e.getAttribute('data-status')])")
    exp_txt = await text(page, "authorization-expires-a_seed1") if await page.locator("[data-testid=authorization-expires-a_seed1]").count() else None
    void_btn = await page.locator("[data-testid=authorization-void-a_seed1]").count()
    cap_btn = await page.locator("[data-testid=authorization-capture-a_seed1]").count()
    await page.screenshot(path=os.path.join(out, "w%d-authorizations-payer.png" % w), full_page=True)
    import re
    rec("S2-026/S2-027/S2-028", "authorize from UI, held shown, refusal error, list newest first, expires RFC3339, void only for payer @%d" % w,
        held == "2300" and aerr and items and items[-1][0] == "authorization-item-a_seed1" and exp_txt and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$", exp_txt)
        and void_btn == 1 and cap_btn == 0, {"held": held, "err": aerr, "items": items[:3], "expires": exp_txt, "void": void_btn, "cap": cap_btn})
    # receiver captures partially from the UI (final:false not exposed by spec UI; default final capture)
    ctx2 = await page.context.browser.new_context(viewport={"width": w, "height": 800})
    p2 = await ctx2.new_page()
    await login_ui(p2, base, "bb")
    await p2.goto(base + "/authorizations")
    await p2.wait_for_selector("[data-testid=authorization-capture-a_seed1]")
    pre = await p2.input_value("[data-testid=authorization-capture-amount-a_seed1]")
    await p2.fill("[data-testid=authorization-capture-amount-a_seed1]", "15.00")
    await p2.click("[data-testid=authorization-capture-a_seed1]")
    await p2.wait_for_timeout(1500)
    st = await p2.get_attribute("[data-testid=authorization-item-a_seed1]", "data-status")
    capd = await text(p2, "authorization-captured-a_seed1") if await p2.locator("[data-testid=authorization-captured-a_seed1]").count() else None
    await p2.screenshot(path=os.path.join(out, "w%d-authorizations-receiver.png" % w), full_page=True)
    m = call("GET", "/me", token=ta)[1]
    rec("S2-027", "capture from UI: prefill remaining, captured shown, remainder released @%d" % w,
        pre in ("20.00",) and st == "captured" and capd == "15.00 EUR" and m["held"] == 300, {"prefill": pre, "status": st, "captured": capd, "payer_held": m["held"]})
    await ctx2.close()
    await page.close()


async def auth_errors_and_logout(ctx, base, w):
    page = await ctx.new_page()
    await page.goto(base + "/login")
    ae0 = await page.locator("[data-testid=auth-error]").count()
    await page.fill("[data-testid=login-email]", "aa@audit.invalid")
    await page.fill("[data-testid=login-password]", "wrong-password")
    await page.click("[data-testid=login-submit]")
    ae1 = await visible(page, "auth-error", 4000)
    await login_ui(page, base)
    hd = await text(page, "current-handle")
    cu = await text(page, "current-user")
    await page.click("[data-testid=logout-button]")
    await page.wait_for_timeout(800)
    await page.goto(base + "/")
    signed_out = await page.locator("[data-testid=current-user]").count() == 0
    rec("S2-012", "auth-error only on error; current-handle exact; logout @%d" % w, ae0 == 0 and ae1 and hd == "aa" and "AA" in cu and signed_out,
        {"auth_error_initial": ae0, "auth_error_after": ae1, "handle": hd, "user": cu, "signed_out": signed_out})
    await page.close()


async def jpy_format(ctx, base, w):
    ap.reset(fixture(mu=0, cur="JPY", holds=False))
    page = await ctx.new_page()
    await login_ui(page, base)
    await page.goto(base + "/")
    await page.wait_for_selector("[data-testid=wallet-balance]")
    wb = await text(page, "wallet-balance")
    held = await page.locator("[data-testid=wallet-held]").count()
    posts = []
    page.on("request", lambda r: posts.append(r.post_data) if r.method == "POST" and "/payments" in r.url else None)
    await page.fill("[data-testid=pay-handle]", "bb")
    await page.fill("[data-testid=pay-amount]", "15.0")
    await page.click("[data-testid=pay-submit]")
    e1 = await visible(page, "pay-error", 2500)
    n = len(posts)
    await page.fill("[data-testid=pay-amount]", "15")
    await page.click("[data-testid=pay-submit]")
    await page.wait_for_timeout(1000)
    body = json.loads(posts[-1]) if len(posts) > n else {}
    rec("S2-015/S2-016/S2-026", "JPY: '100 JPY', no held element when zero, '15.0' rejected (D2-05), '15' -> 15 @%d" % w,
        wb == "100 JPY" and held == 0 and e1 and n == 0 and body.get("amount") == 15, {"wallet": wb, "held_el": held, "posted_bad": n, "body": body})
    await page.close()


XSS = "<img src=x onerror=window.__xss=1>"


async def xss_and_worst_case(ctx, base, out, w):
    """S2-035 (notes/names render as text) and S2-032 worst-case content at 375 px (and 1280)."""
    long_h = "h" * 20
    f = ap.fixture([("aa", 10 ** 12), (long_h, 0), ("cc", 0)])
    f["users"][0]["display_name"] = "A" * 64
    f["users"][1]["password"] = "pw-x-12345"
    long_note = "N" * 200
    f["payments"] = [{"id": "p_w%d" % i, "from_user_id": "u_aa", "to_user_id": "u_" + long_h, "amount": 999999999,
                      "note": long_note if i % 2 else XSS, "visibility": "public"} for i in range(55)]
    f["requests"] = [{"id": "rq_w1", "requester_id": "u_" + long_h, "payer_id": "u_aa", "amount": 1000000000, "note": XSS, "status": "pending"},
                     {"id": "rq_w2", "requester_id": "u_aa", "payer_id": "u_" + long_h, "amount": 1000000000, "note": long_note, "status": "pending"}]
    f["authorizations"] = [{"id": "a_w1", "from_user_id": "u_aa", "to_user_id": "u_" + long_h, "amount": 1000000000, "note": XSS,
                            "visibility": "public", "status": "open",
                            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + 7200))}]
    ap.reset(f)
    page = await ctx.new_page()
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), asyncio.ensure_future(d.dismiss())))
    await login_ui(page, base)
    res = {}
    for r, anchor in (("/", "activity-list"), ("/requests", "incoming-list"), ("/split", "split-submit"), ("/authorizations", "authorization-list")):
        await page.goto(base + r)
        await visible(page, anchor, 6000)
        await page.wait_for_timeout(300)
        sw = await page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        injected = await page.evaluate("document.querySelectorAll('img[src=\"x\"]').length + (window.__xss ? 100 : 0)")
        await page.screenshot(path=os.path.join(out, "w%d-worst-%s.png" % (w, r.strip("/") or "root")), full_page=True)
        res[r] = {"scroll": sw, "injected": injected}
    await page.goto(base + "/")
    await visible(page, "activity-note-p_w0", 6000)
    n0 = await text(page, "activity-note-p_w0")
    n1 = await text(page, "activity-note-p_w1")
    amt = await text(page, "activity-amount-p_w0")
    await page.goto(base + "/requests")
    await visible(page, "request-item-rq_w1", 6000)
    rq_html = await page.inner_text("[data-testid=request-item-rq_w1]")
    rq_amt = await text(page, "request-amount-rq_w1")
    ok_scroll = all(v["scroll"][0] <= v["scroll"][1] for v in res.values())
    ok_xss = all(v["injected"] == 0 for v in res.values()) and not dialogs and n0 == XSS and XSS in rq_html
    rec("S2-032", "no horizontal scroll with worst-case content (200-char note, 20-char handle, 64-char name, max amounts, 55 items) @%d" % w,
        ok_scroll, {k2: v["scroll"] for k2, v in res.items()})
    rec("S2-035", "XSS payload rendered verbatim as text, nothing injected @%d" % w, ok_xss and n1 == long_note,
        {"injected": {k2: v["injected"] for k2, v in res.items()}, "dialogs": dialogs, "note_exact": n0 == XSS})
    rec("S2-015", "no thousands grouping on large amounts @%d" % w, amt == "9999999.99 EUR" and rq_amt == "10000000.00 EUR", {"feed": amt, "req": rq_amt})
    await page.close()


async def main_async(base, out):
    os.makedirs(out, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w, h in WIDTHS:
            for fn in (routes_and_layout, wallet_and_forms, latest_refresh_wins, lost_response, requests_screen, split_screen,
                       authorizations_screen, auth_errors_and_logout, jpy_format, xss_and_worst_case):
                ap.reset(fixture())
                ctx = await b.new_context(viewport={"width": w, "height": h})
                try:
                    if fn is routes_and_layout:
                        await fn(ctx, base, out, w, h)
                    elif fn in (wallet_and_forms, lost_response, requests_screen, authorizations_screen, xss_and_worst_case):
                        await fn(ctx, base, out, w)
                    else:
                        await fn(ctx, base, w)
                except Exception as e:
                    rec("ERROR", "%s @%d" % (fn.__name__, w), False, {"exception": repr(e)[:400]})
                await ctx.close()
        await b.close()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--base", required=True)
    a.add_argument("--out-dir", required=True)
    x = a.parse_args()
    ap.BASE = x.base
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    asyncio.run(main_async(x.base, x.out_dir))
    summ = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(r["pass"] for r in RESULTS), "failed": sum(not r["pass"] for r in RESULTS), "total": len(RESULTS), "results": RESULTS}
    json.dump(summ, open(os.path.join(x.out_dir, "ui-results.json"), "w"), indent=1, ensure_ascii=False, default=str)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
