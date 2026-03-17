# 🚀 Railway Deployment Guide

This guide will help you deploy the complete presentation editor with images, charts, and tables to Railway.

## Prerequisites

### 1. Railway Account
- Sign up at [railway.app](https://railway.app)
- Install the Railway CLI:
  ```bash
  npm install -g @railway/cli
  # or
  yarn global add @railway/cli
  ```

### 2. Git Repository
- Ensure your project is in a Git repository
- Commit all changes:
  ```bash
  git add .
  git commit -m "Complete backend integration for presentation editor"
  git push origin main
  ```

## Quick Deployment

### Option 1: Using the Deployment Script (Recommended)

1. **Make the script executable:**
   ```bash
   chmod +x deploy-to-railway.sh
   ```

2. **Run the deployment script:**
   ```bash
   ./deploy-to-railway.sh
   ```

The script will:
- Check if Railway CLI is installed and logged in
- Create a new project if needed
- Deploy your application
- Test the deployment

### Option 2: Manual Deployment

1. **Login to Railway:**
   ```bash
   railway login
   ```

2. **Initialize project:**
   ```bash
   railway init potomac-presentation-editor
   ```

3. **Deploy:**
   ```bash
   railway deploy
   ```

## Configuration

### Environment Variables

The application requires the following environment variables to be set in Railway:

1. **Navigate to your project settings in Railway dashboard**
2. **Add the following environment variables:**

```
# Required
ENVIRONMENT=production
LOG_LEVEL=INFO

# Optional (if using Supabase)
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_key

# Optional (if using Claude AI)
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Railway.json Configuration

The `railway.json` file is already configured with:
- **Builder**: NIXPACKS (automatic dependency detection)
- **Start Command**: `python main.py`
- **Health Check**: `/health` endpoint
- **Restart Policy**: On failure with max 10 retries

## Docker Deployment

The project includes a `Dockerfile` that:
- Uses Python 3.11 slim base image
- Installs Node.js for presentation generation
- Installs all Python and Node.js dependencies
- Copies the complete application including Claude Skills

To deploy with Docker:
```bash
# Build the image
docker build -t potomac-presentation-editor .

# Run locally for testing
docker run -p 8000:8000 potomac-presentation-editor
```

## Testing the Deployment

### 1. Health Check
```bash
curl https://your-deployment-url.railway.app/health
```

Expected response:
```json
{
  "status": "healthy",
  "routers_active": 15,
  "routers_failed": 0
}
```

### 2. Test Presentation Generation
```bash
curl -X POST https://your-deployment-url.railway.app/api/generate-presentation/test
```

### 3. Manual API Test
```bash
curl -X POST https://your-deployment-url.railway.app/api/generate-presentation \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Presentation",
    "slides": [
      {
        "title": "Test Slide",
        "content": [
          {
            "type": "text",
            "x": 100,
            "y": 100,
            "width": 400,
            "height": 100,
            "content": "Hello World!",
            "style": {
              "fontSize": 16,
              "fontWeight": "bold",
              "fontFamily": "Quicksand",
              "color": "#212121",
              "textAlign": "left"
            }
          }
        ],
        "layout": "blank",
        "background": "#FFFFFF"
      }
    ],
    "theme": "potomac",
    "format": "pptx"
  }' \
  --output test.pptx
```

## Monitoring and Logs

### View Logs
```bash
# View real-time logs
railway logs

# View logs for specific service
railway logs --service your-service-name
```

### Check Deployment Status
```bash
# List deployments
railway deployments

# View specific deployment
railway deployments --id deployment-id
```

## Troubleshooting

### Common Issues

1. **Deployment Timeout**
   - Increase timeout in `railway.json`:
   ```json
   {
     "deploy": {
       "healthcheckTimeout": 600
     }
   }
   ```

2. **Missing Dependencies**
   - Ensure `requirements.txt` and `package.json` are up to date
   - Check Railway logs for specific error messages

3. **Port Issues**
   - The application uses port 8000 by default
   - Railway automatically handles port mapping

4. **Node.js Dependencies**
   - The Dockerfile installs Node.js and npm
   - PptxGenJS is installed via `package.json`

### Debugging Steps

1. **Check Railway Logs:**
   ```bash
   railway logs --tail
   ```

2. **Test Locally:**
   ```bash
   # Run locally to test
   python main.py
   ```

3. **Verify Dependencies:**
   ```bash
   # Check if all dependencies are installed
   pip list
   npm list
   ```

## Performance Optimization

### 1. Caching
- Railway provides automatic caching for dependencies
- Use `.dockerignore` to exclude unnecessary files

### 2. Resource Allocation
- Monitor resource usage in Railway dashboard
- Scale up if needed for high traffic

### 3. Health Checks
- The `/health` endpoint is used for health checks
- Ensure it responds quickly (< 1 second)

## Security Considerations

1. **Environment Variables**
   - Never commit API keys to Git
   - Use Railway's environment variable management

2. **CORS Configuration**
   - The application has strict CORS settings
   - Update `ALLOWED_ORIGINS` in `main.py` for your domain

3. **Rate Limiting**
   - Built-in rate limiting (120 requests/minute per IP)
   - Adjust as needed in `main.py`

## Next Steps

1. **Frontend Integration**
   - Use the `frontend-integration-example.js` as a reference
   - Connect your frontend to the deployed API

2. **Monitoring**
   - Set up monitoring and alerting
   - Monitor API usage and performance

3. **Scaling**
   - Monitor resource usage
   - Scale horizontally if needed

4. **Backup**
   - Set up database backups if using Supabase
   - Consider application data persistence

## Support

If you encounter issues:

1. **Check Logs:** `railway logs`
2. **Test Locally:** Run the application locally first
3. **Railway Documentation:** https://docs.railway.app
4. **GitHub Issues:** Report issues in the project repository

---

🎉 **Your complete presentation editor is now ready for production on Railway!**