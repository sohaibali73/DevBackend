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
    // Yellow Variations (tints of #FEC00F blended toward white)
    YELLOW_100: '#FEC00F',    // 100% - Primary
    YELLOW_80: '#FECD3F',     // 80% tint (20% white blend)
    YELLOW_60: '#FED96F',     // 60% tint (40% white blend)
    YELLOW_40: '#FFE69F',     // 40% tint (60% white blend)
    YELLOW_20: '#FFF2CF',     // 20% tint (80% white blend) — was incorrectly #FED4DA (pink!)

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
  // Normalize: always compare WITH '#' prefix (some callers strip it via _c(), others don't)
  const raw = String(color).toUpperCase().replace('#', '');
  const normalized = '#' + raw;

  // Check if color is forbidden
  if (COLOR_RULES.FORBIDDEN.some(c => c.toUpperCase() === normalized)) {
    throw new Error(`BRAND VIOLATION: Color ${color} is forbidden. Use Potomac brand colors only.`);
  }

  // Check if color is always allowed
  if (COLOR_RULES.ALWAYS_ALLOWED.some(c => c.toUpperCase() === normalized)) {
    return true;
  }

  // Check context-specific restrictions
  if (context === 'investment_strategies' &&
      COLOR_RULES.INVESTMENT_STRATEGIES_ONLY.some(c => c.toUpperCase() === normalized)) {
    return true;
  }

  if (context === 'accent' &&
      COLOR_RULES.ACCENT_ONLY.some(c => c.toUpperCase() === normalized)) {
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
  // Parse a 6-digit hex string (with or without '#') into {r,g,b}
  function hexToRgb(hex) {
    const h = String(hex).replace('#', '');
    if (h.length !== 6) return { r: 0, g: 0, b: 0 };
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
    };
  }

  // Euclidean distance in RGB space
  function colorDistance(hex1, hex2) {
    const a = hexToRgb(hex1);
    const b = hexToRgb(hex2);
    return Math.sqrt((a.r - b.r) ** 2 + (a.g - b.g) ** 2 + (a.b - b.b) ** 2);
  }

  const candidates = COLOR_RULES.ALWAYS_ALLOWED.filter(c => c.length === 7); // valid hex only
  if (!candidates.length) return POTOMAC_COLORS.PRIMARY.YELLOW;

  let nearest = candidates[0];
  let minDist = Infinity;

  candidates.forEach(candidate => {
    const dist = colorDistance(inputColor, candidate);
    if (dist < minDist) {
      minDist = dist;
      nearest = candidate;
    }
  });

  return nearest;
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