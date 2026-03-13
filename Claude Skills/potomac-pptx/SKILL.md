---
name: potomac-pptx
description: "Enhanced PPTX skill with strict Potomac brand compliance. Inherits all capabilities from the base PPTX skill (markitdown extraction, template editing, pptxgenjs generation, visual QA) and adds zero-tolerance brand enforcement, AI-powered template selection, and Potomac-specific design guidelines. Use for all Potomac presentations requiring perfect brand adherence with professional quality assurance."
license: Proprietary. LICENSE.txt has complete terms
---

# Potomac PPTX Skill

**Built on the foundation of the original PPTX skill with enhanced Potomac brand compliance**

## When to Use This Skill

Use this skill for any Potomac presentation needs, inheriting ALL capabilities from the base PPTX skill plus Potomac-specific enhancements:

- **All original PPTX capabilities**: Text extraction, template editing, from-scratch generation
- **Potomac brand requirements**: Perfect brand compliance mandatory
- **Professional presentations**: Client materials, research reports, pitch decks
- **Quality assurance**: Enhanced QA with brand validation

## Core Capabilities (Enhanced from Original PPTX Skill)

### 📋 **All Original PPTX Features (Inherited)**

| Task | Guide | Command |
|------|-------|---------|
| Read/analyze content | **Inherited from original PPTX skill** | `python -m markitdown presentation.pptx` |
| Edit or create from template | Read [editing.md](editing.md) | `python scripts/thumbnail.py presentation.pptx` |
| Create from scratch | Read [pptxgenjs.md](pptxgenjs.md) | `node scripts/generate-potomac-presentation.js` |
| Visual QA and thumbnails | **Original scripts copied** | `python scripts/thumbnail.py presentation.pptx` |

**Complete original PPTX workflow inherited:**
```bash
# Text extraction (original)
python -m markitdown presentation.pptx

# Visual overview (original scripts)
python scripts/thumbnail.py presentation.pptx

# Raw XML manipulation (original)
python scripts/office/unpack.py presentation.pptx unpacked/
python scripts/office/pack.py unpacked/ output.pptx

# Template editing workflow (original + enhanced)
# 1. Analyze → 2. Unpack → 3. Edit → 4. Clean → 5. Pack + Brand Validation

# From-scratch generation (original pptxgenjs + Potomac enhancements)
# Uses pptxgenjs foundation with brand compliance layer
```

### 🛡️ **NEW: Zero-Tolerance Brand Compliance**
- **Potomac color enforcement**: Only #FEC00F (yellow) and #212121 (dark gray) allowed
- **Typography governance**: Rajdhani ALL CAPS headers, Quicksand body text
- **Logo protection**: Automated sizing and placement validation
- **Terminology correction**: "Potomac Fund Management" → "Potomac"
- **100/100 compliance requirement**: Generation fails if brand violations detected

### 🎨 **NEW: Potomac Design Guidelines (Enhanced)**

**Replaces generic color palettes from original skill with Potomac brand colors:**

| Potomac Theme | Primary | Secondary | Accent |
|---------------|---------|-----------|--------|
| **Potomac Standard** | `FEC00F` (yellow) | `212121` (dark gray) | `FFFFFF` (white) |
| **Potomac Executive** | `212121` (dark gray) | `FEC00F` (yellow) | `FFFFFF` (white) |
| **Investment Focus** | `FEC00F` (yellow) | `00DED1` (turquoise) | `212121` (gray) |
| **Funds Only** | `00DED1` (turquoise) | `FEC00F` (yellow) | `212121` (gray) |

**Potomac Typography (Enforced):**
- **Slide titles**: Rajdhani Bold, ALL CAPS, 36-44pt
- **Headers**: Rajdhani Bold, ALL CAPS, 20-24pt  
- **Body text**: Quicksand Regular, 14-16pt
- **Captions**: Quicksand Light, 10-12pt

### 🤖 **NEW: AI-Powered Template Selection**
- **Content classification**: Automatically detects presentation type
- **Smart template selection**: Optimal layout based on content analysis
- **Template confidence scoring**: 70-130% confidence ratings
- **11+ specialized templates**: Enhanced beyond original skill's basic layouts

## Enhanced Workflow

### **Method 1: Enhanced Template Editing (Original + Brand Compliance)**
```bash
# Step 1: Analyze template (original process)
python scripts/thumbnail.py template.pptx

# Step 2: Brand compliance pre-check (NEW)
python scripts/potomac-brand-audit.py template.pptx

# Step 3: Edit with brand enforcement (enhanced)
# Original editing workflow + automatic brand compliance validation

# Step 4: Enhanced QA (original + brand validation)
python scripts/potomac-visual-qa.py output.pptx
```

### **Method 2: Enhanced From-Scratch Generation (Original + Smart Templates)**
```bash
# Uses original pptxgenjs foundation with Potomac enhancements
node scripts/generate-potomac-presentation.js --title "PRESENTATION TITLE" --type research

# Includes original QA process plus brand validation
```

