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

# Run the server
CMD ["soul-legacy", "serve", "--host", "0.0.0.0", "--port", "8080", "--cloud"]
