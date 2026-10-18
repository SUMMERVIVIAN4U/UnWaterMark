#!/bin/sh
set -eu
cd "$(dirname "$0")"
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 MPLCONFIGDIR=/tmp/unwatermark-matplotlib
mkdir -p "$MPLCONFIGDIR"
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port "${PORT:-8765}"
