# fskit-001 · Stage 1 · Adversary verification bundle, candidate 1

This is the adversary's challenge result. It is not an acceptance verdict: only the auditor accepts, after independent reproduction.

## Revisions

| Item | Value |
|---|---|
| Candidate commit | `beeaec72ff53fa75469c5f09236a786632f21fd8` (`result`, main) |
| Candidate `stage-1` tree | `347efba502629e5b5bbd730f35c34bdfe208c478` (checked in my clone) |
| Review clone | `C:\nexus\dev\band-kit\clones\adversary-s1-1`, fresh clone detached at the candidate, `status --porcelain` empty |
| Test revision used for the passing runs | `63c6adbbceecfa2147453ad261d7ffcc95649a94`, suite tree `25429c141698f3472ff6928170a93e48cdc909a3`, branch `adversary` |
| Earlier test revision | `40d6c304aa0d38d2216885fe1c5226cb01a67727` (v1; its run is preserved as event 002) |
| Spec | `pocketful/spec/stage-1.md` SHA-256 `65497dea09a8b432598c71662320cf66c3550e183cfd76e2d7f97318e0d30aa4` |
| Register | r2, `analyst@8e913edb` |
| Tools | Python 3.12.3 with pytest 9.1.1 and httpx 0.28.1 (`~/adv-venv`, pinned in `requirements.txt`); Docker 29.8.0 in WSL2; model `claude-opus-5-5` |

## Results (events in `events/`)

| Event | Check | Outcome |
|---|---|---|
| 001 | Official harness `--stage 1`, host mode, `--out checks/fskit-001-s1-adversary-1` | **PASS.** 147/147, with 0 failed, 0 errors, 0 skipped and 0 deselected. `claimed_stage 1`. The stage-2 probe fails as expected (Playwright `Page.fill` timeout; there is no UI). `report.json` sha256 `a417b148…a1aa`, `stage-1.log` `7a564f0a…bd58`. |
| 002 | Suite v1, full run (`c1-run1/`) | **TOOL_FAIL.** 288 passed and 13 failed. All 13 are the `"Bearer "` case (a trailing space): httpx raised `Illegal header value` on the client side, so no request reached the service. This was my test bug, not a product defect. The run is preserved. |
| 003 | Suite v2, full run (`c1-run2/`) | **PASS.** 301/301: 268 requirement, 25 decision and 8 risk tests. The XC A→B import passed. With PORT unset the service answers on 8080. Every container was healthy within 1 s. No OOM, no restart. |
| 004 | CONC tests repeated 10 times, each with a fresh `--no-cache` image and fresh containers (`c1-conc-r1..r10/`) | **PASS.** 200/200 (20 tests × 10). **0 intermittent failures.** |
| 005 | Inspection of the delivered files | **PASS.** The routes are exactly the 16 spec routes: no deposit or withdraw surface and no stage-2 code. There are no symlinks, submodules or nested .git. The base image is pinned by digest and there are no dependencies. Passwords use scrypt. Nothing detects tests or fixtures. |

Each run folder has its own `SHA256SUMS`. `summary.md` gives pass and fail counts per obligation ID.

## Commands

```sh
# harness (event 001)
wsl -e bash -lc 'cd /mnt/c/nexus/dev/dark-factory-wearedevs && ~/df-venv/bin/python -m harness run --track pocketful --repo /mnt/c/nexus/dev/band-kit/clones/adversary-s1-1 --stage 1 --out /mnt/c/nexus/dev/band-kit/checks/fskit-001-s1-adversary-1'
# suite (events 002/003); the out dir must be new
ADV_TEST_REV=63c6adbb… bash /mnt/c/nexus/dev/band-kit/wt/adversary/verification/adversary/stage-1/run.sh \
  /mnt/c/nexus/dev/band-kit/clones/<clone> beeaec72ff53fa75469c5f09236a786632f21fd8 <new-out-dir>
# CONC repetitions (event 004): the same command with ADV_PYTEST_ARGS=-kconcurrency, 10 times
```

The runner builds `stage-1/` with `--no-cache`. It starts containers A and B with `--cpus 2 --memory 2g --memory-swap 2g -e PORT` on random loopback ports, and container C with PORT unset. It waits for `/health` to return 200 (at most 60 s), runs pytest with `--assert=plain`, and then collects the container logs and `docker stats`. Export bodies are held only in memory, and response reprs redact `token` and `state`. I scanned the evidence folders: they contain no tokens, password hashes or export states.

## What remains untested or only partly tested

1. **S1-001/002, transient states.** Cross-wallet transient atomicity is observed only through proxies. Every balance read during load was ≥ 0, the final sums were conserved, and successful debits matched what the balances allowed. Export state is opaque, so it was not used as a mid-load snapshot.
2. **S1-012 / S1-013.** I did not run isolated mode; the auditor did (auditor-003). My 2-vCPU limit is Docker's `--cpus 2` on a 6-CPU host. Timings measured here are not measurements on dedicated hardware.
3. **S1-017.** The content type is checked on /health, /me and one error response, not on every endpoint.
4. **S1-019.** Unknown fields are checked on payments, settlement entries and pay, but not on signup, login, requests or splits bodies.
5. **S1-050 / D-25.** A wrong method and an unknown route are checked for the envelope and a 4xx status only. The specific code (405 / 404) is not asserted.
6. **S1-175.** The snapshot property is shown by restoring an earlier export after a later write. Export consistency *during* concurrent writes is not tested.
7. **D-23 / D-24.** Import rejection is tested with structural mutations only: missing or wrong track, version or state, and an empty state. It is not tested with a tampered inner state. Reset content errors other than a negative balance (dangling references, duplicates, bad status, `minor_units`) are not tested.
8. **Scale.** The largest fixture was 100 users, and the longest history about 60 payments. Latency with a long history (>10k records) is not tested.
9. **Not tested at all:** a non-ASCII `Idempotency-Key`; an empty `display_name` (D-09); 401 on an unknown route; resets or imports racing live traffic (outside the contract; by code review, a signup in flight across a swap linearizes after it).
10. **XC.** One A→B pair: two independent containers from the same image on the same Docker daemon.
11. **Repetitions.** 10 CONC repetitions on one host. A race with a probability below about 1/200 per test could go unseen.
12. **Hidden tests.** The shipped harness checks are a partial sample, and nothing here predicts the hidden suite.

## Usage (METRICS)

`fskit-001,1,adversary,f603ac21-88ea-434a-844e-bb621f8da63e,Claude Code,claude-opus-5-5,2026-09-28T20:49:24Z,2026-09-28T21:22:50Z,2006,unknown,unknown,unknown,unknown,,true,wall clock from shell and room timestamps,token counts are not exposed to this seat at run time`
