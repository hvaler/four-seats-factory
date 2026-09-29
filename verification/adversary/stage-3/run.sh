#!/usr/bin/env bash
# Adversary stage-3 runner.
#   run.sh <stage3-clone> <candidate-sha> <stage1-clone@beeaec72> <stage2-clone@68583038> <out-dir>
# Builds stage-3/ of the candidate plus the ACCEPTED stage-1 and stage-2 images, then runs the stage-1
# suite, the stage-2 suite (API, CONC, UI 375/1280, D2-18 upgrade into stage 3) and the stage-3 suite.
set -uo pipefail
CLONE=$1; SHA=$2; S1CLONE=$3; S2CLONE=$4; OUT=$5
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${ADV_PY:-$HOME/adv-venv/bin/python}
[ -e "$OUT" ] && { echo "out dir exists: $OUT"; exit 2; }
mkdir -p "$OUT"
cd /tmp
exec > >(tee -a "$OUT/runner.log") 2>&1
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "== adversary stage-3 run $(ts)"
echo "candidate_sha=$SHA clone_head=$(git -C "$CLONE" rev-parse HEAD)"
echo "trees stage3=$(git -C "$CLONE" rev-parse HEAD:stage-3) stage2=$(git -C "$CLONE" rev-parse HEAD:stage-2) stage1=$(git -C "$CLONE" rev-parse HEAD:stage-1)"
echo "clone_status_begin"; git -C "$CLONE" status --porcelain; echo "clone_status_end"
echo "s1_source=$(git -C "$S1CLONE" rev-parse HEAD) tree=$(git -C "$S1CLONE" rev-parse HEAD:stage-1)"
echo "s2_source=$(git -C "$S2CLONE" rev-parse HEAD) tree=$(git -C "$S2CLONE" rev-parse HEAD:stage-2)"
echo "test_rev=${ADV_TEST_REV:-unrecorded} test_dirty=${ADV_TEST_DIRTY:-unrecorded}"
[ "$(git -C "$CLONE" rev-parse HEAD)" = "$SHA" ] || { echo "clone HEAD != candidate"; exit 2; }
docker version --format 'docker client={{.Client.Version}} server={{.Server.Version}}'
"$PY" -V

T3="adv-s3-${SHA:0:12}-$$"; T1="adv-s3base1-$$"; T2="adv-s3base2-$$"
for pair in "$T3:$CLONE/stage-3" "$T1:$S1CLONE/stage-1" "$T2:$S2CLONE/stage-2"; do
  tag=${pair%%:*}; dir=${pair#*:}; T0=$(date +%s)
  docker build --no-cache -t "$tag" "$dir" > "$OUT/build-$(basename "$dir").log" 2>&1; rc=$?
  echo "build $(basename "$dir") exit=$rc seconds=$(( $(date +%s) - T0 ))"; [ $rc -eq 0 ] || exit 3
done
A="adv3-a-$$"; B="adv3-b-$$"; S1="adv3-s1-$$"; S2="adv3-s2-$$"; C="adv3-c-$$"
cleanup() {
  for c in $A $B $S1 $S2 $C; do docker logs "$c" > "$OUT/container-${c%%-$$}.log" 2>&1; docker rm -f "$c" >/dev/null 2>&1; done
  docker image rm -f "$T3" "$T1" "$T2" >/dev/null 2>&1
}
trap cleanup EXIT
wait_health() { local start=$1 port=$2
  for _ in $(seq 1 240); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health")" = "200" ] && { echo $(( $(date +%s) - start )); return 0; }
    sleep 0.25; done; echo timeout; return 1; }
run_c() { local name=$1 img=$2 cport=$3; shift 3
  docker run -d --name "$name" --cpus 2 --memory 2g --memory-swap 2g "$@" -p "127.0.0.1::$cport" "$img" >/dev/null
  docker port "$name" "$cport/tcp" | head -1 | sed 's/.*://'; }
S0=$(date +%s); PA=$(run_c "$A" "$T3" 9761 -e PORT=9761); echo "stage3_a port=$PA health_s=$(wait_health "$S0" "$PA")"
S0=$(date +%s); PB=$(run_c "$B" "$T3" 9762 -e PORT=9762); echo "stage3_b port=$PB health_s=$(wait_health "$S0" "$PB")"
S0=$(date +%s); P1=$(run_c "$S1" "$T1" 9763 -e PORT=9763); echo "stage1_accepted port=$P1 health_s=$(wait_health "$S0" "$P1")"
S0=$(date +%s); P2=$(run_c "$S2" "$T2" 9764 -e PORT=9764); echo "stage2_accepted port=$P2 health_s=$(wait_health "$S0" "$P2")"
S0=$(date +%s); PC=$(run_c "$C" "$T3" 8080); echo "stage3_c(PORT unset) port=$PC health_s=$(wait_health "$S0" "$PC") body=$(curl -s http://127.0.0.1:$PC/health)"
docker rm -f "$C" >/dev/null 2>&1
export ADV_BASE_URL="http://127.0.0.1:$PA" ADV_BASE_URL_B="http://127.0.0.1:$PB" ADV_BASE_URL_S1="http://127.0.0.1:$P1" ADV_BASE_URL_S2="http://127.0.0.1:$P2"
suite() { local name=$1 dir=$2; shift 2; local T0=$(date +%s)
  ( cd "$dir" && ADV_STAGE=3 ADV_SHOTS="$OUT/shots-$name" ADV_RESULTS="$OUT/results-$name.json" "$PY" -m pytest . -p no:cacheprovider \
      --assert=plain -rfEsx -q --junitxml="$OUT/junit-$name.xml" "$@" ) > "$OUT/pytest-$name.log" 2>&1
  local rc=$?; echo "suite_$name exit=$rc seconds=$(( $(date +%s) - T0 )) $(tail -1 "$OUT/pytest-$name.log")"
  "$PY" "$HERE/../stage-1/summarize.py" "$OUT/results-$name.json" > "$OUT/summary-$name.md"; return $rc; }
RC=0
if [ -z "${ADV_ONLY3:-}" ]; then
  suite stage1 "$HERE/../stage-1" || RC=1
  suite stage2 "$HERE/../stage-2" || RC=1
fi
suite stage3 "$HERE" ${ADV_PYTEST_ARGS:-} || RC=1
docker stats --no-stream --format 'stats {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' "$A" "$B"
docker inspect "$A" --format 'stage3_a restarts={{.RestartCount}} oom={{.State.OOMKilled}} running={{.State.Running}}'
echo "== done $(ts)"
cleanup; trap - EXIT
( cd "$OUT" && sha256sum *.log *.xml *.json *.md > SHA256SUMS; for d in shots-*; do [ -d "$d" ] && sha256sum "$d"/*.png >> SHA256SUMS; done )
exit $RC
