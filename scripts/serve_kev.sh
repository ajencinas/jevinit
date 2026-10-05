#!/usr/bin/env bash
# Start the local Kev server (Kev-4B on the GPU) for the ZeroOps pipeline.
#   scripts/serve_kev.sh            # default jaredpalmer/kev-4b on :8009
#   KEV_RUN=jaredpalmer/kev-0.8b scripts/serve_kev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/third_party/kev"
PORT="${KEV_PORT:-8009}"
RUN="${KEV_RUN:-jaredpalmer/kev-4b}"
# CUDA graphs are disabled: the graph buffers OOM a 16 GB card. fp32-ready but bf16 default.
KEV_CUDA_GRAPHS=0 KEV_PREFIX_CACHE=0 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  setsid .venv/bin/python -m kev.serve --run "$RUN" --host 127.0.0.1 --port "$PORT" \
  >/tmp/kev_serve.log 2>&1 </dev/null &
echo "Kev starting on 127.0.0.1:$PORT (run=$RUN). Log: /tmp/kev_serve.log"
echo "Wait for: curl -s http://127.0.0.1:$PORT/v1/models"
