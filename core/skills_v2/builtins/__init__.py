"""
Built-in Skill Definitions
===========================
Model-agnostic skills available to all providers.
"""

from core.skills_v2.builtins.docx_generator import POTOMAC_DOCX_SKILL
from core.skills_v2.builtins.pptx_generator import POTOMAC_PPTX_SKILL
from core.skills_v2.builtins.afl_developer import AFL_DEVELOPER_SKILL
from core.skills_v2.builtins.quant_analyst import QUANT_ANALYST_SKILL

ALL_BUILTIN_SKILLS = [
    POTOMAC_DOCX_SKILL,
    POTOMAC_PPTX_SKILL,
    AFL_DEVELOPER_SKILL,
    QUANT_ANALYST_SKILL,
]