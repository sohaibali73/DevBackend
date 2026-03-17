# 🔌 Complete Backend Integration - Images, Charts & Tables

## Overview

This guide shows how to integrate the **complete presentation editor** (with images, Potomac charts, and Potomac tables) with your PowerPoint skill backend.

---

## 📊 What's New

### **Potomac Chart Templates**
✅ Investment Process Flow
✅ Strategy Performance Viz
✅ Communication Flow
✅ Firm Structure Infographic
✅ OCIO Triangle

**Backend Functions:**
- `createInvestmentProcessFlow()`
- `createStrategyPerformanceViz()`
- `createCommunicationFlow()`
- `createFirmStructureInfographic()`
- `createOCIOTriangle()`

### **Potomac Table Templates**
✅ Passive vs Active Performance
✅ Asset Fee Grid (AFG)
✅ Annualized Returns
✅ Strategy Overview
✅ Performance Attribution
✅ Risk Metrics

**Backend Functions:**
- `createPassiveActiveTable()`
- `createAFGTable()`
- `createAnnualizedReturnTable()`
- `createStrategyOverviewTable()`
- `createAttributionTable()`
- `createRiskMetricsTable()`

### **Image Support**
✅ Upload and embed images
✅ Base64 encoding
✅ Position and resize

---

## 🚀 Step 1: Update API Endpoint

### New API Route: `/api/generate-presentation`

The new API endpoint is located at `api/routes/generate_presentation.py` and handles all element types:

```python
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
```

### Key Features:

1. **Image Processing**: Converts base64 images to temporary files for PPTX embedding
2. **Element Type Support**: Handles text, images, charts, tables, and shapes
3. **Chart Integration**: Uses PotomacVisualElements for chart rendering
4. **Table Integration**: Uses PotomacDynamicTables for table rendering
5. **Error Handling**: Comprehensive error handling with cleanup
6. **Async Processing**: Uses asyncio for non-blocking operations

---

## 🎨 Step 2: Updated Generation Script

### Enhanced Script: `/mnt/skills/user/potomac-pptx/scripts/generate-enhanced-presentation.js`

The updated script now handles all element types:

```javascript
// Process each content element
slideData.content.forEach((element) => {
  switch (element.type) {
    case 'text':
      // Add text element with styling
      slide.addText(element.content, {
        x: element.x / 100,
        y: element.y / 100,
        w: element.width / 100,
        h: element.height / 100,
        fontSize: element.style.fontSize || 16,
        bold: element.style.fontWeight === 'bold',
        fontFace: element.style.fontFamily || 'Quicksand',
        color: element.style.color?.replace('#', '') || COLORS.DARK_GRAY,
        align: element.style.textAlign || 'left',
        valign: 'top',
      });
      break;

    case 'image':
      // Add image element from temp file
      slide.addImage({
        path: element.content.src, // File path from temp
        x: element.x / 100,
        y: element.y / 100,
        w: element.width / 100,
        h: element.height / 100,
      });
      break;

    case 'chart':
      // Add Potomac chart using visual elements system
      const chartType = element.content.type;
      const chartConfig = {
        startX: element.x / 100,
        startY: element.y / 100,
        width: element.width / 100,
        height: element.height / 100,
      };

      switch (chartType) {
        case 'process_flow':
          visualElements.createInvestmentProcessFlow(slide, chartConfig);
          break;
        case 'performance':
          visualElements.createStrategyPerformanceViz(slide, element.content.data, chartConfig);
          break;
        // ... other chart types
      }
      break;

    case 'table':
      // Add Potomac table using dynamic tables system
      const tableType = element.content.type;
      const tablePosition = {
        x: element.x / 100,
        y: element.y / 100,
        w: element.width / 100,
        h: element.height / 100,
      };

      // Convert frontend table data to backend format
      const tableData = convertTableData(tableType, element.content);

      switch (tableType) {
        case 'passive_active':
          dynamicTables.createPassiveActiveTable(slide, tableData, tablePosition);
          break;
        case 'afg':
          dynamicTables.createAFGTable(slide, tableData, tablePosition);
          break;
        // ... other table types
      }
      break;
  }
});
```

---

## 🧪 Step 3: Testing

### Run Integration Tests

Use the provided test script to verify everything works:

```bash
# Make sure the server is running
python main.py

# Run the integration test
python test-integration.py
```

### Test Results

The test will:
1. ✅ Check API health
2. ✅ Verify router loading
3. ✅ Generate a complete presentation with all element types
4. ✅ Save and validate the PPTX file
5. ✅ Verify file structure

