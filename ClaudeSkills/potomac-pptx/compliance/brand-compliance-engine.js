/**
 * Potomac Brand Compliance Engine
 * Zero-Tolerance Brand Enforcement System
 * 
 * This engine ensures 100% brand compliance for all Potomac presentations
 * Any violations will be automatically corrected or generation will be halted
 */

const { POTOMAC_COLORS, COLOR_RULES, validateColor } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS, validateFont, enforceHeaderFormatting, enforceBodyFormatting } = require('../brand-assets/fonts/potomac-fonts.js');

class PotomacBrandComplianceEngine {
  constructor(strictMode = true) {
    this.strictMode = strictMode;
    this.violations = [];
    this.corrections = [];
    this.score = 100;
    
    // Restricted terminology patterns
    this.FORBIDDEN_TERMS = [
      /potomac fund management/gi,
      /potomac fund(?!\s+funds)/gi,  // "Potomac Fund" but not "Potomac Fund Funds"
      /lorem ipsum/gi,
      /xxxx/gi,
      /placeholder/gi,
      /sample text/gi
    ];
    
    // Required company terminology
    this.REQUIRED_CORRECTIONS = {
      'potomac fund management': 'Potomac',
      'potomac fund': 'Potomac',
      'POTOMAC FUND MANAGEMENT': 'POTOMAC',
      'POTOMAC FUND': 'POTOMAC'
    };
  }

  // MAIN COMPLIANCE VALIDATION
  validatePresentation(presentationData) {
    this.violations = [];
    this.corrections = [];
    this.score = 100;
    
    console.log('🛡️ Potomac Brand Compliance Engine - Starting Validation...');
    
    // 1. Validate overall presentation structure
    this.validatePresentationStructure(presentationData);
    
    // 2. Validate each slide
    if (presentationData.slides && Array.isArray(presentationData.slides)) {
      presentationData.slides.forEach((slide, index) => {
        this.validateSlide(slide, index + 1);
      });
    }
    
    // 3. Generate compliance report
    const report = this.generateComplianceReport();
    
    // 4. Enforce strict mode requirements
    if (this.strictMode && this.violations.length > 0) {
      throw new Error(`BRAND COMPLIANCE FAILURE: ${this.violations.length} violations detected. Presentation generation halted. See compliance report for details.`);
    }
    
    return report;
  }

  // PRESENTATION STRUCTURE VALIDATION
  validatePresentationStructure(presentationData) {
    // Validate company name usage
    if (presentationData.title) {
      this.validateCompanyTerminology(presentationData.title, 'Presentation Title');
    }
    
    // Validate tagline usage
    if (presentationData.tagline) {
      this.validateTaglineUsage(presentationData.tagline);
    }
    
    // Ensure proper metadata
    if (!presentationData.company || presentationData.company !== 'Potomac') {
      this.addViolation('COMPANY_NAME', 'Presentation company must be set to "Potomac"', 'Structure');
      if (this.strictMode) {
        presentationData.company = 'Potomac';
        this.addCorrection('Auto-corrected company name to "Potomac"');
      }
    }
  }

  // INDIVIDUAL SLIDE VALIDATION
  validateSlide(slide, slideNumber) {
    console.log(`🔍 Validating Slide ${slideNumber}...`);
    
    // 1. Validate slide colors
    this.validateSlideColors(slide, slideNumber);
    
    // 2. Validate typography
    this.validateSlideTypography(slide, slideNumber);
    
    // 3. Validate content compliance
    this.validateSlideContent(slide, slideNumber);
    
    // 4. Validate layout and spacing
    this.validateSlideLayout(slide, slideNumber);
    
    // 5. Validate logo usage (if present)
    if (slide.logo) {
      this.validateLogoUsage(slide.logo, slideNumber);
    }
  }

