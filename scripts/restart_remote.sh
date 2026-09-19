#!/usr/bin/env bash
# Restart the 玄学助手 service on the NAS without sudo.
# The code directory is the SMB share (Z:\Workspace\ChinaExpe == /Volumes/Storage/Workspace/ChinaExpe),
# so nothing needs to be copied: kill uvicorn and let systemd (Restart=always, 5s) bring it back.
set -euo pipefail
HOST="${1:-haifeng@192.168.50.6}"
PUBLIC="${2:-http://192.168.50.6:1248}"

echo "[1/3] stopping uvicorn on $HOST ..."
# "[u]vicorn" so pkill does not match (and kill) the remote shell running this very command;
# "|| true" locally because a killed remote shell makes ssh return non-zero.
ssh -o BatchMode=yes "$HOST" 'pkill -u haifeng -f "[u]vicorn app.main:app"; true' || true

echo "[2/3] waiting for systemd to restart it ..."
for i in $(seq 1 30); do
  sleep 2
  # Apache answers 503 while uvicorn is still starting, so require the JSON body
  if out=$(curl -s -m 3 "$PUBLIC/api/health" 2>/dev/null) && [[ "$out" == *'"status":"ok"'* ]]; then
    echo "  health: $out"
    break
  fi
  if [ "$i" = 30 ]; then echo "  !! service did not come back; check: ssh $HOST journalctl -u xuanxue -n 50"; exit 1; fi
done

echo "[3/3] smoke ..."
curl -s -m 5 "$PUBLIC/api/people" | head -c 300; echo
echo "done: $PUBLIC"
