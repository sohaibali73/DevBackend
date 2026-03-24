#!/usr/bin/env node

/**
 * Potomac Enhanced Presentation Generator - Complete Backend Integration
 * Handles all element types: images, charts, tables, text, and shapes
 * 
 * Usage: node generate-enhanced-presentation.js --input <file> --output <file> --type enhanced --compliance strict
 */

const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');
const { PotomacVisualElements } = require('../infographics/visual-elements.js');
const { PotomacDynamicTables } = require('../data-tables/dynamic-tables.js');

// Parse command line arguments
const args = process.argv.slice(2);
let inputFile = '';
let outputFile = '';
let complianceMode = 'strict';

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--input') inputFile = args[i + 1];
  if (args[i] === '--output') outputFile = args[i + 1];
  if (args[i] === '--compliance') complianceMode = args[i + 1];
}

if (!inputFile || !outputFile) {
  console.error('Usage: node generate-enhanced-presentation.js --input <file> --output <file> --type enhanced --compliance strict');
  process.exit(1);
}

// Read input data
const inputData = JSON.parse(fs.readFileSync(inputFile, 'utf8'));

// Create presentation
const pptx = new PptxGenJS();

// Set Potomac theme
pptx.defineLayout({ name: 'POTOMAC', width: 10, height: 5.625 });
pptx.layout = 'POTOMAC';

// Potomac brand colors
const COLORS = {
  YELLOW: 'FEC00F',
  DARK_GRAY: '212121',
  TURQUOISE: '00DED1',
  WHITE: 'FFFFFF',
};

// Initialize Potomac visual systems
const visualElements = new PotomacVisualElements(pptx);
const dynamicTables = new PotomacDynamicTables(pptx);

// Add slides
inputData.slides.forEach((slideData, index) => {
  const slide = pptx.addSlide();

  // Set background
  slide.background = { color: slideData.background || COLORS.WHITE };

  // Process each content element
  slideData.content.forEach((element) => {
    switch (element.type) {
      case 'text':
        // Add text element
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

      case 'shape':
        // Add shape element
        slide.addShape('rect', {
          x: element.x / 100,
          y: element.y / 100,
          w: element.width / 100,
          h: element.height / 100,
          fill: { color: element.style.backgroundColor?.replace('#', '') || COLORS.YELLOW },
        });
        break;

      case 'image':
        // Add image element
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
          case 'communication':
            visualElements.createCommunicationFlow(slide, chartConfig);
            break;
          case 'firm_structure':
            visualElements.createFirmStructureInfographic(slide, chartConfig);
            break;
          case 'ocio_triangle':
            visualElements.createOCIOTriangle(slide, chartConfig);
            break;
          default:
            console.warn(`Unknown chart type: ${chartType}`);
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
          case 'annualized_return':
            dynamicTables.createAnnualizedReturnTable(slide, tableData, tablePosition);
            break;
          case 'strategy_overview':
            dynamicTables.createStrategyOverviewTable(slide, tableData, tablePosition);
            break;
          case 'attribution':
            dynamicTables.createAttributionTable(slide, tableData, tablePosition);
            break;
          case 'risk_metrics':
            dynamicTables.createRiskMetricsTable(slide, tableData, tablePosition);
            break;
          default:
            console.warn(`Unknown table type: ${tableType}`);
        }
        break;

      default:
        console.warn(`Unknown element type: ${element.type}`);
    }
  });

  // Add notes
  if (slideData.notes) {
    slide.addNotes(slideData.notes);
  }
});

// Helper function to convert table data
function convertTableData(tableType, content) {
  // Each table type expects different data formats
  // Convert from frontend format (headers + rows) to backend expected format
  
  switch (tableType) {
    case 'passive_active':
      return {
        timeframes: content.rows.map(row => row[0]),
        passive: content.rows.map(row => row[1]),
        active: content.rows.map(row => row[2]),
        outperformance: content.rows.map(row => row[3]),
      };

    case 'afg':
      return {
        assetRanges: content.rows.map(row => row[0]),
        managementFees: content.rows.map(row => row[1]),
        performanceFees: content.rows.map(row => row[2]),
        totalFees: content.rows.map(row => row[3]),
      };

    case 'annualized_return':
      return {
        strategies: content.rows.map(row => row[0]),
        ytd: content.rows.map(row => row[1]),
        oneYear: content.rows.map(row => row[2]),
        threeYear: content.rows.map(row => row[3]),
        fiveYear: content.rows.map(row => row[4]),
        inception: content.rows.map(row => row[5]),
      };

    case 'attribution':
      return {
        factors: content.rows.map(row => row[0]),
        contributions: content.rows.map(row => row[1]),
        weights: content.rows.map(row => row[2]),
      };

    case 'risk_metrics':
      return {
        metrics: content.rows.map(row => row[0]),
        portfolio: content.rows.map(row => row[1]),
        benchmark: content.rows.map(row => row[2]),
        relative: content.rows.map(row => row[3]),
      };

    default:
      // Generic table format
      return {
        headers: content.headers,
        rows: content.rows,
      };
  }
}

// Save presentation
pptx.writeFile({ fileName: outputFile })
  .then(() => {
    console.log(`Presentation generated: ${outputFile}`);
    process.exit(0);
  })
  .catch((err) => {
    console.error('Error generating presentation:', err);
    process.exit(1);
  });
