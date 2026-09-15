#!/usr/bin/env bash
# Wrapper replay sin IBM i — §20 Replay
set -e
ID="${1:-}"
if [ -z "$ID" ]; then
  echo "uso: $0 <ID>  (lista si no se da ID)"
  python3 -m probe.joblog_recorder replay
else
  python3 -m probe.joblog_recorder replay "$ID"
fi
