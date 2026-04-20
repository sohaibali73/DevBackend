'use strict';
/**
 * Theme Library
 * =============
 * A theme is a palette + accent + surface + on-surface colors that any
 * template can look up.  Templates receive a `theme` name (e.g. 'light',
 * 'dark', 'midnight', 'cream') via slide.data.theme; `resolveTheme()`
 * returns the concrete color tokens.
 *
 * Adding a new theme: drop an object into THEMES below.  No template
 * changes are required — every template that uses `resolveTheme(d)` gets
 * the new palette for free.
 */

const { PALETTE } = require('./brand');

/**
 * Standard theme schema:
 *   {
 *     bg          — slide background
 *     surface     — card / panel background
 *     altSurface  — secondary card background
 *     onBg        — text on bg
 *     onSurface   — text on surface
 *     muted       — subtle label / footer text
 *     accent      — primary brand accent (pill fills, underline, bar)
 *     accentSoft  — tinted accent (for backgrounds)
 *     stroke      — card border
 *     isDark      — convenience flag
 *   }
 */
const THEMES = Object.freeze({
  // ── Brand defaults ─────────────────────────────────────────────────────
  light: {
    bg: PALETTE.WHITE, surface: PALETTE.GRAY_05, altSurface: PALETTE.GRAY_10,
    onBg: PALETTE.DARK_GRAY, onSurface: PALETTE.DARK_GRAY,
    muted: PALETTE.GRAY_60, accent: PALETTE.YELLOW, accentSoft: PALETTE.YELLOW_20,
    stroke: PALETTE.GRAY_20, isDark: false,
  },
  dark: {
    bg: PALETTE.DARK_GRAY, surface: '2A2A2A', altSurface: '1A1A1A',
    onBg: PALETTE.WHITE, onSurface: PALETTE.WHITE,
    muted: PALETTE.GRAY_40, accent: PALETTE.YELLOW, accentSoft: '3A3220',
    stroke: '333333', isDark: true,
  },
  // Yellow-forward: every surface is yellow tint, accents are dark gray
  yellow: {
    bg: PALETTE.YELLOW_10, surface: PALETTE.WHITE, altSurface: PALETTE.YELLOW_20,
    onBg: PALETTE.DARK_GRAY, onSurface: PALETTE.DARK_GRAY,
    muted: PALETTE.GRAY_60, accent: PALETTE.DARK_GRAY, accentSoft: PALETTE.YELLOW,
    stroke: PALETTE.YELLOW_80, isDark: false,
  },
  // Cream, print-friendly
  cream: {
    bg: 'FAF6EE', surface: PALETTE.WHITE, altSurface: 'F2EBDA',
    onBg: PALETTE.DARK_GRAY, onSurface: PALETTE.DARK_GRAY,
    muted: '7A6C4A', accent: 'B48A2F', accentSoft: 'EADDB8',
    stroke: 'D9CBA3', isDark: false,
  },
  // Muted slate / corporate blue
  slate: {
    bg: 'F4F6F9', surface: PALETTE.WHITE, altSurface: 'E7ECF3',
    onBg: '1E2A44', onSurface: '1E2A44',
    muted: '5C6B83', accent: '2E4C7C', accentSoft: 'D8E1EF',
    stroke: 'CBD4E0', isDark: false,
  },
  // Deep midnight (dark variant w/ blue tint)
  midnight: {
    bg: '0E1420', surface: '18202F', altSurface: '0A0F18',
    onBg: 'E8ECF5', onSurface: 'E8ECF5',
    muted: '8593B0', accent: PALETTE.YELLOW, accentSoft: '2C2210',
    stroke: '26324A', isDark: true,
  },
  // High-contrast monochrome (print safe)
  mono: {
    bg: PALETTE.WHITE, surface: PALETTE.GRAY_05, altSurface: PALETTE.GRAY_20,
    onBg: PALETTE.BLACK, onSurface: PALETTE.BLACK,
    muted: PALETTE.GRAY_60, accent: PALETTE.BLACK, accentSoft: PALETTE.GRAY_20,
    stroke: PALETTE.GRAY_60, isDark: false,
  },
  // Forest / earthy
  forest: {
    bg: 'F3F7F1', surface: PALETTE.WHITE, altSurface: 'E2ECDC',
    onBg: '1F3A2C', onSurface: '1F3A2C',
    muted: '586B58', accent: '2E7D4F', accentSoft: 'CDE4D0',
    stroke: 'B3CEB7', isDark: false,
  },
  // Warm sunset (gradient-feeling flat)
  sunset: {
    bg: 'FFF4ED', surface: PALETTE.WHITE, altSurface: 'FCE2D0',
    onBg: '5A2A0A', onSurface: '5A2A0A',
    muted: '8F5532', accent: 'E06D2A', accentSoft: 'FFD6B8',
    stroke: 'F2B98C', isDark: false,
  },
  // Minimal (off-white on cream)
  minimal: {
    bg: 'FDFBF7', surface: PALETTE.WHITE, altSurface: 'F3EFE7',
    onBg: '1F1F1F', onSurface: '1F1F1F',
    muted: '8A8A8A', accent: '1F1F1F', accentSoft: 'EFE7D6',
    stroke: 'E2D8C2', isDark: false,
  },
});

/**
 * Resolve a theme by name. Accepts either a string or an object.
 * Unknown names fall back to 'light'. If the caller passes `theme:'dark'`
 * on slide data, we recognize it too.
 */
function resolveTheme(name) {
  if (!name) return THEMES.light;
  if (typeof name === 'object') return { ...THEMES.light, ...name };
  return THEMES[name] || THEMES.light;
}

/** Short-hand colors for a slide-data spec that only sets `theme`. */
function themeFromData(d) {
  if (!d) return THEMES.light;
  if (d.themeObject) return resolveTheme(d.themeObject);
  return resolveTheme(d.theme);
}

module.exports = { THEMES, resolveTheme, themeFromData };
