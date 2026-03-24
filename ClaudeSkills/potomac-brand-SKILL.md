---
name: potomac-brand
description: Apply Potomac brand guidelines to all artifacts, presentations, and visual content. Use when creating HTML/React components, PowerPoint presentations, or any branded materials for Potomac. Ensures consistent use of colors, typography, logos, and brand voice.
---

# Potomac Brand Guidelines

This skill ensures all artifacts, presentations, and visual content align with Potomac's brand identity.

## When to Use This Skill

- Creating HTML or React artifacts for Potomac
- Building PowerPoint presentations (.pptx files)
- Designing any visual content or branded materials
- Writing content that represents Potomac
- Any request mentioning Potomac or its products

## Company Identity

### Company Name
- **Correct**: "Potomac"
- **Incorrect**: "Potomac Fund Management", "Potomac Fund"
- The words "Fund Management" and "Fund" were intentionally dropped to avoid confusion with the Potomac Funds product line

### Domain
- Primary: potomac.com
- Funds: potomacfunds.com

### Products
- Investment Strategies
- TAMP (Turnkey Asset Management Platform)
- Guardrails
- Research
- Potomac Funds (separate domain)

## Color Palette

### Primary Colors

**Potomac Yellow** (Primary brand color)
- HEX: `#FEC00F`
- Use across all communications for brand consistency
- Available in 5 tones: 100%, 80%, 60%, 40%, 20%

**Potomac Dark Gray** (Primary text color)
- HEX: `#212121`
- Use for header text on web and design elements
- Do NOT use for body text
- Primary color for Conquer Risk podcast
- Available in 5 tones: 100%, 80%, 60%, 40%, 20%

### Secondary Colors

**Potomac Turquoise**
- HEX: `#00DED1`
- Use ONLY for Investment Strategies and Potomac Funds
- Do NOT use for other business areas

**Potomac Pink** (Accent color)
- HEX: `#EB2F5C`
- Use sparingly in ads, emails, and website
- Accent only

## Typography

### Headlines: Rajdhani
- **Always use ALL CAPS for headlines**
- Available weights: Bold, Medium, Light
- Primary header font for all Potomac materials
- Web font available via Google Fonts

**Example CSS:**
```css
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;500;700&display=swap');

h1, h2, h3 {
    font-family: 'Rajdhani', sans-serif;
    text-transform: uppercase;
}
```

### Body Copy: Quicksand
- Primary font for all body text
- Available weights: Bold, Medium, Light
- Use for paragraphs, descriptions, and general content

**Example CSS:**
```css
@import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@300;500;700&display=swap');

body, p, div {
    font-family: 'Quicksand', sans-serif;
}
```

### Funds Content: Lexend Deca
- Use EXCLUSIVELY for Potomac Funds materials
- Available weights: Nine weights from Light to Bold
- Do NOT use for general Potomac content

**Example CSS:**
```css
@import url('https://fonts.googleapis.com/css2?family=Lexend+Deca:wght@300;700&display=swap');

.funds-content {
    font-family: 'Lexend Deca', sans-serif;
}
```

## Trademarked Tagline

**"Built to Conquer Risk®"**

Rules:
- Must be in Title Case OR ALL CAPS
- Always include the ® symbol at the end
- Can be used standalone or in context: "Investment strategies and solutions for financial advisors. Built to Conquer Risk®"
- All uses require marketing and compliance approval

## Visual Design Principles

### Logo Usage
- Use full banner mark (icon + wordmark) whenever possible
- Icon may stand alone for social media and digital assets
- Wordmark alone only when white version needed on colored background
- NEVER alter logo colors, proportions, or add effects
- Minimum wordmark width: 35mm

### Don'ts
- Don't stretch or distort the logo
- Don't rotate the logo
- Don't change logo colors
- Don't add effects (shadows, glows, etc.)
- Don't create alternate versions

## Writing Style

### Capitalization (Headline Style)
1. Capitalize first and last words in titles
2. Capitalize all major words (nouns, pronouns, verbs, adjectives, adverbs)
3. Lowercase: the, a, an
4. Lowercase: prepositions (except when used adverbially)
5. Lowercase: and, but, for, or, nor
6. Lowercase: "to" in infinitives

### Hyphenated Compounds
1. Always capitalize first element
2. Capitalize subsequent elements unless they're articles, prepositions, or conjunctions
3. Don't capitalize second element if first is a prefix (anti-, pre-)
4. Capitalize second element in spelled-out numbers (Twenty-One)

### Brand Voice
- Bold and distinctive
- Mission-focused: "conquer risk"
- Professional but confident
- Avoid generic AI aesthetics
- No profanity in official materials

## HTML/React Artifact Guidelines

### Required Structure
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Potomac - [Page Title]</title>
    
    <!-- Import Potomac Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;500;700&family=Quicksand:wght@300;500;700&display=swap" rel="stylesheet">
    
    <style>
        :root {
            --potomac-yellow: #FEC00F;
            --potomac-gray: #212121;
            --potomac-turquoise: #00DED1;
            --potomac-pink: #EB2F5C;
        }
        
        body {
            font-family: 'Quicksand', sans-serif;
            margin: 0;
            padding: 0;
            color: var(--potomac-gray);
        }
        
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Rajdhani', sans-serif;
            text-transform: uppercase;
            color: var(--potomac-gray);
        }
        
        /* Your custom styles here */
    </style>
