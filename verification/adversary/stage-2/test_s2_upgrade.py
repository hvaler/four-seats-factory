"""XC upgrade 1→2 (S2-040..044, S2-902) under D2-18.

Shape S1: page from the stage-2 origin (container A); before the switch its fetch/XHR go to the
ACCEPTED stage-1 container; the stage-1 export is imported into A; after the switch all goes to A.
Shape S2: as above, but the source is a stage-2 container B loaded with a stage-1 export.
Exports are held in memory only and never written (S1-181).
"""
import re

import pytest
from playwright.sync_api import expect, sync_playwright

from adv2 import Api, fixture, fx2, new_key, total
from ui2 import T, NetLog, fill_amount, goto, login, tid

pytestmark = [pytest.mark.ui, pytest.mark.xc, pytest.mark.upgrade]


@pytest.fixture(scope="module")
def pw():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def populate_stage1(s1):
    """Populate the ACCEPTED stage-1 service with every kind of state."""
    fx = fixture()  # a pure stage-1 fixture (no stage-2 fields)
    s1.reset(fx)
    tok = {u["handle"]: s1.login(u["email"]) for u in fx["users"]}
    rec = {"fx": fx, "tok": tok}
    rec["k_pay"] = new_key()
    rec["pay"] = s1.pay(tok["ada"], "bob", 321, key=rec["k_pay"], note="before upgrade")
    assert rec["pay"].status == 201
    rec["k_set"] = new_key()
    rec["set"] = s1.call("POST", "/settlements", {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 40}]},
                         token=tok["op"], key=rec["k_set"])
    assert rec["set"].status == 201
    rec["pending"] = s1.request(tok["bob"], "ada", 250, note="pending across upgrade").json["request_id"]
    return rec


def route_to(page, target_base, state):
    """Send fetch/XHR to state['data'] (a base URL); document and static assets load normally."""
    def handler(route):
        req = route.request
        if req.resource_type in ("fetch", "xhr") and state["data"] != target_base:
            url = re.sub(r"^https?://[^/]+", state["data"], req.url)
            resp = route.fetch(url=url)
            if state.get("lose_next_post") and req.method == "POST" and req.url.split("?")[0].endswith("/payments"):
                state["lose_next_post"] = False
                route.abort("failed")
                return
            route.fulfill(response=resp)
        else:
            route.continue_()
    page.route("**/*", handler)


def run_upgrade(pw, source, target, source_is_stage1):
    rec = populate_stage1(source["s1"])
    if not source_is_stage1:
        exp1 = source["s1"].call("GET", "/_test/export")
        assert source["src"].call("POST", "/_test/import", raw=exp1.raw).status == 204
    src = source["src"]
    target.reset(fx2())  # the target starts with unrelated state
    ctx = pw.new_context(viewport={"width": 375, "height": 900})
    page = ctx.new_page()
    state = {"data": src.base}
    route_to(page, target.base, state)
    net = NetLog(page)
    # sign in before the upgrade: the login call is served by the source
    login(page, target.base, "ada@example.com")
    goto(page, target.base, "/")
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", str(10000 - 321), timeout=T)
    # a pay whose response is lost after it committed on the source
    state["lose_next_post"] = True
    tid(page, "pay-handle").fill("cy")
    fill_amount(page, "pay-amount", "3.00")
    tid(page, "pay-note").fill("lost before export")
    tid(page, "pay-submit").click()
    expect(tid(page, "pay-uncertain")).to_be_visible(timeout=T)
    src_tok = rec["tok"]
    assert src.balance(src_tok["cy"]) == 40 + 300  # committed on the source
    # upgrade between browser requests
    exp = src.call("GET", "/_test/export")
    assert exp.status == 200
    assert target.call("POST", "/_test/import", raw=exp.raw).status == 204
    state["data"] = target.base
    # (a) still signed in with the old token
    expect(tid(page, "current-handle")).to_have_text("ada")
    me = target.me(src_tok["ada"])
    assert me["total"] == me["balance"] == me["available"] == 10000 - 321 - 300 and me["held"] == 0, me
    # (c) the retry recovers the original payment, money moves once
    tid(page, "pay-submit").click()
    expect(tid(page, "pay-uncertain")).to_have_count(0, timeout=T)
    expect(tid(page, "pay-error")).to_have_count(0)
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", str(10000 - 321 - 300), timeout=T)
    assert target.balance(src_tok["cy"]) == 340
    posts = net.writes("/payments")
    assert len(posts) == 2 and posts[0][2] == posts[1][2] and posts[0][3] == posts[1][3], posts
    # D2-13: the stage-1 receipt replays byte-for-byte on stage 2
    rp = target.pay(src_tok["ada"], "bob", 321, key=rec["k_pay"], note="before upgrade")
    assert rp.status == 200 and rp.raw == rec["pay"].raw, "replayed stage-1 receipt differs from the original"
    rs = target.call("POST", "/settlements", {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 40}]},
                     token=src_tok["op"], key=rec["k_set"])
    assert rs.status == 200 and rs.raw == rec["set"].raw
    # (b) the pending stage-1 request is payable from /requests
    goto(page, target.base, "/requests")
    expect(tid(page, "current-handle")).to_have_text("ada", timeout=T)
    tid(page, f"request-pay-{rec['pending']}").click()
    expect(tid(page, f"request-item-{rec['pending']}")).to_have_attribute("data-status", "paid", timeout=T)
    assert target.balance(src_tok["bob"]) == 2500 + 321 + 250
    # the imported state is live: operator, holds and totals
    tot = sum(target.balance(t) for t in src_tok.values())
    assert tot == total(rec["fx"])
    r = target.call("POST", "/authorizations", {"to_handle": "bob", "amount": 100}, token=src_tok["ada"], key=new_key())
    assert r.status == 201
    ctx.close()


@pytest.mark.obl("S2-040", "S2-041", "S2-042", "S2-043", "S2-044", "S2-902")
@pytest.mark.decision("D2-18", "D2-13")
def test_upgrade_1_to_2_from_stage1_container(pw, api_s1, api):
    run_upgrade(pw, {"s1": api_s1, "src": api_s1}, api, source_is_stage1=True)


@pytest.mark.obl("S2-040", "S2-041", "S2-042", "S2-043")
@pytest.mark.decision("D2-18")
def test_upgrade_2_to_2_after_stage1_import(pw, api_s1, api, api_b):
    run_upgrade(pw, {"s1": api_s1, "src": api_b}, api, source_is_stage1=False)
