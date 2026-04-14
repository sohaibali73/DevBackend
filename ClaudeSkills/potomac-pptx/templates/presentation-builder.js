/**
 * Potomac Enhanced Presentation Builder - Phase 2
 * Smart content classification and template selection system
 * 
 * This builder intelligently selects appropriate templates based on content type
 * and presentation purpose, ensuring optimal layout and brand compliance.
 */

const pptxgen = require("pptxgenjs");
const { PotomacSlideTemplates } = require('./slide-templates.js');
const { strictComplianceEnforcement } = require('../compliance/brand-compliance-engine.js');
const { SLIDE_PALETTES } = require('../brand-assets/colors/potomac-colors.js');

class PotomacPresentationBuilder {
  constructor(options = {}) {
    this.pres = new pptxgen();
    this.options = {
      title: options.title || 'POTOMAC PRESENTATION',
      subtitle: options.subtitle || 'Built to Conquer Risk®',
      author: 'Potomac',
      company: 'Potomac',
      palette: options.palette || 'STANDARD',
      presentationType: options.type || 'general',
      strictCompliance: options.strictCompliance !== false,
      ...options
    };
    
    this.setupPresentation();
    this.templates = new PotomacSlideTemplates(this.pres, this.options);
    this.slideStack = [];
    
    // Content classification patterns
    this.classificationRules = this.initializeClassificationRules();
  }

  setupPresentation() {
    // Set presentation properties
    this.pres.author = this.options.author;
    this.pres.company = this.options.company;
    this.pres.revision = '1';
    this.pres.subject = this.options.title;
    this.pres.title = this.options.title;
    
    // Standard 10"×7.5" (LAYOUT_16x9) — all element coordinates assume 10" width
    this.pres.layout = 'LAYOUT_16x9';

    // Define slide masters for consistent branding
    PotomacSlideTemplates.defineAllMasters(this.pres, this.options.palette || 'STANDARD');
  }

  // =======================
  // CONTENT CLASSIFICATION
  // =======================

  initializeClassificationRules() {
    return {
      // Title slide detection patterns
      titleSlide: {
        triggers: ['title', 'opening', 'introduction', 'welcome'],
        indicators: (content) => content.isFirst || content.role === 'title'
      },
      
      // Executive/premium slide patterns
      executiveSlide: {
        triggers: ['executive', 'ceo', 'board', 'leadership', 'strategic', 'vision'],
        indicators: (content) => this.options.presentationType === 'executive'
      },
      
      // Section divider patterns
      sectionDivider: {
        triggers: ['section', 'part', 'chapter', 'agenda', 'overview'],
        indicators: (content) => content.role === 'divider' || content.isSection
      },
      
      // Two-column content patterns
      twoColumn: {
        triggers: ['comparison', 'versus', 'vs', 'before/after', 'pros/cons', 'benefits/risks'],
        indicators: (content) => content.hasComparison || Array.isArray(content.columns) && content.columns.length === 2
      },
      
      // Three-column patterns
      threeColumn: {
        triggers: ['categories', 'pillars', 'segments', 'types', 'options'],
        indicators: (content) => Array.isArray(content.columns) && content.columns.length === 3
      },
      
      // Quote/testimonial patterns
      quote: {
        triggers: ['testimonial', 'quote', 'client says', 'feedback', 'review'],
        indicators: (content) => content.type === 'quote' || (content.text && content.text.includes('"'))
      },
      
      // Metrics/statistics patterns
      metrics: {
        triggers: ['performance', 'results', 'statistics', 'numbers', 'data', 'metrics'],
        indicators: (content) => content.type === 'metrics' || this.hasNumericContent(content)
      },
      
      // Process/timeline patterns
      process: {
        triggers: ['process', 'steps', 'workflow', 'timeline', 'methodology', 'approach'],
        indicators: (content) => content.type === 'process' || this.hasSequentialContent(content)
      },
      
      // Call-to-action patterns
      callToAction: {
        triggers: ['action', 'next steps', 'get started', 'contact', 'schedule'],
        indicators: (content) => content.role === 'cta' || content.isClosing
      }
    };
  }

