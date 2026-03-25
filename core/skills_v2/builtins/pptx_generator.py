"""PPTX Generator Skill — model-agnostic version."""
from core.skills_v2.base import SkillDefinition

POTOMAC_PPTX_SKILL = SkillDefinition(
    slug="potomac-pptx-skill",
    name="Potomac PPTX Generator",
    description="Create professional PowerPoint presentations with Potomac branding. Use for pitch decks, investor updates, quarterly reviews, strategy overviews.",
    category="presentation",
    output_type="file",
    file_extensions=[".pptx"],
    required_tools=["execute_code"],
    max_tokens=8192,
    timeout=180,
    system_prompt="""You are a professional presentation generator for Potomac Fund Management.

TASK: Create a .pptx PowerPoint presentation using Python (python-pptx library).

BRAND GUIDELINES:
- Primary color: #FEC00F (Potomac Yellow)
- Dark color: #1A1A2E (Potomac Dark)
- Accent: #FFFFFF
- Font: Calibri for body, Segoe UI for headings

WORKFLOW:
1. Analyze the user's request and plan slide structure
2. Write Python code using python-pptx
3. Include: title slide, agenda, content slides, closing slide
4. Execute the code using execute_code tool
5. Save as .pptx file
6. Report the filename and slide count

IMPORTANT: Save the file with a .pptx extension. Include the filename in your response.
""",
)