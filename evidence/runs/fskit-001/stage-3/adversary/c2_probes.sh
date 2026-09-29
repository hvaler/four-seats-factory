#!/usr/bin/env bash
# Candidate-2 re-checks: snapshot-memory probe at 20000 reads / 20 in flight (analyst gate 78ccefc0) and at the
# original 5000/10 parameters; F3-01 repro; D3-11 overdraft-at-expiry check. Keeps logs and memory series.
set -u
CL=/mnt/c/nexus/dev/band-kit/clones/adversary-s3-2
D=/mnt/c/nexus/dev/band-kit/wt/adversary/evidence/runs/fskit-001/stage-3/adversary
OUT=$D/c2-probes; mkdir -p $OUT
IMG=adv-probe-s3c2
docker build -q -t $IMG $CL/stage-3 >/dev/null
echo "candidate=$(git -C $CL rev-parse HEAD) stage3_tree=$(git -C $CL rev-parse HEAD:stage-3) image=$(docker image inspect $IMG --format '{{.Id}}')"
start_c() { docker rm -f $1 >/dev/null 2>&1; docker run -d --name $1 --cpus 2 --memory 2g --memory-swap 2g -e PORT=$2 -p 127.0.0.1:$2:$2 $IMG >/dev/null
  for i in $(seq 1 40); do curl -sf http://127.0.0.1:$2/health >/dev/null && break; sleep 0.25; done; }
mem_probe() { local name=$1 n=$2 th=$3 port=$4
  start_c $name $port
  echo "== $name N=$n TH=$th start $(date -u +%FT%TZ) mem_before=$(docker stats --no-stream --format '{{.MemUsage}}' $name)"
  ( while docker inspect $name --format '{{.State.Running}}' 2>/dev/null | grep -q true; do
      echo "$(date -u +%T) $(docker stats --no-stream --format '{{.MemUsage}}' $name 2>/dev/null)"; sleep 2; done ) > $OUT/$name-mem.txt &
  local S=$!
  PROBE_N=$n PROBE_TH=$th ADV_BASE_URL=http://127.0.0.1:$port ~/adv-venv/bin/python $D/probe_snapshot_memory_v2.py 2>&1 | grep -vE '^  |^Traceback|^The above|^$' | tail -6
  sleep 3; kill $S 2>/dev/null
  echo "peak_mem=$(awk '{print $2}' $OUT/$name-mem.txt | sort -h | tail -1) samples=$(wc -l < $OUT/$name-mem.txt)"
  docker inspect $name --format 'state running={{.State.Running}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}'
  docker logs $name > $OUT/$name-container.log 2>&1; docker rm -f $name >/dev/null
  echo "end $(date -u +%FT%TZ)"; }
mem_probe mem20k 20000 20 9790
mem_probe mem5k 5000 10 9791
start_c repro 9792
echo "== F3-01 repro $(date -u +%FT%TZ)"; ADV_BASE_URL=http://127.0.0.1:9792 ~/adv-venv/bin/python $D/repro_void_known_at.py
echo "== D3-11 overdraft at expiry $(date -u +%FT%TZ)"; ADV_BASE_URL=http://127.0.0.1:9792 ~/adv-venv/bin/python $D/probe_overdraft_expiry.py
docker rm -f repro >/dev/null