  /**
   * Classify content to determine best template
   */
  classifyContent(slideData) {
    const contentText = this.extractTextFromSlideData(slideData).toLowerCase();
    const classification = {
      type: 'content', // default
      confidence: 0,   // fixed: was 0.5 which blocked all other classifications
      reasons: [],
      templateMethod: 'createContentSlide'
    };

    // Check each classification rule
    for (const [type, rule] of Object.entries(this.classificationRules)) {
      let score = 0;
      
      // Check trigger words
      const triggerMatches = rule.triggers.filter(trigger => 
        contentText.includes(trigger.toLowerCase())
      ).length;
      
      if (triggerMatches > 0) {
        score += triggerMatches * 0.3;
        classification.reasons.push(`Found ${triggerMatches} trigger word(s) for ${type}`);
      }
      
      // Check indicators
      try {
        if (rule.indicators(slideData)) {
          score += 0.7;
          classification.reasons.push(`Content structure indicates ${type}`);
        }
      } catch (error) {
        // Ignore indicator errors
      }
      
      // Update classification if this type has higher confidence
      if (score > classification.confidence) {
        classification.type = type;
        classification.confidence = score;
        classification.templateMethod = this.getTemplateMethod(type);
      }
    }

    return classification;
  }

  getTemplateMethod(classificationType) {
    const methodMap = {
      // Original classifications
      titleSlide:      'createStandardTitleSlide',
      executiveSlide:  'createExecutiveTitleSlide',
      sectionDivider:  'createSectionDividerSlide',
      twoColumn:       'createTwoColumnSlide',
      threeColumn:     'createThreeColumnSlide',
      quote:           'createQuoteSlide',
      metrics:         'createMetricSlide',
      process:         'createProcessSlide',
      callToAction:    'createCallToActionSlide',
      content:         'createContentSlide',
      // New DeckPlanner types
      executive_summary: 'createExecutiveSummarySlide',
      card_grid:         'createCardGridSlide',
      icon_grid:         'createIconGridSlide',
      hub_spoke:         'createHubSpokeSlide',
      timeline:          'createTimelineSlide',
      matrix_2x2:        'createMatrix2x2Slide',
      scorecard:         'createScorecardSlide',
      comparison:        'createComparisonSlide',
      table:             'createTableSlide',
      chart:             'createChartSlide',
      image_content:     'createImageContentSlide',
      image:             'createImageSlide',
    };

    return methodMap[classificationType] || 'createContentSlide';
  }

  // =======================
  // CONTENT ANALYSIS HELPERS
  // =======================

  extractTextFromSlideData(slideData) {
    let text = '';
    if (slideData.title) text += slideData.title + ' ';
    if (slideData.subtitle) text += slideData.subtitle + ' ';
    if (slideData.content) {
      if (Array.isArray(slideData.content)) {
        text += slideData.content.join(' ') + ' ';
      } else {
        text += slideData.content + ' ';
      }
    }
    if (slideData.leftContent) text += slideData.leftContent + ' ';
    if (slideData.rightContent) text += slideData.rightContent + ' ';
    return text;
  }

  hasNumericContent(slideData) {
    const text = this.extractTextFromSlideData(slideData);
    // Look for percentages, dollar amounts, numbers with units
    const numericPatterns = [
      /\d+%/,           // Percentages
      /\$[\d,]+/,       // Dollar amounts
      /\d+(\.\d+)?[KkMmBb]/,  // Numbers with K, M, B suffixes
      /\d+\.\d+/,       // Decimals
      /\d{4}/           // Years or large numbers
    ];
    
    return numericPatterns.some(pattern => pattern.test(text)) || 
           (slideData.metrics && Array.isArray(slideData.metrics));
  }

