# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the package files
COPY . .

# Install Python dependencies and the package itself
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir .

# Create config directory
RUN mkdir -p /config /media/shows /media/incoming

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV CONFIG_DIR=/config

# Run the application with default configuration
ENTRYPOINT ["python", "-m", "showrenamer.main"]
CMD ["/media/incoming", "--config-dir", "/config"]
