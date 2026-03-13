# Template File Note

The strategy write-up template (`Potomac_WriteUp_Template_Final.docx`) is referenced in the skill but not bundled in the assets directory because it was provided in the context window rather than as an uploaded file.

## Template Location

When using this skill, the template should be:
1. Uploaded by the user to `/mnt/user-data/uploads/`, OR
2. Referenced from its permanent location if available

## Template Structure

The template contains 8 main sections:

1. **Title** - Strategy name and metadata
2. **Inspiration** - Sources and references
3. **Thesis** - Core hypothesis and supporting assumptions
4. **Parameters & Rules** - Detailed buy/sell/exit rules and optimization summary
5. **Link to AFL** - AFL file path and header checklist
6. **Link to Optimization in Excel** - Excel file details
7. **Write-up & Findings** - Summary, statistics, call, risks, next steps
8. **Appendix** - Charts and supporting materials

## Using the Template

The skill will:
1. Check for template in `/mnt/user-data/uploads/`
2. If present, copy it to working directory
3. Unpack the .docx file
4. Edit XML to fill in content
5. Repack and present the completed document

If the template is not available:
- The skill will notify the user
- Offer to create a custom strategy document instead
- Or wait for user to upload the template

## Template Content

The template includes:
- Potomac logo
- "INTERNAL USE ONLY" header
- Structured sections with clear formatting
- Complete disclosure text
- Professional layout and spacing

See `references/strategy-writeup-guide.md` for detailed information on filling out the template.
