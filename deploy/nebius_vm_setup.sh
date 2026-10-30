#!/usr/bin/env bash
# deploy/nebius_vm_setup.sh
# One-shot backend deploy for a fresh Nebius AI Cloud VM (Ubuntu 22.04/24.04, CPU).
# The backend is CPU-only: NVIDIA Nemotron inference runs remotely on Nebius Token
# Factory, so a small general-purpose VM is enough.
#
# Nebius console steps first:
#   1. Compute -> Create VM -> Ubuntu 24.04, 2 vCPU / 4 GB is plenty, public IP ON.
#   2. Security group / firewall: allow inbound TCP 8000 (and 22 for ssh).
#   3. ssh in, then run:
#        export NEBIUS_API_KEY=sk-...            # from tokenfactory.nebius.com
#        export NEBIUS_BASE_URL=...              # exact base URL from the dashboard
#        export NEMOTRON_VL_MODEL=... NEMOTRON_REASON_MODEL=...   # optional overrides
#        export TAVILY_API_KEY=...               # optional
#        curl -fsSL https://raw.githubusercontent.com/Aakashdeep-Srivastava/wastewatch-ai/main/deploy/nebius_vm_setup.sh | bash
#
# The backend comes up on http://<VM_PUBLIC_IP>:8000 — use that as FASTAPI_ORIGIN
# in the Vercel frontend. (Vercel serves HTTPS to the browser and proxies to this
# HTTP origin server-side, so plain HTTP here is fine.)
set -euo pipefail

REPO="${REPO:-https://github.com/Aakashdeep-Srivastava/wastewatch-ai.git}"

sudo apt-get update -y
sudo apt-get install -y docker.io git
sudo systemctl enable --now docker

sudo rm -rf /opt/wastewatch && sudo git clone "$REPO" /opt/wastewatch
cd /opt/wastewatch

sudo docker build -t wastewatch-ai .

# Pass the Nemotron/Nebius config through to the container at runtime.
sudo docker rm -f wastewatch 2>/dev/null || true
sudo docker run -d --name wastewatch --restart unless-stopped -p 8000:8000 \
  -e NEBIUS_API_KEY="${NEBIUS_API_KEY:-}" \
  -e NEBIUS_BASE_URL="${NEBIUS_BASE_URL:-https://api.studio.nebius.com/v1/}" \
  -e NEMOTRON_VL_MODEL="${NEMOTRON_VL_MODEL:-nvidia/Nemotron-3.5-Super-VL}" \
  -e NEMOTRON_REASON_MODEL="${NEMOTRON_REASON_MODEL:-nvidia/nemotron-3-super-120b-a12b}" \
  -e NEMOTRON_DEEP_MODEL="${NEMOTRON_DEEP_MODEL:-nvidia/Nemotron-3-Ultra-550b-a55b}" \
  -e TAVILY_API_KEY="${TAVILY_API_KEY:-}" \
  -e REVIEWER_TOKEN="${REVIEWER_TOKEN:-dev-reviewer-token}" \
  wastewatch-ai

sleep 4
echo "---- health ----"
curl -fsS http://localhost:8000/health || true
echo
echo "WasteWatch backend is live on http://<VM_PUBLIC_IP>:8000"
echo "Set FASTAPI_ORIGIN to that URL in the Vercel frontend."
