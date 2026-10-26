# WasteWatch AI container image.
# OpenCV 5 (headless) + FastAPI served by uvicorn.
FROM python:3.12-slim

# Runtime libs needed by opencv-python-headless on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app

# App Runner / container port. uvicorn reads PORT (default 8000).
ENV PORT=8000 \
    ORBIT_AGENT=rule \
    PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