  hasSequentialContent(slideData) {
    const text = this.extractTextFromSlideData(slideData);
    // Look for sequential indicators
    const sequentialPatterns = [
      /step \d+/i,
      /\d+\./,          // Numbered lists
      /first|second|third|fourth|fifth/i,
      /phase \d+/i,
      /stage \d+/i
    ];
    
    return sequentialPatterns.some(pattern => pattern.test(text)) ||
           (slideData.steps && Array.isArray(slideData.steps));
  }

  // =======================
  // SMART SLIDE CREATION
  // =======================

  /**
   * Add slide with intelligent template selection
   */
  addSlide(slideData) {
    const classification = this.classifyContent(slideData);
    console.log(`🤖 Smart Template Selection: ${classification.type} (confidence: ${Math.round(classification.confidence * 100)}%)`);
    
    if (classification.reasons.length > 0) {
      console.log(`   Reasons: ${classification.reasons.join(', ')}`);
    }

    // Call the appropriate template method
    const templateMethod = this.templates[classification.templateMethod];
    
    if (!templateMethod) {
      console.warn(`⚠️  Template method ${classification.templateMethod} not found, using default`);
      return this.templates.createContentSlide(slideData.title, slideData.content);
    }

    // Prepare arguments based on template type
    let slide;
    try {
      slide = this.callTemplateMethod(classification.templateMethod, slideData);
      
      // Track slide in stack for compliance checking
      this.slideStack.push({
        data: slideData,
        classification,
        slide
      });
      
    } catch (error) {
      console.error(`❌ Error creating slide with ${classification.templateMethod}:`, error.message);
      // Fallback to basic content slide
      slide = this.templates.createContentSlide(slideData.title, slideData.content || 'Content error');
    }

    return slide;
  }

  callTemplateMethod(methodName, slideData) {
    switch (methodName) {
      case 'createStandardTitleSlide':
        return this.templates.createStandardTitleSlide(slideData.title, slideData.subtitle);
      
      case 'createExecutiveTitleSlide':
        return this.templates.createExecutiveTitleSlide(slideData.title, slideData.subtitle, slideData.tagline);
      
      case 'createSectionDividerSlide':
        return this.templates.createSectionDividerSlide(slideData.title, slideData.description);
      
      case 'createTwoColumnSlide':
        return this.templates.createTwoColumnSlide(
          slideData.title, 
          slideData.leftContent || slideData.columns?.[0] || 'Left Content',
          slideData.rightContent || slideData.columns?.[1] || 'Right Content'
        );
      
      case 'createThreeColumnSlide':
        return this.templates.createThreeColumnSlide(
          slideData.title,
          slideData.columns?.[0] || 'Column 1',
          slideData.columns?.[1] || 'Column 2', 
          slideData.columns?.[2] || 'Column 3'
        );
      
      case 'createQuoteSlide':
        return this.templates.createQuoteSlide(
          slideData.quote || slideData.content,
          slideData.attribution,
          slideData.context
        );
      
      case 'createMetricSlide':
        return this.templates.createMetricSlide(
          slideData.title,
          slideData.metrics || this.extractMetrics(slideData),
          slideData.context
        );
      
      case 'createProcessSlide':
        return this.templates.createProcessSlide(
          slideData.title,
          slideData.steps || this.extractSteps(slideData),
          slideData.options
        );
      
      case 'createCallToActionSlide':
        return this.templates.createCallToActionSlide(
          slideData.title,
          slideData.actionText || slideData.content,
          slideData.contactInfo || 'potomac.com | (305) 824-2702',
          slideData.buttonText
        );
      
      // New DeckPlanner types
      case 'createExecutiveSummarySlide':
        return this.templates.createExecutiveSummarySlide(
          slideData.title,
          slideData.bullets || slideData.supporting_points || [],
          slideData.context
        );

      case 'createCardGridSlide':
        return this.templates.createCardGridSlide(
          slideData.title,
          slideData.cards || (slideData.columns || []).map((c, i) => ({ title: `Item ${i + 1}`, text: c }))
        );

      case 'createIconGridSlide':
        return this.templates.createIconGridSlide(
          slideData.title,
          slideData.items || (slideData.bullets || []).map((b, i) => ({ icon: String(i + 1), title: b }))
        );

      case 'createHubSpokeSlide':
        return this.templates.createHubSpokeSlide(
          slideData.title,
          { title: slideData.center_title || 'POTOMAC', subtitle: slideData.center_subtitle || '' },
          (slideData.nodes || slideData.columns || []).map(n => typeof n === 'string' ? { label: n } : n)
        );

      case 'createTimelineSlide':
        return this.templates.createTimelineSlide(
          slideData.title,
          slideData.milestones || (slideData.bullets || []).map(b => ({ label: b, status: 'pending' }))
        );

      case 'createMatrix2x2Slide':
        return this.templates.createMatrix2x2Slide(
          slideData.title,
          slideData.x_axis_label || '',
          slideData.y_axis_label || '',
          slideData.quadrants || []
        );

      case 'createScorecardSlide':
        return this.templates.createScorecardSlide(
          slideData.title,
          slideData.metrics || [],
          slideData.subtitle
        );

      case 'createComparisonSlide':
        return this.templates.createComparisonSlide(
          slideData.title,
          slideData.left_label || slideData.leftLabel || 'OPTION A',
          slideData.right_label || slideData.rightLabel || 'OPTION B',
          slideData.rows || [],
          slideData.winner || null
        );

      case 'createTableSlide':
        return this.templates.createTableSlide(
          slideData.title,
          slideData.headers || slideData.table_headers || [],
          slideData.rows || slideData.table_rows || [],
          slideData.options || {}
        );

      case 'createChartSlide':
        return this.templates.createChartSlide(
          slideData.title,
          slideData.chart_type || slideData.chartType || 'bar',
          slideData.chart_data || slideData.chartData || [],
          slideData.chart_options || {}
        );

      case 'createImageContentSlide':
        return this.templates.createImageContentSlide(
          slideData.title,
          slideData.image_path || slideData.imagePath || null,
          slideData.content || slideData.bullets || '',
          slideData.image_position || 'left'
        );

      case 'createImageSlide':
        return this.templates.createImageSlide(
          slideData.image_path || slideData.imagePath || null,
          slideData.title,
          slideData.overlay !== false
        );

      default:
        return this.templates.createContentSlide(slideData.title, slideData.content);
    }
  }

