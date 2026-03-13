# Potomac DOCX Skill

A comprehensive skill for creating professional, brand-compliant Word documents for Potomac.

## Overview

This skill enables Claude to create any type of Potomac-branded Word document, from strategy write-ups using the official template to custom research reports, memos, and white papers built from scratch.

## Key Features

- **Template-based creation**: Automatically uses Potomac's strategy write-up template when appropriate
- **Custom document builder**: Creates professional documents from scratch for any use case
- **Full brand compliance**: Applies Potomac's color palette, typography, and style guidelines
- **Flexible logo handling**: Supports multiple logo variants based on context
- **Interactive content gathering**: Asks questions when information is incomplete
- **Validation**: Ensures all documents are valid and render correctly

## Structure

```
potomac-docx/
├── SKILL.md                          # Main skill file with complete instructions
├── references/
│   ├── strategy-writeup-guide.md     # Detailed guide for strategy write-ups
│   └── test-cases.md                 # Comprehensive test cases for evaluation
├── examples/
│   └── research-report-example.js    # Complete example of building a research report
└── README.md                         # This file
```

## Dependencies

This skill relies on:

1. **docx skill** (`/mnt/skills/public/docx/SKILL.md`)
   - Provides core Word document creation capabilities
   - Contains all technical documentation for docx-js library
   
2. **potomac-brand skill** (`/mnt/skills/user/potomac-brand/SKILL.md`)
   - Defines Potomac's brand guidelines
   - Colors, fonts, logo usage, style rules

3. **Template file** (`Potomac_WriteUp_Template_Final.docx`)
   - Required for strategy write-ups
   - Should be in `/mnt/user-data/uploads/`

4. **Logo files**:
   - `Potomac_Logo.png` (standard - yellow icon, black text)
   - `Potomac_Logo_Black.png` (formal - all black)
   - `Potomac_Logo_White_and_Yellow.png` (dark backgrounds)

## Document Types Supported

### 1. Strategy Write-Ups (Template-based)
- Uses official Potomac template
- 8 structured sections
- For documenting trading/investment strategies
- Includes performance statistics, parameters, and compliance disclosures

### 2. Research Reports (Custom)
- Built from scratch
- Executive summary, findings, analysis, conclusion
- Proper data visualization and tables
- Professional formatting

### 3. Internal Memos (Custom)
- TO/FROM/DATE/RE structure
- Clear action items
- Professional tone

### 4. White Papers (Custom)
- Multi-section structure
- Cover page
- Table of contents (optional)
- In-depth analysis

### 5. Any Professional Document
- Flexible structure based on user needs
- Always applies Potomac branding

## Usage Workflow

### Strategy Write-Up
1. User requests strategy write-up
2. Claude checks for template in uploads
3. If present, copies and unpacks template
4. Asks for missing information
5. Fills template via XML editing
6. Packs and presents document

### Custom Document
1. User requests document
2. Claude reads docx and brand skills
3. Asks about logo preference
4. Gathers content requirements
5. Creates JavaScript file using docx-js
6. Executes script to generate document
7. Validates and presents

## Branding Standards

### Typography
- **Headers**: Rajdhani, ALL CAPS, bold, #212121
  - H1: 18pt
  - H2: 16pt
  - H3: 14pt
- **Body**: Quicksand, 11pt, #212121

### Colors
- **Primary**: Yellow #FEC00F (accents, table headers, dividers)
- **Text**: Dark Gray #212121
- **Turquoise**: #00DED1 (Investment Strategies/Funds only)
- **Pink**: #EB2F5C (sparingly, emphasis only)

### Page Setup
- US Letter (8.5" x 11")
- 1" margins all around
- Left-aligned text (justified for long-form)

### Required Elements
- Logo (top of document)
- Proper section headers
- Yellow divider before disclosures
- Complete disclosure text
- Potomac.com reference

## Technical Requirements

### Tools
- Node.js with `docx` package installed globally
- Python with LibreOffice support (for validation)
- Access to scripts/office/ utilities

### Key Technical Rules
1. Always set page size explicitly (US Letter: 12240 x 15840 DXA)
2. Use proper numbering config for lists (never unicode bullets)
3. Tables need both `columnWidths` and cell `width` properties
4. Use `WidthType.DXA` for tables (not PERCENTAGE)
5. Use `ShadingType.CLEAR` for table backgrounds
6. All headers must include `outlineLevel` for proper TOC support
7. Override built-in styles with exact IDs: "Heading1", "Heading2", etc.

## Testing

See `references/test-cases.md` for comprehensive test scenarios covering:
- Strategy write-ups with complete/incomplete data
- Research reports with tables and charts
- Internal memos
- Logo selection
- Template handling
- Brand compliance
- Error scenarios

Target success rate: 80%+ across all test cases

## Examples

### Minimal Research Report
See `examples/research-report-example.js` for a complete, working example demonstrating:
- Logo insertion
- Custom styling
- Proper Potomac branding
- Table creation with brand colors
- Disclosure section
- Validation

### Strategy Write-Up
See `references/strategy-writeup-guide.md` for detailed guidance on:
- Template structure
- Section requirements
- XML editing patterns
- Content examples
- Best practices

## Common Issues and Solutions

### Issue: Template not found
**Solution**: Check `/mnt/user-data/uploads/` for template file. If missing, ask user to upload or offer to create custom document.

### Issue: Document won't validate
**Solution**: Check for:
- Table width mismatches
- Missing `type` on ImageRun
- PageBreak not in Paragraph
- Unicode bullets instead of proper numbering

### Issue: Tables render incorrectly
**Solution**: Ensure both table `width` and `columnWidths` are set, and they sum correctly. Use DXA units only.

### Issue: Fonts don't display
**Solution**: Verify font names are exact: "Rajdhani" and "Quicksand". Check that `allCaps: true` is set for headers.

### Issue: Logo doesn't show
**Solution**: Verify logo path, check buffer loaded successfully, confirm `type: "png"` is specified.

## Quality Checklist

Before presenting any document:
- [ ] Logo present and correctly sized
- [ ] All headers use Rajdhani ALL CAPS
- [ ] Body text uses Quicksand
- [ ] Company name is "Potomac"
- [ ] Colors match guidelines (Yellow #FEC00F, Gray #212121)
- [ ] Disclosures included
- [ ] Document validates
- [ ] Tables render correctly
- [ ] Lists use proper numbering
- [ ] US Letter page size

## Maintenance

### Updating Brand Guidelines
If Potomac's brand guidelines change:
1. Update `potomac-brand` skill first
2. Update color codes, fonts, or logo paths in SKILL.md
3. Update examples to reflect changes
4. Re-test all test cases

### Adding New Document Types
To add support for new document types:
1. Create example in `examples/` directory
2. Add structure template to SKILL.md
3. Create test cases in `references/test-cases.md`
4. Update this README

## Support

For questions or issues:
1. Check the docx skill for technical documentation
2. Check the potomac-brand skill for brand guidelines
3. Review examples for working code
4. Consult test cases for expected behavior

## Version History

**v1.0** (Current)
- Initial release
- Strategy write-up template support
- Custom document builder
- Full brand compliance
- Logo variant support
- Interactive content gathering
- Comprehensive test cases
