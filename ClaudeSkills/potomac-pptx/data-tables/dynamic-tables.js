/**
 * Potomac Dynamic Data Table System - Phase 3
 * Converts static Adobe Illustrator tables to dynamic PowerPoint tables
 * 
 * This system recreates the Passive-Active tables, AFG tables, and other 
 * marketing assets as native PowerPoint elements with data binding capability.
 */

const { POTOMAC_COLORS } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS } = require('../brand-assets/fonts/potomac-fonts.js');

class PotomacDynamicTables {
  constructor(pptxGenerator, options = {}) {
    this.pptx = pptxGenerator;
    this.options = options;
    
    // Table styling standards
    this.tableStyles = {
      header: {
        fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW },
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 14,
        fontWeight: 'bold',
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center',
        valign: 'middle'
      },
      cell: {
        fill: { color: POTOMAC_COLORS.PRIMARY.WHITE },
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 12,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center',
        valign: 'middle'
      },
      alternateRow: {
        fill: { color: POTOMAC_COLORS.TONES.YELLOW_20 },
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 12,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center',
        valign: 'middle'
      },
      border: {
        pt: 1,
        color: POTOMAC_COLORS.TONES.GRAY_40
      }
    };
  }

  /**
   * Create Passive vs Active Performance Table
   * Recreates the "01. Passive-Active Table.ai" asset
   */
  createPassiveActiveTable(slide, data, position = { x: 1, y: 2, w: 8, h: 3 }) {
    console.log('📊 Creating Passive vs Active Performance Table...');
    
    // Default data structure if none provided
    const defaultData = {
      timeframes: ['1 Year', '3 Year', '5 Year', '10 Year'],
      passive: ['5.2%', '7.8%', '9.1%', '8.7%'],
      active: ['7.8%', '9.4%', '11.2%', '10.3%'],
      outperformance: ['+2.6%', '+1.6%', '+2.1%', '+1.6%']
    };
    
    const tableData = data || defaultData;
    
    // Create table structure
    const rows = [
      // Header row
      [
        { text: 'TIME PERIOD', options: this.tableStyles.header },
        { text: 'PASSIVE RETURN', options: this.tableStyles.header },
        { text: 'ACTIVE RETURN', options: this.tableStyles.header },
        { text: 'OUTPERFORMANCE', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE } } }
      ]
    ];
    
    // Data rows
    tableData.timeframes.forEach((timeframe, index) => {
      const isAlternate = index % 2 === 1;
      const rowStyle = isAlternate ? this.tableStyles.alternateRow : this.tableStyles.cell;
      
      rows.push([
        { text: timeframe, options: { ...rowStyle, align: 'left', fontWeight: 'bold' } },
        { text: tableData.passive[index], options: rowStyle },
        { text: tableData.active[index], options: { ...rowStyle, fontWeight: 'bold' } },
        { text: tableData.outperformance[index], options: { 
          ...rowStyle, 
          color: POTOMAC_COLORS.SECONDARY.TURQUOISE,
          fontWeight: 'bold'
        }}
      ]);
    });
    
    // Add table to slide
    slide.addTable(rows, {
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      border: this.tableStyles.border,
      columnWidth: [2, 2, 2, 2], // Equal columns
      margin: 0.1
    });
    
    // Add title above table
    slide.addText('PASSIVE VS ACTIVE PERFORMANCE', {
      x: position.x,
      y: position.y - 0.7,
      w: position.w,
      h: 0.5,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 18,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    // Add footnote
    slide.addText('Past performance does not guarantee future results. Data as of [Date].', {
      x: position.x,
      y: position.y + position.h + 0.1,
      w: position.w,
      h: 0.3,
      fontFace: POTOMAC_FONTS.BODY.family,
      fontSize: 10,
      color: POTOMAC_COLORS.TONES.GRAY_60,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create AFG (Asset Fee Grid) Table
   * Recreates the "02. Passive-Active AFG table.ai" asset
   */
  createAFGTable(slide, data, position = { x: 0.5, y: 1.5, w: 9, h: 4 }) {
    console.log('📊 Creating AFG Fee Structure Table...');
    
    // Default AFG data structure
    const defaultData = {
      assetRanges: ['$0 - $1M', '$1M - $5M', '$5M - $10M', '$10M - $25M', '$25M+'],
      managementFees: ['1.00%', '0.85%', '0.75%', '0.65%', '0.50%'],
      performanceFees: ['15%', '15%', '15%', '20%', '20%'],
      totalFees: ['1.15%', '1.00%', '0.90%', '0.85%', '0.70%']
    };
    
    const tableData = data || defaultData;
    
    // Create sophisticated table structure
    const rows = [
      // Header row with Potomac branding
      [
        { text: 'ASSET RANGE', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW } } },
        { text: 'MANAGEMENT FEE', options: this.tableStyles.header },
        { text: 'PERFORMANCE FEE', options: this.tableStyles.header },
        { text: 'EFFECTIVE TOTAL', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE } } }
      ]
    ];
    
    // Data rows with alternating colors and highlighting
    tableData.assetRanges.forEach((range, index) => {
      const isAlternate = index % 2 === 1;
      const baseStyle = isAlternate ? this.tableStyles.alternateRow : this.tableStyles.cell;
      
      rows.push([
        { text: range, options: { ...baseStyle, align: 'left', fontWeight: 'bold' } },
        { text: tableData.managementFees[index], options: baseStyle },
        { text: tableData.performanceFees[index], options: baseStyle },
        { text: tableData.totalFees[index], options: { 
          ...baseStyle, 
          color: POTOMAC_COLORS.SECONDARY.TURQUOISE,
          fontWeight: 'bold'
        }}
      ]);
    });
    
    // Add table with enhanced styling
    slide.addTable(rows, {
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      border: this.tableStyles.border,
      columnWidth: [3, 2, 2, 2], // Wider first column
      margin: 0.15
    });
    
    // Add descriptive title
    slide.addText('ASSET FEE GRID - INVESTMENT MANAGEMENT', {
      x: position.x,
      y: position.y - 0.8,
      w: position.w,
      h: 0.6,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 20,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create Annualized Return Table
   * Recreates the "03. Annualized Return.ai" asset
   */
  createAnnualizedReturnTable(slide, data, position = { x: 1, y: 1.8, w: 8, h: 3.5 }) {
    console.log('📊 Creating Annualized Return Performance Table...');
    
    // Default return data structure
    const defaultData = {
      strategies: ['Bull Bear Strategy', 'Guardian Strategy', 'Income Plus Strategy', 'Navigrowth Strategy'],
      ytd: ['8.2%', '6.7%', '4.9%', '12.3%'],
      oneYear: ['12.8%', '9.4%', '7.2%', '15.7%'],
      threeYear: ['11.2%', '8.9%', '6.8%', '13.4%'],
      fiveYear: ['9.8%', '7.6%', '5.9%', '11.9%'],
      inception: ['10.3%', '8.2%', '6.4%', '12.8%']
    };
    
    const tableData = data || defaultData;
    
    // Create performance table
    const rows = [
      // Header row
      [
        { text: 'STRATEGY', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW } } },
        { text: 'YTD', options: this.tableStyles.header },
        { text: '1-YEAR', options: this.tableStyles.header },
        { text: '3-YEAR', options: this.tableStyles.header },
        { text: '5-YEAR', options: this.tableStyles.header },
        { text: 'INCEPTION', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE } } }
      ]
    ];
    
    // Strategy performance rows
    tableData.strategies.forEach((strategy, index) => {
      const isAlternate = index % 2 === 1;
      const baseStyle = isAlternate ? this.tableStyles.alternateRow : this.tableStyles.cell;
      
      rows.push([
        { text: strategy, options: { ...baseStyle, align: 'left', fontWeight: 'bold', color: POTOMAC_COLORS.PRIMARY.DARK_GRAY } },
        { text: tableData.ytd[index], options: { ...baseStyle, fontWeight: 'bold' } },
        { text: tableData.oneYear[index], options: baseStyle },
        { text: tableData.threeYear[index], options: baseStyle },
        { text: tableData.fiveYear[index], options: baseStyle },
        { text: tableData.inception[index], options: { 
          ...baseStyle, 
          color: POTOMAC_COLORS.SECONDARY.TURQUOISE,
          fontWeight: 'bold'
        }}
      ]);
    });
    
    // Add table
    slide.addTable(rows, {
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      border: this.tableStyles.border,
      columnWidth: [2.5, 1.1, 1.1, 1.1, 1.1, 1.1],
      margin: 0.12
    });
    
    // Add title with accent
    slide.addText('ANNUALIZED RETURNS BY STRATEGY', {
      x: position.x,
      y: position.y - 0.8,
      w: position.w,
      h: 0.6,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 20,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    // Performance disclaimer
    slide.addText('Performance shown is net of fees. Past performance does not guarantee future results.', {
      x: position.x,
      y: position.y + position.h + 0.1,
      w: position.w,
      h: 0.4,
      fontFace: POTOMAC_FONTS.BODY.family,
      fontSize: 10,
      color: POTOMAC_COLORS.TONES.GRAY_60,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create Flexible Data Grid
   * General-purpose table creator for custom data
   */
  createDataGrid(slide, config) {
    const {
      title,
      headers,
      data,
      position = { x: 1, y: 2, w: 8, h: 3 },
      highlightColumn = null,
      showAlternatingRows = true
    } = config;
    
    console.log(`📊 Creating Data Grid: ${title}...`);
    
    // Create header row
    const rows = [
      headers.map((header, index) => ({
        text: header.toUpperCase(),
        options: {
          ...this.tableStyles.header,
          fill: { color: index === highlightColumn ? POTOMAC_COLORS.SECONDARY.TURQUOISE : POTOMAC_COLORS.PRIMARY.YELLOW }
        }
      }))
    ];
    
    // Create data rows
    data.forEach((rowData, rowIndex) => {
      const isAlternate = showAlternatingRows && rowIndex % 2 === 1;
      const baseStyle = isAlternate ? this.tableStyles.alternateRow : this.tableStyles.cell;
      
      const row = rowData.map((cellData, colIndex) => ({
        text: cellData.toString(),
        options: {
          ...baseStyle,
          align: colIndex === 0 ? 'left' : 'center', // First column left-aligned
          fontWeight: colIndex === highlightColumn ? 'bold' : baseStyle.fontWeight,
          color: colIndex === highlightColumn ? POTOMAC_COLORS.SECONDARY.TURQUOISE : baseStyle.color
        }
      }));
      
      rows.push(row);
    });
    
    // Add table
    slide.addTable(rows, {
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      border: this.tableStyles.border,
      margin: 0.1
    });
    
    // Add title if provided
    if (title) {
      slide.addText(title.toUpperCase(), {
        x: position.x,
        y: position.y - 0.7,
        w: position.w,
        h: 0.5,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 18,
        fontWeight: 'bold',
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center'
      });
    }
    
    return slide;
  }

  /**
   * Create Strategy Comparison Table
   * Multi-strategy performance comparison
   */
  createStrategyComparisonTable(slide, strategies, position = { x: 0.5, y: 1.5, w: 9, h: 4 }) {
    console.log('📊 Creating Strategy Comparison Table...');
    
    // Default strategy data
    const defaultStrategies = [
      {
        name: 'Bull Bear',
        description: 'Trend-following momentum strategy',
        risk: 'Medium',
        return: '12.8%',
        maxDrawdown: '8.5%',
        sharpeRatio: '1.14'
      },
      {
        name: 'Guardian',
        description: 'Defensive capital preservation',
        risk: 'Low',
        return: '8.9%',
        maxDrawdown: '4.2%',
        sharpeRatio: '1.28'
      },
      {
        name: 'Income Plus',
        description: 'Enhanced income generation',
        risk: 'Low-Medium',
        return: '6.8%',
        maxDrawdown: '3.8%',
        sharpeRatio: '1.05'
      },
      {
        name: 'Navigrowth',
        description: 'Growth-oriented equity strategy',
        risk: 'Medium-High',
        return: '15.2%',
        maxDrawdown: '12.3%',
        sharpeRatio: '1.09'
      }
    ];
    
    const strategyData = strategies || defaultStrategies;
    
    // Create header row
    const rows = [
      [
        { text: 'STRATEGY', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW } } },
        { text: 'DESCRIPTION', options: this.tableStyles.header },
        { text: 'RISK LEVEL', options: this.tableStyles.header },
        { text: 'ANNUAL RETURN', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE } } },
        { text: 'MAX DRAWDOWN', options: this.tableStyles.header },
        { text: 'SHARPE RATIO', options: this.tableStyles.header }
      ]
    ];
    
    // Create strategy rows
    strategyData.forEach((strategy, index) => {
      const isAlternate = index % 2 === 1;
      const baseStyle = isAlternate ? this.tableStyles.alternateRow : this.tableStyles.cell;
      
      rows.push([
        { text: strategy.name.toUpperCase(), options: { ...baseStyle, align: 'left', fontWeight: 'bold' } },
        { text: strategy.description, options: { ...baseStyle, align: 'left', fontSize: 11 } },
        { text: strategy.risk, options: baseStyle },
        { text: strategy.return, options: { 
          ...baseStyle, 
          color: POTOMAC_COLORS.SECONDARY.TURQUOISE,
          fontWeight: 'bold' 
        }},
        { text: strategy.maxDrawdown, options: baseStyle },
        { text: strategy.sharpeRatio, options: baseStyle }
      ]);
    });
    
    // Add table
    slide.addTable(rows, {
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      border: this.tableStyles.border,
      columnWidth: [1.3, 2.2, 1.2, 1.3, 1.3, 1.2],
      margin: 0.08
    });
    
    // Add title
    slide.addText('POTOMAC INVESTMENT STRATEGIES OVERVIEW', {
      x: position.x,
      y: position.y - 0.7,
      w: position.w,
      h: 0.5,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 18,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create Performance Attribution Table
   * Shows performance breakdown by factors
   */
  createAttributionTable(slide, data, position = { x: 1, y: 2, w: 8, h: 3.5 }) {
    console.log('📊 Creating Performance Attribution Table...');
    
    // Default attribution data
    const defaultData = {
      factors: ['Asset Allocation', 'Security Selection', 'Market Timing', 'Other Factors'],
      contributions: ['+2.4%', '+1.8%', '+0.7%', '+0.3%'],
      weights: ['45%', '35%', '15%', '5%']
    };
    
    const tableData = data || defaultData;
    
    // Create attribution table
    const rows = [
      // Header
      [
        { text: 'ATTRIBUTION FACTOR', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW } } },
        { text: 'CONTRIBUTION', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE } } },
        { text: 'WEIGHT', options: this.tableStyles.header }
      ]
    ];
    
    // Factor rows
    tableData.factors.forEach((factor, index) => {
      const isAlternate = index % 2 === 1;
      const baseStyle = isAlternate ? this.tableStyles.alternateRow : this.tableStyles.cell;
      
      rows.push([
        { text: factor, options: { ...baseStyle, align: 'left' } },
        { text: tableData.contributions[index], options: { 
          ...baseStyle, 
          color: POTOMAC_COLORS.SECONDARY.TURQUOISE,
          fontWeight: 'bold'
        }},
        { text: tableData.weights[index], options: baseStyle }
      ]);
    });
    
    // Add total row
    const totalContribution = tableData.contributions
      .map(c => parseFloat(c.replace('%', '').replace('+', '')))
      .reduce((sum, val) => sum + val, 0);
    
    rows.push([
      { text: 'TOTAL EXCESS RETURN', options: { 
        ...this.tableStyles.header, 
        fill: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY },
        color: POTOMAC_COLORS.PRIMARY.WHITE
      }},
      { text: `+${totalContribution.toFixed(1)}%`, options: { 
        ...this.tableStyles.header, 
        fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE },
        color: POTOMAC_COLORS.PRIMARY.WHITE
      }},
      { text: '100%', options: { 
        ...this.tableStyles.header, 
        fill: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY },
        color: POTOMAC_COLORS.PRIMARY.WHITE
      }}
    ]);
    
    slide.addTable(rows, {
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      border: this.tableStyles.border,
      columnWidth: [4, 2, 2],
      margin: 0.1
    });
    
    // Title
    slide.addText('PERFORMANCE ATTRIBUTION ANALYSIS', {
      x: position.x,
      y: position.y - 0.7,
      w: position.w,
      h: 0.5,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 18,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create Risk Metrics Table
   * Risk analysis and measurement display
   */
  createRiskMetricsTable(slide, data, position = { x: 1, y: 2, w: 8, h: 3 }) {
    console.log('📊 Creating Risk Metrics Table...');
    
    const defaultData = {
      metrics: ['Maximum Drawdown', 'Volatility', 'Beta', 'Correlation', 'VaR (95%)', 'Calmar Ratio'],
      portfolio: ['8.5%', '11.2%', '0.78', '0.85', '2.1%', '1.32'],
      benchmark: ['18.2%', '16.8%', '1.00', '1.00', '3.8%', '0.89'],
      relative: ['-9.7%', '-5.6%', '-0.22', '-0.15', '-1.7%', '+0.43']
    };
    
    const tableData = data || defaultData;
    
    const rows = [
      // Header
      [
        { text: 'RISK METRIC', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW } } },
        { text: 'PORTFOLIO', options: { ...this.tableStyles.header, fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE } } },
        { text: 'BENCHMARK', options: this.tableStyles.header },
        { text: 'RELATIVE', options: this.tableStyles.header }
      ]
    ];
    
    // Metrics rows
    tableData.metrics.forEach((metric, index) => {
      const isAlternate = index % 2 === 1;
      const baseStyle = isAlternate ? this.tableStyles.alternateRow : this.tableStyles.cell;
      
      rows.push([
        { text: metric, options: { ...baseStyle, align: 'left' } },
        { text: tableData.portfolio[index], options: { 
          ...baseStyle, 
          color: POTOMAC_COLORS.SECONDARY.TURQUOISE,
          fontWeight: 'bold'
        }},
        { text: tableData.benchmark[index], options: baseStyle },
        { text: tableData.relative[index], options: { 
          ...baseStyle,
          color: tableData.relative[index].startsWith('+') ? POTOMAC_COLORS.SECONDARY.TURQUOISE : POTOMAC_COLORS.SECONDARY.PINK,
          fontWeight: 'bold'
        }}
      ]);
    });
    
    slide.addTable(rows, {
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      border: this.tableStyles.border,
      columnWidth: [3, 1.5, 1.5, 2],
      margin: 0.1
    });
    
    slide.addText('RISK ANALYSIS - RELATIVE TO BENCHMARK', {
      x: position.x,
      y: position.y - 0.7,
      w: position.w,
      h: 0.5,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 18,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }
}

// Export table creation system
module.exports = {
  PotomacDynamicTables
};