  // =======================
  // DATA EXTRACTION HELPERS
  // =======================

  extractMetrics(slideData) {
    // Try to extract metrics from content
    if (slideData.metrics) return slideData.metrics;
    
    const content = this.extractTextFromSlideData(slideData);
    const metrics = [];
    
    // Simple metric extraction patterns
    const patterns = [
      { regex: /(\d+)%/, type: 'percentage' },
      { regex: /\$(\d+(?:,\d{3})*(?:\.\d{2})?)[MmKk]?/, type: 'currency' },
      { regex: /(\d+(?:\.\d+)?)[KkMmBb]/, type: 'number' }
    ];
    
    patterns.forEach(pattern => {
      const matches = content.match(new RegExp(pattern.regex, 'g'));
      if (matches) {
        matches.slice(0, 3).forEach((match, index) => { // Max 3 metrics
          metrics.push({
            value: match,
            label: `Metric ${index + 1}` // Would need better label extraction
          });
        });
      }
    });
    
    return metrics.length > 0 ? metrics : [
      { value: '100%', label: 'Success Rate' } // Default fallback
    ];
  }

  extractSteps(slideData) {
    // Try to extract process steps from content
    if (slideData.steps) return slideData.steps;
    
    const content = slideData.content;
    if (Array.isArray(content)) {
      return content.map((item, index) => ({
        title: `Step ${index + 1}`,
        description: item
      }));
    }
    
    // Default steps
    return [
      { title: 'Discovery', description: 'Understanding your needs' },
      { title: 'Strategy', description: 'Developing the approach' },
      { title: 'Implementation', description: 'Executing the plan' },
      { title: 'Monitoring', description: 'Ongoing optimization' }
    ];
  }

  // =======================
  // PRESENTATION TYPES
  // =======================

