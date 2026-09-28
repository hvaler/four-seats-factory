"""Stage-2 UI rows in a real Chromium at 375 and 1280 px (S2-010..035, S2-901)."""
import os
import re
import time

import pytest
from playwright.sync_api import expect, sync_playwright

from adv2 import Api, W2, auth_rec, fmt, fx2, new_key, user
from ui2 import (T, WIDTHS, NetLog, amount_of, assert_no_hscroll, fill_amount, goto, login, shot, tid)

pytestmark = pytest.mark.ui
ROUTES = ["/", "/requests", "/split", "/authorizations"]


@pytest.fixture(scope="module")
def pw():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(params=WIDTHS, ids=lambda w: f"w{w}")
def page(pw, request):
    ctx = pw.new_context(viewport={"width": request.param, "height": 900})
    pg = ctx.new_page()
    pg.width = request.param
    dialogs = []
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.dialogs = dialogs
    yield pg
    ctx.close()


@pytest.fixture
def base(api):
    return api.base


def world(api, **kw):
    return W2(api, fx2(**kw))


def feed_ids(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('[data-testid="activity-list"] [data-testid^="activity-item-"]'))
        .map(e => e.getAttribute('data-testid').slice('activity-item-'.length))""")


# --- routes, auth ---------------------------------------------------------------------------

@pytest.mark.obl("S2-010", "S2-012", "S2-032", "S2-034", "S2-901")
def test_routes_deep_link_signed_in(api, page, base):
    world(api)
    login(page, base, "ada@example.com")
    for r in ROUTES + ["/signup", "/login"]:
        goto(page, base, r)
        if r in ROUTES:
            expect(tid(page, "current-user")).to_contain_text("Ada", timeout=T)
            assert tid(page, "current-handle").inner_text().strip() == "ada"
        assert_no_hscroll(page, r)
        shot(page, f"route{r.replace('/', '_') or '_root'}-w{page.width}")


@pytest.mark.obl("S2-012")
def test_login_error_logout_and_signed_out(api, page, base):
    world(api)
    goto(page, base, "/login")
    expect(tid(page, "auth-error")).to_have_count(0)
    tid(page, "login-email").fill("ada@example.com")
    tid(page, "login-password").fill("wrong password")
    tid(page, "login-submit").click()
    expect(tid(page, "auth-error")).to_be_visible(timeout=T)
    login(page, base, "ada@example.com")
    expect(tid(page, "auth-error")).to_have_count(0)
    tid(page, "logout-button").click()
    expect(tid(page, "current-user")).to_have_count(0, timeout=T)
    for r in ROUTES:
        goto(page, base, r)
        expect(tid(page, "current-user")).to_have_count(0)
        assert tid(page, "wallet-balance").count() == 0 or "100.00 EUR" not in page.content()
        assert "ada@example.com" not in page.content()


@pytest.mark.obl("S2-012", "S1-033")
def test_signup_ui(api, page, base):
    world(api)
    goto(page, base, "/signup")
    for email, pw_, err in [("ada@example.com", "long enough pw", True), ("x.y@example.com", "short", True)]:
        tid(page, "signup-email").fill(email)
        tid(page, "signup-password").fill(pw_)
        tid(page, "signup-display-name").fill("Xavier")
        tid(page, "signup-submit").click()
        expect(tid(page, "auth-error")).to_be_visible(timeout=T)
    tid(page, "signup-email").fill("Zoe.K@example.com")
    tid(page, "signup-password").fill("long enough pw")
    tid(page, "signup-display-name").fill("Zoe")
    tid(page, "signup-submit").click()
    expect(tid(page, "current-user")).to_contain_text("Zoe", timeout=T)
    assert tid(page, "current-handle").inner_text().strip() == "zoe_k"


# --- wallet and pay --------------------------------------------------------------------------

@pytest.mark.obl("S2-013", "S2-015", "S2-026")
@pytest.mark.parametrize("cur,mu,bal,text", [("EUR", 2, 10000, "100.00 EUR"), ("JPY", 0, 1200, "1200 JPY"),
                                             ("BHD", 3, 1500, "1.500 BHD"), ("EUR", 2, 123456789, "1234567.89 EUR")])
def test_wallet_formatting(api, page, base, cur, mu, bal, text):
    fx = fx2(currency=cur, minor_units=mu)
    fx["users"][0]["balance"] = bal
    W2(api, fx)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    wb, wa = tid(page, "wallet-balance"), tid(page, "wallet-available")
    expect(wb).to_have_text(text, timeout=T)
    assert amount_of(wb) == bal and amount_of(wa) == bal
    expect(wa).to_have_text(text)
    expect(tid(page, "wallet-held")).to_have_count(0)


@pytest.mark.obl("S2-014", "S2-016", "S2-020", "S2-013")
def test_pay_decimal_keep_values_no_duplicate(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    net = NetLog(page)
    tid(page, "pay-handle").fill("bob")
    fill_amount(page, "pay-amount", "15.5")
    tid(page, "pay-note").fill("dinner")
    tid(page, "pay-visibility").select_option("private")
    tid(page, "pay-submit").click()
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", "8450", timeout=T)
    assert w.me("bob")["total"] == 2500 + 1550
    for t, v in [("pay-handle", "bob"), ("pay-amount", "15.5"), ("pay-note", "dinner")]:
        assert tid(page, t).input_value() == v, t
    assert tid(page, "pay-visibility").input_value() == "private"
    expect(tid(page, "pay-error")).to_have_count(0)
    tid(page, "pay-submit").click()
    page.wait_for_timeout(1500)
    assert w.me("bob")["total"] == 2500 + 1550, "resubmitting the unchanged form moved money again"
    expect(tid(page, "pay-error")).to_have_count(0)
    tid(page, "pay-note").fill("dinner 2")
    tid(page, "pay-submit").click()
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", "6900", timeout=T)
    keys = [k for (_m, _p, k, _b) in net.writes("/payments")]
    assert len(set(keys)) == 2, keys  # unchanged resubmit reused the key (or sent nothing)
    ids = feed_ids(page)
    mine = [p for p in api.activity(w.tok["ada"], limit=200).json["payments"] if p["from_handle"] == "ada"]
    assert len([p for p in mine if p["amount"] == 1550]) == 2
    assert ids[:2] == [p["payment_id"] for p in mine[:2]]


@pytest.mark.obl("S2-014")
def test_double_click_one_payment(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    tid(page, "pay-handle").fill("bob")
    fill_amount(page, "pay-amount", "1.00")
    tid(page, "pay-submit").dblclick()
    page.wait_for_timeout(2000)
    assert w.me("bob")["total"] == 2600


@pytest.mark.obl("S2-016")
@pytest.mark.parametrize("bad", ["15.005", "abc", "-5", "1e3", "", "1,000.00", "12.3.4"])
def test_pay_bad_decimal_sends_nothing(api, page, base, bad):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    net = NetLog(page)
    tid(page, "pay-handle").fill("bob")
    fill_amount(page, "pay-amount", bad)
    tid(page, "pay-submit").click()
    expect(tid(page, "pay-error")).to_be_visible(timeout=T)
    page.wait_for_timeout(500)
    assert net.writes("/payments") == [], net.writes("/payments")
    assert w.me("ada")["total"] == 10000


@pytest.mark.obl("S2-016")
@pytest.mark.decision("D2-05")
@pytest.mark.parametrize("cur,mu,typed,minor", [("JPY", 0, "15", 15), ("BHD", 3, "1.5", 1500), ("EUR", 2, "15", 1500),
                                                ("EUR", 2, " 2.50 ", 250)])
def test_decimal_conversion(api, page, base, cur, mu, typed, minor):
    w = W2(api, fx2(currency=cur, minor_units=mu))
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    tid(page, "pay-handle").fill("bob")
    fill_amount(page, "pay-amount", typed)
    tid(page, "pay-submit").click()
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", str(10000 - minor), timeout=T)


@pytest.mark.obl("S2-016")
@pytest.mark.decision("D2-05")
def test_jpy_rejects_decimal_point(api, page, base):
    w = W2(api, fx2(currency="JPY", minor_units=0))
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    net = NetLog(page)
    tid(page, "pay-handle").fill("bob")
    fill_amount(page, "pay-amount", "15.0")
    tid(page, "pay-submit").click()
    expect(tid(page, "pay-error")).to_be_visible(timeout=T)
    assert net.writes("/payments") == []


@pytest.mark.obl("S2-022", "S2-013")
def test_refused_payment_other_client_spent(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    api.pay(w.tok["ada"], "dee", 9500)  # another client spends
    tid(page, "pay-handle").fill("bob")
    fill_amount(page, "pay-amount", "10.00")
    tid(page, "pay-note").fill("keep me")
    tid(page, "pay-submit").click()
    expect(tid(page, "pay-error")).to_be_visible(timeout=T)
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", "500", timeout=T)
    assert [tid(page, t).input_value() for t in ("pay-handle", "pay-amount", "pay-note")] == ["bob", "10.00", "keep me"]


@pytest.mark.obl("S2-013")
def test_request_form(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    tid(page, "request-handle").fill("ada")
    fill_amount(page, "request-amount", "3.00")
    tid(page, "request-submit").click()
    expect(tid(page, "request-error")).to_be_visible(timeout=T)  # self_request
    tid(page, "request-handle").fill("cy")
    fill_amount(page, "request-amount", "3.00")
    tid(page, "request-note").fill("taxi")
    tid(page, "request-submit").click()
    page.wait_for_timeout(1500)
    got = [r for r in api.requests(w.tok["cy"]).json["requests"] if r["requester_handle"] == "ada"]
    assert len(got) == 1 and got[0]["amount"] == 300 and got[0]["note"] == "taxi"


# --- feed ----------------------------------------------------------------------------------------

@pytest.mark.obl("S2-017", "S1-039")
def test_feed_items(api, page, base):
    w = world(api)
    p1 = api.pay(w.tok["ada"], "bob", 1, visibility="private").json
    p2 = api.pay(w.tok["bob"], "cy", 250, note="").json
    p3 = api.pay(w.tok["cy"], "dee", 1, visibility="private").json   # hidden from ada
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    ids = feed_ids(page)
    assert ids[:2] == [p2["payment_id"], p1["payment_id"]] and p3["payment_id"] not in ids and ids[-1] == "p_1"
    it = tid(page, f"activity-item-{p1['payment_id']}")
    assert it.get_attribute("data-visibility") == "private"
    assert tid(page, f"activity-item-{p2['payment_id']}").get_attribute("data-visibility") == "public"
    parties = tid(page, f"activity-parties-{p2['payment_id']}").inner_text()
    assert "bob" in parties and "cy" in parties
    assert tid(page, f"activity-amount-{p2['payment_id']}").inner_text().strip() == "2.50 EUR"
    note = tid(page, f"activity-note-{p2['payment_id']}")
    expect(note).to_have_count(1)
    assert note.inner_text() == ""
    assert tid(page, "activity-note-p_1").inner_text() == "coffee"
    expect(tid(page, "empty-activity")).to_have_count(0)


@pytest.mark.obl("S2-017")
def test_empty_activity(api, page, base):
    W2(api, fx2(users=[user("u_x", "xan", 5), user("u_y", "yol", 5)], payments=[], requests=[],
                 settlement_operator_ids=[]))
    login(page, base, "xan@example.com")
    goto(page, base, "/")
    expect(tid(page, "empty-activity")).to_be_visible(timeout=T)
    goto(page, base, "/requests")
    expect(tid(page, "empty-requests")).to_be_visible(timeout=T)
    goto(page, base, "/authorizations")
    expect(tid(page, "empty-authorizations")).to_be_visible(timeout=T)


XSS = ['<img src=x onerror="window.__xss=1">', '</td><script>window.__xss=2</script>', '"><svg onload=window.__xss=3>']


@pytest.mark.obl("S2-035", "S1-098")
def test_notes_render_as_text(api, page, base):
    w = world(api)
    pays = [api.pay(w.tok["bob"], "ada", 1, note=n).json for n in XSS]
    rq = api.request(w.tok["bob"], "ada", 1, note=XSS[0]).json
    au = w.authorize("bob", "ada", 1, note=XSS[1]).json
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    for p, n in zip(pays, XSS):
        assert tid(page, f"activity-note-{p['payment_id']}").inner_text() == n
    goto(page, base, "/requests")
    assert XSS[0] in tid(page, f"request-item-{rq['request_id']}").inner_text()
    goto(page, base, "/authorizations")
    assert XSS[1] in tid(page, f"authorization-item-{au['authorization_id']}").inner_text()
    goto(page, base, "/split")
    assert page.evaluate("() => window.__xss === undefined"), "injected script ran"
    assert page.dialogs == []
    assert page.locator('img[src="x"], svg[onload]').count() == 0


# --- requests ------------------------------------------------------------------------------------

@pytest.mark.obl("S2-018", "S2-020")
def test_requests_screen(api, page, base):
    w = world(api)
    out_rq = api.request(w.tok["ada"], "cy", 700).json["request_id"]
    dec = api.request(w.tok["dee"], "ada", 5).json["request_id"]
    paid = api.request(w.tok["dee"], "ada", 6).json["request_id"]
    api.pay_request(w.tok["ada"], paid)
    login(page, base, "ada@example.com")
    goto(page, base, "/requests")
    inc, out = tid(page, "incoming-list"), tid(page, "outgoing-list")
    expect(inc.get_by_test_id("request-item-rq_1")).to_have_attribute("data-status", "pending", timeout=T)
    expect(out.get_by_test_id(f"request-item-{out_rq}")).to_be_visible()
    assert tid(page, "request-amount-rq_1").inner_text().strip() == "12.00 EUR"
    expect(tid(page, "request-pay-rq_1")).to_be_visible()
    expect(tid(page, "request-decline-rq_1")).to_be_visible()
    expect(tid(page, "request-cancel-rq_1")).to_have_count(0)
    expect(tid(page, f"request-cancel-{out_rq}")).to_be_visible()
    expect(tid(page, f"request-pay-{out_rq}")).to_have_count(0)
    for t in (f"request-pay-{paid}", f"request-decline-{paid}", f"request-cancel-{paid}"):
        expect(tid(page, t)).to_have_count(0)
    assert tid(page, f"request-item-{paid}").get_attribute("data-status") == "paid"
    tid(page, f"request-decline-{dec}").click()
    expect(tid(page, f"request-item-{dec}")).to_have_attribute("data-status", "declined", timeout=T)
    tid(page, "request-pay-rq_1").click()
    expect(tid(page, "request-item-rq_1")).to_have_attribute("data-status", "paid", timeout=T)
    expect(tid(page, "request-pay-rq_1")).to_have_count(0)
    tid(page, f"request-cancel-{out_rq}").click()
    expect(tid(page, f"request-item-{out_rq}")).to_have_attribute("data-status", "cancelled", timeout=T)
    assert w.me("ada")["total"] == 10000 - 6 - 1200


@pytest.mark.obl("S2-023")
def test_stale_request_pay_button(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/requests")
    expect(tid(page, "request-pay-rq_1")).to_be_visible(timeout=T)
    api.call("POST", "/requests/rq_1/cancel", token=w.tok["bob"])
    tid(page, "request-pay-rq_1").click()
    expect(tid(page, "request-error")).to_be_visible(timeout=T)
    expect(tid(page, "request-pay-rq_1")).to_have_count(0, timeout=T)
    assert w.me("ada")["total"] == 10000


# --- split ---------------------------------------------------------------------------------------

@pytest.mark.obl("S2-019")
@pytest.mark.parametrize("amount,handles,expect_shares", [
    ("10.00", "bob, ada ,cy", [("bob", "3.34 EUR"), ("ada", "3.33 EUR"), ("cy", "3.33 EUR")]),
    ("10.00", "cy,bob,ada", [("cy", "3.34 EUR"), ("bob", "3.33 EUR"), ("ada", "3.33 EUR")]),
    ("0.01", "bob,cy,dee", [("bob", "0.01 EUR"), ("cy", "0.00 EUR"), ("dee", "0.00 EUR")]),
])
def test_split_preview_matches_server(api, page, base, amount, handles, expect_shares):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/split")
    net = NetLog(page)
    fill_amount(page, "split-amount", amount)
    tid(page, "split-handles").fill(handles)
    tid(page, "split-note").fill("dinner")
    prev = tid(page, "split-preview")
    for h, txt in expect_shares:
        expect(prev.get_by_test_id(f"split-share-{h}")).to_have_text(txt, timeout=T)
    assert net.writes("/splits") == []
    tid(page, "split-submit").click()
    page.wait_for_timeout(1500)
    posted = net.writes("/splits")
    assert len(posted) == 1
    others = [h for h, _ in expect_shares if h != "ada"]
    for h in others:
        rqs = [r for r in api.requests(w.tok[h]).json["requests"] if r["note"] == "dinner"]
        want = dict(expect_shares)[h]
        assert len(rqs) == 1 and fmt(rqs[0]["amount"], 2, "EUR") == want


@pytest.mark.obl("S2-019", "S2-016")
def test_split_errors(api, page, base):
    world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/split")
    net = NetLog(page)
    fill_amount(page, "split-amount", "1.005")
    tid(page, "split-handles").fill("bob")
    tid(page, "split-submit").click()
    expect(tid(page, "split-error")).to_be_visible(timeout=T)
    assert net.writes("/splits") == []
    fill_amount(page, "split-amount", "1.00")
    tid(page, "split-handles").fill("bob,ghost")
    tid(page, "split-submit").click()
    expect(tid(page, "split-error")).to_be_visible(timeout=T)


# --- competing clients, uncertain writes -----------------------------------------------------------

@pytest.mark.obl("S2-021")
def test_latest_refresh_wins(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    tid(page, "pay-handle").fill("bob")
    held = []
    mode = {"hold": False}

    def handler(route):
        req = route.request
        if mode["hold"] and req.method == "GET" and req.resource_type in ("fetch", "xhr"):
            held.append((route, route.fetch()))
        else:
            route.continue_()

    page.route("**/*", handler)
    mode["hold"] = True
    tid(page, "wallet-refresh").click()
    page.wait_for_timeout(700)
    mode["hold"] = False
    assert held, "the refresh sent no fetch/xhr GET (cannot apply latest-refresh-wins test)"
    api.pay(w.tok["dee"], "ada", 700)
    tid(page, "wallet-refresh").click()
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", "10700", timeout=T)
    for route, resp in held:
        try:
            route.fulfill(response=resp)
        except Exception:
            pass
    page.wait_for_timeout(1500)
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", "10700")
    expect(tid(page, "wallet-available")).to_have_attribute("data-amount", "10700")
    assert tid(page, "pay-handle").input_value() == "bob"
    page.unroute("**/*")


@pytest.mark.obl("S2-024")
def test_lost_payment_response_after_commit(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    net = NetLog(page)
    lost = {"n": 0}

    def handler(route):
        if route.request.method == "POST" and lost["n"] == 0:
            lost["n"] += 1
            route.fetch()          # the server commits the payment
            route.abort("failed")  # ...but the browser never sees the response
        else:
            route.continue_()

    page.route("**/payments", handler)
    tid(page, "pay-handle").fill("bob")
    fill_amount(page, "pay-amount", "4.00")
    tid(page, "pay-note").fill("lost")
    tid(page, "pay-submit").click()
    unc = tid(page, "pay-uncertain")
    expect(unc).to_be_visible(timeout=T)
    assert unc.inner_text().strip() != ""
    expect(tid(page, "pay-error")).to_have_count(0)
    assert w.me("bob")["total"] == 2900  # it did commit
    tid(page, "pay-submit").click()
    expect(tid(page, "pay-uncertain")).to_have_count(0, timeout=T)
    expect(tid(page, "pay-error")).to_have_count(0)
    expect(tid(page, "wallet-balance")).to_have_attribute("data-amount", "9600", timeout=T)
    assert w.me("bob")["total"] == 2900, "the retry moved money twice"
    posts = net.writes("/payments")
    assert len(posts) == 2 and posts[0][2] == posts[1][2] and posts[0][3] == posts[1][3], posts
    page.unroute("**/payments")


# --- authorizations UI ----------------------------------------------------------------------------

@pytest.mark.obl("S2-026", "S2-028", "S2-030")
def test_seeded_hold_headline(api, page, base):
    W2(api, fx2(authorizations=[auth_rec("a_seed", "u_ada", "u_bob", 2500)]))
    login(page, base, "ada@example.com")
    goto(page, base, "/")
    expect(tid(page, "wallet-available")).to_have_text("75.00 EUR", timeout=T)
    assert amount_of(tid(page, "wallet-available")) == 7500
    expect(tid(page, "wallet-held")).to_have_text("25.00 EUR")
    assert amount_of(tid(page, "wallet-held")) == 2500
    expect(tid(page, "wallet-balance")).to_have_text("100.00 EUR")
    sizes = page.evaluate("""() => ['wallet-available','wallet-balance','wallet-held'].map(t => {
        const s = getComputedStyle(document.querySelector(`[data-testid="${t}"]`));
        return [parseFloat(s.fontSize), parseInt(s.fontWeight)]; })""")
    assert sizes[0][0] > sizes[1][0] and sizes[0][0] > sizes[2][0], f"available is not the headline: {sizes}"
    shot(page, f"wallet-with-hold-w{page.width}")


@pytest.mark.obl("S2-026", "S2-027", "S2-020")
def test_authorize_capture_void_ui(api, page, base):
    w = world(api)
    login(page, base, "ada@example.com")
    goto(page, base, "/authorizations")
    if tid(page, "authorize-handle").count() == 0:
        goto(page, base, "/")
    tid(page, "authorize-handle").fill("bob")
    fill_amount(page, "authorize-amount", "20.00")
    tid(page, "authorize-note").fill("deposit")
    tid(page, "authorize-visibility").select_option("private")
    tid(page, "authorize-submit").click()
    expect(tid(page, "wallet-held")).to_have_attribute("data-amount", "2000", timeout=T)
    expect(tid(page, "wallet-available")).to_have_attribute("data-amount", "8000")
    a1 = w.auths("ada").json["authorizations"][0]
    fill_amount(page, "authorize-amount", "30.01")
    tid(page, "authorize-handle").fill("cy")
    tid(page, "authorize-submit").click()
    page.wait_for_timeout(1500)
    a2 = [x for x in w.auths("ada").json["authorizations"] if x["to_handle"] == "cy"][0]
    fill_amount(page, "authorize-amount", "999.00")
    tid(page, "authorize-submit").click()
    expect(tid(page, "authorize-error")).to_be_visible(timeout=T)
    goto(page, base, "/authorizations")
    item = tid(page, f"authorization-item-{a1['authorization_id']}")
    expect(item).to_have_attribute("data-status", "open", timeout=T)
    assert tid(page, f"authorization-amount-{a1['authorization_id']}").inner_text().strip() == "20.00 EUR"
    assert tid(page, f"authorization-expires-{a1['authorization_id']}").inner_text().strip() == a1["expires_at"]
    expect(tid(page, f"authorization-void-{a1['authorization_id']}")).to_be_visible()
    expect(tid(page, f"authorization-capture-{a1['authorization_id']}")).to_have_count(0)
    tid(page, f"authorization-void-{a2['authorization_id']}").click()
    expect(tid(page, f"authorization-item-{a2['authorization_id']}")).to_have_attribute("data-status", "voided", timeout=T)
    expect(tid(page, "wallet-held")).to_have_attribute("data-amount", "2000", timeout=T)
    # the receiver captures part of it
    tid(page, "logout-button").click()
    login(page, base, "bob@example.com")
    goto(page, base, "/authorizations")
    aid = a1["authorization_id"]
    pre = tid(page, f"authorization-capture-amount-{aid}")
    expect(pre).to_have_value("20.00", timeout=T)
    expect(tid(page, f"authorization-void-{aid}")).to_have_count(0)
    fill_amount(page, f"authorization-capture-amount-{aid}", "25.00")
    tid(page, f"authorization-capture-{aid}").click()
    expect(tid(page, "authorization-error")).to_be_visible(timeout=T)
    assert pre.input_value() == "25.00"
    fill_amount(page, f"authorization-capture-amount-{aid}", "5.00")
    tid(page, f"authorization-capture-{aid}").click()
    page.wait_for_timeout(1500)
    assert w.me("ada")["total"] == 9500 and w.me("bob")["total"] == 3000
    status = tid(page, f"authorization-item-{aid}").get_attribute("data-status")
    # the spec does not say whether the UI capture is final: accept either reading, consistently
    if status == "captured":
        expect(tid(page, f"authorization-captured-{aid}")).to_have_text("5.00 EUR")
        expect(tid(page, f"authorization-capture-{aid}")).to_have_count(0)
        assert w.held("ada") == 0
    else:
        assert status == "open", status
        expect(tid(page, f"authorization-captured-{aid}")).to_have_count(0)
        expect(tid(page, f"authorization-capture-amount-{aid}")).to_have_value("15.00", timeout=T)
        assert w.held("ada") == 1500
    ids = page.evaluate("""() => Array.from(document.querySelectorAll('[data-testid="authorization-list"] [data-testid^="authorization-item-"]'))
        .map(e => e.getAttribute('data-testid').slice('authorization-item-'.length))""")
    api_order = [x["authorization_id"] for x in w.auths("bob").json["authorizations"]]
    assert ids == api_order


@pytest.mark.obl("S2-027")
def test_partial_capture_prefill_follows_remainder(api, page, base):
    w = world(api)
    aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
    w.capture("bob", aid, {"amount": 700, "final": False})
    login(page, base, "bob@example.com")
    goto(page, base, "/authorizations")
    expect(tid(page, f"authorization-capture-amount-{aid}")).to_have_value("13.00", timeout=T)
    expect(tid(page, f"authorization-item-{aid}")).to_have_attribute("data-status", "open")
    expect(tid(page, f"authorization-captured-{aid}")).to_have_count(0)


# --- quality proxies, labels, focus, overflow ----------------------------------------------------

@pytest.mark.obl("S2-033")
def test_inputs_have_visible_labels_and_focus_ring(api, page, base):
    world(api)
    login(page, base, "ada@example.com")
    missing = []
    for r in ["/", "/split", "/authorizations"]:
        goto(page, base, r)
        missing += page.evaluate("""(route) => Array.from(document.querySelectorAll('input[data-testid],select[data-testid],textarea[data-testid]'))
            .filter(e => e.offsetParent !== null)
            .filter(e => {
              const labs = Array.from(e.labels || []).filter(l => l.offsetParent !== null && l.innerText.trim());
              const lb = e.getAttribute('aria-labelledby');
              const byId = lb && lb.split(' ').some(id => { const x = document.getElementById(id); return x && x.innerText.trim(); });
              return !(labs.length || byId);
            }).map(e => route + ' ' + e.getAttribute('data-testid'))""", r)
    assert missing == [], f"inputs without a visible label: {missing}"
    goto(page, base, "/")
    tid(page, "pay-handle").focus()
    page.keyboard.press("Tab")
    ring = page.evaluate("""() => { const e = document.activeElement; const s = getComputedStyle(e);
        return [e.getAttribute('data-testid'), s.outlineStyle, s.outlineWidth, s.boxShadow]; }""")
    assert ring[1] != "none" and ring[2] != "0px" or ring[3] not in ("none", ""), f"no visible focus indicator: {ring}"


@pytest.mark.obl("S2-032")
def test_no_horizontal_scroll_worst_case(api, page, base):
    long_name = "Maximiliana " * 6
    users = [user("u_ada", "ada", 10**9 * 10), user("u_x", "abcdefghijklmnopqrst", 10**9, name=long_name.strip())]
    pays = [{"id": f"p_{i}", "from_user_id": "u_ada", "to_user_id": "u_x", "amount": 1000000000,
             "note": "N" * 200, "visibility": "public"} for i in range(55)]
    reqs = [{"id": f"rq_{i}", "requester_id": "u_x", "payer_id": "u_ada", "amount": 1000000000,
             "note": "R" * 200, "status": "pending"} for i in range(8)]
    auths = [auth_rec(f"a_{i}", "u_ada", "u_x", 1000000000, note="A" * 200) for i in range(3)]
    W2(api, fx2(users=users, payments=pays, requests=reqs, authorizations=auths, settlement_operator_ids=[]))
    for email in ("ada@example.com", "abcdefghijklmnopqrst@example.com"):
        login(page, base, email)
        for r in ROUTES:
            goto(page, base, r)
            assert_no_hscroll(page, f"{r} as {email}")
            shot(page, f"worst{r.replace('/', '_') or '_root'}-{email[:3]}-w{page.width}")
        tid(page, "logout-button").click()