### **Method 3: NEW - AI-Powered Generation**
```bash
# Smart template selection with brand compliance
node scripts/generate-enhanced-presentation.js --type pitch --compliance strict
```

## Enhanced Quality Assurance

### **Original QA Process (Inherited)**
1. **Content QA**: `python -m markitdown output.pptx`
2. **Visual inspection**: Convert to images and inspect
3. **Issue detection**: Overlapping elements, text overflow, spacing problems
4. **Verification loop**: Fix → Re-verify → Repeat until clean

### **NEW: Brand Compliance QA (Added)**
```bash
# Brand-specific checks (in addition to original QA)
python scripts/potomac-brand-qa.py presentation.pptx

# Check for brand violations (enhanced from original)
python -m markitdown presentation.pptx | grep -iE "potomac fund management|potomac fund|xxxx|lorem"

# Logo usage validation (NEW)
python scripts/logo-compliance-check.py presentation.pptx
```

**Enhanced Visual QA Prompt (Original + Brand Focus):**
```
Visually inspect these slides for BOTH technical and brand issues:

ORIGINAL CHECKS (from base PPTX skill):
- Overlapping elements, text overflow, spacing issues
- Low-contrast elements, alignment problems
- Placeholder content, margin violations

NEW BRAND CHECKS (Potomac-specific):
- Non-Potomac colors (only #FEC00F yellow, #212121 gray allowed)
- Wrong fonts (headers must be Rajdhani ALL CAPS, body must be Quicksand)
- Logo violations (sizing, placement, modifications)
- Incorrect terminology ("Potomac Fund Management" vs "Potomac")
- Missing ® symbol on "Built to Conquer Risk®"

Report ALL issues found - both technical and brand violations.
```

## Presentation Types (Enhanced)

### **Research Presentations**
- Inherits original slide design principles
- Adds Potomac brand compliance
- Smart template selection for data visualization
- Market analysis with brand-compliant charts

### **Client Pitch Decks**
- Professional layouts from original skill foundation
- Enhanced with Potomac value proposition templates
- Brand-compliant process flows and metrics
- Zero-tolerance brand enforcement

### **Market Outlook**  
- Uses original design guidelines enhanced with Potomac branding
- Economic indicator displays with brand colors
- Comparison layouts with strict brand compliance

## Dependencies (Enhanced from Original)

**Original PPTX Dependencies (Required):**
- `pip install "markitdown[pptx]"` - text extraction
- `pip install Pillow` - thumbnail grids
- `npm install -g pptxgenjs` - creating from scratch
- LibreOffice (`soffice`) - PDF conversion
- Poppler (`pdftoppm`) - PDF to images

**NEW Potomac Dependencies:**
- Potomac brand asset library (logos, fonts, colors)
- Brand compliance validation engine
- Smart template selection system
- Enhanced QA tools with brand checking

## File Structure (Enhanced)

```
skills/potomac-pptx/
├── SKILL.md                    # This enhanced skill
├── scripts/                    # Original PPTX scripts + Potomac enhancements
│   ├── thumbnail.py            # Inherited from original
│   ├── generate-potomac-presentation.js  # Enhanced version
│   ├── potomac-brand-audit.py  # NEW - Brand compliance checking
│   └── potomac-visual-qa.py    # Enhanced QA with brand validation
├── brand-assets/               # NEW - Potomac brand library
│   ├── logos/                  # Potomac logo variants
│   ├── colors/                 # Brand color definitions  
│   └── fonts/                  # Typography standards
├── templates/                  # Enhanced templates with brand compliance
├── compliance/                 # NEW - Brand enforcement engine
└── examples/                   # Sample brand-compliant outputs
```

## Usage Examples

### **Enhanced Template Editing (Original Workflow + Brand Compliance)**
```bash
# Original process enhanced with brand validation
python scripts/thumbnail.py existing-template.pptx
python scripts/potomac-brand-audit.py existing-template.pptx  # NEW
# Edit with brand compliance active
python scripts/potomac-visual-qa.py output.pptx  # Enhanced QA
```

### **Smart Generation (NEW - Built on Original Foundation)**
```bash
# AI-powered template selection with brand compliance
node scripts/generate-enhanced-presentation.js --type research --title "Q1 MARKET ANALYSIS"
```

## Success Criteria

**Inherits original PPTX quality standards PLUS:**
- ✅ 100/100 brand compliance score (mandatory)
- ✅ All original QA checks passed
- ✅ Perfect Potomac brand adherence
- ✅ Professional presentation quality
- ✅ Zero brand violations detected

## Key Enhancement: Perfect Integration

This skill **extends rather than replaces** the original PPTX skill:
- **Keeps all original capabilities** (markitdown, editing, pptxgenjs, QA)
- **Adds brand enforcement layer** on top of existing tools
- **Enhances design guidelines** with Potomac specifications
- **Improves QA process** with brand compliance validation
- **Maintains compatibility** with all original workflows

**Result**: Professional-grade presentations with perfect Potomac brand compliance using proven PPTX generation and quality assurance processes.

---

*Built to Conquer Risk® - Enhanced PPTX Generation with Zero-Tolerance Brand Compliance*