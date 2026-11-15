#!/usr/bin/env bash
# =====================================================================
#  ONE UNIVERSAL START COMMAND  ->  bash start.sh
#  Works on: VPS (Ubuntu/Debian/CentOS), Termux, macOS, Raspberry Pi, WSL.
#  It automatically: finds Python, creates venv, installs requirements
#  (only when they change), creates .env, and restarts the bot if it crashes.
# =====================================================================
cd "$(dirname "$0")" || exit 1

# 1) Find Python
PY=""
for c in python3 python python3.12 python3.11 python3.10 python3.9; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "[ERROR] Python not found. Install it first:"
  echo "  Ubuntu/Debian : sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  echo "  Termux        : pkg install python -y"
  exit 1
fi

# 2) .env
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "[INFO] .env created. Edit it (nano .env), set BOT_TOKEN, then run again."
  exit 0
fi

# 3) Virtual environment (falls back to system python if venv unavailable)
if [ ! -d venv ]; then
  "$PY" -m venv venv >/dev/null 2>&1 || echo "[WARN] venv not available, using system Python"
fi
if [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
  PY=python
fi

# 4) Install requirements only if requirements.txt changed
HASH_NOW=$( (md5sum requirements.txt 2>/dev/null || md5 -q requirements.txt 2>/dev/null || cksum requirements.txt) | awk '{print $1}')
HASH_OLD=$(cat .req_hash 2>/dev/null)
if [ "$HASH_NOW" != "$HASH_OLD" ]; then
  echo "[INFO] Installing requirements..."
  "$PY" -m pip install --upgrade pip -q >/dev/null 2>&1
  if "$PY" -m pip install -r requirements.txt -q || "$PY" -m pip install -r requirements.txt -q --break-system-packages; then
    echo "$HASH_NOW" > .req_hash
  else
    echo "[ERROR] Requirement install failed."; exit 1
  fi
fi

# 5) Token check (skipped if BOT_TOKEN is provided by the host environment)
TOKEN_IN_ENV="${BOT_TOKEN:-}"
TOKEN_IN_FILE=$(grep -E '^BOT_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
if [ -z "$TOKEN_IN_ENV" ] && { [ -z "$TOKEN_IN_FILE" ] || [ "$TOKEN_IN_FILE" = "YOUR_BOT_TOKEN_HERE" ]; }; then
  echo "[ERROR] BOT_TOKEN is not set. Open .env (nano .env) and paste your BotFather token."
  exit 1
fi

# 6) Run forever (auto-restart after crash)
echo "[INFO] Starting bot... (Ctrl+C to stop)"
trap 'echo; echo "[INFO] Stopped."; exit 0' INT TERM
while true; do
  "$PY" main.py
  echo "[WARN] Bot exited. Restarting in 5 seconds..."
  sleep 5
done