  // COLOR VALIDATION
  validateSlideColors(slide, slideNumber) {
    const context = this.determineSlideContext(slide);
    
    // Check background color
    if (slide.backgroundColor) {
      try {
        validateColor(slide.backgroundColor, context);
      } catch (error) {
        this.addViolation('COLOR_VIOLATION', error.message, `Slide ${slideNumber}`);
        if (this.strictMode) {
          slide.backgroundColor = POTOMAC_COLORS.PRIMARY.WHITE;
          this.addCorrection(`Slide ${slideNumber}: Corrected background to brand white`);
        }
      }
    }
    
    // Check element colors
    if (slide.elements && Array.isArray(slide.elements)) {
      slide.elements.forEach((element, elementIndex) => {
        if (element.color) {
          try {
            validateColor(element.color, context);
          } catch (error) {
            this.addViolation('COLOR_VIOLATION', 
              `Element ${elementIndex + 1}: ${error.message}`, 
              `Slide ${slideNumber}`);
            if (this.strictMode) {
              element.color = this.getAppropriateColor(element.type, context);
              this.addCorrection(`Slide ${slideNumber}, Element ${elementIndex + 1}: Corrected to brand color`);
            }
          }
        }
      });
    }
  }

  // TYPOGRAPHY VALIDATION
  validateSlideTypography(slide, slideNumber) {
    const context = this.determineSlideContext(slide);
    
    // Validate slide title typography
    if (slide.title) {
      this.validateTextElement({
        text: slide.title,
        type: 'header',
        fontFamily: slide.titleFont || 'auto-detect',
        fontSize: slide.titleSize
      }, slideNumber, 'Title');
    }
    
    // Validate text elements
    if (slide.elements) {
      slide.elements.forEach((element, elementIndex) => {
        if (element.type === 'text') {
          this.validateTextElement(element, slideNumber, `Element ${elementIndex + 1}`);
        }
      });
    }
  }

  validateTextElement(element, slideNumber, elementDescription) {
    // Determine if this should be header or body text
    const isHeader = element.type === 'header' || 
                    element.role === 'title' || 
                    element.fontSize > 20 ||
                    element.text === element.text.toUpperCase();

    const expectedFont = isHeader ? POTOMAC_FONTS.HEADERS.family : POTOMAC_FONTS.BODY.family;
    
    // Check font compliance
    if (element.fontFamily && element.fontFamily !== 'auto-detect') {
      try {
        const context = element.context || 'general';
        const elementType = isHeader ? 'header' : 'body';
        validateFont(element.fontFamily, context, elementType);
      } catch (error) {
        this.addViolation('TYPOGRAPHY_VIOLATION', 
          `${elementDescription}: ${error.message}`, 
          `Slide ${slideNumber}`);
        if (this.strictMode) {
          element.fontFamily = expectedFont;
          if (isHeader) {
            element.textTransform = 'uppercase';
          }
          this.addCorrection(`Slide ${slideNumber}, ${elementDescription}: Corrected font to ${expectedFont}`);
        }
      }
    }
    
    // Enforce ALL CAPS for headers
    if (isHeader && element.text !== element.text.toUpperCase()) {
      this.addViolation('HEADER_CASE_VIOLATION', 
        `${elementDescription}: Headers must be ALL CAPS. Found: "${element.text}"`, 
        `Slide ${slideNumber}`);
      if (this.strictMode) {
        element.text = element.text.toUpperCase();
        element.textTransform = 'uppercase';
        this.addCorrection(`Slide ${slideNumber}, ${elementDescription}: Converted to ALL CAPS`);
      }
    }
  }

  // CONTENT VALIDATION
  validateSlideContent(slide, slideNumber) {
    const allText = this.extractAllTextFromSlide(slide);
    
    // Check for forbidden terminology
    this.FORBIDDEN_TERMS.forEach(pattern => {
      if (pattern.test(allText)) {
        const matches = allText.match(pattern);
        matches.forEach(match => {
          this.addViolation('TERMINOLOGY_VIOLATION', 
            `Forbidden term found: "${match}"`, 
            `Slide ${slideNumber}`);
          
          if (this.strictMode) {
            // Apply corrections to all text elements
            this.correctTerminologyInSlide(slide, match);
            this.addCorrection(`Slide ${slideNumber}: Corrected forbidden terminology`);
          }
        });
      }
    });
    
    // Validate tagline usage
    const taglineRegex = /__disabled_tagline__/gi;
    const taglineMatches = null;
    if (taglineMatches) {
      taglineMatches.forEach(match => {
        if (!match.includes('®')) {
          this.addViolation('TAGLINE_VIOLATION', 
            `Tagline missing ® symbol: "${match}"`, 
            `Slide ${slideNumber}`);
          if (this.strictMode) {
            this.correctTaglineInSlide(slide);
            this.addCorrection(`Slide ${slideNumber}: Added ® symbol to tagline`);
          }
        }
      });
    }
  }

