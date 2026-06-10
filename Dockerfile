# =============================================================================
# Multi-Stage Dockerfile — FastAPI Backend (Analyst by Potomac)
# =============================================================================

# STAGE 1: Builder — compile dependencies
FROM python:3.11-slim as builder

WORKDIR /build

# System dependencies for building Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and build wheels.
# NOTE: no --no-deps — we need wheels for transitive deps too (e.g. tqdm), so the
# offline `pip install --no-index` in the runtime stage can resolve everything.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# STAGE 2: Runtime — minimal production image
FROM python:3.11-slim

WORKDIR /app

# Environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PIP_NO_CACHE_DIR=1

# System dependencies for runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    # OCR (required by pytesseract + unstructured)
    tesseract-ocr \
    tesseract-ocr-eng \
    # Magic byte detection (required by filetype + unstructured)
    libmagic1 \
    # PyMuPDF system libs
    libgl1 \
    libglib2.0-0 \
    # PDF parsing (required by pdfplumber + unstructured)
    poppler-utils \
    # Office format conversion
    libreoffice \
    # Audio processing (required by pydub)
    ffmpeg \
    # Health check
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js + tools for PPTX generation
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g pptxgenjs docx && \
    npm cache clean --force && \
    rm -rf /var/lib/apt/lists/*

# Copy wheels from builder and install
COPY --from=builder /build/wheels /wheels
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# Copy application code (ordered by change frequency)
COPY config.py .
COPY db/ ./db/
COPY core/ ./core/
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY ["ALL NORGATE TICKERS.txt", "./ALL NORGATE TICKERS.txt"]
COPY ClaudeSkills/ ./ClaudeSkills/
COPY main.py .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

EXPOSE ${PORT}

# Run with uvicorn directly (simpler for containerized environments)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
