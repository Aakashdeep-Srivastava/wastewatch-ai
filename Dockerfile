# WasteWatch AI container image (backend: FastAPI + OpenCV 5 + Nemotron client).
# CPU-only — Nemotron inference runs remotely on Nebius Token Factory, so this
# image needs no GPU. Deploy on a Nebius AI Cloud VM (Docker) or any container host.
FROM python:3.12-slim

# Runtime libs needed by opencv-python-headless (and rasterio) on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app

# Writable runtime dirs (StaticFiles mount + JSON alert store).
RUN mkdir -p out data

# Container port. uvicorn reads PORT (default 8000). NVIDIA/Nebius credentials and
# model IDs are injected at runtime (NEBIUS_API_KEY, NEBIUS_BASE_URL, NEMOTRON_*).
ENV PORT=8000 \
    ORBIT_AGENT=rule \
    PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
