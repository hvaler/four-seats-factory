"""Observation probe (not a finding): what the UI shows when a capture response is lost after commit.
Usage: ADV_BASE_URL=http://127.0.0.1:<port> python probe_lost_capture.py"""
import sys
sys.path.insert(0, "/mnt/c/nexus/dev/band-kit/wt/adversary/verification/adversary/stage-2")
from playwright.sync_api import sync_playwright
from adv2 import Api, W2, fx2
from ui2 import login, goto, tid, fill_amount

api = Api(); w = W2(api, fx2())
aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 900})
    login(pg, api.base, "bob@example.com"); goto(pg, api.base, "/authorizations")
    state = {"n": 0}
    def h(route):
        if route.request.method == "POST" and state["n"] == 0:
            state["n"] += 1; route.fetch(); route.abort("failed")
        else:
            route.continue_()
    pg.route("**/capture", h)
    fill_amount(pg, f"authorization-capture-amount-{aid}", "5.00")
    tid(pg, f"authorization-capture-{aid}").click(); pg.wait_for_timeout(1500)
    shown = pg.evaluate("""() => Array.from(document.querySelectorAll('[data-testid^="authorization-"]'))
        .filter(e => /error|uncertain|success/.test(e.getAttribute('data-testid')) && e.offsetParent !== null)
        .map(e => [e.getAttribute('data-testid'), e.innerText.trim(), getComputedStyle(e).color, e.className])""")
    print("after lost capture:", shown)
    print("server: bob total", w.me("bob")["total"], "ada held", w.held("ada"),
          "status", [x["status"] for x in w.auths("bob").json["authorizations"]])
    print("input now:", repr(tid(pg, f"authorization-capture-amount-{aid}").input_value()) if tid(pg, f"authorization-capture-amount-{aid}").count() else "absent")
    pg.unroute("**/capture")
    if tid(pg, f"authorization-capture-{aid}").count():
        tid(pg, f"authorization-capture-{aid}").click(); pg.wait_for_timeout(1500)
        print("after retry click:", pg.evaluate("""() => Array.from(document.querySelectorAll('[data-testid^="authorization-"]'))
            .filter(e => /error|uncertain|success/.test(e.getAttribute('data-testid')) && e.offsetParent !== null)
            .map(e => [e.getAttribute('data-testid'), e.innerText.trim()])"""), "bob total", w.me("bob")["total"])
    b.close()
