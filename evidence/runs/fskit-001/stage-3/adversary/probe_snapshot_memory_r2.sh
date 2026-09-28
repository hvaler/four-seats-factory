#!/usr/bin/env bash
# Run 2 of the snapshot-memory risk probe: keeps container logs, exit code and a memory time series.
set -u
IMG=adv-probe-s3mem; C=adv-probe-s3mem2; OUT=/mnt/c/nexus/dev/band-kit/wt/adversary/evidence/runs/fskit-001/stage-3/adversary/probe_snapshot_memory_r2
mkdir -p $OUT
docker build -q -t $IMG /mnt/c/nexus/dev/band-kit/clones/adversary-s3-1/stage-3 >/dev/null
docker rm -f $C >/dev/null 2>&1
docker run -d --name $C --cpus 2 --memory 2g --memory-swap 2g -e PORT=9781 -p 127.0.0.1:9781:9781 $IMG >/dev/null
for i in $(seq 1 40); do curl -sf http://127.0.0.1:9781/health >/dev/null && break; sleep 0.25; done
echo "start $(date -u +%FT%TZ) candidate=$(git -C /mnt/c/nexus/dev/band-kit/clones/adversary-s3-1 rev-parse HEAD) image=$(docker inspect $C --format '{{.Image}}')"
( while docker inspect $C --format '{{.State.Running}}' 2>/dev/null | grep -q true; do
    echo "$(date -u +%T) $(docker stats --no-stream --format '{{.MemUsage}} cpu={{.CPUPerc}}' $C 2>/dev/null)"; sleep 2; done ) > $OUT/mem_series.txt &
SAMPLER=$!
ADV_BASE_URL=http://127.0.0.1:9781 ~/adv-venv/bin/python /mnt/c/nexus/dev/band-kit/wt/adversary/evidence/runs/fskit-001/stage-3/adversary/probe_snapshot_memory.py 2>&1 | grep -v '^  \|^Traceback\|^    \|^The above\|^$' | tail -12
sleep 3
kill $SAMPLER 2>/dev/null
docker inspect $C --format 'state running={{.State.Running}} exit_code={{.State.ExitCode}} oom={{.State.OOMKilled}} error={{.State.Error}} finished={{.State.FinishedAt}}'
docker logs $C > $OUT/container.log 2>&1
echo "container_log_tail:"; tail -25 $OUT/container.log
echo "mem_series_tail:"; tail -6 $OUT/mem_series.txt
echo "end $(date -u +%FT%TZ)"
docker rm -f $C >/dev/null
