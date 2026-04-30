#!/usr/bin/env node

/**
 * Phase 3 Asset Integration Test
 * Tests all converted Adobe Illustrator assets in PowerPoint format
 */

const { PotomacAssetIntegratedBuilder } = require('../asset-conversion/integrated-assets.js');

async function testPhase3Assets() {
  console.log('🧪 Phase 3 Asset Integration Test');
  console.log('Testing all converted Adobe Illustrator assets...');
  console.log('---');
  
  try {
    // Create builder with asset integration
    const builder = new PotomacAssetIntegratedBuilder({
      title: 'PHASE 3 ASSET SHOWCASE',
      subtitle: 'Adobe Illustrator Assets Converted to PowerPoint',
      palette: 'STANDARD'
    });
    
    // Title slide
    builder.addSlide({
      title: 'ASSET CONVERSION SHOWCASE',
      subtitle: 'Phase 3: Adobe Illustrator → Native PowerPoint',
      role: 'title',
      isFirst: true
    });
    
    // Test Passive-Active Table
    builder.addSlide({
      title: 'Performance Comparison Analysis',
      assetType: 'dataTable',
      assetKey: 'passive-active',
      data: {
        timeframes: ['1 Year', '3 Year', '5 Year', '10 Year'],
        passive: ['5.2%', '7.8%', '9.1%', '8.7%'],
        active: ['7.8%', '9.4%', '11.2%', '10.3%'],
        outperformance: ['+2.6%', '+1.6%', '+2.1%', '+1.6%']
      }
    });
    
    // Test AFG Table  
    builder.addSlide({
      title: 'Fee Structure Overview',
      assetType: 'dataTable',
      assetKey: 'afg-table',
      data: {
        assetRanges: ['$0 - $1M', '$1M - $5M', '$5M - $10M', '$10M - $25M', '$25M+'],
        managementFees: ['1.00%', '0.85%', '0.75%', '0.65%', '0.50%'],
        performanceFees: ['15%', '15%', '15%', '20%', '20%'],
        totalFees: ['1.15%', '1.00%', '0.90%', '0.85%', '0.70%']
      }
    });
    
    // Test Strategy Returns Table
    builder.addSlide({
      title: 'Strategy Performance Results',
      assetType: 'dataTable',
      assetKey: 'returns',
      data: {
        strategies: ['Bull Bear Strategy', 'Guardian Strategy', 'Income Plus Strategy', 'Navigrowth Strategy'],
        ytd: ['8.2%', '6.7%', '4.9%', '12.3%'],
        oneYear: ['12.8%', '9.4%', '7.2%', '15.7%'],
        threeYear: ['11.2%', '8.9%', '6.8%', '13.4%'],
        fiveYear: ['9.8%', '7.6%', '5.9%', '11.9%'],
        inception: ['10.3%', '8.2%', '6.4%', '12.8%']
      }
    });
    
    // Test Firm Structure Infographic
    builder.addSlide({
      title: 'Our Organization',
      assetType: 'infographic',
      assetKey: 'firm-structure',
      config: {
        startX: 0.5,
        startY: 1.5,
        width: 9,
        height: 4.5
      }
    });
    
    // Test Investment Process Flow
    builder.addSlide({
      title: 'Our Systematic Approach',
      assetType: 'infographic',
      assetKey: 'process-flow',
      config: {
        startX: 0.8,
        startY: 2.2,
        width: 8.4,
        height: 2.8
      }
    });
    
    // Test OCIO Triangle
    builder.addSlide({
      title: 'OCIO Service Model',
      assetType: 'infographic',
      assetKey: 'ocio-triangle',
      config: {
        centerX: 5,
        centerY: 3.5,
        size: 2.5
      }
    });
    
    // Test Risk Metrics Table
    builder.addSlide({
      title: 'Risk Analysis Summary',
      assetType: 'dataTable',
      assetKey: 'risk-metrics',
      data: {
        metrics: ['Maximum Drawdown', 'Volatility', 'Beta', 'Correlation', 'VaR (95%)', 'Calmar Ratio'],
        portfolio: ['8.5%', '11.2%', '0.78', '0.85', '2.1%', '1.32'],
        benchmark: ['18.2%', '16.8%', '1.00', '1.00', '3.8%', '0.89'],
        relative: ['-9.7%', '-5.6%', '-0.22', '-0.15', '-1.7%', '+0.43']
      }
    });
    
    // Test Strategy Performance Visualization
    builder.addSlide({
      title: 'Bull vs Bear Market Performance',
      assetType: 'infographic',
      assetKey: 'strategy-performance',
      data: {
        bullMarket: { return: '+18.5%', period: '2021-2022' },
        bearMarket: { return: '+3.2%', period: '2022-2023' },
        benchmark: { bull: '+12.8%', bear: '-15.6%' }
      },
      config: {
        startX: 1,
        startY: 1.5,
        width: 8,
        height: 4
      }
    });
    
    // Closing
    builder.addSlide({
      title: 'ASSET MIGRATION COMPLETE',
      role: 'cta',
      isClosing: true,
      actionText: 'All Adobe Illustrator assets successfully converted to native PowerPoint elements with dynamic data binding capability.',
      contactInfo: 'potomac.com | '
    });
    
    // Save test presentation
    const outputPath = await builder.save('phase3-asset-showcase.pptx');
    
    // Generate asset report
    const assetSummary = builder.assets.getAvailableAssets();
    
    console.log('---');
    console.log('🎉 Phase 3 Asset Test Complete!');
    console.log(`📄 File: ${outputPath}`);
    console.log(`📊 Converted Assets: ${assetSummary.total} total`);
    console.log(`   - Data Tables: ${assetSummary.dataTables}`);
    console.log(`   - Infographics: ${assetSummary.infographics}`);
    console.log('✅ All Adobe Illustrator assets now available as native PowerPoint elements');
    
    return outputPath;
    
  } catch (error) {
    console.error('❌ Phase 3 Asset Test Failed:', error.message);
    throw error;
  }
}

// Run test
if (require.main === module) {
  testPhase3Assets();
}