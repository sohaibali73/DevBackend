# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
# Prevents Python from writing .pyc files and keeps logs moving in real-time
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js and npm for presentation generation
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy package.json and install Node.js dependencies
COPY package.json .
RUN npm install

# Copy application code (order matters: least changed to most changed)
COPY config.py .
COPY api/ ./api/
COPY core/ ./core/
COPY db/ ./db/
COPY main.py .
COPY Claude\ Skills/ ./Claude\ Skills/

# Expose the port (Note: Railway ignores this, but it's good practice)
EXPOSE 8000

# We omit the Docker HEALTHCHECK here because Railway uses its own
# networking layer to probe your /health endpoint.

# Start command
# Using the list format ensures signals (like SIGTERM) are handled correctly
CMD ["python", "main.py"]