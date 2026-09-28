#!/usr/bin/env bash
# Adversary stage-2 runner.
#   run.sh <stage2-clone> <candidate-sha> <stage1-clone-at-accepted> <out-dir>
# Builds stage-2/ of the candidate and stage-1/ of the ACCEPTED revision, starts independent
# containers under the limits, then runs (1) the stage-1 suite against stage-2/ (S2-904) and
# (2) the stage-2 suite (API, CONC, UI at 375/1280, XC upgrade 1->2). Exports are never written.
set -uo pipefail
CLONE=$1; SHA=$2; S1CLONE=$3; OUT=$4
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${ADV_PY:-$HOME/adv-venv/bin/python}
[ -e "$OUT" ] && { echo "out dir exists: $OUT"; exit 2; }
mkdir -p "$OUT"
exec > >(tee -a "$OUT/runner.log") 2>&1
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "== adversary stage-2 run $(ts)"
echo "candidate_sha=$SHA clone_head=$(git -C "$CLONE" rev-parse HEAD)"
echo "stage2_tree=$(git -C "$CLONE" rev-parse HEAD:stage-2) stage1_tree_in_candidate=$(git -C "$CLONE" rev-parse HEAD:stage-1)"
echo "clone_status_begin"; git -C "$CLONE" status --porcelain; echo "clone_status_end"
echo "s1_clone_head=$(git -C "$S1CLONE" rev-parse HEAD) s1_tree=$(git -C "$S1CLONE" rev-parse HEAD:stage-1)"
echo "test_rev=${ADV_TEST_REV:-unrecorded} test_dirty=${ADV_TEST_DIRTY:-unrecorded}"
[ "$(git -C "$CLONE" rev-parse HEAD)" = "$SHA" ] || { echo "clone HEAD != candidate"; exit 2; }
docker version --format 'docker client={{.Client.Version}} server={{.Server.Version}}'
"$PY" -V; "$PY" -m pip freeze | tr '\n' ' '; echo
"$PY" -c "from playwright.sync_api import sync_playwright as s; p=s().start(); b=p.chromium.launch(); print('chromium', b.version); b.close(); p.stop()"

TAG2="adv-s2-${SHA:0:12}-$$"; TAG1="adv-s2base-s1-$$"
T0=$(date +%s); docker build --no-cache -t "$TAG2" "$CLONE/stage-2" > "$OUT/build-stage2.log" 2>&1; B2=$?
echo "build_stage2_exit=$B2 seconds=$(( $(date +%s) - T0 ))"
T0=$(date +%s); docker build --no-cache -t "$TAG1" "$S1CLONE/stage-1" > "$OUT/build-stage1.log" 2>&1; B1=$?
echo "build_stage1_exit=$B1 seconds=$(( $(date +%s) - T0 ))"
[ $B2 -eq 0 ] && [ $B1 -eq 0 ] || exit 3
docker image inspect "$TAG2" --format 'image2_id={{.Id}} size={{.Size}}'

A="adv2-a-$$"; B="adv2-b-$$"; S="adv2-s1-$$"; C="adv2-c-$$"
cleanup() {
  for c in $A $B $S $C; do docker logs "$c" > "$OUT/container-${c%%-$$}.log" 2>&1; docker rm -f "$c" >/dev/null 2>&1; done
  docker image rm -f "$TAG2" "$TAG1" >/dev/null 2>&1
}
trap cleanup EXIT
wait_health() {
  local start=$1 port=$2
  for _ in $(seq 1 240); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health")" = "200" ] && { echo $(( $(date +%s) - start )); return 0; }
    sleep 0.25
  done
  echo timeout; return 1
}
run_c() { local name=$1 img=$2 cport=$3; shift 3
  docker run -d --name "$name" --cpus 2 --memory 2g --memory-swap 2g "$@" -p "127.0.0.1::$cport" "$img" >/dev/null
  docker port "$name" "$cport/tcp" | head -1 | sed 's/.*://'; }
S0=$(date +%s); PA=$(run_c "$A" "$TAG2" 9741 -e PORT=9741); echo "stage2_a port=$PA health_s=$(wait_health "$S0" "$PA")"
S0=$(date +%s); PB=$(run_c "$B" "$TAG2" 9742 -e PORT=9742); echo "stage2_b port=$PB health_s=$(wait_health "$S0" "$PB")"
S0=$(date +%s); PS=$(run_c "$S" "$TAG1" 9743 -e PORT=9743); echo "stage1_accepted port=$PS health_s=$(wait_health "$S0" "$PS")"
S0=$(date +%s); PC=$(run_c "$C" "$TAG2" 8080); echo "stage2_c(PORT unset) port=$PC health_s=$(wait_health "$S0" "$PC") body=$(curl -s http://127.0.0.1:$PC/health)"
docker rm -f "$C" >/dev/null 2>&1
echo "clock host=$(date -u +%s.%N) container=$(docker exec "$A" date -u +%s 2>/dev/null || echo n/a)"

export ADV_BASE_URL="http://127.0.0.1:$PA" ADV_BASE_URL_B="http://127.0.0.1:$PB" ADV_BASE_URL_S1="http://127.0.0.1:$PS"
if [ -z "${ADV_SKIP_S1SUITE:-}" ]; then
  T0=$(date +%s)
  ( cd "$HERE/../stage-1" && ADV_STAGE=2 ADV_RESULTS="$OUT/results-stage1suite.json" "$PY" -m pytest . -p no:cacheprovider \
      --assert=plain -rfEsx -q --junitxml="$OUT/junit-stage1suite.xml" ) > "$OUT/pytest-stage1suite.log" 2>&1
  echo "stage1suite_exit=$? seconds=$(( $(date +%s) - T0 )) $(tail -1 "$OUT/pytest-stage1suite.log")"
fi
T0=$(date +%s)
( cd "$HERE" && ADV_SHOTS="$OUT/shots" ADV_RESULTS="$OUT/results.json" "$PY" -m pytest . -p no:cacheprovider --assert=plain \
    -rfEsx -q --junitxml="$OUT/junit.xml" ${ADV_PYTEST_ARGS:-} ) > "$OUT/pytest.log" 2>&1
PYT=$?
echo "stage2suite_exit=$PYT seconds=$(( $(date +%s) - T0 )) $(tail -1 "$OUT/pytest.log")"
docker stats --no-stream --format 'stats {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' "$A" "$B" "$S"
docker inspect "$A" --format 'stage2_a restarts={{.RestartCount}} oom={{.State.OOMKilled}} running={{.State.Running}}'
"$PY" "$HERE/../stage-1/summarize.py" "$OUT/results.json" > "$OUT/summary.md"
[ -f "$OUT/results-stage1suite.json" ] && "$PY" "$HERE/../stage-1/summarize.py" "$OUT/results-stage1suite.json" > "$OUT/summary-stage1suite.md"
echo "== done $(ts)"
cleanup; trap - EXIT
( cd "$OUT" && sha256sum *.log *.xml *.json *.md > SHA256SUMS; [ -d shots ] && sha256sum shots/*.png >> SHA256SUMS )
exit $PYT
