FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir .

# Set cloud mode
ENV SOUL_LEGACY_MODE=cloud

EXPOSE 8080

# Bypass CLI bug - run uvicorn directly with shell for PORT expansion
CMD uvicorn soul_legacy.server.app:app --host 0.0.0.0 --port ${PORT:-8080}