### Manual Testing

You can also test manually using curl:

```bash
# Test with image
curl -X POST http://localhost:8070/api/generate-presentation \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Image Test",
    "slides": [
      {
        "title": "Test Slide",
        "content": [
          {
            "type": "image",
            "x": 100,
            "y": 100,
            "width": 400,
            "height": 300,
            "content": {
              "src": "data:image/png;base64,iVBORw0KG...",
              "alt": "Test Image"
            }
          }
        ],
        "layout": "blank",
        "background": "#FFFFFF"
      }
    ]
  }' \
  --output test-image.pptx

# Test with chart
curl -X POST http://localhost:8070/api/generate-presentation \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Chart Test",
    "slides": [
      {
        "title": "Investment Process",
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
      }
    ]
  }' \
  --output test-chart.pptx

# Test with table
curl -X POST http://localhost:8070/api/generate-presentation \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Table Test",
    "slides": [
      {
        "title": "Performance Data",
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
    ]
  }' \
  --output test-table.pptx
```

---

## 📊 Step 4: Verify Output

### Check Generated PPTX Files

Open each generated PPTX and verify:

✅ **Images:**
- Image appears in correct position
- Image maintains aspect ratio
- Image quality is good

✅ **Charts:**
- Chart follows Potomac brand guidelines
- Colors are correct (#FEC00F, #212121, #00DED1)
- Fonts are Rajdhani (titles) and Quicksand (body)
- Layout matches template design

✅ **Tables:**
- Table structure is correct
- Header row has yellow background
- Alternating row colors
- Brand-compliant styling
- Data is accurate

---

## 🎯 Step 5: Frontend Integration

### Complete Frontend Example

The `frontend-integration-example.js` file provides a complete frontend implementation:

```javascript
class PresentationEditor {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.presentation = {
      title: 'New Presentation',
      slides: [],
      theme: 'potomac'
    };
    this.currentSlideIndex = 0;
    this.init();
  }

  // Methods for adding elements
  addElement(type) {
    const slide = this.presentation.slides[this.currentSlideIndex];
    if (!slide) return;

    const element = this.createElement(type);
    slide.content.push(element);
    this.render();
  }

  createElement(type) {
    const baseElement = {
      x: 100,
      y: 100,
      width: 200,
      height: 100
    };

    switch (type) {
      case 'text':
        return {
          ...baseElement,
          type: 'text',
          content: 'New Text',
          style: {
            fontSize: 16,
            fontWeight: 'normal',
            fontFamily: 'Quicksand',
            color: '#212121',
            textAlign: 'left'
          }
        };
      
      case 'image':
        return {
          ...baseElement,
          type: 'image',
          content: {
            src: '',
            alt: 'Image description'
          }
        };
      
      case 'chart':
        return {
          ...baseElement,
          type: 'chart',
          content: {
            type: 'process_flow',
            data: {},
            config: {
              skillFunction: 'createInvestmentProcessFlow'
            }
          }
        };
      
      case 'table':
        return {
          ...baseElement,
          type: 'table',
          content: {
            type: 'passive_active',
            headers: ['TIME PERIOD', 'PASSIVE', 'ACTIVE', 'OUTPERFORMANCE'],
            rows: [
              ['1 Year', '5.2%', '7.8%', '+2.6%'],
              ['3 Year', '7.8%', '9.4%', '+1.6%']
            ],
            config: {
              skillFunction: 'createPassiveActiveTable'
            }
          }
        };
      
      default:
        return baseElement;
    }
  }

  async exportPresentation() {
    try {
      // Prepare slide data for backend
      const slideData = this.presentation.slides.map(slide => ({
        title: slide.title,
        content: slide.content.map(el => {
          if (el.type === 'text') {
            return {
              type: 'text',
              x: el.x,
              y: el.y,
              width: el.width,
              height: el.height,
              content: el.content,
              style: el.style,
            };
          } else if (el.type === 'chart') {
            return {
              type: 'chart',
              x: el.x,
              y: el.y,
              width: el.width,
              height: el.height,
              content: {
                type: el.content.type,
                data: el.content.data,
                config: el.content.config,
              },
            };
          } else if (el.type === 'table') {
            return {
              type: 'table',
              x: el.x,
              y: el.y,
              width: el.width,
              height: el.height,
              content: {
                type: el.content.type,
                headers: el.content.headers,
                rows: el.content.rows,
                config: el.content.config,
              },
            };
          } else if (el.type === 'image') {
            return {
              type: 'image',
              x: el.x,
              y: el.y,
              width: el.width,
              height: el.height,
              content: {
                src: el.content.src,
                alt: el.content.alt,
              },
            };
          } else if (el.type === 'shape') {
            return {
              type: 'shape',
              x: el.x,
              y: el.y,
              width: el.width,
              height: el.height,
              style: el.style,
            };
          }
          return { type: el.type, ...el };
        }),
        layout: slide.layout,
        notes: slide.notes,
        background: slide.background,
      }));

      // Call backend API
      const response = await fetch('/api/generate-presentation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: this.presentation.title,
          slides: slideData,
          theme: this.presentation.theme,
          format: 'pptx',
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.details || 'Generation failed');
      }

      // Download file
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${this.presentation.title}.pptx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      alert('Presentation generated successfully!');
    } catch (error) {
      console.error('Export error:', error);
      alert(`Export failed: ${error.message}`);
    }
  }
}
```

---

## 🔍 Troubleshooting

### Issue: Images not appearing

**Check:**
1. Image base64 is being properly extracted
2. Temp file is created successfully
3. File path is correct in slide data
4. Image file is not deleted before PPTX generation

**Fix:**
```javascript
// Verify image temp file exists
const imageExists = fs.existsSync(imagePath);
console.log('Image file exists:', imageExists);
```

### Issue: Charts render incorrectly

**Check:**
1. Chart type matches available templates
2. `PotomacVisualElements` is imported correctly
3. Chart config positions are scaled correctly (pixels to inches)
4. Potomac colors are defined

**Fix:**
```javascript
// Log chart type and config
console.log('Chart type:', chartType);
console.log('Chart config:', chartConfig);
```

### Issue: Tables have wrong data

**Check:**
1. Table data conversion matches expected format
2. Headers match table type
3. Row data is in correct order
4. `PotomacDynamicTables` is imported

**Fix:**
```javascript
// Log converted table data
const tableData = convertTableData(tableType, element.content);
console.log('Converted table data:', tableData);
```

### Issue: Brand colors wrong

**Check:**
1. Colors are 6-digit hex without #
2. Potomac colors constant is correct
3. Theme colors are passed properly

**Fix:**
```javascript
const COLORS = {
  YELLOW: 'FEC00F',
  DARK_GRAY: '212121',
  TURQUOISE: '00DED1',
  WHITE: 'FFFFFF',
};
```

---

## ✅ Complete Integration Checklist

- [ ] API endpoint handles images, charts, tables
- [ ] Generation script imports visual elements and tables
- [ ] Image base64 conversion works
- [ ] All chart types render correctly
- [ ] All table types render correctly
- [ ] Brand compliance maintained
- [ ] Temp files cleaned up properly
- [ ] Error handling in place
- [ ] Frontend sends proper data format
- [ ] Testing complete for all element types

---

## 🎉 Success Criteria

Your integration is complete when:

✅ You can add images via upload
✅ All 5 Potomac charts render perfectly
✅ All 6 Potomac tables render with correct data
✅ Brand colors are 100% compliant
✅ Fonts are correct (Rajdhani + Quicksand)
✅ Export downloads working PPTX
✅ No TypeScript errors
✅ No console errors
✅ Performance is acceptable (<5s for 10-slide deck)

---

## 🚀 Next Level Features

Once basic integration works:

1. **Chart Data Editing**: Allow users to edit chart data in UI
2. **Table Cell Editing**: Inline table editing
3. **Image Cropping**: Crop tool for images
4. **Bulk Upload**: Upload multiple images at once
5. **Chart Presets**: Save custom chart configurations
6. **Table Templates**: Custom table templates
7. **Theme Switching**: Switch between Potomac themes
8. **Export Options**: PDF export, specific slide ranges

---

## 📁 File Structure

```
DevBackend/
├── api/routes/generate_presentation.py     # New API endpoint
├── main.py                                 # Updated to include new router
├── test-integration.py                     # Integration test script
├── frontend-integration-example.js         # Complete frontend example
└── Claude Skills/potomac-pptx/
    ├── scripts/generate-enhanced-presentation.js  # Updated generation script
    ├── infographics/visual-elements.js            # Chart templates
    └── data-tables/dynamic-tables.js              # Table templates
```

---

*Built to Conquer Risk® - Complete Presentation Editor with Potomac PowerPoint Skill Integration*