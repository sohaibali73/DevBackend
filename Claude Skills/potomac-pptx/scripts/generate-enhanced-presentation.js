#!/usr/bin/env node

/**
 * Potomac Enhanced Presentation Generator - Phase 2
 * Smart template selection and universal presentation system
 * 
 * Usage: node generate-enhanced-presentation.js --type research --title "MARKET ANALYSIS" --output "research.pptx"
 */

const { PotomacPresentationBuilder } = require('../templates/presentation-builder.js');
const path = require('path');

// PRESENTATION TYPE CONFIGURATIONS
const PRESENTATION_TYPES = {
  research: {
    name: 'Research Presentation',
    description: 'Investment research and market analysis',
    defaultTitle: 'INVESTMENT RESEARCH',
    defaultSubtitle: 'Market Analysis & Strategic Insights',
    palette: 'STANDARD',
    sampleData: {
      keyFindings: [
        { value: '12.5%', label: 'Expected Return' },
        { value: '15%', label: 'Volatility' },
        { value: '0.83', label: 'Sharpe Ratio' }
      ],
      currentEnvironment: 'Current Environment:\n\n• Market volatility remains elevated\n• Interest rate uncertainty persists\n• Inflation concerns moderate\n• Geopolitical tensions continue',
      outlook: 'Our Outlook:\n\n• Selective opportunities emerging\n• Quality factor outperforming\n• Defensive positioning preferred\n• Active management advantage evident',
      implications: [
        'Focus on high-quality, dividend-paying stocks',
        'Maintain geographic and sector diversification',
        'Consider alternative investments for yield',
        'Monitor Federal Reserve policy changes closely'
      ]
    }
  },

  pitch: {
    name: 'Client Pitch',
    description: 'Client presentation and business development',
    defaultTitle: 'POTOMAC INVESTMENT SOLUTIONS',
    defaultSubtitle: 'Your Partner in Conquering Risk',
    palette: 'STANDARD',
    sampleData: {
      approach: [
        { title: 'Discovery', description: 'Comprehensive assessment of your goals, constraints, and risk tolerance' },
        { title: 'Strategy', description: 'Custom investment strategy design based on your unique situation' },
        { title: 'Implementation', description: 'Professional execution and portfolio construction' },
        { title: 'Management', description: 'Ongoing monitoring, rebalancing, and optimization' }
      ],
      valueProps: [
        'Experience:\n\n• 15+ years in institutional investing\n• Proven track record across cycles\n• Deep market expertise\n• Rigorous research process',
        'Technology:\n\n• Advanced portfolio analytics\n• Real-time risk monitoring\n• Proprietary screening tools\n• Institutional-grade platforms',
        'Service:\n\n• Dedicated relationship management\n• Quarterly performance reviews\n• 24/7 client portal access\n• Transparent fee structure'
      ],
      results: [
        { value: '94%', label: 'Client Retention' },
        { value: '$2.5B', label: 'Assets Under Management' },
        { value: '8.2%', label: 'Average Annual Return' }
      ]
    }
  },

  outlook: {
    name: 'Market Outlook',
    description: 'Market commentary and forward-looking analysis',
    defaultTitle: 'MARKET OUTLOOK 2025',
    defaultSubtitle: 'Navigating Uncertainty with Confidence',
    palette: 'INVESTMENT',
    sampleData: {
      challenges: 'Key Challenges:\n\n• Persistent inflation pressures\n• Central bank policy uncertainty\n• Geopolitical risk factors\n• Supply chain disruptions',
      opportunities: 'Emerging Opportunities:\n\n• Energy transition investments\n• Technology sector recovery\n• International diversification\n• Fixed income normalization',
      indicators: [
        { value: '3.2%', label: 'GDP Growth Forecast' },
        { value: '2.8%', label: 'Core Inflation Target' },
        { value: '4.5%', label: '10-Year Treasury' }
      ],
      strategy: [
        'Overweight quality growth companies with pricing power',
        'Maintain defensive allocations in utilities and healthcare',
        'Increase exposure to international developed markets',
        'Selective opportunities in emerging market debt'
      ]
    }
  },

  demo: {
    name: 'Feature Demo',
    description: 'Demonstration of all Phase 2 template types',
    defaultTitle: 'POTOMAC TEMPLATE SHOWCASE',
    defaultSubtitle: 'Phase 2 Universal Template System',
    palette: 'STANDARD',
    sampleData: {} // Will be handled by custom demo generation
  }
};

class EnhancedPresentationCLI {
  constructor() {
    this.availableTypes = Object.keys(PRESENTATION_TYPES);
  }

