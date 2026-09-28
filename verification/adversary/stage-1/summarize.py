"""Turn results.json into a per-obligation summary (requirements, decisions, risk probes)."""
import json
import sys
from collections import defaultdict

rows = json.load(open(sys.argv[1], encoding="utf-8"))
by = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0, "tests": []})
counts = defaultdict(int)
for r in rows:
    cls = "risk" if r["risk"] else ("decision" if r["decisions"] else "requirement")
    counts[(cls, r["outcome"])] += 1
    for o in r["obligations"] or ["(untagged)"]:
        e = by[o]
        e[r["outcome"]] += 1
        if r["outcome"] != "passed":
            e["tests"].append(f'{r["outcome"]}: {r["test"]} [{cls}{" " + ",".join(r["decisions"]) if r["decisions"] else ""}]')

print("# Adversary stage-1 results by obligation\n")
print("| class | passed | failed | skipped |\n|---|---|---|---|")
for cls in ("requirement", "decision", "risk"):
    print(f"| {cls} | {counts[(cls, 'passed')]} | {counts[(cls, 'failed')]} | {counts[(cls, 'skipped')]} |")
print("\n| obligation | passed | failed | skipped |\n|---|---|---|---|")
for o in sorted(by):
    e = by[o]
    print(f"| {o} | {e['passed']} | {e['failed']} | {e['skipped']} |")
print("\n## Non-passing tests\n")
for o in sorted(by):
    for t in by[o]["tests"]:
        print(f"- {o}: {t}")