  /**
   * Generate Research Presentation
   */
  generateResearchPresentation(data) {
    console.log('📊 Generating Research Presentation...');
    
    // Title slide
    this.addSlide({
      title: data.title || this.options.title,
      subtitle: data.subtitle || 'Investment Research & Analysis',
      role: 'title',
      isFirst: true
    });
    
    // Executive Summary
    this.addSlide({
      title: 'Executive Summary',
      content: data.executiveSummary || [
        'Market conditions remain challenging',
        'Opportunities exist in selected sectors', 
        'Risk management is paramount',
        'Strategic positioning recommended'
      ]
    });
    
    // Key Findings (Metrics)
    if (data.keyFindings) {
      this.addSlide({
        title: 'Key Findings',
        type: 'metrics',
        metrics: data.keyFindings
      });
    }
    
    // Market Analysis (Two-column)
    this.addSlide({
      title: 'Market Analysis',
      hasComparison: true,
      leftContent: data.currentEnvironment || 'Current Environment:\n\n• Market volatility elevated\n• Economic uncertainty persists\n• Sector rotation continuing',
      rightContent: data.outlook || 'Our Outlook:\n\n• Selective opportunities emerging\n• Defensive positioning preferred\n• Active management advantage'
    });
    
    // Investment Implications
    this.addSlide({
      title: 'Investment Implications',
      content: data.implications || [
        'Maintain diversified portfolio approach',
        'Focus on quality companies with strong fundamentals',
        'Consider defensive sectors for stability',
        'Monitor interest rate environment closely'
      ]
    });
    
    // Closing
    this.addSlide({
      title: 'Questions & Discussion',
      role: 'cta',
      isClosing: true,
      actionText: 'Ready to discuss how these insights can benefit your portfolio?',
      contactInfo: 'potomac.com | (305) 824-2702 | info@potomac.com'
    });
    
    return this;
  }

  /**
   * Generate Client Pitch Presentation
   */
  generateClientPitch(data) {
    console.log('🎯 Generating Client Pitch...');
    
    // Executive Title
    this.addSlide({
      title: data.title || 'Potomac Investment Solutions',
      subtitle: data.subtitle || 'Your Partner in Conquering Risk',
      role: 'title',
      isFirst: true
    });
    
    // Our Approach (Process)
    this.addSlide({
      title: 'Our Proven Approach',
      type: 'process',
      steps: data.approach || [
        { title: 'Listen', description: 'Understanding your unique goals and constraints' },
        { title: 'Analyze', description: 'Comprehensive risk assessment and opportunity identification' },
        { title: 'Design', description: 'Custom strategy tailored to your objectives' },
        { title: 'Execute', description: 'Professional implementation and ongoing management' }
      ]
    });
    
    // Value Proposition (Three columns)
    this.addSlide({
      title: 'Why Choose Potomac',
      columns: data.valueProps || [
        'Experience:\n\n• Proven track record\n• Seasoned professionals\n• Institutional-quality research',
        'Innovation:\n\n• Cutting-edge technology\n• Advanced risk management\n• Systematic approach',
        'Service:\n\n• Personal attention\n• Transparent reporting\n• Ongoing communication'
      ]
    });
    
    // Results (Metrics)
    if (data.results) {
      this.addSlide({
        title: 'Client Results',
        type: 'metrics',
        metrics: data.results,
        context: 'Past performance does not guarantee future results'
      });
    }
    
    // Next Steps (Call to Action)
    this.addSlide({
      title: 'Let\'s Get Started',
      role: 'cta',
      isClosing: true,
      actionText: 'Ready to experience the Potomac difference? Let\'s schedule a consultation to discuss your specific needs.',
      buttonText: 'Schedule Consultation',
      contactInfo: 'potomac.com | (305) 824-2702 | info@potomac.com'
    });
    
    return this;
  }