  parseArgs() {
    const args = process.argv.slice(2);
    const options = {
      type: 'demo',
      title: null,
      subtitle: null,
      output: null,
      palette: null,
      help: false
    };

    for (let i = 0; i < args.length; i += 2) {
      const flag = args[i];
      const value = args[i + 1];

      switch (flag) {
        case '--type':
          if (this.availableTypes.includes(value)) {
            options.type = value;
          } else {
            console.error(`❌ Invalid type: ${value}. Available types: ${this.availableTypes.join(', ')}`);
            process.exit(1);
          }
          break;
        case '--title':
          options.title = value;
          break;
        case '--subtitle':
          options.subtitle = value;
          break;
        case '--output':
          options.output = value;
          break;
        case '--palette':
          options.palette = value;
          break;
        case '--help':
          options.help = true;
          break;
      }
    }

    // Set defaults based on presentation type
    const typeConfig = PRESENTATION_TYPES[options.type];
    if (!options.title) options.title = typeConfig.defaultTitle;
    if (!options.subtitle) options.subtitle = typeConfig.defaultSubtitle;
    if (!options.palette) options.palette = typeConfig.palette;
    if (!options.output) options.output = `${options.type}-presentation.pptx`;

    return options;
  }

  showHelp() {
    console.log(`
🎯 Potomac Enhanced Presentation Generator - Phase 2

USAGE:
  node generate-enhanced-presentation.js [options]

OPTIONS:
  --type <type>       Presentation type (default: demo)
  --title <title>     Custom presentation title
  --subtitle <sub>    Custom subtitle  
  --output <file>     Output filename
  --palette <name>    Color palette (STANDARD, DARK, INVESTMENT, FUNDS)
  --help             Show this help

PRESENTATION TYPES:
${Object.entries(PRESENTATION_TYPES).map(([key, config]) => 
  `  ${key.padEnd(10)} - ${config.description}`
).join('\n')}

EXAMPLES:
  # Generate research presentation
  node generate-enhanced-presentation.js --type research --title "Q1 2025 MARKET ANALYSIS"
  
  # Generate client pitch
  node generate-enhanced-presentation.js --type pitch --palette INVESTMENT
  
  # Generate market outlook  
  node generate-enhanced-presentation.js --type outlook --output "market-outlook-2025.pptx"
  
  # Generate demo of all templates
  node generate-enhanced-presentation.js --type demo

PHASE 2 FEATURES:
  ✨ Smart template selection based on content analysis
  🎨 Universal template system with 11+ slide types
  📊 Automatic content classification and layout optimization
  🛡️ Enhanced brand compliance with zero-tolerance enforcement
  🚀 Presentation type generators (research, pitch, outlook)
    `);
  }

