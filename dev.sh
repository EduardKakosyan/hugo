#!/usr/bin/env bash
# dev.sh — Start the full HUGO stack: simulator + backend + frontend
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

SIMULATOR_PID=""
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    trap - EXIT INT TERM  # prevent re-entry
    echo ""
    echo "[dev] Shutting down..."
    for pid in $SIMULATOR_PID $BACKEND_PID $FRONTEND_PID; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "[dev] All services stopped."
}

trap cleanup EXIT INT TERM

# ── 1. Install dependencies if needed ────────────────────────────────────────

echo "[dev] Checking backend dependencies..."
(cd "$BACKEND_DIR" && uv sync --dev --quiet)

echo "[dev] Checking frontend dependencies..."
(cd "$FRONTEND_DIR" && pnpm install --silent)

# ── 2. Start the Reachy Mini simulator daemon ────────────────────────────────

echo "[dev] Starting Reachy Mini simulator daemon..."
(cd "$BACKEND_DIR" && uv run reachy-mini-daemon --sim --headless --deactivate-audio --log-level WARNING) &
SIMULATOR_PID=$!

echo "[dev] Waiting for simulator to initialize..."
sleep 4

if ! kill -0 "$SIMULATOR_PID" 2>/dev/null; then
    echo "[dev] ERROR: Simulator daemon failed to start. Check reachy-mini installation."
    exit 1
fi
echo "[dev] Simulator daemon running (PID: $SIMULATOR_PID)"

# ── 3. Start the backend (FastAPI) ──────────────────────────────────────────

echo "[dev] Starting backend on http://localhost:8080 ..."
(cd "$BACKEND_DIR" && REACHY_SIMULATION=true uv run uvicorn src.main:app --reload --port 8080 --log-level info) &
BACKEND_PID=$!

echo "[dev] Waiting for backend to initialize..."
sleep 3

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "[dev] ERROR: Backend failed to start."
    exit 1
fi
echo "[dev] Backend running (PID: $BACKEND_PID)"

# ── 4. Start the frontend (SvelteKit) ───────────────────────────────────────

echo "[dev] Starting frontend on http://localhost:5173 ..."
(cd "$FRONTEND_DIR" && pnpm dev) &
FRONTEND_PID=$!

sleep 2
echo "[dev] Frontend running (PID: $FRONTEND_PID)"

# ── 5. Ready ─────────────────────────────────────────────────────────────────

echo ""
echo "============================================"
echo "  HUGO dev stack is running!"
echo ""
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8080"
echo "  API docs:  http://localhost:8080/docs"
echo "  Simulator: reachy-mini-daemon --sim"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "============================================"
echo ""

# Wait for any child to exit
wait
