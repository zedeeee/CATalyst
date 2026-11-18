#!/usr/bin/env bash
# One-Click Installer for CATalyst MCP Server (macOS / Linux).
# Requires: Python 3.10+, uv, and 7-Zip (p7zip) if unpacking V5Automation.chm locally.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# 1. Locate uv
UV_CMD="$(command -v uv || true)"
if [[ -z "$UV_CMD" ]]; then
  for cand in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if [[ -x "$cand" ]]; then
      UV_CMD="$cand"
      break
    fi
  done
fi

if [[ -z "$UV_CMD" ]]; then
  echo "[ERROR] uv is required but not found."
  echo "Install uv first, then re-run ./install.sh:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

export CATALYST_INSTALLER_PROG="./install.sh"

# Fast-path: show --help / -h without triggering uv sync
for arg in "$@"; do
  if [[ "$arg" == "-h" || "$arg" == "--help" ]]; then
    if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
      exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/install.py" "$@"
    else
      exec "$UV_CMD" run --no-project python "$PROJECT_ROOT/install.py" "$@"
    fi
  fi
done

# 2. Sync isolated project .venv
echo "[STEP 0] Syncing isolated virtual environment (.venv)..."
if ! "$UV_CMD" sync; then
  if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    echo "[WARN] uv sync failed; continuing with existing .venv..."
  else
    echo "[ERROR] uv sync failed and no local .venv exists. Check network/Python 3.10+."
    exit 1
  fi
fi

# 3. Run Python installer inside isolated .venv
exec "$UV_CMD" run python "$PROJECT_ROOT/install.py" "$@"
