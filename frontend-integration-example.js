/**
 * Frontend Integration Example - Complete Presentation Editor
 * 
 * This file demonstrates how to integrate the complete presentation editor
 * with images, charts, and tables into your frontend application.
 */

/**
 * Complete Presentation Editor Component
 * 
 * This component provides a full-featured presentation editor with:
 * - Text editing
 * - Image upload and embedding
 * - Potomac chart templates
 * - Potomac table templates
 * - Shape creation
 * - Export to PPTX
 */

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

  init() {
    this.render();
    this.bindEvents();
  }

  render() {
    this.container.innerHTML = `
      <div class="presentation-editor">
        <div class="editor-header">
          <input type="text" id="presentation-title" value="${this.presentation.title}" placeholder="Presentation Title">
          <div class="editor-toolbar">
            <button onclick="editor.addSlide()">Add Slide</button>
            <button onclick="editor.addElement('text')">Add Text</button>
            <button onclick="editor.addElement('image')">Add Image</button>
            <button onclick="editor.addElement('chart')">Add Chart</button>
            <button onclick="editor.addElement('table')">Add Table</button>
            <button onclick="editor.addElement('shape')">Add Shape</button>
            <button onclick="editor.exportPresentation()">Export PPTX</button>
          </div>
        </div>
        <div class="editor-content">
          <div class="slide-list">
            ${this.presentation.slides.map((slide, index) => `
              <div class="slide-thumbnail ${index === this.currentSlideIndex ? 'active' : ''}" onclick="editor.selectSlide(${index})">
                <div class="slide-title">${slide.title || 'Untitled Slide'}</div>
                <div class="slide-elements">${slide.content.length} elements</div>
              </div>
            `).join('')}
          </div>
          <div class="slide-editor" id="slide-editor">
            ${this.renderSlideEditor()}
          </div>
        </div>
      </div>
    `;
  }

  renderSlideEditor() {
    const slide = this.presentation.slides[this.currentSlideIndex];
    if (!slide) return '<div class="empty-slide">Select a slide or add a new one</div>';

    return `
      <div class="slide-preview" style="background: ${slide.background || '#FFFFFF'}">
        <div class="slide-title-bar">
          <input type="text" value="${slide.title || ''}" placeholder="Slide Title" oninput="editor.updateSlideTitle(event.target.value)">
          <input type="text" value="${slide.subtitle || ''}" placeholder="Slide Subtitle" oninput="editor.updateSlideSubtitle(event.target.value)">
        </div>
        <div class="slide-content-area">
          ${slide.content.map((element, index) => this.renderElement(element, index)).join('')}
        </div>
        <div class="slide-notes">
          <textarea placeholder="Slide notes..." oninput="editor.updateSlideNotes(event.target.value)">${slide.notes || ''}</textarea>
        </div>
      </div>
    `;
  }

  renderElement(element, index) {
    switch (element.type) {
      case 'text':
        return `
          <div class="element text-element" style="left: ${element.x}px; top: ${element.y}px; width: ${element.width}px; height: ${element.height}px;">
            <textarea style="font-size: ${element.style.fontSize}px; font-family: ${element.style.fontFamily}; color: ${element.style.color}; text-align: ${element.style.textAlign};" oninput="editor.updateTextContent(${index}, event.target.value)">${element.content}</textarea>
            <div class="element-controls">
              <button onclick="editor.editElementStyle(${index})">Style</button>
              <button onclick="editor.removeElement(${index})">Delete</button>
            </div>
          </div>
        `;
      
      case 'image':
        return `
          <div class="element image-element" style="left: ${element.x}px; top: ${element.y}px; width: ${element.width}px; height: ${element.height}px;">
            <img src="${element.content.src}" alt="${element.content.alt}">
            <div class="element-controls">
              <button onclick="editor.replaceImage(${index})">Replace</button>
              <button onclick="editor.removeElement(${index})">Delete</button>
            </div>
          </div>
        `;
      
      case 'chart':
        return `
          <div class="element chart-element" style="left: ${element.x}px; top: ${element.y}px; width: ${element.width}px; height: ${element.height}px;">
            <div class="chart-preview">
              <h4>${this.getChartTypeName(element.content.type)}</h4>
              <p>Chart Type: ${element.content.type}</p>
            </div>
            <div class="element-controls">
              <button onclick="editor.editChart(${index})">Configure</button>
              <button onclick="editor.removeElement(${index})">Delete</button>
            </div>
          </div>
        `;
      
      case 'table':
        return `
          <div class="element table-element" style="left: ${element.x}px; top: ${element.y}px; width: ${element.width}px; height: ${element.height}px;">
            <div class="table-preview">
              <h4>${this.getTableTypeName(element.content.type)}</h4>
              <p>Table Type: ${element.content.type}</p>
              <p>Rows: ${element.content.rows.length}</p>
            </div>
            <div class="element-controls">
              <button onclick="editor.editTable(${index})">Configure</button>
              <button onclick="editor.removeElement(${index})">Delete</button>
            </div>
          </div>
        `;
      
      case 'shape':
        return `
          <div class="element shape-element" style="left: ${element.x}px; top: ${element.y}px; width: ${element.width}px; height: ${element.height}px; background-color: ${element.style.backgroundColor};">
            <div class="element-controls">
              <button onclick="editor.editShape(${index})">Style</button>
              <button onclick="editor.removeElement(${index})">Delete</button>
            </div>
          </div>
        `;
      
      default:
        return '';
    }
  }

  getChartTypeName(type) {
    const names = {
      'process_flow': 'Investment Process Flow',
      'performance': 'Strategy Performance Viz',
      'communication': 'Communication Flow',
      'firm_structure': 'Firm Structure Infographic',
      'ocio_triangle': 'OCIO Triangle'
    };
    return names[type] || type;
  }

  getTableTypeName(type) {
    const names = {
      'passive_active': 'Passive vs Active Performance',
      'afg': 'Asset Fee Grid',
      'annualized_return': 'Annualized Returns',
      'strategy_overview': 'Strategy Overview',
      'attribution': 'Performance Attribution',
      'risk_metrics': 'Risk Metrics'
    };
    return names[type] || type;
  }

  bindEvents() {
    // Title input event
    document.getElementById('presentation-title').addEventListener('input', (e) => {
      this.presentation.title = e.target.value;
    });
  }

  addSlide() {
    this.presentation.slides.push({
      title: 'New Slide',
      content: [],
      layout: 'blank',
      notes: '',
      background: '#FFFFFF'
    });
    this.currentSlideIndex = this.presentation.slides.length - 1;
    this.render();
  }

  selectSlide(index) {
    this.currentSlideIndex = index;
    this.render();
  }

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
      
      case 'shape':
        return {
          ...baseElement,
          type: 'shape',
          style: {
            backgroundColor: '#FEC00F'
          }
        };
      
      default:
        return baseElement;
    }
  }

  updateSlideTitle(title) {
    this.presentation.slides[this.currentSlideIndex].title = title;
  }

  updateSlideSubtitle(subtitle) {
    this.presentation.slides[this.currentSlideIndex].subtitle = subtitle;
  }

  updateSlideNotes(notes) {
    this.presentation.slides[this.currentSlideIndex].notes = notes;
  }

  updateTextContent(index, content) {
    this.presentation.slides[this.currentSlideIndex].content[index].content = content;
  }

  removeElement(index) {
    this.presentation.slides[this.currentSlideIndex].content.splice(index, 1);
    this.render();
  }

  async replaceImage(index) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (file) {
        const base64 = await this.fileToBase64(file);
        this.presentation.slides[this.currentSlideIndex].content[index].content.src = base64;
        this.render();
      }
    };
    input.click();
  }

  async fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  editElementStyle(index) {
    // Implementation for editing element styles
    console.log('Edit element style:', index);
  }

  editChart(index) {
    // Implementation for editing chart configuration
    console.log('Edit chart:', index);
  }

  editTable(index) {
    // Implementation for editing table data
    console.log('Edit table:', index);
  }

  editShape(index) {
    // Implementation for editing shape styles
    console.log('Edit shape:', index);
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

// Initialize the editor
const editor = new PresentationEditor('editor-container');

/**
 * Chart Configuration Examples
 */
const chartExamples = {
  process_flow: {
    type: 'process_flow',
    data: {},
    config: {
      skillFunction: 'createInvestmentProcessFlow'
    }
  },
  
  performance: {
    type: 'performance',
    data: {
      bullMarket: { return: '+18.5%', period: '2021-2022' },
      bearMarket: { return: '+3.2%', period: '2022-2023' },
      benchmark: { bull: '+12.8%', bear: '-15.6%' }
    },
    config: {
      skillFunction: 'createStrategyPerformanceViz'
    }
  },
  
  communication: {
    type: 'communication',
    data: {},
    config: {
      skillFunction: 'createCommunicationFlow'
    }
  },
  
  firm_structure: {
    type: 'firm_structure',
    data: {},
    config: {
      skillFunction: 'createFirmStructureInfographic'
    }
  },
  
  ocio_triangle: {
    type: 'ocio_triangle',
    data: {},
    config: {
      skillFunction: 'createOCIOTriangle'
    }
  }
};

/**
 * Table Configuration Examples
 */
const tableExamples = {
  passive_active: {
    type: 'passive_active',
    headers: ['TIME PERIOD', 'PASSIVE', 'ACTIVE', 'OUTPERFORMANCE'],
    rows: [
      ['1 Year', '5.2%', '7.8%', '+2.6%'],
      ['3 Year', '7.8%', '9.4%', '+1.6%'],
      ['5 Year', '9.1%', '11.2%', '+2.1%'],
      ['10 Year', '8.7%', '10.3%', '+1.6%']
    ],
    config: {
      skillFunction: 'createPassiveActiveTable'
    }
  },
  
  afg: {
    type: 'afg',
    headers: ['ASSET RANGE', 'MANAGEMENT FEE', 'PERFORMANCE FEE', 'EFFECTIVE TOTAL'],
    rows: [
      ['$0 - $1M', '1.00%', '15%', '1.15%'],
      ['$1M - $5M', '0.85%', '15%', '1.00%'],
      ['$5M - $10M', '0.75%', '15%', '0.90%'],
      ['$10M - $25M', '0.65%', '20%', '0.85%'],
      ['$25M+', '0.50%', '20%', '0.70%']
    ],
    config: {
      skillFunction: 'createAFGTable'
    }
  },
  
  annualized_return: {
    type: 'annualized_return',
    headers: ['STRATEGY', 'YTD', '1-YEAR', '3-YEAR', '5-YEAR', 'INCEPTION'],
    rows: [
      ['Bull Bear Strategy', '8.2%', '12.8%', '11.2%', '9.8%', '10.3%'],
      ['Guardian Strategy', '6.7%', '9.4%', '8.9%', '7.6%', '8.2%'],
      ['Income Plus Strategy', '4.9%', '7.2%', '6.8%', '5.9%', '6.4%'],
      ['Navigrowth Strategy', '12.3%', '15.7%', '13.4%', '11.9%', '12.8%']
    ],
    config: {
      skillFunction: 'createAnnualizedReturnTable'
    }
  },
  
  attribution: {
    type: 'attribution',
    headers: ['ATTRIBUTION FACTOR', 'CONTRIBUTION', 'WEIGHT'],
    rows: [
      ['Asset Allocation', '+2.4%', '45%'],
      ['Security Selection', '+1.8%', '35%'],
      ['Market Timing', '+0.7%', '15%'],
      ['Other Factors', '+0.3%', '5%']
    ],
    config: {
      skillFunction: 'createAttributionTable'
    }
  },
  
  risk_metrics: {
    type: 'risk_metrics',
    headers: ['RISK METRIC', 'PORTFOLIO', 'BENCHMARK', 'RELATIVE'],
    rows: [
      ['Maximum Drawdown', '8.5%', '18.2%', '-9.7%'],
      ['Volatility', '11.2%', '16.8%', '-5.6%'],
      ['Beta', '0.78', '1.00', '-0.22'],
      ['Correlation', '0.85', '1.00', '-0.15'],
      ['VaR (95%)', '2.1%', '3.8%', '-1.7%'],
      ['Calmar Ratio', '1.32', '0.89', '+0.43']
    ],
    config: {
      skillFunction: 'createRiskMetricsTable'
    }
  }
};

/**
 * CSS Styles for the Editor
 */
const editorStyles = `
.presentation-editor {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}

.editor-header {
  padding: 1rem;
  background: white;
  border-bottom: 1px solid #ddd;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.editor-toolbar button {
  margin-left: 0.5rem;
  padding: 0.5rem 1rem;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.editor-toolbar button:hover {
  background: #0056b3;
}

.editor-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.slide-list {
  width: 200px;
  background: white;
  border-right: 1px solid #ddd;
  padding: 1rem;
  overflow-y: auto;
}

.slide-thumbnail {
  padding: 1rem;
  margin-bottom: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  background: #fff;
}

.slide-thumbnail.active {
  border-color: #007bff;
  background: #e3f2fd;
}

.slide-editor {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
  display: flex;
  justify-content: center;
}

.slide-preview {
  width: 900px;
  height: 506px;
  background: white;
  border: 1px solid #ddd;
  position: relative;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.slide-title-bar {
  padding: 1rem;
  border-bottom: 1px solid #eee;
}

.slide-title-bar input {
  width: 100%;
  font-size: 24px;
  font-weight: bold;
  border: none;
  outline: none;
}

.slide-content-area {
  padding: 2rem;
  position: relative;
  height: 350px;
}

.element {
  position: absolute;
  border: 1px dashed #ccc;
  padding: 0.5rem;
  background: rgba(255, 255, 255, 0.8);
}

.element:hover {
  border-color: #007bff;
  background: rgba(0, 123, 255, 0.1);
}

.element-controls {
  position: absolute;
  top: -25px;
  right: 0;
}

.element-controls button {
  margin-left: 0.25rem;
  padding: 0.25rem 0.5rem;
  font-size: 10px;
  border: 1px solid #ccc;
  background: white;
  cursor: pointer;
}

.slide-notes {
  padding: 1rem;
  border-top: 1px solid #eee;
}

.slide-notes textarea {
  width: 100%;
  height: 100px;
  border: 1px solid #ddd;
  padding: 0.5rem;
  resize: vertical;
}

.chart-preview, .table-preview {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
}

.text-element textarea {
  width: 100%;
  height: 100%;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
}

.image-element img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.shape-element {
  border: 1px solid #ccc;
}
`;

// Add styles to document
const styleSheet = document.createElement("style");
styleSheet.type = "text/css";
styleSheet.innerText = editorStyles;
document.head.appendChild(styleSheet);