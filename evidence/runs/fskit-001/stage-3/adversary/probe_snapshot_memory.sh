#!/usr/bin/env bash
set -u
IMG=adv-probe-s3mem; C=adv-probe-s3mem
docker build -q -t $IMG /mnt/c/nexus/dev/band-kit/clones/adversary-s3-1/stage-3 >/dev/null
docker rm -f $C >/dev/null 2>&1
docker run -d --name $C --cpus 2 --memory 2g --memory-swap 2g -e PORT=9780 -p 127.0.0.1:9780:9780 $IMG >/dev/null
for i in $(seq 1 40); do curl -sf http://127.0.0.1:9780/health >/dev/null && break; sleep 0.25; done
echo "start $(date -u +%FT%TZ) candidate=$(git -C /mnt/c/nexus/dev/band-kit/clones/adversary-s3-1 rev-parse HEAD)"
echo "mem_before $(docker stats --no-stream --format '{{.MemUsage}}' $C)"
ADV_BASE_URL=http://127.0.0.1:9780 ~/adv-venv/bin/python /mnt/c/nexus/dev/band-kit/wt/adversary/evidence/runs/fskit-001/stage-3/adversary/probe_snapshot_memory.py
echo "mem_after $(docker stats --no-stream --format '{{.MemUsage}}' $C)"
docker inspect $C --format 'oom={{.State.OOMKilled}} restarts={{.RestartCount}} running={{.State.Running}}'
echo "end $(date -u +%FT%TZ)"
docker rm -f $C >/dev/null
