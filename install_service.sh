#!/usr/bin/env bash
# VPS: make the bot start automatically on boot & run 24/7 (systemd).
# Usage:  sudo bash install_service.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo: sudo bash install_service.sh"; exit 1; fi
command -v systemctl >/dev/null || { echo "systemd not found. Use: nohup bash start.sh &  or Docker."; exit 1; }
# prepare venv + requirements once
bash -c "cd '$DIR' && [ -d venv ] || python3 -m venv venv; . venv/bin/activate && pip install -q -r requirements.txt"
cat > /etc/systemd/system/indigo-bot.service <<UNIT
[Unit]
Description=Indigo Builders Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python $DIR/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now indigo-bot
echo "Done. Status: systemctl status indigo-bot | Logs: journalctl -u indigo-bot -f"