  generateDemoPresentation(builder) {
    console.log('🎭 Generating Phase 2 Feature Demo...');

    // Title slide
    builder.addSlide({
      title: 'POTOMAC TEMPLATE SHOWCASE',
      subtitle: 'Phase 2 Universal Template System Demonstration',
      role: 'title',
      isFirst: true
    });

    // Section divider
    builder.addSlide({
      title: 'TITLE SLIDE VARIANTS',
      description: 'Multiple title slide options for different presentation types',
      role: 'divider',
      isSection: true
    });

    // Executive title slide demo
    builder.addSlide({
      title: 'EXECUTIVE PRESENTATION',
      subtitle: 'Premium dark theme for high-impact presentations',
      tagline: 'Built to Conquer Risk®'
    });

    // Content slide variants section
    builder.addSlide({
      title: 'CONTENT SLIDE TEMPLATES',
      description: 'Smart template selection based on content analysis',
      role: 'divider',
      isSection: true
    });

    // Two-column comparison
    builder.addSlide({
      title: 'MARKET COMPARISON',
      hasComparison: true,
      leftContent: 'Traditional Approach:\n\n• Static asset allocation\n• Benchmark-relative performance\n• Limited risk controls\n• Quarterly rebalancing',
      rightContent: 'Potomac Approach:\n\n• Dynamic asset allocation\n• Absolute risk management\n• Systematic guardrails\n• Continuous monitoring'
    });

    // Three-column layout
    builder.addSlide({
      title: 'INVESTMENT PILLARS',
      columns: [
        'Research:\n\n• Quantitative analysis\n• Fundamental research\n• Risk assessment\n• Market intelligence',
        'Strategy:\n\n• Portfolio construction\n• Asset allocation\n• Risk budgeting\n• Performance attribution',
        'Execution:\n\n• Trade optimization\n• Cost management\n• Liquidity planning\n• Operational efficiency'
      ]
    });

    // Metrics slide
    builder.addSlide({
      title: 'KEY PERFORMANCE METRICS',
      type: 'metrics',
      metrics: [
        { value: '12.8%', label: 'Annualized Return' },
        { value: '11.2%', label: 'Volatility' },
        { value: '1.14', label: 'Sharpe Ratio' },
        { value: '94%', label: 'Client Retention' },
        { value: '$2.5B', label: 'Assets Under Management' },
        { value: '8.5%', label: 'Maximum Drawdown' }
      ],
      context: 'Performance data represents composite results from 2019-2024. Past performance does not guarantee future results.'
    });

    // Process slide
    builder.addSlide({
      title: 'INVESTMENT PROCESS',
      type: 'process',
      steps: [
        { title: 'Research', description: 'Comprehensive market and security analysis using quantitative and fundamental techniques' },
        { title: 'Strategy', description: 'Portfolio construction based on risk-adjusted return optimization and client objectives' },
        { title: 'Implementation', description: 'Efficient trade execution with attention to market impact and transaction costs' },
        { title: 'Monitoring', description: 'Continuous risk monitoring and portfolio rebalancing using systematic guardrails' }
      ]
    });

    // Quote slide
    builder.addSlide({
      type: 'quote',
      quote: 'Potomac\'s systematic approach to risk management has helped us navigate volatile markets while maintaining our long-term investment objectives.',
      attribution: 'Chief Investment Officer',
      context: 'Large Institutional Client'
    });

    // Specialized slides section
    builder.addSlide({
      title: 'SPECIALIZED TEMPLATES',
      description: 'Advanced layouts for specific content types',
      role: 'divider',
      isSection: true
    });

    // Call to action slide
    builder.addSlide({
      title: 'EXPERIENCE THE DIFFERENCE',
      role: 'cta',
      isClosing: true,
      actionText: 'Ready to see how Potomac\'s systematic approach can enhance your portfolio? Let\'s schedule a consultation to discuss your specific needs and objectives.',
      buttonText: 'Schedule Consultation',
      contactInfo: 'potomac.com | (305) 824-2702 | info@potomac.com'
    });

    return builder;
  }

  async run() {
    const options = this.parseArgs();

    if (options.help) {
      this.showHelp();
      return;
    }

    const typeConfig = PRESENTATION_TYPES[options.type];
    
    console.log('🎯 Potomac Enhanced Presentation Generator - Phase 2');
    console.log(`Type: ${typeConfig.name}`);
    console.log(`Title: ${options.title}`);
    console.log(`Subtitle: ${options.subtitle}`);
    console.log(`Palette: ${options.palette}`);
    console.log(`Output: ${options.output}`);
    console.log('---');

    try {
      // Create enhanced builder
      const builder = new PotomacPresentationBuilder({
        title: options.title,
        subtitle: options.subtitle,
        palette: options.palette,
        presentationType: options.type,
        strictCompliance: true
      });

      // Generate presentation based on type
      switch (options.type) {
        case 'research':
          builder.generateResearchPresentation(typeConfig.sampleData);
          break;
        case 'pitch':
          builder.generateClientPitch(typeConfig.sampleData);
          break;
        case 'outlook':
          builder.generateMarketOutlook(typeConfig.sampleData);
          break;
        case 'demo':
          this.generateDemoPresentation(builder);
          break;
        default:
          throw new Error(`Unknown presentation type: ${options.type}`);
      }

      // Validate compliance
      const compliance = await builder.validateCompliance();
      if (!compliance.compliant && builder.options.strictCompliance) {
        console.error('❌ Presentation failed enhanced brand compliance. Generation aborted.');
        if (compliance.report) {
          console.log('Compliance Report:', JSON.stringify(compliance.report, null, 2));
        }
        process.exit(1);
      }

      // Save presentation
      const outputPath = await builder.save(options.output);

      console.log('---');
      console.log('🎉 Enhanced Potomac presentation generated successfully!');
      console.log(`📄 File: ${outputPath}`);
      console.log('✅ Enhanced brand compliance: PASSED');
      console.log(`🤖 Smart template selection: ACTIVE`);
      
      if (compliance.report && compliance.report.templateUsage) {
        console.log(`📊 Template usage: ${compliance.report.templateUsage}`);
      }

    } catch (error) {
      console.error('❌ Error generating enhanced presentation:', error.message);
      console.error(error.stack);
      process.exit(1);
    }
  }
}

// Run CLI
if (require.main === module) {
  const cli = new EnhancedPresentationCLI();
  cli.run();
}

module.exports = {
  EnhancedPresentationCLI,
  PRESENTATION_TYPES
};