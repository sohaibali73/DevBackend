"""
RevisionEngine
==============
Converts natural language revision instructions into concrete PptxReviser
and AutomizerSandbox operations, then executes them.

This is the "smart revise" layer — the user says what they want in plain
English, Claude translates it into a typed operation list, and the engine
executes it against the PPTX.

Supported revision types (mapped from natural language)
-------------------------------------------------------
PptxReviser operations (fast, no subprocess):
  find_replace     "Change Q1 2025 to Q2 2025 everywhere"
  delete_slide     "Remove slide 5"
  reorder_slides   "Move slide 10 to position 2"
  update_table     "Update row 2, col 3 on slide 8 to 14.2x"
  append_slides    "Add a new title slide at the end"
  update_slide     "Replace the content of slide 4 with ..."

AutomizerSandbox operations (for structural PPTX changes):
  merge_slides     "Insert slides 15-19 from source.pptx after slide 10"
  set_text         "Set the text of shape 'Title 1' on slide 3 to '...'"
  replace_tagged   "Replace {{QUARTER}} with Q2 2025"

Usage
-----
    from core.vision.revision_engine import RevisionEngine

    engine = RevisionEngine()
    result = await engine.smart_revise(
        pptx_bytes=existing_pptx_bytes,
        instruction="Change all references from Q1 to Q2, and delete slide 7",
        output_filename="Q2_Report.pptx",
    )
    if result.success:
        # result.pptx_bytes = updated file
        # result.operations = what was done
        # result.summary = human-readable summary
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Result dataclass
# =============================================================================

@dataclass
class RevisionResult:
    success:       bool
    pptx_bytes:    Optional[bytes] = None
    filename:      Optional[str]   = None
    operations:    List[Dict]      = field(default_factory=list)
    summary:       str             = ""
    exec_time_ms:  float           = 0.0
    error:         Optional[str]   = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":      self.success,
            "filename":     self.filename,
            "operations":   self.operations,
            "summary":      self.summary,
            "exec_time_ms": self.exec_time_ms,
            "error":        self.error,
        }


# =============================================================================
# Claude prompt for revision parsing
# =============================================================================

_REVISION_SYSTEM = """
You are a presentation revision assistant. Your job is to parse a natural
language revision instruction and convert it into a structured list of
typed revision operations.

Return ONLY valid JSON — a single array of operation objects.
No markdown, no prose.

AVAILABLE OPERATION TYPES
─────────────────────────
1. find_replace
   { "type": "find_replace", "find": "<text>", "replace": "<text>" }
   Use for: global text substitutions across ALL slides

2. delete_slide
   { "type": "delete_slide", "slide_index": <0-based int> }
   Use for: removing a slide (convert 1-based user input to 0-based)

3. reorder_slides
   { "type": "reorder_slides", "order": [<0-based int>, ...] }
   Full new order of ALL slide indices. Length must match total slide count.
   "order" field must include ALL slide indices in the new desired order.
   If slide count is unknown, use null for order and include a "description" field.

4. update_table
   { "type": "update_table", "slide_index": <0-based>, "row": <0-based>, "col": <0-based>, "value": "<text>" }
   Use for: updating a specific table cell

5. append_slides
   { "type": "append_slides", "slides": [<pptx_sandbox slide spec>] }
   Use for: adding new slides to the end. slide spec must be valid pptx_sandbox format.

6. update_slide
   { "type": "update_slide", "slide_index": <0-based>, "slide": { "title": "", "bullets": [], "text": "" } }
   Use for: replacing the content of an existing slide

7. set_text
   { "type": "set_text", "slide_index": <0-based>, "shape_name": "<name>", "text": "<new text>" }
   Use for: setting exact text in a named shape

8. replace_tagged
   { "type": "replace_tagged", "tag": "<TAG>", "value": "<replacement>" }
   Use for: replacing {{TAG}} placeholders

