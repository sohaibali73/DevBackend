#!/usr/bin/env python3
"""
Complete Backend Integration Test Script
========================================
Tests the complete presentation editor integration with images, charts, and tables.
"""

import requests
import json
import base64
import time
import os
from pathlib import Path

# Test configuration
BASE_URL = "http://localhost:8070"
API_ENDPOINT = f"{BASE_URL}/api/generate-presentation"

# Sample base64 image (1x1 pixel)
SAMPLE_IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

def test_complete_presentation():
    """Test complete presentation with all element types."""
    
    print("🧪 Testing Complete Backend Integration...")
    print("=" * 50)
    
    # Test data with all element types
    test_data = {
        "title": "Complete Integration Test - Images, Charts & Tables",
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
                    },
                    {
                        "type": "text",
                        "x": 100,
                        "y": 250,
                        "width": 600,
                        "height": 50,
                        "content": "Testing images, charts, and tables integration",
                        "style": {
                            "fontSize": 18,
                            "fontWeight": "normal",
                            "fontFamily": "Quicksand",
                            "color": "#666666",
                            "textAlign": "center"
                        }
                    }
                ],
                "layout": "title",
                "notes": "This is the title slide for our integration test.",
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
                            "src": SAMPLE_IMAGE,
                            "alt": "Test Image"
                        }
                    },
                    {
                        "type": "text",
                        "x": 550,
                        "y": 100,
                        "width": 300,
                        "height": 100,
                        "content": "Image Upload Test",
                        "style": {
                            "fontSize": 24,
                            "fontWeight": "bold",
                            "fontFamily": "Rajdhani",
                            "color": "#212121",
                            "textAlign": "left"
                        }
                    },
                    {
                        "type": "text",
                        "x": 550,
                        "y": 200,
                        "width": 300,
                        "height": 150,
                        "content": "This slide tests image upload and embedding functionality. The image should appear on the left side of the slide.",
                        "style": {
                            "fontSize": 14,
                            "fontWeight": "normal",
                            "fontFamily": "Quicksand",
                            "color": "#666666",
                            "textAlign": "left"
                        }
                    }
                ],
                "layout": "blank",
                "notes": "Testing image upload and base64 to file conversion.",
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
                    },
                    {
                        "type": "text",
                        "x": 50,
                        "y": 50,
                        "width": 700,
                        "height": 30,
                        "content": "Investment Process Flow Chart",
                        "style": {
                            "fontSize": 20,
                            "fontWeight": "bold",
                            "fontFamily": "Rajdhani",
                            "color": "#212121",
                            "textAlign": "center"
                        }
                    }
                ],
                "layout": "blank",
                "notes": "Testing Potomac chart template integration.",
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
                                ["3 Year", "7.8%", "9.4%", "+1.6%"],
                                ["5 Year", "9.1%", "11.2%", "+2.1%"],
                                ["10 Year", "8.7%", "10.3%", "+1.6%"]
                            ],
                            "config": {
                                "skillFunction": "createPassiveActiveTable"
                            }
                        }
                    },
                    {
                        "type": "text",
                        "x": 50,
                        "y": 50,
                        "width": 700,
                        "height": 30,
                        "content": "Passive vs Active Performance Table",
                        "style": {
                            "fontSize": 20,
                            "fontWeight": "bold",
                            "fontFamily": "Rajdhani",
                            "color": "#212121",
                            "textAlign": "center"
                        }
                    }
                ],
                "layout": "blank",
                "notes": "Testing Potomac table template integration.",
                "background": "#FFFFFF"
            },
            {
                "title": "Multiple Charts Test",
                "content": [
                    {
                        "type": "chart",
                        "x": 50,
                        "y": 100,
                        "width": 350,
                        "height": 250,
                        "content": {
                            "type": "performance",
                            "data": {
                                "bullMarket": { "return": "+18.5%", "period": "2021-2022" },
                                "bearMarket": { "return": "+3.2%", "period": "2022-2023" },
                                "benchmark": { "bull": "+12.8%", "bear": "-15.6%" }
                            },
                            "config": {
                                "skillFunction": "createStrategyPerformanceViz"
                            }
                        }
                    },
                    {
                        "type": "chart",
                        "x": 420,
                        "y": 100,
                        "width": 350,
                        "height": 250,
                        "content": {
                            "type": "communication",
                            "data": {},
                            "config": {
                                "skillFunction": "createCommunicationFlow"
                            }
                        }
                    },
                    {
                        "type": "text",
                        "x": 50,
                        "y": 50,
                        "width": 700,
                        "height": 30,
                        "content": "Multiple Chart Types",
                        "style": {
                            "fontSize": 20,
                            "fontWeight": "bold",
                            "fontFamily": "Rajdhani",
                            "color": "#212121",
                            "textAlign": "center"
                        }
                    }
                ],
                "layout": "blank",
                "notes": "Testing multiple chart types on one slide.",
                "background": "#FFFFFF"
            },
            {
                "title": "Multiple Tables Test",
                "content": [
                    {
                        "type": "table",
                        "x": 50,
                        "y": 100,
                        "width": 350,
                        "height": 200,
                        "content": {
                            "type": "afg",
                            "headers": ["ASSET RANGE", "MANAGEMENT FEE", "PERFORMANCE FEE", "EFFECTIVE TOTAL"],
                            "rows": [
                                ["$0 - $1M", "1.00%", "15%", "1.15%"],
                                ["$1M - $5M", "0.85%", "15%", "1.00%"],
                                ["$5M - $10M", "0.75%", "15%", "0.90%"]
                            ],
                            "config": {
                                "skillFunction": "createAFGTable"
                            }
                        }
                    },
                    {
                        "type": "table",
                        "x": 420,
                        "y": 100,
                        "width": 350,
                        "height": 200,
                        "content": {
                            "type": "annualized_return",
                            "headers": ["STRATEGY", "YTD", "1-YEAR", "3-YEAR"],
                            "rows": [
                                ["Bull Bear", "8.2%", "12.8%", "11.2%"],
                                ["Guardian", "6.7%", "9.4%", "8.9%"],
                                ["Income Plus", "4.9%", "7.2%", "6.8%"]
                            ],
                            "config": {
                                "skillFunction": "createAnnualizedReturnTable"
                            }
                        }
                    },
                    {
                        "type": "text",
                        "x": 50,
                        "y": 50,
                        "width": 700,
                        "height": 30,
                        "content": "Multiple Table Types",
                        "style": {
                            "fontSize": 20,
                            "fontWeight": "bold",
                            "fontFamily": "Rajdhani",
                            "color": "#212121",
                            "textAlign": "center"
                        }
                    }
                ],
                "layout": "blank",
                "notes": "Testing multiple table types on one slide.",
                "background": "#FFFFFF"
            }
        ],
        "theme": "potomac",
        "format": "pptx"
    }
    
    print("📊 Sending test request to API...")
    
    try:
        # Send request to API
        response = requests.post(
            API_ENDPOINT,
            json=test_data,
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        
        if response.status_code == 200:
            print("✅ API request successful!")
            
            # Save the generated PPTX file
            filename = f"integration_test_{int(time.time())}.pptx"
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Presentation saved as: {filename}")
            print(f"📁 File size: {len(response.content)} bytes")
            
            # Verify file is valid PPTX
            if filename.endswith('.pptx'):
                import zipfile
                try:
                    with zipfile.ZipFile(filename, 'r') as zip_file:
                        files = zip_file.namelist()
                        if 'ppt/presentation.xml' in files:
                            print("✅ Valid PPTX file structure detected")
                        else:
                            print("⚠️  PPTX structure may be incomplete")
                except zipfile.BadZipFile:
                    print("❌ Invalid PPTX file - bad zip format")
            
            return True
            
        else:
            print(f"❌ API request failed with status {response.status_code}")
            print(f"Error: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Make sure the server is running on port 8070.")
        return False
    except requests.exceptions.Timeout:
        print("❌ Request timed out. The server may be taking too long to process.")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_api_health():
    """Test if the API is running and healthy."""
    print("🏥 Testing API Health...")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ API is healthy!")
            print(f"   Status: {health_data.get('status', 'unknown')}")
            print(f"   Routers active: {health_data.get('routers_active', 0)}")
            print(f"   Routers failed: {health_data.get('routers_failed', 0)}")
            return True
        else:
            print(f"❌ Health check failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_generate_presentation_router():
    """Test if the generate_presentation router is loaded."""
    print("🔌 Testing Generate Presentation Router...")
    
    try:
        # Try to access the test endpoint
        response = requests.post(f"{BASE_URL}/api/generate-presentation/test", timeout=10)
        if response.status_code == 200:
            print("✅ Generate presentation router is working!")
            return True
        else:
            print(f"❌ Router test failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Router test failed: {e}")
        return False

def main():
    """Run all integration tests."""
    print("🚀 Complete Backend Integration Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: API Health
    health_ok = test_api_health()
    print()
    
    # Test 2: Router Test
    router_ok = test_generate_presentation_router()
    print()
    
    # Test 3: Complete Integration Test
    if health_ok and router_ok:
        integration_ok = test_complete_presentation()
        print()
        
        # Summary
        print("📊 Test Summary")
        print("=" * 30)
        print(f"API Health: {'✅ PASS' if health_ok else '❌ FAIL'}")
        print(f"Router Test: {'✅ PASS' if router_ok else '❌ FAIL'}")
        print(f"Integration Test: {'✅ PASS' if integration_ok else '❌ FAIL'}")
        print()
        
        if health_ok and router_ok and integration_ok:
            print("🎉 All tests passed! Complete backend integration is working.")
            print()
            print("Next steps:")
            print("1. Open the generated PPTX file to verify content")
            print("2. Check that images, charts, and tables render correctly")
            print("3. Verify Potomac brand compliance (colors, fonts)")
            print("4. Test with your frontend application")
        else:
            print("❌ Some tests failed. Check the error messages above.")
    else:
        print("❌ Skipping integration test due to prerequisite failures.")

if __name__ == "__main__":
    main()