  // LAYOUT VALIDATION
  validateSlideLayout(slide, slideNumber) {
    // Check for minimum margins
    const MIN_MARGIN = 0.5; // inches
    
    if (slide.elements) {
      slide.elements.forEach((element, elementIndex) => {
        // Check if elements are too close to edges
        if (element.x < MIN_MARGIN || element.y < MIN_MARGIN) {
          this.addViolation('LAYOUT_VIOLATION', 
            `Element ${elementIndex + 1} too close to slide edge. Minimum margin: ${MIN_MARGIN}\"`, 
            `Slide ${slideNumber}`);
        }
        
        // Check for overlapping elements (simplified check)
        if (element.width && element.height) {
          const elementRight = element.x + element.width;
          const elementBottom = element.y + element.height;
          
          // Check against slide boundaries (assuming 13.333" x 7.5" widescreen slide)
          if (elementRight > 13.333 - MIN_MARGIN || elementBottom > 7.5 - MIN_MARGIN) {
            this.addViolation('LAYOUT_VIOLATION', 
              `Element ${elementIndex + 1} extends beyond safe margins`, 
              `Slide ${slideNumber}`);
          }
        }
      });
    }
  }

  // LOGO VALIDATION
  validateLogoUsage(logo, slideNumber) {
    // Check logo file path/name for approved versions
    const approvedLogoFiles = [
      'potomac-full-logo.png',
      'potomac-icon-yellow.png', 
      'potomac-icon-black.png'
    ];
    
    if (logo.src && !approvedLogoFiles.some(approved => logo.src.includes(approved))) {
      this.addViolation('LOGO_VIOLATION', 
        `Unapproved logo file: ${logo.src}. Use only approved Potomac logo variants.`, 
        `Slide ${slideNumber}`);
    }
    
    // Check minimum size requirements
    if (logo.width && logo.width < 1.38) { // 35mm = ~1.38 inches
      this.addViolation('LOGO_VIOLATION', 
        `Logo too small. Minimum wordmark width: 35mm (1.38\")`, 
        `Slide ${slideNumber}`);
    }
    
    // Check for prohibited modifications
    if (logo.rotation && logo.rotation !== 0) {
      this.addViolation('LOGO_VIOLATION', 
        `Logo rotation prohibited. Logos must not be rotated.`, 
        `Slide ${slideNumber}`);
    }
  }

  // UTILITY FUNCTIONS
  determineSlideContext(slide) {
    const allText = this.extractAllTextFromSlide(slide).toLowerCase();
    
    if (allText.includes('investment strategies') || allText.includes('potomac funds')) {
      return 'investment_strategies';
    }
    
    return 'general';
  }

  extractAllTextFromSlide(slide) {
    let allText = '';
    
    if (slide.title) allText += slide.title + ' ';
    if (slide.subtitle) allText += slide.subtitle + ' ';
    
    if (slide.elements) {
      slide.elements.forEach(element => {
        if (element.text) allText += element.text + ' ';
        if (element.content) allText += element.content + ' ';
      });
    }
    
    return allText;
  }

  correctTerminologyInSlide(slide, incorrectTerm) {
    const correction = this.REQUIRED_CORRECTIONS[incorrectTerm.toLowerCase()] || 'Potomac';
    
    if (slide.title) slide.title = slide.title.replace(new RegExp(incorrectTerm, 'gi'), correction);
    if (slide.subtitle) slide.subtitle = slide.subtitle.replace(new RegExp(incorrectTerm, 'gi'), correction);
    
    if (slide.elements) {
      slide.elements.forEach(element => {
        if (element.text) element.text = element.text.replace(new RegExp(incorrectTerm, 'gi'), correction);
        if (element.content) element.content = element.content.replace(new RegExp(incorrectTerm, 'gi'), correction);
      });
    }
  }

  correctTaglineInSlide(slide) {
    const taglineRegex = /(built to conquer risk)(?!®)/gi;
    const correctedTagline = 'Built to Conquer Risk®';
    
    if (slide.title) slide.title = slide.title.replace(taglineRegex, correctedTagline);
    if (slide.subtitle) slide.subtitle = slide.subtitle.replace(taglineRegex, correctedTagline);
    
    if (slide.elements) {
      slide.elements.forEach(element => {
        if (element.text) element.text = element.text.replace(taglineRegex, correctedTagline);
        if (element.content) element.content = element.content.replace(taglineRegex, correctedTagline);
      });
    }
  }

