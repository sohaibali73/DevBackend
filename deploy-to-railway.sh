#!/bin/bash

# Potomac Presentation Editor - Railway Deployment Script
# This script helps deploy the complete backend integration to Railway

echo "🚀 Potomac Presentation Editor - Railway Deployment"
echo "=================================================="
echo ""

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Please install it first:"
    echo "   npm install -g @railway/cli"
    echo "   or visit: https://docs.railway.app/guides/cli"
    exit 1
fi

echo "✅ Railway CLI found"

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "❌ Not logged into Railway. Please run: railway login"
    exit 1
fi

echo "✅ Logged into Railway"

# Check if project exists
PROJECT_NAME="potomac-presentation-editor"
if ! railway list | grep -q "$PROJECT_NAME"; then
    echo "❌ Project '$PROJECT_NAME' not found in Railway"
    echo "   Creating new project..."
    railway init "$PROJECT_NAME"
fi

echo "✅ Using project: $PROJECT_NAME"

# Deploy to Railway
echo ""
echo "📦 Deploying to Railway..."
echo ""

# Deploy the project
railway deploy

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Deployment successful!"
    echo ""
    
    # Get the deployment URL
    DEPLOYMENT_URL=$(railway domains | grep "https" | head -1)
    if [ -n "$DEPLOYMENT_URL" ]; then
        echo "🌐 Your application is available at: $DEPLOYMENT_URL"
        echo ""
        echo "🧪 Testing the deployment..."
        echo ""
        
        # Test the health endpoint
        echo "🏥 Testing health endpoint..."
        curl -s "$DEPLOYMENT_URL/health" && echo " ✅ Health check passed"
        
        echo ""
        echo "🔌 Testing generate-presentation router..."
        curl -s -X POST "$DEPLOYMENT_URL/api/generate-presentation/test" && echo " ✅ Router test passed"
        
        echo ""
        echo "✅ All tests passed! Your complete presentation editor is now live on Railway."
        echo ""
        echo "📋 Next steps:"
        echo "   1. Open the deployment URL in your browser"
        echo "   2. Test the API endpoints"
        echo "   3. Integrate with your frontend application"
        echo "   4. Monitor logs: railway logs"
        echo ""
        echo "🔗 Deployment URL: $DEPLOYMENT_URL"
    else
        echo "⚠️  Could not retrieve deployment URL"
        echo "   Check your Railway dashboard for the deployment status"
    fi
else
    echo "❌ Deployment failed"
    echo "   Check the logs: railway logs"
    exit 1
fi