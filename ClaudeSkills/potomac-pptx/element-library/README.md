# Potomac Design Element Library

This directory stores InDesign-exported PNG assets used by the **PPTX Intelligence
Pipeline** for design element matching and slide reconstruction.

## Directory Structure

```
element-library/
  icons/         → Strategy icons, hexagon badges, symbol icons
  logos/         → Potomac logo variants (sync from brand-assets/logos/)
  backgrounds/   → Full-slide background textures and gradients
  badges/        → Badge and pill-shaped label templates
  dividers/      → Horizontal/vertical line divider elements
  shapes/        → Generic shape templates (arrows, callouts, etc.)
```

## How to Add Elements

### Via API (recommended)
```http
POST /pptx/element-library/upload
Content-Type: multipart/form-data

files[]: <PNG file>
category: icons
tags: hexagon,strategy,yellow
```

### Manually (drop files into the correct subdirectory)
The element matcher auto-indexes new files in the directory on the next API call.
You can also force a re-index:
```http
POST /pptx/element-library/rebuild-index
```

## Naming Conventions

Use descriptive hyphenated names so the auto-tagger works well:

```
icons/
  hexagon-globe.png          → tags: hexagon, globe
  hexagon-shield.png         → tags: hexagon, shield
  hexagon-bear.png           → tags: hexagon, bear
  hexagon-anchor.png         → tags: hexagon, anchor
  hexagon-cross.png          → tags: hexagon, cross
  arrow-right-yellow.png     → tags: arrow, right, yellow
  chart-bar-yellow.png       → tags: chart, bar, yellow

badges/
  strategy-badge-yellow.png
  kpi-badge-dark.png
  label-pill-gray.png

backgrounds/
  dark-strategy-bg.png       → dark gradient background
  light-clean-bg.png
  hero-image-dark.png

dividers/
  yellow-line-thick.png
  yellow-line-thin.png
  gray-divider.png

shapes/
  rectangle-yellow.png
  rectangle-dark.png
  callout-yellow.png
```

## How Matching Works

When the Vision Engine detects an element on a slide image, it describes it
(e.g., "yellow hexagon with globe icon"). The ElementMatcher:

1. Computes a **perceptual hash** (pHash + aHash + dHash) of the detected element
2. Compares it against all indexed library elements using **Hamming distance**
3. Returns the closest match if similarity ≥ 50%

Perceptual hashing is resilient to:
- Minor color variations
- Small size differences
- JPEG compression artifacts
- Slight rotation (< 5°)

## Catalog API

```http
GET /pptx/element-library/catalog
```

Returns:
```json
{
  "total_elements": 24,
  "categories": {
    "icons": ["hexagon-globe.png", "hexagon-shield.png", ...],
    "badges": ["strategy-badge-yellow.png"],
    "backgrounds": ["dark-strategy-bg.png"]
  }
}
```
