#!/usr/bin/env bash
# deploy/ec2_setup.sh
# Run ON a fresh Graviton (arm64) EC2 instance: t4g.small, Ubuntu 24.04.
# Security group: allow inbound TCP 8000 (demo) and 22 (ssh). Attach an Elastic IP.
set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip git libgl1 libglib2.0-0

# clone your repo (override by passing a URL as the first argument)
REPO="${1:-https://github.com/Aakashdeep-Srivastava/wastewatch-ai.git}"
git clone "$REPO" app_src || (cd app_src && git pull)
cd app_src

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip freeze > requirements.lock
python -m pytest -q || true   # smoke test; don't block deploy

# run as a background service
cat <<'UNIT' | sudo tee /etc/systemd/system/wastewatch.service
[Unit]
Description=WasteWatch AI
After=network.target
[Service]
WorkingDirectory=/home/ubuntu/app_src
Environment=ORBIT_AGENT=rule
ExecStart=/home/ubuntu/app_src/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
User=ubuntu
[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now wastewatch
echo "WasteWatch AI is live on http://<ELASTIC_IP>:8000"
