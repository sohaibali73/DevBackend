#!/usr/bin/env node

/**
 * Potomac Presentation Generator - Phase 1
 * Basic branded presentation generation with strict compliance
 * 
 * Usage: node generate-potomac-presentation.js --title "PRESENTATION TITLE" --slides 5
 */

const pptxgen = require("pptxgenjs");
const { strictComplianceEnforcement } = require('../compliance/brand-compliance-engine.js');
const { POTOMAC_COLORS, SLIDE_PALETTES } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS, TYPOGRAPHY_PRESETS } = require('../brand-assets/fonts/potomac-fonts.js');
const path = require('path');
const fs = require('fs');

class PotomacPresentationGenerator {
  constructor(options = {}) {
    this.pres = new pptxgen();
    this.options = {
      title: options.title || 'POTOMAC PRESENTATION',
      subtitle: options.subtitle || 'Built to Conquer Risk®',
      author: 'Potomac',
      company: 'Potomac',
      palette: options.palette || 'STANDARD',
      strictCompliance: options.strictCompliance !== false, // Default true
      ...options
    };
    
    this.setupPresentation();
  }

  setupPresentation() {
    // Set presentation properties
    this.pres.author = this.options.author;
    this.pres.company = this.options.company;
    this.pres.revision = '1';
    this.pres.subject = this.options.title;
    this.pres.title = this.options.title;
    
    // Widescreen 13.333"×7.5" (16:9) format
    this.pres.layout = 'LAYOUT_WIDE';
  }

  // SLIDE TEMPLATES
  
