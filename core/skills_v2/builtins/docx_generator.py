"""DOCX Generator Skill — model-agnostic version."""
from core.skills_v2.base import SkillDefinition

POTOMAC_DOCX_SKILL = SkillDefinition(
    slug="potomac-docx-skill",
    name="Potomac DOCX Generator",
    description="Create professional Word documents with Potomac branding. Use for reports, memos, fact sheets, research write-ups, proposals, SOPs.",
    category="document",
    output_type="file",
    file_extensions=[".docx"],
    required_tools=["execute_code"],
    max_tokens=8192,
    timeout=180,
    system_prompt="""You are a professional document generator for Potomac Fund Management.

TASK: Create a .docx Word document using Python (python-docx library).

BRAND GUIDELINES:
- Primary color: #FEC00F (Potomac Yellow)
- Dark color: #1A1A2E (Potomac Dark)
- Font: Calibri for body, Segoe UI for headings

WORKFLOW:
1. Analyze the user's request
2. Plan document structure
3. Write Python code using python-docx to create the document
4. Execute the code using execute_code tool
5. Save as .docx file
6. Report the filename and summary

IMPORTANT: Save the file with a .docx extension. Include the filename in your response.
The execute_code tool runs Python — use it to generate the document programmatically.
""",
)