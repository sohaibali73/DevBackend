/**
 * Potomac Dynamic Data Table System — Phase 3 (Fixed)
 *
 * FIXES applied:
 *  - fontWeight: 'bold' → bold: true  (correct pptxgenjs option)
 *  - _c() helper strips '#' from brand color hex strings
 *  - Color references in fill.color and border.color now use _c()
 */

'use strict';

const { POTOMAC_COLORS } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS }  = require('../brand-assets/fonts/potomac-fonts.js');

// Strip leading '#' from brand colors (pptxgenjs does not want the '#' prefix)
function _c(hex) { return hex ? String(hex).replace('#', '') : 'FEC00F'; }

const C = POTOMAC_COLORS;
const F = POTOMAC_FONTS;


class PotomacDynamicTables {
  constructor(pptxGenerator, options = {}) {
    this.pptx    = pptxGenerator;
    this.options = options;

    this.tableStyles = {
      header: {
        fill:     { color: _c(C.PRIMARY.YELLOW) },
        fontFace: F.HEADERS.family,
        fontSize: 14,
        bold:     true,
        color:    _c(C.PRIMARY.DARK_GRAY),
        align:    'center',
        valign:   'middle',
      },
      cell: {
        fill:     { color: _c(C.PRIMARY.WHITE) },
        fontFace: F.BODY.family,
        fontSize: 12,
        color:    _c(C.PRIMARY.DARK_GRAY),
        align:    'center',
        valign:   'middle',
      },
      alternateRow: {
        fill:     { color: _c(C.TONES.YELLOW_20) },
        fontFace: F.BODY.family,
        fontSize: 12,
        color:    _c(C.PRIMARY.DARK_GRAY),
        align:    'center',
        valign:   'middle',
      },
      border: {
        pt:    1,
        color: _c(C.TONES.GRAY_40),
      },
    };
  }


