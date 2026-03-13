/**
 * Potomac Brand Colors - Strict Enforcement
 * Based on Potomac Communication Style Guide
 * 
 * CRITICAL: These are the ONLY approved colors for Potomac presentations
 * Any deviation will trigger brand compliance violations
 */

const POTOMAC_COLORS = {
  // PRIMARY BRAND COLORS (Always Available)
  PRIMARY: {
    YELLOW: '#FEC00F',        // Potomac Yellow - PRIMARY brand color
    DARK_GRAY: '#212121',     // Potomac Dark Gray - Headers ONLY, never body text
    WHITE: '#FFFFFF',         // White backgrounds and contrast text
  },

  // SECONDARY COLORS (Restricted Usage)
  SECONDARY: {
    TURQUOISE: '#00DED1',     // ONLY for Investment Strategies & Potomac Funds
    PINK: '#EB2F5C',          // Accent color - use sparingly
  },

  // TONAL VARIATIONS (Auto-calculated)
  TONES: {
    // Yellow Variations
    YELLOW_100: '#FEC00F',    // 100% - Primary
    YELLOW_80: '#FEC542',     // 80% opacity
    YELLOW_60: '#FECA75',     // 60% opacity  
    YELLOW_40: '#FECFA8',     // 40% opacity
    YELLOW_20: '#FED4DA',     // 20% opacity

    // Gray Variations
    GRAY_100: '#212121',      // 100% - Primary
    GRAY_80: '#4A4A4A',       // 80% opacity
    GRAY_60: '#737373',       // 60% opacity
    GRAY_40: '#9D9D9D',       // 40% opacity
    GRAY_20: '#C6C6C6',       // 20% opacity
  }
};

// COLOR USAGE RULES
const COLOR_RULES = {
  // Primary Usage - Always Allowed
  ALWAYS_ALLOWED: [
    POTOMAC_COLORS.PRIMARY.YELLOW,
    POTOMAC_COLORS.PRIMARY.DARK_GRAY,
    POTOMAC_COLORS.PRIMARY.WHITE,
    ...Object.values(POTOMAC_COLORS.TONES)
  ],

  // Restricted Usage - Conditional
  INVESTMENT_STRATEGIES_ONLY: [
    POTOMAC_COLORS.SECONDARY.TURQUOISE
  ],

  ACCENT_ONLY: [
    POTOMAC_COLORS.SECONDARY.PINK
  ],

  // Forbidden Colors (Will trigger violations)
  FORBIDDEN: [
    '#0000FF',    // Generic blue
    '#FF0000',    // Generic red  
    '#00FF00',    // Generic green
    '#800080',    // Generic purple
    '#FFA500',    // Generic orange
    // Add more as needed
  ]
};

// COLOR VALIDATION FUNCTIONS
function validateColor(color, context = 'general') {
  const upperColor = color.toUpperCase();
  
  // Check if color is forbidden
  if (COLOR_RULES.FORBIDDEN.includes(upperColor)) {
    throw new Error(`BRAND VIOLATION: Color ${color} is forbidden. Use Potomac brand colors only.`);
  }

  // Check if color is always allowed
  if (COLOR_RULES.ALWAYS_ALLOWED.includes(upperColor)) {
    return true;
  }

  // Check context-specific restrictions
  if (context === 'investment_strategies' && COLOR_RULES.INVESTMENT_STRATEGIES_ONLY.includes(upperColor)) {
    return true;
  }

  if (context === 'accent' && COLOR_RULES.ACCENT_ONLY.includes(upperColor)) {
    return true;
  }

  // Color not found in approved lists
  throw new Error(`BRAND VIOLATION: Color ${color} not approved for context '${context}'. Use approved Potomac colors only.`);
}

function getApprovedColors(context = 'general') {
  let approved = [...COLOR_RULES.ALWAYS_ALLOWED];
  
  if (context === 'investment_strategies') {
    approved = approved.concat(COLOR_RULES.INVESTMENT_STRATEGIES_ONLY);
  }
  
  if (context === 'accent') {
    approved = approved.concat(COLOR_RULES.ACCENT_ONLY);
  }
  
  return approved;
}

function getNearestBrandColor(inputColor) {
  // Convert RGB to hex if needed and find closest brand color
  // This is a simplified version - could be enhanced with proper color distance calculation
  const brandColors = COLOR_RULES.ALWAYS_ALLOWED;
  
  // For now, default to primary yellow for non-compliant colors
  return POTOMAC_COLORS.PRIMARY.YELLOW;
}

// COLOR PALETTE DEFINITIONS
const SLIDE_PALETTES = {
  // Standard Presentation Palette
  STANDARD: {
    background: POTOMAC_COLORS.PRIMARY.WHITE,
    accent: POTOMAC_COLORS.PRIMARY.YELLOW,
    text: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
    supporting: POTOMAC_COLORS.TONES.GRAY_60
  },

  // Dark/Premium Palette
  DARK: {
    background: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
    accent: POTOMAC_COLORS.PRIMARY.YELLOW,
    text: POTOMAC_COLORS.PRIMARY.WHITE,
    supporting: POTOMAC_COLORS.TONES.YELLOW_60
  },

  // Investment Strategies Palette (Turquoise Allowed)
  INVESTMENT: {
    background: POTOMAC_COLORS.PRIMARY.WHITE,
    accent: POTOMAC_COLORS.SECONDARY.TURQUOISE,
    text: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
    supporting: POTOMAC_COLORS.PRIMARY.YELLOW
  },

  // Funds Palette (Turquoise Primary)
  FUNDS: {
    background: POTOMAC_COLORS.PRIMARY.WHITE,
    accent: POTOMAC_COLORS.SECONDARY.TURQUOISE,
    text: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
    supporting: POTOMAC_COLORS.TONES.GRAY_40
  }
};

// EXPORT FOR USE IN PRESENTATION GENERATION
module.exports = {
  POTOMAC_COLORS,
  COLOR_RULES,
  SLIDE_PALETTES,
  validateColor,
  getApprovedColors,
  getNearestBrandColor
};

// Browser/Client-side export
if (typeof window !== 'undefined') {
  window.PotomacColors = {
    POTOMAC_COLORS,
    COLOR_RULES,
    SLIDE_PALETTES,
    validateColor,
    getApprovedColors,
    getNearestBrandColor
  };
}