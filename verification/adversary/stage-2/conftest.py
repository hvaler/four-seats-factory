import json
import os

import pytest

from adv2 import Api, W2, fx2

_RESULTS = []


def pytest_configure(config):
    for m in ("obl(*ids): obligation ids", "decision(*ids): analyst decision ids",
              "risk: optional robustness probe", "xc: two containers", "ui: real browser",
              "upgrade: needs a stage-1 container (ADV_BASE_URL_S1)", "slow: waits on the clock"):
        config.addinivalue_line("markers", m)


def pytest_collection_modifyitems(config, items):
    for it in items:
        if "xc" in it.keywords and not os.environ.get("ADV_BASE_URL_B"):
            it.add_marker(pytest.mark.skip(reason="ADV_BASE_URL_B not set"))
        if "upgrade" in it.keywords and not os.environ.get("ADV_BASE_URL_S1"):
            it.add_marker(pytest.mark.skip(reason="ADV_BASE_URL_S1 not set"))


def pytest_runtest_makereport(item, call):
    if call.when != "call" and not (call.when == "setup" and call.excinfo is not None):
        return
    outcome = "passed" if call.excinfo is None else (
        "skipped" if call.excinfo.errisinstance(pytest.skip.Exception) else "failed")
    _RESULTS.append({"test": item.nodeid,
                     "obligations": [a for m in item.iter_markers("obl") for a in m.args],
                     "decisions": [a for m in item.iter_markers("decision") for a in m.args],
                     "risk": item.get_closest_marker("risk") is not None,
                     "phase": call.when, "outcome": outcome, "duration_s": round(call.duration, 3),
                     "error": None if call.excinfo is None else str(call.excinfo.value)[:2000]})


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("ADV_RESULTS")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_RESULTS, f, indent=1, ensure_ascii=False)


@pytest.fixture
def api():
    a = Api()
    yield a
    a.close()


@pytest.fixture
def api_b():
    a = Api(os.environ["ADV_BASE_URL_B"])
    yield a
    a.close()


@pytest.fixture
def api_s1():
    a = Api(os.environ["ADV_BASE_URL_S1"])
    yield a
    a.close()


@pytest.fixture
def w(api):
    return W2(api, fx2())
