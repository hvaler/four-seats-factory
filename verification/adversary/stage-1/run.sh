#!/usr/bin/env bash
# Adversary stage-1 runner. Builds the candidate's stage-1/ image from a clean clone,
# starts independent containers under the §2 limits, and runs this suite against them.
#
#   run.sh <clone-dir> <candidate-sha> <out-dir>
#
# All paths are WSL paths. <out-dir> must not exist. Export bodies are never written.
set -uo pipefail
CLONE=$1; SHA=$2; OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${ADV_PY:-$HOME/adv-venv/bin/python}
[ -e "$OUT" ] && { echo "out dir exists: $OUT"; exit 2; }
mkdir -p "$OUT"
exec > >(tee -a "$OUT/runner.log") 2>&1
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "== adversary stage-1 run $(ts)"
echo "candidate_sha=$SHA"
echo "clone_head=$(git -C "$CLONE" rev-parse HEAD)"
echo "clone_stage1_tree=$(git -C "$CLONE" rev-parse HEAD:stage-1)"
echo "clone_status_porcelain_begin"; git -C "$CLONE" status --porcelain; echo "clone_status_porcelain_end"
# WSL git cannot follow a worktree created from Windows, so the caller records the test
# revision on the Windows side and passes it in.
echo "test_rev=${ADV_TEST_REV:-unrecorded} test_tree=${ADV_TEST_TREE:-unrecorded} test_dirty=${ADV_TEST_DIRTY:-unrecorded}"
[ "$(git -C "$CLONE" rev-parse HEAD)" = "$SHA" ] || { echo "clone HEAD != candidate"; exit 2; }
docker version --format 'docker client={{.Client.Version}} server={{.Server.Version}}'
"$PY" -V; "$PY" -m pip freeze | tr '\n' ' '; echo

TAG="adv-s1-${SHA:0:12}-$$"
T0=$(date +%s)
docker build --no-cache -t "$TAG" "$CLONE/stage-1" > "$OUT/build.log" 2>&1
BUILD=$?
echo "build_exit=$BUILD build_seconds=$(( $(date +%s) - T0 )) image=$TAG"
[ $BUILD -eq 0 ] || exit 3
docker image inspect "$TAG" --format 'image_id={{.Id}} size={{.Size}}'

A="adv-s1-a-$$"; B="adv-s1-b-$$"; C="adv-s1-c-$$"
cleanup() {
  for c in $A $B $C; do docker logs "$c" > "$OUT/container-${c%%-$$}.log" 2>&1; docker rm -f "$c" >/dev/null 2>&1; done
  docker image rm -f "$TAG" >/dev/null 2>&1
}
trap cleanup EXIT

wait_health() {  # name port -> prints seconds to first 200, or fails after 60 s
  local start=$1 port=$2
  for _ in $(seq 1 240); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health")" = "200" ]; then
      echo $(( $(date +%s) - start )); return 0; fi
    sleep 0.25
  done
  echo "timeout"; return 1
}

run_c() {  # name extra-args... ; echoes the mapped host port
  local name=$1 cport=$2; shift 2
  docker run -d --name "$name" --cpus 2 --memory 2g --memory-swap 2g "$@" -p "127.0.0.1::$cport" "$TAG" >/dev/null
  docker port "$name" "$cport/tcp" | head -1 | sed 's/.*://'
}

S=$(date +%s); PA=$(run_c "$A" 9731 -e PORT=9731); HA=$(wait_health "$S" "$PA"); echo "container_a port=$PA health_s=$HA"
S=$(date +%s); PB=$(run_c "$B" 9732 -e PORT=9732); HB=$(wait_health "$S" "$PB"); echo "container_b port=$PB health_s=$HB"
# S1-014: PORT unset -> 8080
S=$(date +%s); PC=$(run_c "$C" 8080); HC=$(wait_health "$S" "$PC"); echo "container_c(PORT unset) port=$PC health_s=$HC"
BODY=$(curl -s "http://127.0.0.1:$PC/health"); echo "S1-014 default_port_health_body=$BODY"
docker rm -f "$C" >/dev/null 2>&1

export ADV_BASE_URL="http://127.0.0.1:$PA" ADV_BASE_URL_B="http://127.0.0.1:$PB" ADV_RESULTS="$OUT/results.json"
T0=$(date +%s)
( cd "$HERE" && "$PY" -m pytest . -p no:cacheprovider --assert=plain -rfEsx -q \
    --junitxml="$OUT/junit.xml" ${ADV_PYTEST_ARGS:-} ) > "$OUT/pytest.log" 2>&1
PYT=$?
echo "pytest_exit=$PYT pytest_seconds=$(( $(date +%s) - T0 ))"
tail -3 "$OUT/pytest.log"
docker stats --no-stream --format 'stats {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' "$A" "$B"
docker inspect "$A" --format 'container_a restarts={{.RestartCount}} oom={{.State.OOMKilled}} running={{.State.Running}}'
"$PY" "$HERE/summarize.py" "$OUT/results.json" > "$OUT/summary.md"
echo "== done $(ts)"
cleanup; trap - EXIT
( cd "$OUT" && sha256sum *.log *.xml *.json *.md > SHA256SUMS )
exit $PYT
