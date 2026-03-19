# =============================================================================
# Dockerfile — BULLETPROOF EDITION
# FastAPI backend on Railway
# =============================================================================

# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Prevents Python from writing .pyc files and keeps logs moving in real-time
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# =============================================================================
# SYSTEM DEPENDENCIES
# =============================================================================

RUN apt-get update && apt-get install -y \
    # Build tools
    gcc \
    libffi-dev \
    curl \
    # OCR (required by pytesseract + unstructured)
    tesseract-ocr \
    tesseract-ocr-eng \
    # Magic byte detection (required by filetype + unstructured)
    libmagic1 \
    # PyMuPDF system libs (crashes without these)
    libgl1 \
    libglib2.0-0 \
    # PDF parsing (required by pdfplumber + unstructured)
    poppler-utils \
    # Old Office format conversion .doc/.ppt/.xls (required by unstructured)
    libreoffice \
    # Audio processing (required by pydub)
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# NODE.JS + PPTXGENJS
# =============================================================================

RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pptxgenjs && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# PYTHON DEPENDENCIES
# =============================================================================

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =============================================================================
# APPLICATION CODE
# Ordered least-changed to most-changed for optimal layer caching
# =============================================================================

COPY config.py .
COPY db/ ./db/
COPY core/ ./core/
COPY api/ ./api/

COPY main.py .

# =============================================================================
# RUNTIME
# =============================================================================

# Railway manages port binding via $PORT env var
EXPOSE 8000

# Gunicorn with UvicornWorker for production-grade async handling
# --timeout 120 matches keep-alive in main.py for long-running skill API calls
# --workers 2 is safe for Railway's default memory limits
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "120"]