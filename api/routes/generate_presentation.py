"""
Presentation Generation API Route
==================================
REST endpoint for generating PowerPoint presentations with complete element support:
- Images (base64 upload and embedding)
- Potomac charts (visual elements)
- Potomac tables (dynamic tables)
- Text and shapes

Usage: POST /api/generate-presentation
"""

import os
import json
import tempfile
import asyncio
import base64
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
import aiofiles
import subprocess
from pathlib import Path

router = APIRouter()

# Potomac brand colors
POTOMAC_COLORS = {
    'YELLOW': 'FEC00F',
    'DARK_GRAY': '212121',
    'TURQUOISE': '00DED1',
    'WHITE': 'FFFFFF',
}

@router.post("/api/generate-presentation")
async def generate_presentation(request: Request):
    """
    Generate a PowerPoint presentation from slide data with complete element support.
    
    Request body format:
    {
        "title": "Presentation Title",
        "slides": [
            {
                "title": "Slide Title",
                "content": [
                    {
                        "type": "text",
                        "x": 100,
                        "y": 100,
                        "width": 400,
                        "height": 100,
                        "content": "Text content",
                        "style": {
                            "fontSize": 16,
                            "fontWeight": "bold",
                            "fontFamily": "Quicksand",
                            "color": "#212121",
                            "textAlign": "left"
                        }
                    },
                    {
                        "type": "image",
                        "x": 100,
                        "y": 250,
                        "width": 400,
                        "height": 300,
                        "content": {
                            "src": "data:image/png;base64,iVBORw0KG...",
                            "alt": "Description"
                        }
                    },
                    {
                        "type": "chart",
                        "x": 50,
                        "y": 100,
                        "width": 700,
                        "height": 350,
                        "content": {
                            "type": "process_flow",
                            "data": {},
                            "config": {
                                "skillFunction": "createInvestmentProcessFlow"
                            }
                        }
                    },
                    {
                        "type": "table",
                        "x": 50,
                        "y": 100,
                        "width": 700,
                        "height": 300,
                        "content": {
                            "type": "passive_active",
                            "headers": ["TIME PERIOD", "PASSIVE", "ACTIVE", "OUTPERFORMANCE"],
                            "rows": [
                                ["1 Year", "5.2%", "7.8%", "+2.6%"],
                                ["3 Year", "7.8%", "9.4%", "+1.6%"]
                            ],
                            "config": {
                                "skillFunction": "createPassiveActiveTable"
                            }
                        }
                    }
                ],
                "layout": "blank",
                "notes": "Slide notes",
                "background": "#FFFFFF"
            }
        ],
        "theme": "potomac",
        "format": "pptx"
    }
    """
    try:
        body = await request.json()
        title = body.get("title", "Presentation")
        slides = body.get("slides", [])
        theme = body.get("theme", "potomac")
        format_type = body.get("format", "pptx")
        
        if not slides:
            raise HTTPException(status_code=400, detail="No slides provided")
        
        # Generate unique filename
        import time
        timestamp = int(time.time() * 1000)
        filename = f"{title.replace(' ', '_').replace('/', '_')}_{timestamp}"
        input_path = f"/tmp/{filename}.json"
        output_path = f"/tmp/{filename}.{format_type}"
        
        # Process slides and extract images
        processed_slides = []
        for slide in slides:
            processed_content = []
            
            for element in slide.get("content", []):
                if element["type"] == "image" and element["content"]["src"].startswith("data:"):
                    # Handle base64 image
                    base64_data = element["content"]["src"].split(",")[1]
                    image_buffer = base64_data.encode('utf-8')
                    
                    # Create temp image file
                    import base64
                    image_data = base64.b64decode(base64_data)
                    image_filename = f"img_{timestamp}_{len(processed_content)}.png"
                    image_path = f"/tmp/{image_filename}"
                    
                    async with aiofiles.open(image_path, 'wb') as f:
                        await f.write(image_data)
                    
                    processed_content.append({
                        **element,
                        "content": {
                            **element["content"],
                            "src": image_path
                        }
                    })
                else:
                    processed_content.append(element)
            
            processed_slides.append({
                **slide,
                "content": processed_content
            })
        
        # Write slide data to temp file
        slide_data = {
            "title": title,
            "slides": processed_slides,
            "theme": theme
        }
        
        async with aiofiles.open(input_path, 'w') as f:
            await f.write(json.dumps(slide_data, indent=2))
        
        # Call the PowerPoint generation script
        skill_path = "/mnt/skills/user/potomac-pptx"
        command = [
            "node", 
            f"{skill_path}/scripts/generate-enhanced-presentation.js",
            "--input", input_path,
            "--output", output_path,
            "--type", "enhanced",
            "--compliance", "strict"
        ]
        
        # Execute the command
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise HTTPException(status_code=500, detail=f"Generation failed: {error_msg}")
        
        # Read generated file
        async with aiofiles.open(output_path, 'rb') as f:
            file_buffer = await f.read()
        
        # Clean up temp files
        await cleanup_temp_files(input_path, output_path, timestamp)
        
        # Return file
        content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation" if format_type == "pptx" else "application/pdf"
        
        return FileResponse(
            output_path,
            media_type=content_type,
            filename=f"{filename}.{format_type}",
            background=BackgroundTask(cleanup_file, output_path)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.post("/api/generate-presentation/test")
async def test_presentation():
    """Test endpoint to generate a sample presentation with all element types."""
    
    test_data = {
        "title": "Complete Integration Test",
        "slides": [
            {
                "title": "Title Slide",
                "content": [
                    {
                        "type": "text",
                        "x": 100,
                        "y": 100,
                        "width": 600,
                        "height": 100,
                        "content": "Complete Backend Integration Test",
                        "style": {
                            "fontSize": 32,
                            "fontWeight": "bold",
                            "fontFamily": "Rajdhani",
                            "color": "#212121",
                            "textAlign": "center"
                        }
                    }
                ],
                "layout": "title",
                "background": "#FFFFFF"
            },
            {
                "title": "Image Test",
                "content": [
                    {
                        "type": "image",
                        "x": 100,
                        "y": 100,
                        "width": 400,
                        "height": 300,
                        "content": {
                            "src": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
                            "alt": "Test Image"
                        }
                    }
                ],
                "layout": "blank",
                "background": "#FFFFFF"
            },
            {
                "title": "Chart Test",
                "content": [
                    {
                        "type": "chart",
                        "x": 50,
                        "y": 100,
                        "width": 700,
                        "height": 350,
                        "content": {
                            "type": "process_flow",
                            "data": {},
                            "config": {
                                "skillFunction": "createInvestmentProcessFlow"
                            }
                        }
                    }
                ],
                "layout": "blank",
                "background": "#FFFFFF"
            },
            {
                "title": "Table Test",
                "content": [
                    {
                        "type": "table",
                        "x": 50,
                        "y": 100,
                        "width": 700,
                        "height": 300,
                        "content": {
                            "type": "passive_active",
                            "headers": ["TIME PERIOD", "PASSIVE", "ACTIVE", "OUTPERFORMANCE"],
                            "rows": [
                                ["1 Year", "5.2%", "7.8%", "+2.6%"],
                                ["3 Year", "7.8%", "9.4%", "+1.6%"]
                            ],
                            "config": {
                                "skillFunction": "createPassiveActiveTable"
                            }
                        }
                    }
                ],
                "layout": "blank",
                "background": "#FFFFFF"
            }
        ],
        "theme": "potomac",
        "format": "pptx"
    }
    
    return await generate_presentation(test_data)


async def cleanup_temp_files(input_path: str, output_path: str, timestamp: int):
    """Clean up temporary files."""
    try:
        # Remove input file
        if os.path.exists(input_path):
            os.unlink(input_path)
        
        # Remove image temp files
        temp_dir = "/tmp"
        for filename in os.listdir(temp_dir):
            if filename.startswith(f"img_{timestamp}") and filename.endswith(".png"):
                file_path = os.path.join(temp_dir, filename)
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    
    except Exception as e:
        print(f"Warning: Failed to cleanup temp files: {e}")


class BackgroundTask:
    """Background task for cleanup after response."""
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    async def __call__(self):
        await self.func(*self.args, **self.kwargs)


async def cleanup_file(file_path: str):
    """Clean up a single file."""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        print(f"Warning: Failed to cleanup file {file_path}: {e}")


# Add the router to your main app
# from main import app
# app.include_router(router)