  getAppropriateColor(elementType, context) {
    switch (elementType) {
      case 'header':
      case 'title':
        return POTOMAC_COLORS.PRIMARY.DARK_GRAY;
      case 'accent':
        return context === 'investment_strategies' 
          ? POTOMAC_COLORS.SECONDARY.TURQUOISE 
          : POTOMAC_COLORS.PRIMARY.YELLOW;
      default:
        return POTOMAC_COLORS.PRIMARY.DARK_GRAY;
    }
  }

  validateCompanyTerminology(text, location) {
    // Check for forbidden company name variations
    this.FORBIDDEN_TERMS.forEach(pattern => {
      if (pattern.test(text)) {
        const matches = text.match(pattern);
        matches.forEach(match => {
          this.addViolation('TERMINOLOGY_VIOLATION', 
            `Forbidden term found: "${match}" in ${location}`, 
            location);
        });
      }
    });
  }

  validateTaglineUsage(tagline) {
    // Tagline validation disabled — no enforced tagline.
    if (false) {
      this.addViolation('TAGLINE_VIOLATION', '', 'Presentation Structure');
    }
  }

  // VIOLATION TRACKING
  addViolation(type, message, location) {
    this.violations.push({
      type,
      message,
      location,
      timestamp: new Date().toISOString(),
      severity: 'HIGH'
    });
    this.score -= 5; // Deduct points for each violation
  }

  addCorrection(message) {
    this.corrections.push({
      message,
      timestamp: new Date().toISOString()
    });
  }

  // COMPLIANCE REPORTING
  generateComplianceReport() {
    const report = {
      overallScore: Math.max(0, this.score),
      complianceStatus: this.violations.length === 0 ? 'COMPLIANT' : 'VIOLATIONS_DETECTED',
      totalViolations: this.violations.length,
      totalCorrections: this.corrections.length,
      strictMode: this.strictMode,
      
      summary: {
        colorViolations: this.violations.filter(v => v.type === 'COLOR_VIOLATION').length,
        typographyViolations: this.violations.filter(v => v.type === 'TYPOGRAPHY_VIOLATION').length,
        terminologyViolations: this.violations.filter(v => v.type === 'TERMINOLOGY_VIOLATION').length,
        logoViolations: this.violations.filter(v => v.type === 'LOGO_VIOLATION').length,
        layoutViolations: this.violations.filter(v => v.type === 'LAYOUT_VIOLATION').length,
      },
      
      violations: this.violations,
      corrections: this.corrections,
      
      recommendation: this.getRecommendation()
    };
    
    console.log('📊 Brand Compliance Report Generated');
    console.log(`Overall Score: ${report.overallScore}/100`);
    console.log(`Status: ${report.complianceStatus}`);
    console.log(`Violations: ${report.totalViolations}, Corrections: ${report.totalCorrections}`);
    
    return report;
  }

  getRecommendation() {
    if (this.violations.length === 0) {
      return 'APPROVED: Presentation meets all Potomac brand standards.';
    } else if (this.strictMode && this.corrections.length > 0) {
      return 'CORRECTED: All violations automatically fixed. Presentation now compliant.';
    } else {
      return 'REVIEW REQUIRED: Manual corrections needed before approval.';
    }
  }
}

// STANDALONE VALIDATION FUNCTIONS
function quickComplianceCheck(presentationData) {
  const engine = new PotomacBrandComplianceEngine(false);
  return engine.validatePresentation(presentationData);
}

function strictComplianceEnforcement(presentationData) {
  const engine = new PotomacBrandComplianceEngine(true);
  return engine.validatePresentation(presentationData);
}

// EXPORT
module.exports = {
  PotomacBrandComplianceEngine,
  quickComplianceCheck,
  strictComplianceEnforcement
};

// Browser/Client-side export
if (typeof window !== 'undefined') {
  window.PotomacCompliance = {
    PotomacBrandComplianceEngine,
    quickComplianceCheck,
    strictComplianceEnforcement
  };
}