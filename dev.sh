#!/usr/bin/env bash
# dev.sh — Start the full HUGO stack: simulator + backend + frontend
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    trap - EXIT INT TERM  # prevent re-entry
    echo ""
    echo "[dev] Shutting down..."

    # Kill children in reverse order
    for pid in $FRONTEND_PID $BACKEND_PID; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        fi
    done

    # Wait briefly for graceful exit, then force-kill stragglers
    sleep 1
    for pid in $FRONTEND_PID $BACKEND_PID; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
        fi
    done

    # Free ports in case of leaked processes
    for port in 8000 8080 5173; do
        lsof -ti :"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
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

# ── 2. Free ports from previous runs ─────────────────────────────────────────

for port in 8000 8080 5173; do
    lsof -ti :"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
done
sleep 1

# ── 3. Start the backend (FastAPI) first — daemon streams video to it ────────

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

# ── 4. Start the frontend (SvelteKit) ────────────────────────────────────────
# Note: The backend lifespan auto-spawns the reachy-mini-daemon when
# REACHY_SIMULATION=true and no running daemon is found. No need to start
# a second daemon here.

echo "[dev] Waiting for backend simulator daemon to initialize..."
sleep 4

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
echo "  Simulator: http://localhost:8000 (auto-spawned by backend)"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "============================================"
echo ""

# Wait for any child to exit
wait
