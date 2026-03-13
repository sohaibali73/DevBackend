/**
 * Potomac Universal Slide Templates - Phase 2
 * Modular template system for all presentation types
 * 
 * This system provides comprehensive slide templates that can be combined
 * to create any type of Potomac presentation with perfect brand compliance.
 */

const { POTOMAC_COLORS, SLIDE_PALETTES } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS, TYPOGRAPHY_PRESETS } = require('../brand-assets/fonts/potomac-fonts.js');
const path = require('path');

class PotomacSlideTemplates {
  constructor(pptxGenerator, options = {}) {
    this.pptx = pptxGenerator;
    this.palette = SLIDE_PALETTES[options.palette || 'STANDARD'];
    this.logoPath = path.join(__dirname, '../brand-assets/logos/potomac-full-logo.png');
    
    // Template configuration
    this.config = {
      slideWidth: 10,
      slideHeight: 7.5,
      margins: {
        standard: 0.5,
        content: 0.75,
        title: 1.0
      },
      spacing: {
        lineHeight: 1.2,
        bulletSpacing: 36,
        paragraphSpacing: 24
      }
    };
  }

  // =======================
  // TITLE SLIDE TEMPLATES
  // =======================

  /**
   * Standard Title Slide
   * Full-screen branded title slide with logo and accent
   */
  createStandardTitleSlide(title, subtitle = null, options = {}) {
    const slide = this.pptx.addSlide();
    const config = { ...this.config, ...options };
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Logo (top right)
    this.addLogo(slide, {
      x: 8.5, y: 0.5, w: 1.3, h: 0.5
    });
    
    // Main title (large, centered)
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 2.5, w: 9, h: 1.5,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 44, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center', valign: 'middle', bold: true
    });
    
    // Subtitle (optional)
    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.5, y: 4.2, w: 9, h: 0.8,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 20,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center', valign: 'middle'
      });
    }
    
    // Accent bar
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0.5, y: 5.5, w: 9, h: 0.1,
      fill: { color: this.palette.accent }
    });
    
    return slide;
  }

  /**
   * Executive Title Slide
   * Premium dark background for high-impact presentations
   */
  createExecutiveTitleSlide(title, subtitle = null, tagline = 'Built to Conquer Risk®') {
    const slide = this.pptx.addSlide();
    
    // Dark background
    slide.background = { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY };
    
    // Logo (top right, white version)
    this.addLogo(slide, {
      x: 8.3, y: 0.4, w: 1.5, h: 0.6
    });
    
    // Main title (white text)
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 2.2, w: 9, h: 1.8,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 48, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.WHITE,
      align: 'center', valign: 'middle', bold: true
    });
    
    // Subtitle
    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.5, y: 4.2, w: 9, h: 0.7,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 22,
        color: POTOMAC_COLORS.TONES.YELLOW_80,
        align: 'center', valign: 'middle'
      });
    }
    
    // Tagline with accent
    slide.addText(tagline, {
      x: 0.5, y: 5.8, w: 9, h: 0.6,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 18,
      color: POTOMAC_COLORS.PRIMARY.YELLOW,
      align: 'center', valign: 'middle', italic: true
    });
    
    return slide;
  }

  /**
   * Section Divider Title
   * Clean divider slide for major sections
   */
  createSectionDividerSlide(sectionTitle, description = null) {
    const slide = this.pptx.addSlide();
    
    // Light background with subtle accent
    slide.background = { color: POTOMAC_COLORS.TONES.YELLOW_20 };
    
    // Small logo (top right)
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Section number or icon area (left accent)
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0, y: 0, w: 0.3, h: 7.5,
      fill: { color: this.palette.accent }
    });
    
    // Section title (large, left-aligned)
    slide.addText(sectionTitle.toUpperCase(), {
      x: 0.8, y: 2.5, w: 7.5, h: 1.5,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 42, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'left', valign: 'middle', bold: true
    });
    
    // Description (optional)
    if (description) {
      slide.addText(description, {
        x: 0.8, y: 4.2, w: 7.5, h: 1.2,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 18,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'left', valign: 'middle'
      });
    }
    
    return slide;
  }

  // =======================
  // CONTENT SLIDE TEMPLATES
  // =======================

  /**
   * Standard Content Slide
   * Basic content slide with bullet points
   */
  createContentSlide(title, content, options = {}) {
    const slide = this.pptx.addSlide();
    const showBullets = options.bullets !== false;
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Small logo (top right)
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Title
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 8, h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 36, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      bold: true
    });
    
    // Title underline
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0.5, y: 1.4, w: 2, h: 0.05,
      fill: { color: this.palette.accent }
    });
    
    // Content
    if (Array.isArray(content) && showBullets) {
      const bulletText = content.map(item => ({ text: item, options: { bullet: true } }));
      slide.addText(bulletText, {
        x: 0.5, y: 2.2, w: 9, h: 4.5,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 18,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        bullet: true, lineSpacing: this.config.spacing.bulletSpacing
      });
    } else {
      slide.addText(Array.isArray(content) ? content.join('\n') : content, {
        x: 0.5, y: 2.2, w: 9, h: 4.5,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 16,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        lineSpacing: this.config.spacing.paragraphSpacing
      });
    }
    
    return slide;
  }

  /**
   * Two-Column Layout
   * Side-by-side content presentation
   */
  createTwoColumnSlide(title, leftContent, rightContent, options = {}) {
    const slide = this.pptx.addSlide();
    const columnWidth = 4.3;
    const gapWidth = 0.4;
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Logo
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Title
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 8, h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 32, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      bold: true
    });
    
    // Title underline
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0.5, y: 1.4, w: 2, h: 0.05,
      fill: { color: this.palette.accent }
    });
    
    // Left column
    slide.addText(leftContent, {
      x: 0.5, y: 2.2, w: columnWidth, h: 4.5,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 16,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      lineSpacing: this.config.spacing.paragraphSpacing
    });
    
    // Right column  
    slide.addText(rightContent, {
      x: 0.5 + columnWidth + gapWidth, y: 2.2, w: columnWidth, h: 4.5,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 16,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      lineSpacing: this.config.spacing.paragraphSpacing
    });
    
    // Column separator (subtle)
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0.5 + columnWidth + (gapWidth/2) - 0.02, y: 2.2,
      w: 0.04, h: 4,
      fill: { color: POTOMAC_COLORS.TONES.GRAY_20 }
    });
    
    return slide;
  }

  /**
   * Three-Column Layout  
   * Triple column content for comparisons or categories
   */
  createThreeColumnSlide(title, leftContent, centerContent, rightContent) {
    const slide = this.pptx.addSlide();
    const columnWidth = 2.8;
    const gapWidth = 0.3;
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Logo
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Title
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 8, h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 30, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      bold: true
    });
    
    // Title underline
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0.5, y: 1.4, w: 2, h: 0.05,
      fill: { color: this.palette.accent }
    });
    
    // Three columns
    const columns = [leftContent, centerContent, rightContent];
    columns.forEach((content, index) => {
      const xPos = 0.5 + (columnWidth + gapWidth) * index;
      
      slide.addText(content, {
        x: xPos, y: 2.2, w: columnWidth, h: 4.5,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 14,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        lineSpacing: this.config.spacing.paragraphSpacing
      });
    });
    
    return slide;
  }

  // =======================
  // SPECIALIZED TEMPLATES
  // =======================

  /**
   * Quote/Testimonial Slide
   * Highlight important quotes or testimonials
   */
  createQuoteSlide(quote, attribution = null, context = null) {
    const slide = this.pptx.addSlide();
    
    // Light accent background
    slide.background = { color: POTOMAC_COLORS.TONES.YELLOW_20 };
    
    // Logo
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Large quotation mark
    slide.addText('"', {
      x: 0.5, y: 1.5, w: 1, h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 72, fontWeight: '700',
      color: this.palette.accent,
      align: 'center'
    });
    
    // Quote text (large, italic)
    slide.addText(quote, {
      x: 1.5, y: 2.2, w: 7, h: 2.5,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 22,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center', valign: 'middle',
      italic: true, lineSpacing: 32
    });
    
    // Attribution
    if (attribution) {
      slide.addText(`— ${attribution}`, {
        x: 1.5, y: 5.2, w: 7, h: 0.8,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 16,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center', fontWeight: '600'
      });
    }
    
    // Context (optional)
    if (context) {
      slide.addText(context, {
        x: 1.5, y: 6.0, w: 7, h: 0.6,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 12,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center'
      });
    }
    
    return slide;
  }

  /**
   * Key Metric/Statistic Slide
   * Highlight important numbers or statistics
   */
  createMetricSlide(title, metrics, context = null) {
    const slide = this.pptx.addSlide();
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Logo
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Title
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 8, h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 32, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      bold: true
    });
    
    // Title underline
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0.5, y: 1.4, w: 2, h: 0.05,
      fill: { color: this.palette.accent }
    });
    
    // Metrics (support array of metrics)
    if (Array.isArray(metrics)) {
      const metricsPerRow = Math.min(3, metrics.length);
      const metricWidth = 8.5 / metricsPerRow;
      
      metrics.forEach((metric, index) => {
        const row = Math.floor(index / metricsPerRow);
        const col = index % metricsPerRow;
        const xPos = 0.75 + col * metricWidth;
        const yPos = 2.5 + row * 1.8;
        
        // Metric value (large)
        slide.addText(metric.value, {
          x: xPos, y: yPos, w: metricWidth - 0.2, h: 1,
          fontFace: POTOMAC_FONTS.HEADERS.family,
          fontSize: 48, fontWeight: '700',
          color: this.palette.accent,
          align: 'center', bold: true
        });
        
        // Metric label
        slide.addText(metric.label, {
          x: xPos, y: yPos + 1, w: metricWidth - 0.2, h: 0.6,
          fontFace: POTOMAC_FONTS.BODY.family, fontSize: 14,
          color: POTOMAC_COLORS.TONES.GRAY_60,
          align: 'center'
        });
      });
    }
    
    // Context text (bottom)
    if (context) {
      slide.addText(context, {
        x: 0.5, y: 6.2, w: 9, h: 1,
        fontFace: POTOMAC_FONTS.BODY.family, fontSize: 14,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center', lineSpacing: 20
      });
    }
    
    return slide;
  }

  /**
   * Process/Timeline Slide
   * Show sequential steps or timeline
   */
  createProcessSlide(title, steps, options = {}) {
    const slide = this.pptx.addSlide();
    const horizontal = options.layout !== 'vertical';
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Logo
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Title
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 8, h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 30, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      bold: true
    });
    
    // Title underline
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 0.5, y: 1.4, w: 2, h: 0.05,
      fill: { color: this.palette.accent }
    });
    
    if (horizontal) {
      // Horizontal process flow
      const stepWidth = 8.5 / steps.length;
      
      steps.forEach((step, index) => {
        const xPos = 0.75 + index * stepWidth;
        const yPos = 2.8;
        
        // Step number circle
        slide.addShape(this.pptx.shapes.ELLIPSE, {
          x: xPos + (stepWidth/2) - 0.25, y: yPos - 0.25,
          w: 0.5, h: 0.5,
          fill: { color: this.palette.accent }
        });
        
        // Step number
        slide.addText((index + 1).toString(), {
          x: xPos + (stepWidth/2) - 0.25, y: yPos - 0.25,
          w: 0.5, h: 0.5,
          fontFace: POTOMAC_FONTS.HEADERS.family,
          fontSize: 18, fontWeight: '700',
          color: POTOMAC_COLORS.PRIMARY.WHITE,
          align: 'center', valign: 'middle'
        });
        
        // Step title
        slide.addText(step.title.toUpperCase(), {
          x: xPos, y: yPos + 0.5, w: stepWidth - 0.1, h: 0.7,
          fontFace: POTOMAC_FONTS.HEADERS.family,
          fontSize: 14, fontWeight: '600',
          color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
          align: 'center'
        });
        
        // Step description
        slide.addText(step.description, {
          x: xPos, y: yPos + 1.3, w: stepWidth - 0.1, h: 2,
          fontFace: POTOMAC_FONTS.BODY.family, fontSize: 12,
          color: POTOMAC_COLORS.TONES.GRAY_60,
          align: 'center', lineSpacing: 16
        });
        
        // Connecting arrow (except for last step)
        if (index < steps.length - 1) {
          slide.addShape(this.pptx.shapes.ARROW_RIGHT, {
            x: xPos + stepWidth - 0.3, y: yPos + 0.1,
            w: 0.4, h: 0.2,
            fill: { color: POTOMAC_COLORS.TONES.GRAY_40 }
          });
        }
      });
    }
    
    return slide;
  }

  // =======================
  // CLOSING SLIDE TEMPLATES
  // =======================

  /**
   * Standard Closing Slide
   * Thank you slide with contact information
   */
  createClosingSlide(title = 'THANK YOU', contactInfo = null) {
    const slide = this.pptx.addSlide();
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Large logo (centered)
    this.addLogo(slide, {
      x: 4.25, y: 1.5, w: 1.5, h: 0.6
    });
    
    // Main message
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 2.8, w: 9, h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 40, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center', bold: true
    });
    
    // Tagline
    slide.addText('Built to Conquer Risk®', {
      x: 0.5, y: 4, w: 9, h: 0.6,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 18,
      color: this.palette.accent,
      align: 'center', italic: true
    });
    
    // Contact information
    const defaultContact = 'potomac.com\n(305) 824-2702\ninfo@potomac.com';
    slide.addText(contactInfo || defaultContact, {
      x: 0.5, y: 5.5, w: 9, h: 1.5,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 14,
      color: POTOMAC_COLORS.TONES.GRAY_60,
      align: 'center', lineSpacing: 20
    });
    
    return slide;
  }

  /**
   * Call-to-Action Slide
   * Closing slide with specific action request
   */
  createCallToActionSlide(title, actionText, contactInfo, buttonText = 'GET STARTED') {
    const slide = this.pptx.addSlide();
    
    // Background
    slide.background = { color: this.palette.background };
    
    // Logo
    this.addLogo(slide, {
      x: 8.8, y: 0.3, w: 1, h: 0.4
    });
    
    // Title
    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 1.5, w: 9, h: 1.2,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 36, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center', bold: true
    });
    
    // Action text
    slide.addText(actionText, {
      x: 0.5, y: 3, w: 9, h: 1.5,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 18,
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center', lineSpacing: 28
    });
    
    // Call-to-action button
    slide.addShape(this.pptx.shapes.RECTANGLE, {
      x: 3.5, y: 4.8, w: 3, h: 0.8,
      fill: { color: this.palette.accent },
      line: { color: this.palette.accent, width: 2 }
    });
    
    slide.addText(buttonText.toUpperCase(), {
      x: 3.5, y: 4.8, w: 3, h: 0.8,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 16, fontWeight: '700',
      color: POTOMAC_COLORS.PRIMARY.WHITE,
      align: 'center', valign: 'middle'
    });
    
    // Contact info
    slide.addText(contactInfo, {
      x: 0.5, y: 6, w: 9, h: 1,
      fontFace: POTOMAC_FONTS.BODY.family, fontSize: 14,
      color: POTOMAC_COLORS.TONES.GRAY_60,
      align: 'center', lineSpacing: 18
    });
    
    return slide;
  }

  // =======================
  // UTILITY METHODS
  // =======================

  addLogo(slide, position) {
    // Use the full logo by default
    const fs = require('fs');
    
    if (fs.existsSync(this.logoPath)) {
      slide.addImage({
        path: this.logoPath,
        x: position.x, y: position.y,
        w: position.w, h: position.h
      });
    } else {
      // Fallback text logo
      slide.addText('POTOMAC', {
        x: position.x, y: position.y,
        w: position.w, h: position.h,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 16, fontWeight: '700',
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center', valign: 'middle', bold: true
      });
    }
  }

  // Template metadata for smart selection
  getTemplateMetadata() {
    return {
      title: [
        { name: 'Standard Title', method: 'createStandardTitleSlide', use: 'General presentations' },
        { name: 'Executive Title', method: 'createExecutiveTitleSlide', use: 'High-impact executive presentations' },
        { name: 'Section Divider', method: 'createSectionDividerSlide', use: 'Major section breaks' }
      ],
      content: [
        { name: 'Standard Content', method: 'createContentSlide', use: 'Basic content with bullets' },
        { name: 'Two Column', method: 'createTwoColumnSlide', use: 'Comparisons, before/after' },
        { name: 'Three Column', method: 'createThreeColumnSlide', use: 'Category comparisons' },
        { name: 'Quote', method: 'createQuoteSlide', use: 'Testimonials, important quotes' },
        { name: 'Metrics', method: 'createMetricSlide', use: 'Key statistics, performance data' },
        { name: 'Process', method: 'createProcessSlide', use: 'Step-by-step workflows' }
      ],
      closing: [
        { name: 'Standard Closing', method: 'createClosingSlide', use: 'Thank you with contact info' },
        { name: 'Call to Action', method: 'createCallToActionSlide', use: 'Specific next steps' }
      ]
    };
  }
}

module.exports = {
  PotomacSlideTemplates
};