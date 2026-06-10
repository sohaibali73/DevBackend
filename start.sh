#!/bin/bash
# Quick Start Script for Potomac API Deployment

set -e

echo "🐳 Building Docker image for Potomac API..."
docker build -t potomac-api:latest .

echo "✅ Build complete!"
echo ""
echo "📝 Setup Instructions:"
echo "1. Copy .env.example to .env.local"
echo "   cp .env.example .env.local"
echo ""
echo "2. Edit .env.local with your Supabase and API keys"
echo "   - SUPABASE_URL"
echo "   - SUPABASE_KEY"
echo "   - SUPABASE_SERVICE_KEY"
echo "   - SUPABASE_JWT_SECRET"
echo "   - API_KEYS for LLM providers (Anthropic, OpenAI, etc.)"
echo ""
echo "3. Start services:"
echo "   docker compose up -d"
echo ""
echo "4. View logs:"
echo "   docker compose logs -f api"
echo ""
echo "5. Access:"
echo "   API: http://localhost:8000"
echo "   Docs: http://localhost:8000/docs"
echo "   Health: http://localhost:8000/health"
echo ""
echo "📦 Services running:"
echo "   - API (FastAPI) on :8000"
echo "   - PostgreSQL on :5432"
echo "   - Redis on :6379"
echo ""
echo "🧹 Cleanup:"
echo "   docker compose down -v  # Stop & remove volumes"