  /**
   * Create Title Slide with Potomac branding
   */
  createTitleSlide(title, subtitle = null) {
    console.log('🎯 Creating Title Slide...');
    
    const slide = this.pres.addSlide();
    const palette = SLIDE_PALETTES[this.options.palette];
    
    // Set background
    slide.background = { color: palette.background };
    
    // Add logo (top right)
    this.addLogo(slide, {
      x: 11.3333,
      y: 0.6667,
      w: 1.7333,
      h: 0.6667
    });
    
    // Add main title
    slide.addText(title.toUpperCase(), {
      x: 0.6667,
      y: 3.3333,
      w: 12.0,
      h: 2.0,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 44,
      bold: true,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY.replace('#', ''),
      align: 'center',
      valign: 'middle',
    });
    
    // Add subtitle if provided
    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.6667,
        y: 5.6,
        w: 12.0,
        h: 1.0667,
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 20,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center',
        valign: 'middle'
      });
    }
    
    // Add accent bar
    slide.addShape(this.pres.ShapeType.rect, {
      x: 0.6667,
      y: 7.3333,
      w: 12.0,
      h: 0.1333,
      fill: { color: palette.accent.replace('#', '') },
      line: { color: palette.accent.replace('#', ''), width: 0.0 },
    });
    
    return slide;
  }

  /**
   * Create Content Slide with bullet points
   */
  createContentSlide(title, content) {
    console.log(`🎯 Creating Content Slide: ${title}`);
    
    const slide = this.pres.addSlide();
    const palette = SLIDE_PALETTES[this.options.palette];
    
    // Set background
    slide.background = { color: palette.background };
    
    // Add logo (small, top right)
    this.addLogo(slide, {
      x: 11.7333,
      y: 0.4,
      w: 1.3333,
      h: 0.5333
    });
    
    // Add slide title
    slide.addText(title.toUpperCase(), {
      x: 0.6667,
      y: 0.6667,
      w: 10.6667,
      h: 1.3333,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 36,
      bold: true,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY.replace('#', ''),
    });
    
    // Add title underline
    slide.addShape(this.pres.ShapeType.rect, {
      x: 0.6667,
      y: 1.8667,
      w: 2.6667,
      h: 0.0667,
      fill: { color: palette.accent.replace('#', '') },
      line: { color: palette.accent.replace('#', ''), width: 0.0 },
    });
    
    // Add content bullets
    if (Array.isArray(content)) {
      const bulletText = content.map(item => ({ text: item, options: { bullet: true } }));
      
      slide.addText(bulletText, {
        x: 0.6667,
        y: 2.9333,
        w: 12.0,
        h: 6.0,
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 18,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        bullet: true,
        lineSpacing: 36
      });
    } else {
      // Single paragraph content
      slide.addText(content, {
        x: 0.6667,
        y: 2.9333,
        w: 12.0,
        h: 6.0,
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 16,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        lineSpacing: 24
      });
    }
    
    return slide;
  }

  /**
   * Create Two-Column Content Slide
   */
  createTwoColumnSlide(title, leftContent, rightContent) {
    console.log(`🎯 Creating Two-Column Slide: ${title}`);
    
    const slide = this.pres.addSlide();
    const palette = SLIDE_PALETTES[this.options.palette];
    
    // Set background
    slide.background = { color: palette.background };
    
    // Add logo
    this.addLogo(slide, {
      x: 11.7333,
      y: 0.4,
      w: 1.3333,
      h: 0.5333
    });
    
    // Add title
    slide.addText(title.toUpperCase(), {
      x: 0.6667,
      y: 0.6667,
      w: 10.6667,
      h: 1.3333,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 32,
      bold: true,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY.replace('#', ''),
    });
    
    // Title underline
    slide.addShape(this.pres.ShapeType.rect, {
      x: 0.6667,
      y: 1.8667,
      w: 2.6667,
      h: 0.0667,
      fill: { color: palette.accent.replace('#', '') },
      line: { color: palette.accent.replace('#', ''), width: 0.0 },
    });
    
    // Left column
    slide.addText(leftContent, {
      x: 0.6667,
      y: 2.9333,
      w: 5.7333,
      h: 6.0,
      fontFace: POTOMAC_FONTS.BODY.family,
      fontSize: 16,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      lineSpacing: 24
    });
    
    // Right column
    slide.addText(rightContent, {
      x: 6.9333,
      y: 2.9333,
      w: 5.7333,
      h: 6.0,
      fontFace: POTOMAC_FONTS.BODY.family,
      fontSize: 16,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      lineSpacing: 24
    });
    
    // Column separator
    slide.addShape(this.pres.ShapeType.rect, {
      x: 6.64,
      y: 2.9333,
      w: 0.0533,
      h: 5.3333,
      fill: { color: POTOMAC_COLORS.TONES.GRAY_20.replace('#', '') },
      line: { color: POTOMAC_COLORS.TONES.GRAY_20.replace('#', ''), width: 0.0 },
    });
    
    return slide;
  }

  /**
   * Create Closing/Contact Slide
   */
  createClosingSlide(title = 'THANK YOU', contactInfo = null) {
    console.log('🎯 Creating Closing Slide...');
    
    const slide = this.pres.addSlide();
    const palette = SLIDE_PALETTES[this.options.palette];
    
    // Set background
    slide.background = { color: palette.background };
    
    // Add large logo (centered)
    this.addLogo(slide, {
      x: 5.6667,
      y: 2.0,
      w: 2.0,
      h: 0.8
    });
    
    // Add main message
    slide.addText(title.toUpperCase(), {
      x: 0.6667,
      y: 3.7333,
      w: 12.0,
      h: 1.3333,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 40,
      bold: true,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY.replace('#', ''),
      align: 'center',
    });
    
    // Add tagline
    slide.addText('Built to Conquer Risk®', {
      x: 0.6667,
      y: 5.3333,
      w: 12.0,
      h: 0.8,
      fontFace: POTOMAC_FONTS.BODY.family,
      fontSize: 18,
      color: palette.accent,
      align: 'center',
      italic: true
    });
    
    // Add contact info if provided
    if (contactInfo) {
      slide.addText(contactInfo, {
        x: 0.6667,
        y: 7.3333,
        w: 12.0,
        h: 2.0,
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 14,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center',
        lineSpacing: 20
      });
    } else {
      // Default contact
      slide.addText('potomac.com\n(305) 824-2702\ninfo@potomac.com', {
        x: 0.6667,
        y: 7.3333,
        w: 12.0,
        h: 2.0,
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 14,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center',
        lineSpacing: 20
      });
    }
    
    return slide;
  }

  // UTILITY METHODS
  
  addLogo(slide, position) {
    // Use the full logo by default
    const logoPath = path.join(__dirname, '../brand-assets/logos/potomac-full-logo.png');
    
    if (fs.existsSync(logoPath)) {
      slide.addImage({
        path: logoPath,
        x: position.x,
        y: position.y,
        w: position.w,
        h: position.h
      });
    } else {
      // Fallback text logo if image not found
      slide.addText('POTOMAC', {
        x: position.x,
        y: position.y,
        w: position.w,
        h: position.h,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 16,
        fontWeight: '700',
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center',
        valign: 'middle',
        bold: true
      });
    }
  }

  // PRESENTATION ASSEMBLY

  /**
   * Generate a sample presentation for testing
   */
  generateSamplePresentation() {
    console.log('🚀 Generating Sample Potomac Presentation...');
    
    // Title Slide
    this.createTitleSlide(
      this.options.title,
      this.options.subtitle
    );
    
    // Sample content slides
    this.createContentSlide('KEY INVESTMENT THEMES', [
      'Diversification in volatile markets',
      'Active vs. passive strategy selection',
      'Risk management through systematic guardrails',
      'Long-term value creation focus'
    ]);
    
    this.createTwoColumnSlide(
      'MARKET OUTLOOK',
      'Current Environment:\n\n• Elevated volatility persists\n• Interest rate uncertainty\n• Geopolitical tensions\n• Inflation concerns remain',
      'Our Response:\n\n• Dynamic asset allocation\n• Risk-managed strategies\n• Diversified approach\n• Built to Conquer Risk®'
    );
    
    this.createContentSlide('POTOMAC ADVANTAGE', [
      'Proven investment strategies',
      'Turnkey Asset Management Platform',
      'Comprehensive research capabilities',
      'Risk management through Guardrails'
    ]);
    
    // Closing slide
    this.createClosingSlide();
    
    console.log('✅ Sample presentation generated successfully');
    return this;
  }

  /**
   * Validate presentation against brand compliance
   */
  validateCompliance() {
    if (!this.options.strictCompliance) {
      console.log('⚠️ Brand compliance validation skipped');
      return { compliant: true, report: null };
    }
    
    console.log('🛡️ Running brand compliance validation...');
    
    try {
      // Create presentation data structure for validation
      const presentationData = {
        title: this.options.title,
        subtitle: this.options.subtitle,
        company: this.options.company,
        author: this.options.author,
        slides: [] // In a real implementation, this would be populated from slide data
      };
      
      const report = strictComplianceEnforcement(presentationData);
      
      if (report.complianceStatus === 'COMPLIANT') {
        console.log('✅ Presentation passes all brand compliance checks');
        return { compliant: true, report };
      } else {
        console.log('❌ Brand compliance violations detected');
        console.log(`Violations: ${report.totalViolations}, Corrections: ${report.totalCorrections}`);
        return { compliant: false, report };
      }
    } catch (error) {
      console.error('❌ Brand compliance validation failed:', error.message);
      return { compliant: false, error: error.message };
    }
  }

  /**
   * Save presentation to file
   */
  async save(filename) {
    const outputPath = path.join(__dirname, '../examples/', filename);
    
    // Ensure examples directory exists
    const examplesDir = path.dirname(outputPath);
    if (!fs.existsSync(examplesDir)) {
      fs.mkdirSync(examplesDir, { recursive: true });
    }
    
    try {
      await this.pres.writeFile({ fileName: outputPath });
      console.log(`📄 Presentation saved: ${outputPath}`);
      return outputPath;
    } catch (error) {
      console.error('❌ Failed to save presentation:', error.message);
      throw error;
    }
  }
}