  /**
   * Passive vs Active Performance Table
   */
  createPassiveActiveTable(slide, data, position = { x: 1, y: 2, w: 8, h: 3 }) {
    console.log('📊 Creating Passive vs Active Performance Table...');

    const defaultData = {
      timeframes:      ['1 Year', '3 Year', '5 Year', '10 Year'],
      passive:         ['5.2%', '7.8%', '9.1%', '8.7%'],
      active:          ['7.8%', '9.4%', '11.2%', '10.3%'],
      outperformance:  ['+2.6%', '+1.6%', '+2.1%', '+1.6%'],
    };

    const td = data || defaultData;

    const rows = [
      [
        { text: 'TIME PERIOD',     options: this.tableStyles.header },
        { text: 'PASSIVE RETURN',  options: this.tableStyles.header },
        { text: 'ACTIVE RETURN',   options: this.tableStyles.header },
        { text: 'OUTPERFORMANCE',  options: { ...this.tableStyles.header, fill: { color: _c(C.SECONDARY.TURQUOISE) } } },
      ],
      ...td.timeframes.map((tf, i) => {
        const base = i % 2 === 1 ? this.tableStyles.alternateRow : this.tableStyles.cell;
        return [
          { text: tf,                        options: { ...base, align: 'left', bold: true } },
          { text: td.passive[i],             options: base },
          { text: td.active[i],              options: { ...base, bold: true } },
          { text: td.outperformance[i],      options: { ...base, color: _c(C.SECONDARY.TURQUOISE), bold: true } },
        ];
      }),
    ];

    slide.addTable(rows, {
      x: position.x, y: position.y, w: position.w, h: position.h,
      border: this.tableStyles.border,
      colW: [2, 2, 2, 2],
      margin: 0.1,
    });

    slide.addText('PASSIVE VS ACTIVE PERFORMANCE', {
      x: position.x, y: position.y - 0.7, w: position.w, h: 0.5,
      fontFace: F.HEADERS.family, fontSize: 18,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    slide.addText('Past performance does not guarantee future results. Data as of [Date].', {
      x: position.x, y: position.y + position.h + 0.1, w: position.w, h: 0.3,
      fontFace: F.BODY.family, fontSize: 10,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }


  /**
   * AFG (Asset Fee Grid) Table
   */
  createAFGTable(slide, data, position = { x: 0.5, y: 1.5, w: 9, h: 4 }) {
    console.log('📊 Creating AFG Fee Structure Table...');

    const defaultData = {
      assetRanges:     ['$0 - $1M', '$1M - $5M', '$5M - $10M', '$10M - $25M', '$25M+'],
      managementFees:  ['1.00%', '0.85%', '0.75%', '0.65%', '0.50%'],
      performanceFees: ['15%', '15%', '15%', '20%', '20%'],
      totalFees:       ['1.15%', '1.00%', '0.90%', '0.85%', '0.70%'],
    };

    const td = data || defaultData;

    const rows = [
      [
        { text: 'ASSET RANGE',      options: { ...this.tableStyles.header, fill: { color: _c(C.PRIMARY.YELLOW) } } },
        { text: 'MANAGEMENT FEE',   options: this.tableStyles.header },
        { text: 'PERFORMANCE FEE',  options: this.tableStyles.header },
        { text: 'EFFECTIVE TOTAL',  options: { ...this.tableStyles.header, fill: { color: _c(C.SECONDARY.TURQUOISE) } } },
      ],
      ...td.assetRanges.map((range, i) => {
        const base = i % 2 === 1 ? this.tableStyles.alternateRow : this.tableStyles.cell;
        return [
          { text: range,              options: { ...base, align: 'left', bold: true } },
          { text: td.managementFees[i],  options: base },
          { text: td.performanceFees[i], options: base },
          { text: td.totalFees[i],    options: { ...base, color: _c(C.SECONDARY.TURQUOISE), bold: true } },
        ];
      }),
    ];

    slide.addTable(rows, {
      x: position.x, y: position.y, w: position.w, h: position.h,
      border: this.tableStyles.border,
      colW: [3, 2, 2, 2],
      margin: 0.15,
    });

    slide.addText('ASSET FEE GRID - INVESTMENT MANAGEMENT', {
      x: position.x, y: position.y - 0.8, w: position.w, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 20,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }


  /**
   * Annualized Return Table
   */
  createAnnualizedReturnTable(slide, data, position = { x: 1, y: 1.8, w: 8, h: 3.5 }) {
    console.log('📊 Creating Annualized Return Performance Table...');

    const defaultData = {
      strategies: ['Bull Bear Strategy', 'Guardian Strategy', 'Income Plus Strategy', 'Navigrowth Strategy'],
      ytd:        ['8.2%', '6.7%', '4.9%', '12.3%'],
      oneYear:    ['12.8%', '9.4%', '7.2%', '15.7%'],
      threeYear:  ['11.2%', '8.9%', '6.8%', '13.4%'],
      fiveYear:   ['9.8%', '7.6%', '5.9%', '11.9%'],
      inception:  ['10.3%', '8.2%', '6.4%', '12.8%'],
    };

    const td = data || defaultData;

    const rows = [
      [
        { text: 'STRATEGY',  options: { ...this.tableStyles.header, fill: { color: _c(C.PRIMARY.YELLOW) } } },
        { text: 'YTD',       options: this.tableStyles.header },
        { text: '1-YEAR',    options: this.tableStyles.header },
        { text: '3-YEAR',    options: this.tableStyles.header },
        { text: '5-YEAR',    options: this.tableStyles.header },
        { text: 'INCEPTION', options: { ...this.tableStyles.header, fill: { color: _c(C.SECONDARY.TURQUOISE) } } },
      ],
      ...td.strategies.map((strat, i) => {
        const base = i % 2 === 1 ? this.tableStyles.alternateRow : this.tableStyles.cell;
        return [
          { text: strat,           options: { ...base, align: 'left', bold: true, color: _c(C.PRIMARY.DARK_GRAY) } },
          { text: td.ytd[i],       options: { ...base, bold: true } },
          { text: td.oneYear[i],   options: base },
          { text: td.threeYear[i], options: base },
          { text: td.fiveYear[i],  options: base },
          { text: td.inception[i], options: { ...base, color: _c(C.SECONDARY.TURQUOISE), bold: true } },
        ];
      }),
    ];

    slide.addTable(rows, {
      x: position.x, y: position.y, w: position.w, h: position.h,
      border: this.tableStyles.border,
      colW: [2.5, 1.1, 1.1, 1.1, 1.1, 1.1],
      margin: 0.12,
    });

    slide.addText('ANNUALIZED RETURNS BY STRATEGY', {
      x: position.x, y: position.y - 0.8, w: position.w, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 20,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    slide.addText('Performance shown is net of fees. Past performance does not guarantee future results.', {
      x: position.x, y: position.y + position.h + 0.1, w: position.w, h: 0.4,
      fontFace: F.BODY.family, fontSize: 10,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }


  /**
   * Strategy Comparison Table
   */
  createStrategyComparisonTable(slide, strategies, position = { x: 0.5, y: 1.5, w: 9, h: 4 }) {
    console.log('📊 Creating Strategy Comparison Table...');

    const defaultStrategies = [
      { name: 'Bull Bear',    description: 'Trend-following momentum strategy',    risk: 'Medium',      return: '12.8%', maxDrawdown: '8.5%',  sharpeRatio: '1.14' },
      { name: 'Guardian',     description: 'Defensive capital preservation',       risk: 'Low',         return: '8.9%',  maxDrawdown: '4.2%',  sharpeRatio: '1.28' },
      { name: 'Income Plus',  description: 'Enhanced income generation',           risk: 'Low-Medium',  return: '6.8%',  maxDrawdown: '3.8%',  sharpeRatio: '1.05' },
      { name: 'Navigrowth',   description: 'Growth-oriented equity strategy',      risk: 'Medium-High', return: '15.2%', maxDrawdown: '12.3%', sharpeRatio: '1.09' },
    ];

    const sd = strategies || defaultStrategies;

    const rows = [
      [
        { text: 'STRATEGY',      options: { ...this.tableStyles.header, fill: { color: _c(C.PRIMARY.YELLOW) } } },
        { text: 'DESCRIPTION',   options: this.tableStyles.header },
        { text: 'RISK LEVEL',    options: this.tableStyles.header },
        { text: 'ANNUAL RETURN', options: { ...this.tableStyles.header, fill: { color: _c(C.SECONDARY.TURQUOISE) } } },
        { text: 'MAX DRAWDOWN',  options: this.tableStyles.header },
        { text: 'SHARPE RATIO',  options: this.tableStyles.header },
      ],
      ...sd.map((s, i) => {
        const base = i % 2 === 1 ? this.tableStyles.alternateRow : this.tableStyles.cell;
        return [
          { text: s.name.toUpperCase(),   options: { ...base, align: 'left', bold: true } },
          { text: s.description,          options: { ...base, align: 'left', fontSize: 11 } },
          { text: s.risk,                 options: base },
          { text: s.return,               options: { ...base, color: _c(C.SECONDARY.TURQUOISE), bold: true } },
          { text: s.maxDrawdown,          options: base },
          { text: s.sharpeRatio,          options: base },
        ];
      }),
    ];

    slide.addTable(rows, {
      x: position.x, y: position.y, w: position.w, h: position.h,
      border: this.tableStyles.border,
      colW: [1.3, 2.2, 1.2, 1.3, 1.3, 1.2],
      margin: 0.08,
    });

    slide.addText('POTOMAC INVESTMENT STRATEGIES OVERVIEW', {
      x: position.x, y: position.y - 0.7, w: position.w, h: 0.5,
      fontFace: F.HEADERS.family, fontSize: 18,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }


  /**
   * Performance Attribution Table
   */
  createAttributionTable(slide, data, position = { x: 1, y: 2, w: 8, h: 3.5 }) {
    console.log('📊 Creating Performance Attribution Table...');

    const defaultData = {
      factors:       ['Asset Allocation', 'Security Selection', 'Market Timing', 'Other Factors'],
      contributions: ['+2.4%', '+1.8%', '+0.7%', '+0.3%'],
      weights:       ['45%', '35%', '15%', '5%'],
    };

    const td = data || defaultData;

    const rows = [
      [
        { text: 'ATTRIBUTION FACTOR', options: { ...this.tableStyles.header, fill: { color: _c(C.PRIMARY.YELLOW) } } },
        { text: 'CONTRIBUTION',       options: { ...this.tableStyles.header, fill: { color: _c(C.SECONDARY.TURQUOISE) } } },
        { text: 'WEIGHT',             options: this.tableStyles.header },
      ],
      ...td.factors.map((factor, i) => {
        const base = i % 2 === 1 ? this.tableStyles.alternateRow : this.tableStyles.cell;
        return [
          { text: factor,                 options: { ...base, align: 'left' } },
          { text: td.contributions[i],    options: { ...base, color: _c(C.SECONDARY.TURQUOISE), bold: true } },
          { text: td.weights[i],          options: base },
        ];
      }),
    ];

    // Total row
    const totalContrib = td.contributions
      .map(c => parseFloat(c.replace('%', '').replace('+', '')))
      .reduce((sum, v) => sum + v, 0);

    rows.push([
      { text: 'TOTAL EXCESS RETURN', options: { ...this.tableStyles.header, fill: { color: _c(C.PRIMARY.DARK_GRAY) }, color: _c(C.PRIMARY.WHITE) } },
      { text: `+${totalContrib.toFixed(1)}%`, options: { ...this.tableStyles.header, fill: { color: _c(C.SECONDARY.TURQUOISE) }, color: _c(C.PRIMARY.WHITE) } },
      { text: '100%',               options: { ...this.tableStyles.header, fill: { color: _c(C.PRIMARY.DARK_GRAY) }, color: _c(C.PRIMARY.WHITE) } },
    ]);

    slide.addTable(rows, {
      x: position.x, y: position.y, w: position.w, h: position.h,
      border: this.tableStyles.border,
      colW: [4, 2, 2],
      margin: 0.1,
    });

    slide.addText('PERFORMANCE ATTRIBUTION ANALYSIS', {
      x: position.x, y: position.y - 0.7, w: position.w, h: 0.5,
      fontFace: F.HEADERS.family, fontSize: 18,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }


  /**
   * Risk Metrics Table
   */
  createRiskMetricsTable(slide, data, position = { x: 1, y: 2, w: 8, h: 3 }) {
    console.log('📊 Creating Risk Metrics Table...');

    const defaultData = {
      metrics:   ['Maximum Drawdown', 'Volatility', 'Beta', 'Correlation', 'VaR (95%)', 'Calmar Ratio'],
      portfolio: ['8.5%', '11.2%', '0.78', '0.85', '2.1%', '1.32'],
      benchmark: ['18.2%', '16.8%', '1.00', '1.00', '3.8%', '0.89'],
      relative:  ['-9.7%', '-5.6%', '-0.22', '-0.15', '-1.7%', '+0.43'],
    };

    const td = data || defaultData;

    const rows = [
      [
        { text: 'RISK METRIC', options: { ...this.tableStyles.header, fill: { color: _c(C.PRIMARY.YELLOW) } } },
        { text: 'PORTFOLIO',   options: { ...this.tableStyles.header, fill: { color: _c(C.SECONDARY.TURQUOISE) } } },
        { text: 'BENCHMARK',   options: this.tableStyles.header },
        { text: 'RELATIVE',    options: this.tableStyles.header },
      ],
      ...td.metrics.map((metric, i) => {
        const base = i % 2 === 1 ? this.tableStyles.alternateRow : this.tableStyles.cell;
        const relColor = td.relative[i].startsWith('+')
          ? _c(C.SECONDARY.TURQUOISE)
          : _c(C.SECONDARY.PINK);
        return [
          { text: metric,          options: { ...base, align: 'left' } },
          { text: td.portfolio[i], options: { ...base, color: _c(C.SECONDARY.TURQUOISE), bold: true } },
          { text: td.benchmark[i], options: base },
          { text: td.relative[i],  options: { ...base, color: relColor, bold: true } },
        ];
      }),
    ];

    slide.addTable(rows, {
      x: position.x, y: position.y, w: position.w, h: position.h,
      border: this.tableStyles.border,
      colW: [3, 1.5, 1.5, 2],
      margin: 0.1,
    });

    slide.addText('RISK ANALYSIS - RELATIVE TO BENCHMARK', {
      x: position.x, y: position.y - 0.7, w: position.w, h: 0.5,
      fontFace: F.HEADERS.family, fontSize: 18,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }


  /**
   * Flexible Data Grid — generic table creator.
   */
  createDataGrid(slide, config) {
    const {
      title,
      headers,
      data,
      position = { x: 1, y: 2, w: 8, h: 3 },
      highlightColumn = null,
      showAlternatingRows = true,
    } = config;

    console.log(`📊 Creating Data Grid: ${title}...`);

    const hRow = headers.map((h, ci) => ({
      text: h.toUpperCase(),
      options: {
        ...this.tableStyles.header,
        fill: { color: ci === highlightColumn ? _c(C.SECONDARY.TURQUOISE) : _c(C.PRIMARY.YELLOW) },
      },
    }));

    const dataRows = data.map((row, ri) => {
      const isAlt = showAlternatingRows && ri % 2 === 1;
      const base  = isAlt ? this.tableStyles.alternateRow : this.tableStyles.cell;
      return row.map((cell, ci) => ({
        text: String(cell),
        options: {
          ...base,
          align: ci === 0 ? 'left' : 'center',
          bold:  ci === highlightColumn,
          color: ci === highlightColumn ? _c(C.SECONDARY.TURQUOISE) : base.color,
        },
      }));
    });

    slide.addTable([hRow, ...dataRows], {
      x: position.x, y: position.y, w: position.w, h: position.h,
      border: this.tableStyles.border,
      margin: 0.1,
    });

    if (title) {
      slide.addText(title.toUpperCase(), {
        x: position.x, y: position.y - 0.7, w: position.w, h: 0.5,
        fontFace: F.HEADERS.family, fontSize: 18,
        bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
      });
    }

    return slide;
  }
}

module.exports = { PotomacDynamicTables };