</head>
<body>
    <!-- Content here -->
</body>
</html>
```

### React Components
```jsx
import React from 'react';

// Always use Tailwind for styling
// Set up CSS variables for brand colors

const PotomacComponent = () => {
  return (
    <div style={{
      '--potomac-yellow': '#FEC00F',
      '--potomac-gray': '#212121',
      '--potomac-turquoise': '#00DED1',
      '--potomac-pink': '#EB2F5C'
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;500;700&family=Quicksand:wght@300;500;700&display=swap');
        
        .potomac-heading {
          font-family: 'Rajdhani', sans-serif;
          text-transform: uppercase;
          color: var(--potomac-gray);
        }
        
        .potomac-body {
          font-family: 'Quicksand', sans-serif;
          color: var(--potomac-gray);
        }
      `}</style>
      
      {/* Component content */}
    </div>
  );
};

export default PotomacComponent;
```

## PowerPoint Presentation Guidelines

### Color Scheme
- Primary accent: Potomac Yellow (#FEC00F)
- Text: Potomac Dark Gray (#212121)
- White backgrounds with yellow accents
- Use turquoise only for Investment Strategies/Funds content

### Typography
- **Slide Titles**: Rajdhani Bold, ALL CAPS
- **Body Text**: Quicksand Regular or Medium
- **Emphasis**: Quicksand Bold
- Maintain consistent sizing across presentation

### Slide Structure
1. **Title Slide**
   - Large Rajdhani heading (ALL CAPS)
   - Tagline option: "Built to Conquer Risk®"
   - Yellow accent elements

2. **Content Slides**
   - Rajdhani headers (ALL CAPS)
   - Quicksand body text
   - Yellow highlights for key information
   - Ample white space

3. **Data Slides**
   - Use brand colors for charts/graphs
   - Yellow for primary data points
   - Gray for supporting information
   - Turquoise only for Funds data

### Best Practices
- Maintain consistent margins
- Use yellow strategically as accent color
- Keep slides clean and uncluttered
- Never use more than 3 brand colors per slide
- All text in Rajdhani (headers) or Quicksand (body)

## Compliance Requirements

1. All marketing materials require compliance approval before distribution
2. Include standard disclosure on all materials
3. Business communications must use Potomac email (@potomac.com)
4. Social media posts about products/strategies require pre-approval
5. Cannot make promissory statements or reference performance without approval

## Quick Reference

| Element | Specification |
|---------|--------------|
| **Company Name** | Potomac |
| **Primary Color** | Yellow #FEC00F |
| **Text Color** | Dark Gray #212121 |
| **Headlines** | Rajdhani (ALL CAPS) |
| **Body Text** | Quicksand |
| **Funds** | Lexend Deca |
| **Tagline** | Built to Conquer Risk® |
| **Website** | potomac.com |

## Implementation Checklist

Before finalizing any Potomac artifact or presentation:

- [ ] Used "Potomac" (not "Potomac Fund Management")
- [ ] Applied correct color palette (Yellow #FEC00F, Gray #212121)
- [ ] Used Rajdhani for headlines (ALL CAPS)
- [ ] Used Quicksand for body text
- [ ] Used Lexend Deca only for Funds content (if applicable)
- [ ] Included ® symbol with tagline (if used)
- [ ] Followed capitalization rules for titles
- [ ] Avoided logo alteration
- [ ] Used turquoise only for Investment Strategies/Funds
- [ ] Maintained professional, bold brand voice
- [ ] Included compliance disclosure (for presentations/marketing)

## Examples

### Good HTML Header
```html
<header style="background: #FEC00F; padding: 20px;">
  <h1 style="font-family: 'Rajdhani', sans-serif; text-transform: uppercase; color: #212121; margin: 0;">
    POTOMAC
  </h1>
  <p style="font-family: 'Quicksand', sans-serif; color: #212121; margin: 5px 0 0 0;">
    Built to Conquer Risk®
  </p>
</header>
```

### Good Slide Title
```
CONQUERING MARKET VOLATILITY
Investment Strategies for Modern Advisors
```

### Good Color Usage
- **Primary**: Yellow backgrounds, yellow accent bars, yellow highlights
- **Text**: Dark gray on white or yellow backgrounds
- **Funds**: Turquoise accents only when discussing Investment Strategies or Potomac Funds
- **Accent**: Pink sparingly for calls-to-action or emphasis

## Notes for Claude

When creating content for Potomac:

1. **Always start** by importing the correct fonts (Rajdhani, Quicksand)
2. **Set up CSS variables** for brand colors at the root level
3. **Use ALL CAPS** for all Rajdhani headers - never forget this
4. **Be selective** with turquoise - only for Investment Strategies/Funds
5. **Think bold** - Potomac's brand is confident and distinctive
6. **Maintain consistency** - every element should feel cohesive
7. **Check compliance** - remind user about approval requirements for marketing materials

Remember: This brand represents a mission to "conquer risk" - make it confident, professional, and unmistakably Potomac.
