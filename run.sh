#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

mkdir -p Artifacts/Input/raw Artifacts/Input/processed Artifacts/Input/archived Artifacts/Sprockets Artifacts/Cogs

echo "=== Starting ICM pipeline ==="
echo "Working directory: $(pwd)"

python3 input_processor.py &
INPUT_PID=$!
python3 agentic_loop.py &
AGENT_PID=$!

echo "Input processor PID: $INPUT_PID"
echo "Agentic loop PID: $AGENT_PID"

tap() {
    if kill -0 "$1" 2>/dev/null; then
        wait "$1"
    fi
}

cleanup() {
    echo "\n=== Stopping ICM pipeline ==="
    kill "$INPUT_PID" "$AGENT_PID" 2>/dev/null || true
    wait "$INPUT_PID" "$AGENT_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

wait "$INPUT_PID" "$AGENT_PID"
