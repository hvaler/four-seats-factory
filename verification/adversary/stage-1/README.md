# Adversary stage-1 suite (fskit-001)

This is an independent black-box HTTP suite for Pocketful stage 1. It was derived from
`pocketful/spec/stage-1.md` (SHA-256 `65497dea…0aa4`) and register r2
(`analyst@8e913edb`). It does not use the product source, the harness or the shipped
public tests.

- Every test carries `@pytest.mark.obl("S1-…")`.
- Tests that depend on an analyst decision also carry `@pytest.mark.decision("D-…")`.
- Optional robustness probes are in `test_risk.py` and marked `risk`. Their failures are
  reported separately and are not contract defects.
- `xc` tests need a second, independent container (`ADV_BASE_URL_B`).
- Export bodies are held only in memory. Response reprs redact `token` and `state` (S1-181).

## Run

```sh
python3 -m venv ~/adv-venv && ~/adv-venv/bin/pip install -r requirements.txt
git clone C:/nexus/dev/band-kit/result <clone>; git -C <clone> checkout --detach <sha>
bash run.sh <clone> <sha> <new-out-dir>
```

`run.sh` does the following:

1. Builds `stage-1/` with `--no-cache`.
2. Starts containers A and B with `--cpus 2 --memory 2g` and `-e PORT`, plus container C
   with PORT unset (S1-014), and measures the time to the first healthy response.
3. Runs pytest and writes `runner.log`, `build.log`, `pytest.log`, `junit.xml`,
   `results.json`, `summary.md`, the container logs and `SHA256SUMS`.
