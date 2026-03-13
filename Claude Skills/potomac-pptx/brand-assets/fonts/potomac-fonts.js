/**
 * Potomac Typography Standards - Strict Enforcement
 * Based on Potomac Communication Style Guide
 * 
 * CRITICAL: These are the ONLY approved fonts for Potomac presentations
 * Headers MUST use Rajdhani in ALL CAPS
 * Body text MUST use Quicksand
 */

const POTOMAC_FONTS = {
  // PRIMARY HEADER FONT (Rajdhani - Google Fonts)
  HEADERS: {
    family: 'Rajdhani',
    weights: ['300', '400', '500', '600', '700'],  // Light, Regular, Medium, SemiBold, Bold
    googleFontsUrl: 'https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700&display=swap',
    
    // MANDATORY FORMATTING
    transform: 'uppercase',     // ALWAYS ALL CAPS - NO EXCEPTIONS
    defaultWeight: '700',       // Bold is standard
    
    // Size Guidelines
    sizes: {
      slideTitle: '44pt',       // Main slide titles
      sectionHeader: '24pt',    // Section headers
      subHeader: '20pt',        // Sub-headers
      smallHeader: '18pt'       // Small headers/labels
    },
    
    // Usage Rules
    usage: {
      required: 'ALL slide titles and headers',
      forbidden: 'Body text, captions, fine print',
      transform: 'UPPERCASE ONLY - never sentence case'
    }
  },

  // PRIMARY BODY FONT (Quicksand - Google Fonts)
  BODY: {
    family: 'Quicksand',
    weights: ['300', '400', '500', '600', '700'],  // Light, Regular, Medium, SemiBold, Bold
    googleFontsUrl: 'https://fonts.googleapis.com/css2?family=Quicksand:wght@300;400;500;600;700&display=swap',
    
    defaultWeight: '400',       // Regular is standard
    
    // Size Guidelines
    sizes: {
      bodyText: '16pt',         // Standard body text
      smallText: '14pt',        // Small body text
      captions: '12pt',         // Captions and fine print
      footnotes: '10pt'         // Footnotes and disclaimers
    },
    
    // Usage Rules
    usage: {
      required: 'All body text, bullets, captions',
      forbidden: 'Headers, slide titles',
      casing: 'Sentence case or normal capitalization'
    }
  },

  // FUNDS-ONLY FONT (Lexend Deca - Google Fonts)
  FUNDS_ONLY: {
    family: 'Lexend Deca',
    weights: ['100', '200', '300', '400', '500', '600', '700', '800', '900'],
    googleFontsUrl: 'https://fonts.googleapis.com/css2?family=Lexend+Deca:wght@100;200;300;400;500;600;700;800;900&display=swap',
    
    // RESTRICTED USAGE
    restriction: 'POTOMAC FUNDS CONTENT ONLY',
    usage: {
      allowedFor: 'Potomac Funds materials exclusively',
      forbidden: 'General Potomac content, other business lines'
    }
  }
};

// FONT VALIDATION FUNCTIONS
function validateFont(fontFamily, context = 'general', elementType = 'body') {
  const upperFont = fontFamily.toLowerCase();
  
  // Check if using Funds font inappropriately
  if (upperFont.includes('lexend') && context !== 'potomac_funds') {
    throw new Error(`BRAND VIOLATION: Lexend Deca is restricted to Potomac Funds content only.`);
  }
  
  // Check header font compliance
  if (elementType === 'header' && !upperFont.includes('rajdhani')) {
    throw new Error(`BRAND VIOLATION: Headers must use Rajdhani font. Found: ${fontFamily}`);
  }
  
  // Check body font compliance  
  if (elementType === 'body' && !upperFont.includes('quicksand') && !upperFont.includes('lexend')) {
    throw new Error(`BRAND VIOLATION: Body text must use Quicksand font. Found: ${fontFamily}`);
  }
  
  return true;
}

