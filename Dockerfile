FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest and install the package
COPY . .
RUN pip install --no-cache-dir .

# Expose port
EXPOSE 8080

# Run the server - use shell form to expand $PORT
CMD soul-legacy serve --host 0.0.0.0 --port ${PORT:-8080} --cloud
