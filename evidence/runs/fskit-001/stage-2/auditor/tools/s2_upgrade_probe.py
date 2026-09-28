#!/usr/bin/env python3
"""Auditor-owned 1->2 upgrade probe (fskit-001; S2-040..S2-044, S2-902, D2-13, D2-18).

Containers (all started by the auditor, fresh):
  --s1   ACCEPTED stage-1 image (built from a clone at beeaec72)
  --s2a  stage-2 candidate, serves the UI origin (and is the API target of part A)
  --s2b  stage-2 candidate, fresh; the browser's data calls switch to it after the import (part B)
Export bodies are held in memory only; only SHA-256 and booleans are recorded.

usage: s2_upgrade_probe.py --s1 URL --s2a URL --s2b URL --out-dir DIR
"""
import argparse, asyncio, hashlib, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, k
from playwright.async_api import async_playwright

RESULTS = []


def rec(ob, name, ok, detail):
    RESULTS.append({"obligation": ob, "probe": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + ob + " " + name + " :: " + json.dumps(detail, default=str)[:300], flush=True)


def raw_call(method, path, body, token, key, base):
    """Like call() but also returns the exact response bytes (for D2-13 byte equality)."""
    import urllib.request, urllib.error
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Idempotency-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def populate_stage1(s1):
    f = ap.fixture([("op", 0), ("aa", 10000), ("bb", 5000), ("cc", 0)], operators=["op"])
    ap.reset(f, base=s1)
    t = {h: ap.login(h, base=s1) for h in ("op", "aa", "bb", "cc")}
    st = {"tokens": t}
    k1 = k()
    st["k1"] = (k1, {"to_handle": "bb", "amount": 700, "note": "done", "visibility": "private"})
    st["r1"] = raw_call("POST", "/payments", st["k1"][1], t["aa"], k1, s1)
    s, rq, _ = call("POST", "/requests", {"payer_handle": "aa", "amount": 1200, "note": "pending-taxi"}, token=t["bb"], key=k(), base=s1)
    st["pending_rq"] = rq["request_id"]
    sk = k()
    st["sk"] = (sk, {"transfers": [{"from_handle": "bb", "to_handle": "cc", "amount": 300}, {"from_handle": "aa", "to_handle": "bb", "amount": 100}]})
    st["rs"] = raw_call("POST", "/settlements", st["sk"][1], t["op"], sk, s1)
    k2 = k()   # "lost response": committed on stage 1, the client never saw the answer
    st["k2"] = (k2, {"to_handle": "cc", "amount": 55, "note": "lost"})
    st["r2"] = raw_call("POST", "/payments", st["k2"][1], t["aa"], k2, s1)
    fk = k()
    st["fk"] = fk
    call("POST", "/payments", {"to_handle": "cc", "amount": 10 ** 9}, token=t["aa"], key=fk, base=s1)   # failed (409)
    st["balances"] = {h: call("GET", "/me", token=t[h], base=s1)[1]["balance"] for h in t}
    return st


def api_part(s1, s2):
    st = populate_stage1(s1)
    t = st["tokens"]
    s, ex, _ = call("GET", "/_test/export", base=s1)
    ex_sha = hashlib.sha256(json.dumps(ex, sort_keys=True).encode()).hexdigest()
    ap.reset(ap.fixture([("zz", 5)]), base=s2)
    tz = ap.login("zz", base=s2)
    si, _, _ = call("POST", "/_test/import", ex, base=s2)
    mes = {h: call("GET", "/me", token=t[h], base=s2) for h in t}
    ok_me = all(m[0] == 200 and m[1]["balance"] == m[1]["total"] == m[1]["available"] == st["balances"][h] and m[1]["held"] == 0 for h, m in mes.items())
    rec("S2-040/S2-041", "stage-1 export imports into stage-2; old tokens valid; balances kept; no holds", s == 200 and si == 204 and ok_me and call("GET", "/me", token=tz, base=s2)[0] == 401,
        {"export": s, "import": si, "export_sha256": ex_sha})
    rp1 = raw_call("POST", "/payments", st["k1"][1], t["aa"], st["k1"][0], s2)
    rp2 = raw_call("POST", "/payments", st["k2"][1], t["aa"], st["k2"][0], s2)
    rps = raw_call("POST", "/settlements", st["sk"][1], t["op"], st["sk"][0], s2)
    rec("S2-043/D2-13/S1-176", "stage-1 receipts replay on stage-2 as 200 with the ORIGINAL bytes",
        (rp1[0], rp2[0], rps[0]) == (200, 200, 200) and rp1[1] == st["r1"][1] and rp2[1] == st["r2"][1] and rps[1] == st["rs"][1]
        and b"authorization_id" not in rp1[1], {"s": [rp1[0], rp2[0], rps[0]]})
    d = call("POST", "/payments", dict(st["k1"][1], amount=701), token=t["aa"], key=st["k1"][0], base=s2)
    f = call("POST", "/payments", {"to_handle": "cc", "amount": 1}, token=t["aa"], key=st["fk"], base=s2)
    pay = call("POST", "/requests/%s/pay" % st["pending_rq"], {}, token=t["aa"], key=k(), base=s2)
    feed = call("GET", "/activity?limit=200", token=t["aa"], base=s2)[1]["payments"]
    mem = [p for p in feed if p.get("settlement_id")]
    tot = sum(call("GET", "/me", token=t[h], base=s2)[1]["total"] for h in t)
    rec("S2-040/S2-042/S2-044", "imported state exercised: key reuse 409, failed key reusable, pending request payable, feed has authorization_id, conservation",
        (d[0], code(d[1])) == (409, "idempotency_key_reuse") and f[0] == 201 and pay[0] == 201 and pay[1]["authorization_id"] is None
        and all("authorization_id" in p for p in feed) and len(mem) == 1 and tot == 15000,
        {"diff_body": d[0], "failed_key": f[0], "pay_pending": pay[0], "feed": len(feed), "total": tot})


async def ui_part(s1, s2a, s2b, out):
    st = populate_stage1(s1)
    ap.reset(ap.fixture([("zz", 5)]), base=s2a)          # the UI origin has unrelated state; data never comes from it
    ap.reset(ap.fixture([("yy", 5)]), base=s2b)
    target = {"base": s1}
    posts = []

    async def route_data(route):
        req = route.request
        if req.resource_type in ("fetch", "xhr"):
            url = target["base"] + req.url[len(s2a):]
            if req.method == "POST" and "/payments" in req.url:
                posts.append((req.headers.get("idempotency-key"), req.post_data, target["base"]))
                if len(posts) == 1:
                    await route.fetch(url=url)              # commits on stage 1
                    await route.abort("connectionreset")   # the response is lost
                    return
            resp = await route.fetch(url=url)
            await route.fulfill(response=resp)
        else:
            await route.continue_()                          # document + static assets from the stage-2 origin
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w in (375, 1280):
            if w == 1280:
                st = populate_stage1(s1)
                ap.reset(ap.fixture([("yy", 5)]), base=s2b)
                target["base"] = s1
                posts.clear()
            ctx = await b.new_context(viewport={"width": w, "height": 800})
            page = await ctx.new_page()
            await page.route(s2a + "/**", route_data)
            await page.goto(s2a + "/login")
            await page.fill("[data-testid=login-email]", "aa@audit.invalid")
            await page.fill("[data-testid=login-password]", "pw-aa-12345")
            await page.click("[data-testid=login-submit]")
            ok_login = True
            try:
                await page.wait_for_selector("[data-testid=current-user]", timeout=8000)
            except Exception:
                ok_login = False
            await page.goto(s2a + "/")
            await page.wait_for_selector("[data-testid=pay-submit]", timeout=8000)
            await page.fill("[data-testid=pay-handle]", "cc")
            await page.fill("[data-testid=pay-amount]", "4.44")
            await page.fill("[data-testid=pay-note]", "lost-before-upgrade")
            await page.click("[data-testid=pay-submit]")
            unc = False
            try:
                await page.wait_for_selector("[data-testid=pay-uncertain]", state="visible", timeout=6000)
                unc = True
            except Exception:
                pass
            # --- the upgrade, between browser requests ---
            s, ex, _ = call("GET", "/_test/export", base=s1)
            s1_aa = call("GET", "/me", token=st["tokens"]["aa"], base=s1)[1]["balance"]
            si, _, _ = call("POST", "/_test/import", ex, base=s2b)
            target["base"] = s2b
            await page.click("[data-testid=pay-submit]")         # same form, unchanged
            cleared = False
            try:
                await page.wait_for_selector("[data-testid=pay-uncertain]", state="detached", timeout=6000)
                cleared = True
            except Exception:
                cleared = await page.locator("[data-testid=pay-uncertain]").count() == 0
            await page.wait_for_timeout(800)
            shown = await page.get_attribute("[data-testid=wallet-balance]", "data-amount")
            b2_aa = call("GET", "/me", token=st["tokens"]["aa"], base=s2b)[1]["balance"]
            still = await page.locator("[data-testid=current-user]").count() > 0
            same = len(posts) >= 2 and posts[0][:2] == posts[1][:2] and posts[1][2] == s2b
            await page.screenshot(path=os.path.join(out, "w%d-upgrade-after-retry.png" % w), full_page=True)
            rec("S2-041/S2-043/D2-18", "browser signed in on stage-1 data stays signed in after import; lost pay retried with same key+body recovers original; money once @%d" % w,
                ok_login and unc and si == 204 and cleared and same and still and b2_aa == s1_aa and shown == str(b2_aa) and st["balances"]["aa"] - b2_aa == 444,
                {"login": ok_login, "uncertain": unc, "import": si, "cleared": cleared, "same_key_body": same, "signed_in": still,
                 "s1_balance_after_lost": s1_aa, "s2_balance": b2_aa, "shown": shown})
            # pending stage-1 request payable through the request screen
            await page.goto(s2a + "/requests")
            rid = st["pending_rq"]
            payable = False
            try:
                await page.wait_for_selector("[data-testid='request-pay-%s']" % rid, timeout=6000)
                await page.click("[data-testid='request-pay-%s']" % rid)
                await page.wait_for_timeout(1200)
                stt = await page.get_attribute("[data-testid='request-item-%s']" % rid, "data-status")
                payable = stt == "paid"
            except Exception as e:
                stt = repr(e)[:80]
            api_st = [r for r in call("GET", "/requests?limit=200", token=st["tokens"]["aa"], base=s2b)[1]["requests"] if r["request_id"] == rid]
            await page.screenshot(path=os.path.join(out, "w%d-upgrade-requests.png" % w), full_page=True)
            rec("S2-042/D2-18", "stage-1 pending request paid from /requests after upgrade @%d" % w, payable and api_st and api_st[0]["status"] == "paid",
                {"ui_status": stt, "api_status": api_st[0]["status"] if api_st else None})
            await ctx.close()
        await b.close()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--s1", required=True)
    a.add_argument("--s2a", required=True)
    a.add_argument("--s2b", required=True)
    a.add_argument("--out-dir", required=True)
    x = a.parse_args()
    os.makedirs(x.out_dir, exist_ok=True)
    ap.BASE = x.s1
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        api_part(x.s1, x.s2a)
    except Exception as e:
        rec("ERROR", "api_part", False, {"exception": repr(e)[:400]})
    try:
        asyncio.run(ui_part(x.s1, x.s2a, x.s2b, x.out_dir))
    except Exception as e:
        rec("ERROR", "ui_part", False, {"exception": repr(e)[:400]})
    summ = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(r["pass"] for r in RESULTS), "failed": sum(not r["pass"] for r in RESULTS), "total": len(RESULTS), "results": RESULTS}
    json.dump(summ, open(os.path.join(x.out_dir, "upgrade-results.json"), "w"), indent=1, ensure_ascii=False, default=str)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