function enforceHeaderFormatting(textElement) {
  // Automatically apply header formatting
  if (textElement.type === 'header' || textElement.role === 'title') {
    return {
      ...textElement,
      fontFamily: POTOMAC_FONTS.HEADERS.family,
      fontWeight: POTOMAC_FONTS.HEADERS.defaultWeight,
      textTransform: 'uppercase',
      fontSize: textElement.fontSize || POTOMAC_FONTS.HEADERS.sizes.slideTitle
    };
  }
  return textElement;
}

function enforceBodyFormatting(textElement) {
  // Automatically apply body formatting
  if (textElement.type === 'body' || textElement.role === 'content') {
    return {
      ...textElement,
      fontFamily: POTOMAC_FONTS.BODY.family,
      fontWeight: textElement.fontWeight || POTOMAC_FONTS.BODY.defaultWeight,
      fontSize: textElement.fontSize || POTOMAC_FONTS.BODY.sizes.bodyText
    };
  }
  return textElement;
}

// FONT LOADING FOR PRESENTATIONS
const FONT_IMPORTS = {
  // CSS import for web-based presentations
  css: `
    @import url('${POTOMAC_FONTS.HEADERS.googleFontsUrl}');
    @import url('${POTOMAC_FONTS.BODY.googleFontsUrl}');
    @import url('${POTOMAC_FONTS.FUNDS_ONLY.googleFontsUrl}');
  `,
  
  // HTML head links
  html: [
    `<link href="${POTOMAC_FONTS.HEADERS.googleFontsUrl}" rel="stylesheet">`,
    `<link href="${POTOMAC_FONTS.BODY.googleFontsUrl}" rel="stylesheet">`,
    `<link href="${POTOMAC_FONTS.FUNDS_ONLY.googleFontsUrl}" rel="stylesheet">`
  ],
  
  // PowerPoint font names (fallback to system fonts if web fonts not available)
  powerpoint: {
    headers: ['Rajdhani', 'Arial Black', 'Impact', 'Arial'],
    body: ['Quicksand', 'Calibri', 'Arial', 'sans-serif'],
    funds: ['Lexend Deca', 'Calibri', 'Arial', 'sans-serif']
  }
};

// TYPOGRAPHY PRESETS
const TYPOGRAPHY_PRESETS = {
  // Standard slide title
  SLIDE_TITLE: {
    fontFamily: POTOMAC_FONTS.HEADERS.family,
    fontSize: POTOMAC_FONTS.HEADERS.sizes.slideTitle,
    fontWeight: '700',
    textTransform: 'uppercase',
    color: '#212121'  // Potomac Dark Gray
  },
  
  // Section header
  SECTION_HEADER: {
    fontFamily: POTOMAC_FONTS.HEADERS.family,
    fontSize: POTOMAC_FONTS.HEADERS.sizes.sectionHeader,
    fontWeight: '600',
    textTransform: 'uppercase',
    color: '#212121'
  },
  
  // Standard body text
  BODY_TEXT: {
    fontFamily: POTOMAC_FONTS.BODY.family,
    fontSize: POTOMAC_FONTS.BODY.sizes.bodyText,
    fontWeight: '400',
    color: '#212121'
  },
  
  // Caption text
  CAPTION: {
    fontFamily: POTOMAC_FONTS.BODY.family,
    fontSize: POTOMAC_FONTS.BODY.sizes.captions,
    fontWeight: '300',
    color: '#737373'  // Gray 60%
  },
  
  // Funds content (when appropriate)
  FUNDS_HEADER: {
    fontFamily: POTOMAC_FONTS.FUNDS_ONLY.family,
    fontSize: '36pt',
    fontWeight: '600',
    color: '#00DED1'  // Turquoise
  }
};

// EXPORT FOR USE IN PRESENTATION GENERATION
module.exports = {
  POTOMAC_FONTS,
  FONT_IMPORTS,
  TYPOGRAPHY_PRESETS,
  validateFont,
  enforceHeaderFormatting,
  enforceBodyFormatting
};

// Browser/Client-side export
if (typeof window !== 'undefined') {
  window.PotomacFonts = {
    POTOMAC_FONTS,
    FONT_IMPORTS,
    TYPOGRAPHY_PRESETS,
    validateFont,
    enforceHeaderFormatting,
    enforceBodyFormatting
  };
}