IMPORTANT RULES
───────────────
- User slide numbers are 1-based; convert to 0-based for ALL operations
- For "delete slide 5", use slide_index: 4
- For "reorder", if you can't know total count, set order to null
- Multiple operations can be in one instruction — return ALL of them
- Return [] if no actionable operations can be extracted
- ALWAYS return a JSON array (even for one operation)

EXAMPLES
────────
Input: "Change all Q1 2025 to Q2 2025 and delete slide 3"
Output:
[
  { "type": "find_replace", "find": "Q1 2025", "replace": "Q2 2025" },
  { "type": "delete_slide", "slide_index": 2 }
]

Input: "Move slide 5 to position 2"
Output:
[
  { "type": "reorder_slides", "order": null,
    "description": "Move slide 5 (index 4) to position 2 (index 1)" }
]

Input: "Replace {{QUARTER}} with Q2 2025"
Output:
[
  { "type": "replace_tagged", "tag": "QUARTER", "value": "Q2 2025" }
]
""".strip()


# =============================================================================
# RevisionEngine
# =============================================================================

class RevisionEngine:
    """
    Translates natural language revision instructions into typed operations
    and executes them against a PPTX file.
    """

    def __init__(self, model: str = "claude-opus-4-5"):
        self.model = model

    # ──────────────────────────────────────────────────────────────────────────
    # Main public API
    # ──────────────────────────────────────────────────────────────────────────

    async def smart_revise(
        self,
        pptx_bytes:       bytes,
        instruction:      str,
        output_filename:  str = "revised_presentation.pptx",
        slide_count:      Optional[int] = None,
        extra_context:    str = "",
    ) -> RevisionResult:
        """
        Parse the instruction with Claude and execute the revision.

        Parameters
        ----------
        pptx_bytes      : raw bytes of the current PPTX
        instruction     : natural language revision request
        output_filename : filename for the output
        slide_count     : optional known slide count (helps Claude with reordering)
        extra_context   : optional additional context (e.g., deck title, current analysis)

        Returns
        -------
        RevisionResult with updated pptx_bytes and operation summary
        """
        start = time.time()

        if not pptx_bytes:
            return RevisionResult(False, error="No PPTX bytes provided")
        if not instruction.strip():
            return RevisionResult(False, error="No instruction provided")

        # Auto-detect slide count if not provided
        if slide_count is None:
            from core.vision.slide_renderer import SlideRenderer
            slide_count = SlideRenderer.get_slide_count(pptx_bytes)

        # ── 1. Parse instruction with Claude ─────────────────────────────────
        operations = await self._parse_instruction(
            instruction=instruction,
            slide_count=slide_count,
            extra_context=extra_context,
        )

        if not operations:
            return RevisionResult(
                False,
                error="Could not parse any revision operations from the instruction.",
            )

        # ── 2. Resolve reorder operations (fill in order if null) ─────────────
        operations = self._resolve_reorder(operations, slide_count)

        # ── 3. Execute all operations ─────────────────────────────────────────
        from core.sandbox.pptx_reviser import PptxReviser
        reviser = PptxReviser()

        # Separate reviser ops from automizer ops
        reviser_ops    = [op for op in operations if op["type"] in (
            "find_replace", "delete_slide", "reorder_slides",
            "update_table", "append_slides", "update_slide",
        )]
        automizer_ops  = [op for op in operations if op["type"] in (
            "set_text", "replace_tagged", "merge_slides",
        )]

        current_bytes = pptx_bytes

        # Run reviser ops
        if reviser_ops:
            revise_result = reviser.revise(
                pptx_bytes=current_bytes,
                revisions=reviser_ops,
                output_filename=output_filename,
            )
            if not revise_result.success:
                return RevisionResult(
                    False,
                    operations=operations,
                    error=f"PptxReviser failed: {revise_result.error}",
                    exec_time_ms=round((time.time() - start) * 1000, 2),
                )
            current_bytes = revise_result.data

        # Run automizer ops (via AutomizerSandbox update mode)
        if automizer_ops and current_bytes:
            import asyncio
            loop = asyncio.get_event_loop()
            auto_result = await loop.run_in_executor(
                None,
                self._run_automizer_ops,
                current_bytes, automizer_ops, output_filename,
            )
            if auto_result and auto_result.success:
                current_bytes = auto_result.data

        # ── 4. Build summary ──────────────────────────────────────────────────
        summary = self._build_summary(operations, instruction)

        return RevisionResult(
            success=True,
            pptx_bytes=current_bytes,
            filename=output_filename,
            operations=operations,
            summary=summary,
            exec_time_ms=round((time.time() - start) * 1000, 2),
        )

    async def parse_only(
        self,
        instruction:   str,
        slide_count:   int = 0,
        extra_context: str = "",
    ) -> List[Dict[str, Any]]:
        """Parse instruction to operations without executing (preview mode)."""
        ops = await self._parse_instruction(instruction, slide_count, extra_context)
        return self._resolve_reorder(ops, slide_count)

    # ──────────────────────────────────────────────────────────────────────────
    # Claude instruction parser
    # ──────────────────────────────────────────────────────────────────────────

    async def _parse_instruction(
        self,
        instruction:   str,
        slide_count:   int,
        extra_context: str,
    ) -> List[Dict[str, Any]]:
        """Call Claude to parse a natural language instruction into operations."""
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set — using heuristic parser")
                return self._heuristic_parse(instruction, slide_count)

            client = anthropic.AsyncAnthropic(api_key=api_key)

            context_block = ""
            if slide_count:
                context_block += f"\nThe presentation has {slide_count} slides (indices 0–{slide_count-1} in 0-based)."
            if extra_context:
                context_block += f"\nAdditional context: {extra_context}"

            user_message = (
                f"Revision instruction:{context_block}\n\n"
                f"\"{instruction}\"\n\n"
                f"Return the JSON operation array."
            )

            msg = await client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=_REVISION_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
            )

            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()

            ops = json.loads(raw)
            if isinstance(ops, list):
                return ops
            return []

        except Exception as exc:
            logger.warning("_parse_instruction (Claude) failed: %s — using heuristic", exc)
            return self._heuristic_parse(instruction, slide_count)

    # ──────────────────────────────────────────────────────────────────────────
    # Heuristic parser (fallback when Claude unavailable)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _heuristic_parse(instruction: str, slide_count: int) -> List[Dict[str, Any]]:
        """
        Simple regex-based fallback parser for common revision patterns.
        Used when Claude API is not available.
        """
        ops: List[Dict[str, Any]] = []
        text = instruction.lower()

        # find/replace: "change X to Y" / "replace X with Y"
        for pattern in [
            r'(?:change|update|replace)\s+"([^"]+)"\s+(?:to|with)\s+"([^"]+)"',
            r"(?:change|update|replace)\s+'([^']+)'\s+(?:to|with)\s+'([^']+)'",
            r"(?:change|update)\s+(\S+)\s+to\s+(\S+)",
        ]:
            m = re.search(pattern, instruction, re.IGNORECASE)
            if m:
                ops.append({"type": "find_replace", "find": m.group(1), "replace": m.group(2)})
                break

        # delete slide: "delete slide 5" / "remove slide 5"
        m = re.search(r"(?:delete|remove)\s+slide\s+(\d+)", text)
        if m:
            ops.append({"type": "delete_slide", "slide_index": int(m.group(1)) - 1})

        # move slide: "move slide X to position Y"
        m = re.search(r"move\s+slide\s+(\d+)\s+to\s+(?:position\s+)?(\d+)", text)
        if m:
            from_idx = int(m.group(1)) - 1
            to_idx   = int(m.group(2)) - 1
            if slide_count > 0:
                order = list(range(slide_count))
                if from_idx < slide_count:
                    order.remove(from_idx)
                    order.insert(to_idx, from_idx)
                ops.append({"type": "reorder_slides", "order": order})
            else:
                ops.append({
                    "type": "reorder_slides", "order": None,
                    "description": f"Move slide {m.group(1)} to position {m.group(2)}"
                })

        return ops

    # ──────────────────────────────────────────────────────────────────────────
    # Reorder resolver
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_reorder(ops: List[Dict], slide_count: int) -> List[Dict]:
        """
        For reorder_slides ops where order=null, compute the actual order
        from the operation description using slide_count.
        """
        for op in ops:
            if op.get("type") != "reorder_slides":
                continue
            if op.get("order") is not None:
                continue
            if slide_count <= 0:
                continue

            desc = op.get("description", "")
            # Try to extract "from_idx → to_idx" pattern
            m = re.search(r"slide\s+(\d+)\s+\(index\s+(\d+)\)\s+to\s+position\s+(\d+)\s+\(index\s+(\d+)\)", desc)
            if m:
                from_idx = int(m.group(2))
                to_idx   = int(m.group(4))
                order = list(range(slide_count))
                if from_idx < slide_count:
                    order.remove(from_idx)
                    order.insert(min(to_idx, len(order)), from_idx)
                op["order"] = order

        return ops

    # ──────────────────────────────────────────────────────────────────────────
    # Automizer ops runner
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _run_automizer_ops(pptx_bytes: bytes, ops: List[Dict], filename: str):
        """Execute automizer-native operations via AutomizerSandbox update mode."""
        from core.sandbox.automizer_sandbox import AutomizerSandbox

        # Map our op types to automizer mod specs
        slide_mods_map: Dict[int, List[Dict]] = {}
        global_replacements = []

        for op in ops:
            if op["type"] == "set_text":
                idx = op.get("slide_index", 0)
                slide_mods_map.setdefault(idx + 1, []).append({
                    "op":    "set_text",
                    "shape": op.get("shape_name", ""),
                    "text":  op.get("text", ""),
                })
            elif op["type"] == "replace_tagged":
                # Apply as global replacement  
                global_replacements.append({
                    "find":    f"{{{{{op.get('tag', '')}}}}}",
                    "replace": op.get("value", ""),
                })

        slide_modifications = [
            {"slide_number": snum, "modifications": mods}
            for snum, mods in slide_mods_map.items()
        ]

        spec = {
            "mode":               "update",
            "root_template":      "input.pptx",
            "filename":           filename,
            "global_replacements": global_replacements,
            "slide_modifications": slide_modifications,
        }

        sandbox = AutomizerSandbox()
        return sandbox.run(spec=spec, template_bytes=pptx_bytes)

    # ──────────────────────────────────────────────────────────────────────────
    # Summary builder
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_summary(ops: List[Dict], original_instruction: str) -> str:
        """Build a human-readable summary of what was done."""
        if not ops:
            return "No operations executed."

        lines = []
        for op in ops:
            t = op.get("type", "")
            if t == "find_replace":
                lines.append(f'• Replaced "{op.get("find")}" → "{op.get("replace")}" globally')
            elif t == "delete_slide":
                lines.append(f'• Deleted slide {op.get("slide_index", 0) + 1}')
            elif t == "reorder_slides":
                lines.append(f'• Reordered {len(op.get("order") or [])} slides')
            elif t == "update_table":
                lines.append(
                    f'• Updated table on slide {op.get("slide_index", 0)+1}, '
                    f'row {op.get("row", 0)+1}, col {op.get("col", 0)+1} '
                    f'→ "{op.get("value")}"'
                )
            elif t == "append_slides":
                lines.append(f'• Appended {len(op.get("slides", []))} new slide(s)')
            elif t == "update_slide":
                lines.append(f'• Updated content of slide {op.get("slide_index", 0)+1}')
            elif t == "set_text":
                lines.append(
                    f'• Set text of "{op.get("shape_name")}" on slide '
                    f'{op.get("slide_index", 0)+1}'
                )
            elif t == "replace_tagged":
                lines.append(f'• Replaced {{{{op.get("tag")}}}} → "{op.get("value")}"')
            else:
                lines.append(f'• {t} operation')

        return f'Applied {len(ops)} revision(s) to "{original_instruction}":\n' + "\n".join(lines)