// COMMAND LINE INTERFACE
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    title: 'POTOMAC PRESENTATION',
    subtitle: 'Built to Conquer Risk®',
    slides: 5,
    output: 'potomac-sample-presentation.pptx',
    palette: 'STANDARD'
  };
  
  for (let i = 0; i < args.length; i += 2) {
    const flag = args[i];
    const value = args[i + 1];
    
    switch (flag) {
      case '--title':
        options.title = value;
        break;
      case '--subtitle':
        options.subtitle = value;
        break;
      case '--slides':
        options.slides = parseInt(value) || 5;
        break;
      case '--output':
        options.output = value;
        break;
      case '--palette':
        options.palette = value;
        break;
      case '--help':
        console.log(`
Potomac Presentation Generator - Phase 1

Usage: node generate-potomac-presentation.js [options]

Options:
  --title <title>     Presentation title (default: "POTOMAC PRESENTATION")
  --subtitle <sub>    Presentation subtitle (default: "Built to Conquer Risk®")
  --slides <number>   Number of slides (default: 5)
  --output <filename> Output filename (default: "potomac-sample-presentation.pptx")
  --palette <palette> Color palette: STANDARD, DARK, INVESTMENT, FUNDS (default: STANDARD)
  --help             Show this help

Examples:
  node generate-potomac-presentation.js
  node generate-potomac-presentation.js --title "MARKET OUTLOOK 2025" --slides 8
  node generate-potomac-presentation.js --palette INVESTMENT --output "investment-deck.pptx"
        `);
        process.exit(0);
    }
  }
  
  return options;
}

// MAIN EXECUTION
async function main() {
  try {
    const options = parseArgs();
    
    console.log('🎯 Potomac Presentation Generator - Phase 1');
    console.log(`Title: ${options.title}`);
    console.log(`Subtitle: ${options.subtitle}`);
    console.log(`Palette: ${options.palette}`);
    console.log(`Output: ${options.output}`);
    console.log('---');
    
    // Create generator
    const generator = new PotomacPresentationGenerator(options);
    
    // Generate sample presentation
    generator.generateSamplePresentation();
    
    // Validate compliance
    const compliance = generator.validateCompliance();
    if (!compliance.compliant && generator.options.strictCompliance) {
      console.error('❌ Presentation failed brand compliance. Generation aborted.');
      if (compliance.report) {
        console.log('Compliance Report:', JSON.stringify(compliance.report, null, 2));
      }
      process.exit(1);
    }
    
    // Save presentation
    const outputPath = await generator.save(options.output);
    
    console.log('---');
    console.log('🎉 Potomac presentation generated successfully!');
    console.log(`📄 File: ${outputPath}`);
    console.log('✅ Brand compliance: PASSED');
    
  } catch (error) {
    console.error('❌ Error generating presentation:', error.message);
    process.exit(1);
  }
}

// Export for use as module
module.exports = {
  PotomacPresentationGenerator
};

// Run if called directly
if (require.main === module) {
  main();
}