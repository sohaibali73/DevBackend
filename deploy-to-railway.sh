#!/bin/bash

# Simple deployment script for Railway
echo "Starting deployment to Railway..."

# Check if railway CLI is available
if ! command -v railway &> /dev/null; then
    echo "Error: Railway CLI not found. Please install it first."
    exit 1
fi

# Ensure we're in the correct project
echo "Current project: $(railway status | grep 'Project:' | cut -d: -f2 | xargs)"
echo "Current environment: $(railway status | grep 'Environment:' | cut -d: -f2 | xargs)"
echo "Current service: $(railway status | grep 'Service:' | cut -d: -f2 | xargs)"

# Deploy
echo "Deploying..."
railway up

echo "Deployment completed!"