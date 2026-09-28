"""Browser regression test for the capture input on /authorizations (S2-027, D2-19).

1. A refused capture (amount above the remainder) shows authorization-error and
   keeps the typed amount in authorization-capture-amount-{id}.
2. A successful partial non-final capture resets the prefill to the new
   remainder.

Runs at 375 px and 1280 px against a running service:

    python test/browser/capture_draft_test.py http://127.0.0.1:8080

Needs Python 3.12+ with Playwright and Chromium (`pip install playwright` and
`python -m playwright install chromium`). It resets the service state.
"""

import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8080"
PASSWORD = "correct horse"
FIXTURE = {
    "currency": "EUR",
    "minor_units": 2,
    "users": [
        {"id": "u_ada", "email": "ada@example.com", "password": PASSWORD,
         "display_name": "Ada", "handle": "ada", "balance": 10000},
        {"id": "u_bob", "email": "bob@example.com", "password": PASSWORD,
         "display_name": "Bob", "handle": "bob", "balance": 2500},
    ],
}


def call(method, path, body=None, token=None, key=None):
    headers = {"content-type": "application/json", "accept": "application/json"}
    if token:
        headers["authorization"] = "Bearer " + token
    if key:
        headers["idempotency-key"] = key
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as res:
        text = res.read()
        return json.loads(text) if text else None


def check(cond, what):
    if not cond:
        raise AssertionError(what)
    print("ok  ", what)


def run(browser, width):
    call("POST", "/_test/reset", FIXTURE)
    ada = call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD})["token"]
    auth = call("POST", "/authorizations", {"to_handle": "bob", "amount": 2000}, ada, f"draft-{width}")
    aid = auth["authorization_id"]

    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(BASE + "/login")
    page.get_by_test_id("login-email").fill("bob@example.com")
    page.get_by_test_id("login-password").fill(PASSWORD)
    page.get_by_test_id("login-submit").click()
    page.wait_for_url(BASE + "/")
    page.goto(BASE + "/authorizations")

    amount = page.get_by_test_id(f"authorization-capture-amount-{aid}")
    amount.wait_for()
    check(amount.input_value() == "20.00", f"{width}px: prefill is the remainder 20.00")

    # 1. A refused capture keeps the typed amount.
    amount.fill("25.00")
    page.get_by_test_id(f"authorization-capture-{aid}").click()
    page.get_by_test_id("authorization-error").wait_for()
    page.get_by_test_id(f"authorization-item-{aid}").wait_for()
    page.wait_for_load_state("networkidle")
    check(page.get_by_test_id(f"authorization-capture-amount-{aid}").input_value() == "25.00",
          f"{width}px: the typed 25.00 is kept after the refusal")
    check(page.get_by_test_id(f"authorization-item-{aid}").get_attribute("data-status") == "open",
          f"{width}px: the hold stays open")

    # 2. A successful partial non-final capture resets the prefill to the new remainder.
    page.get_by_test_id(f"authorization-capture-amount-{aid}").fill("7.00")
    page.get_by_label("Keep the rest on hold").check()
    page.get_by_test_id(f"authorization-capture-{aid}").click()
    page.get_by_test_id("authorization-success").wait_for()
    page.wait_for_load_state("networkidle")
    check(page.get_by_test_id("authorization-error").count() == 0, f"{width}px: no error after success")
    check(page.get_by_test_id(f"authorization-capture-amount-{aid}").input_value() == "13.00",
          f"{width}px: the prefill follows the new remainder 13.00")
    check(page.get_by_test_id("wallet-available").get_attribute("data-amount") == "3200",
          f"{width}px: bob's available is 2500 + 700")
    page.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for width in (375, 1280):
                run(browser, width)
        finally:
            browser.close()
    print("PASS capture_draft_test")


if __name__ == "__main__":
    main()
