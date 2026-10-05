#!/usr/bin/env bash
# Stop the local Kev server started by scripts/serve_kev.sh
set -uo pipefail
if pgrep -f "python -m kev.serve" >/dev/null 2>&1; then
  pkill -f "python -m kev.serve"
  sleep 2
  echo "Kev stopped."
else
  echo "Kev not running."
fi
