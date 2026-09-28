#!/usr/bin/env python3
"""Auditor's independent reproduction of adversary finding F2-01 (S2-027 r2: capture input kept after a refused capture)."""
import asyncio, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, k
from playwright.async_api import async_playwright

BASE = sys.argv[1]
ap.BASE = BASE


async def run(w):
    ap.reset(ap.fixture([("aa", 5000), ("bb", 2500)]))
    ta = ap.login("aa")
    s, a, _ = call("POST", "/authorizations", {"to_handle": "bb", "amount": 2000}, token=ta, key=k())
    aid = a["authorization_id"]
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await (await b.new_context(viewport={"width": w, "height": 800})).new_page()
        await pg.goto(BASE + "/login")
        await pg.fill("[data-testid=login-email]", "bb@audit.invalid")
        await pg.fill("[data-testid=login-password]", "pw-bb-12345")
        await pg.click("[data-testid=login-submit]")
        await pg.wait_for_selector("[data-testid=current-user]")
        await pg.goto(BASE + "/authorizations")
        sel = "[data-testid=authorization-capture-amount-%s]" % aid
        await pg.wait_for_selector(sel)
        pre = await pg.input_value(sel)
        await pg.fill(sel, "25.00")
        await pg.click("[data-testid=authorization-capture-%s]" % aid)
        err = True
        try:
            await pg.wait_for_selector("[data-testid=authorization-error]", state="visible", timeout=4000)
        except Exception:
            err = False
        await pg.wait_for_timeout(800)
        after = await pg.input_value(sel)
        m = call("GET", "/me", token=ta)[1]
        await b.close()
    return {"width": w, "prefill": pre, "error_shown": err, "input_after": after, "payer_held": m["held"], "payer_total": m["total"]}


out = [asyncio.run(run(w)) for w in (375, 1280)]
print(json.dumps(out))
print("REPRODUCED" if all(o["error_shown"] and o["input_after"] != "25.00" for o in out) else "NOT_REPRODUCED")