  /**
   * Generate Market Outlook Presentation
   */
  generateMarketOutlook(data) {
    console.log('🔮 Generating Market Outlook...');
    
    // Title
    this.addSlide({
      title: data.title || 'Market Outlook 2025',
      subtitle: data.subtitle || 'Navigating Uncertainty with Confidence',
      role: 'title',
      isFirst: true
    });
    
    // Current Market Environment
    this.addSlide({
      title: 'Current Market Environment',
      hasComparison: true,
      leftContent: data.challenges || 'Key Challenges:\n\n• Persistent inflation concerns\n• Geopolitical tensions\n• Rate environment uncertainty\n• Supply chain disruptions',
      rightContent: data.opportunities || 'Emerging Opportunities:\n\n• Sector rotation continues\n• Value over growth themes\n• International diversification\n• Alternative investments'
    });
    
    // Economic Indicators (Metrics)
    if (data.indicators) {
      this.addSlide({
        title: 'Key Economic Indicators',
        type: 'metrics',
        metrics: data.indicators
      });
    }
    
    // Investment Strategy
    this.addSlide({
      title: 'Our Strategic Response',
      content: data.strategy || [
        'Maintain defensive positioning while seeking selective opportunities',
        'Focus on quality companies with pricing power',
        'Diversify across asset classes and geographies',
        'Active risk management and regular portfolio rebalancing'
      ]
    });
    
    // Closing
    this.addSlide({
      title: 'Built to Conquer Risk®',
      role: 'cta',
      isClosing: true,
      actionText: 'Contact us to learn how our strategies can help navigate these challenging markets.',
      contactInfo: 'potomac.com | (305) 824-2702 | info@potomac.com'
    });
    
    return this;
  }

  // =======================
  // VALIDATION & OUTPUT
  // =======================

  /**
   * Validate presentation compliance
   */
  async validateCompliance() {
    if (!this.options.strictCompliance) {
      console.log('⚠️ Brand compliance validation skipped');
      return { compliant: true, report: null };
    }
    
    console.log('🛡️ Running enhanced brand compliance validation...');
    
    try {
      // Create detailed presentation data for validation
      const presentationData = {
        title: this.options.title,
        subtitle: this.options.subtitle,
        company: this.options.company,
        author: this.options.author,
        slides: this.slideStack.map(item => ({
          title: item.data.title,
          content: item.data.content,
          classification: item.classification,
          // Add other slide data as needed for validation
        }))
      };
      
      const report = strictComplianceEnforcement(presentationData);
      
      if (report.complianceStatus === 'COMPLIANT') {
        console.log('✅ Enhanced presentation passes all brand compliance checks');
        console.log(`📊 Template Usage: ${this.getTemplateUsageStats()}`);
        return { compliant: true, report };
      } else {
        console.log('❌ Brand compliance violations detected');
        console.log(`Violations: ${report.totalViolations}, Corrections: ${report.totalCorrections}`);
        return { compliant: false, report };
      }
    } catch (error) {
      console.error('❌ Enhanced brand compliance validation failed:', error.message);
      return { compliant: false, error: error.message };
    }
  }

  getTemplateUsageStats() {
    const usage = {};
    this.slideStack.forEach(item => {
      const type = item.classification.type;
      usage[type] = (usage[type] || 0) + 1;
    });
    
    return Object.entries(usage)
      .map(([type, count]) => `${type}: ${count}`)
      .join(', ');
  }

  /**
   * Save presentation to file
   */
  async save(filename) {
    const path = require('path');
    const fs = require('fs');
    
    const outputPath = path.join(__dirname, '../examples/', filename);
    
    // Ensure examples directory exists
    const examplesDir = path.dirname(outputPath);
    if (!fs.existsSync(examplesDir)) {
      fs.mkdirSync(examplesDir, { recursive: true });
    }
    
    try {
      await this.pres.writeFile({ fileName: outputPath });
      console.log(`📄 Enhanced presentation saved: ${outputPath}`);
      return outputPath;
    } catch (error) {
      console.error('❌ Failed to save enhanced presentation:', error.message);
      throw error;
    }
  }
}

module.exports = {
  PotomacPresentationBuilder
};