"""
Skill Gateway – Execute Claude custom beta skills
===================================================
Thin wrapper around ``anthropic.Anthropic.beta.messages`` that activates a
registered skill from the central registry (``core.skills``) and returns the
response.  Supports both blocking and streaming modes.

Usage::

    gateway = SkillGateway(api_key="sk-ant-…")
    result  = gateway.execute("backtest-expert", "Analyze this equity curve …")
    # result = {"text": "…", "skill": "backtest-expert", "usage": {…}, …}

    # Streaming
    for chunk in gateway.stream("quant-analyst", "Build a momentum strategy …"):
        print(chunk["content"], end="")
"""

import json
import logging
import time
from typing import Any, Dict, Generator, List, Optional

import anthropic

from core.skills import (
    CODE_EXECUTION_TOOL,
    SKILL_REGISTRY,
    SKILLS_BETAS,
    SkillDefinition,
    get_skill,
)

logger = logging.getLogger(__name__)

# Default model (same as the rest of the platform)
DEFAULT_MODEL = "claude-sonnet-4-6"  # FIX-12: was claude-haiku-4-5-20251001


class SkillGateway:
    """Execute any registered custom beta skill via the Claude API."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
    ):
        self.api_key = api_key
        self.model = model
        self._client: Optional[anthropic.Anthropic] = None

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------
    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    # ------------------------------------------------------------------
    # Public API – blocking
    # ------------------------------------------------------------------
    def execute(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Dict[str, Any]:
        """
        Execute a skill and return the full response.

        Parameters
        ----------
        skill_slug : str
            Slug of the skill (e.g. ``"backtest-expert"``).
        user_message : str
            The user's prompt / request.
        system_prompt : str, optional
            Override the skill's default system prompt.
        conversation_history : list, optional
            Prior messages in Anthropic format (``[{"role": …, "content": …}]``).
        max_tokens : int, optional
            Override the skill's default ``max_tokens``.
        extra_context : str
            Additional context appended to the system prompt (e.g. KB context).

        Returns
        -------
        dict
            ``{"text", "skill", "usage", "model", "execution_time"}``
        """
        skill = self._resolve_skill(skill_slug)
        sys_prompt = self._build_system_prompt(skill, system_prompt, extra_context)
        messages = self._build_messages(user_message, conversation_history)
        tokens = max_tokens or skill.max_tokens

        start = time.time()
        try:
            # "files-api-2025-04-14" is required to retrieve generated files
            # after the skill run (docx/pptx skills save files in the container).
            active_betas = list(SKILLS_BETAS) + ["files-api-2025-04-14"]

            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=tokens,
                system=sys_prompt,
                messages=messages,
                betas=active_betas,
                container=skill.to_container(),
                tools=[CODE_EXECUTION_TOOL],
            )
            text = self._extract_text(response)
            files = self._extract_files(response)
            elapsed = time.time() - start

            result = {
                "text": text,
                "skill": skill.slug,
                "skill_name": skill.name,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "model": response.model,
                "execution_time": round(elapsed, 2),
                "stop_reason": response.stop_reason,
            }

            # Include file artifacts if the skill produced any (DOCX/PPTX skills)
            if files:
                result["files"] = files
                logger.info(
                    "Skill %s produced %d file artifact(s)", skill_slug, len(files)
                )

            return result

        except anthropic.APIError as exc:
            logger.error("Skill %s API error: %s", skill_slug, exc)
            raise
        except Exception as exc:
            logger.error("Skill %s execution error: %s", skill_slug, exc, exc_info=True)
            raise

    def download_files(self, file_refs: list) -> list:
        """Download file artifacts returned by execute().

        Parameters
        ----------
        file_refs : list
            The ``result["files"]`` list from ``execute()`` —
            each item is ``{"file_id": "file_abc123"}``.

        Returns
        -------
        list of dicts:
            [{"file_id": ..., "filename": ..., "content": <bytes>}, ...]

        Usage::

            result = gateway.execute("potomac-docx-skill", "Create a fund fact sheet…")
            if result.get("files"):
                downloaded = gateway.download_files(result["files"])
                for f in downloaded:
                    with open(f["filename"], "wb") as fh:
                        fh.write(f["content"])
        """
        downloaded = []
        for ref in file_refs:
            file_id = ref.get("file_id")
            if not file_id:
                continue
            try:
                meta = self.client.beta.files.retrieve_metadata(
                    file_id,
                    betas=["files-api-2025-04-14"],
                )
                raw = self.client.beta.files.download(
                    file_id,
                    betas=["files-api-2025-04-14"],
                )
                # SDK returns a streaming response; read all bytes
                content = b"".join(raw.iter_bytes()) if hasattr(raw, "iter_bytes") else raw.read()
                downloaded.append({
                    "file_id": file_id,
                    "filename": getattr(meta, "filename", f"{file_id}.docx"),
                    "content": content,
                })
                logger.info("Downloaded file %s (%d bytes)", file_id, len(content))
            except Exception as exc:
                logger.error("Failed to download file %s: %s", file_id, exc)
        return downloaded

    # ------------------------------------------------------------------
    # Public API – streaming
    # ------------------------------------------------------------------
    def stream(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Stream a skill response chunk-by-chunk.

        Yields dicts with ``{"type": "chunk"|"complete"|"error", …}``.
        """
        skill = self._resolve_skill(skill_slug)
        sys_prompt = self._build_system_prompt(skill, system_prompt, extra_context)
        messages = self._build_messages(user_message, conversation_history)
        tokens = max_tokens or skill.max_tokens

        start = time.time()
        full_text = ""

        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=tokens,
                system=sys_prompt,
                messages=messages,
                betas=SKILLS_BETAS,
                container=skill.to_container(),
                tools=[CODE_EXECUTION_TOOL],
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    yield {
                        "type": "chunk",
                        "content": text,
                    }

            elapsed = time.time() - start
            yield {
                "type": "complete",
                "text": full_text,
                "skill": skill.slug,
                "skill_name": skill.name,
                "execution_time": round(elapsed, 2),
            }

        except Exception as exc:
            logger.error("Skill %s stream error: %s", skill_slug, exc, exc_info=True)
            yield {
                "type": "error",
                "error": str(exc),
                "skill": skill_slug,
            }

    # ------------------------------------------------------------------
    # Public API – Vercel AI SDK v7 Beta UI Message Stream Protocol streaming
    # ------------------------------------------------------------------
    def stream_ai_sdk(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Generator[str, None, None]:
        """
        Stream response in Vercel AI SDK v7 Beta UI Message Stream Protocol format.

        Yields pre-formatted JSON objects ready to be sent as an SSE-style stream::

            {"type":"start","messageId":"msg_…"}\\n
            {"type":"text-start","id":"text_…"}\\n
            {"type":"text-delta","id":"text_…","delta":"chunk of text"}\\n
            …
            {"type":"text-end","id":"text_…"}\\n
            {"type":"finish","finishReason":"stop"}\\n

        This is compatible with ``useChat()`` from @ai-sdk/react v7 Beta on the
        Next.js frontend.
        """
        skill = self._resolve_skill(skill_slug)
        sys_prompt = self._build_system_prompt(skill, system_prompt, extra_context)
        messages = self._build_messages(user_message, conversation_history)
        tokens = max_tokens or skill.max_tokens

        import re as _re

        start = time.time()
        full_text = ""
        message_id = f"msg_{int(time.time() * 1000)}"
        text_id = f"text_{int(time.time() * 1000)}"

        try:
            # Include files-api beta so we can retrieve generated files after streaming
            active_betas = list(SKILLS_BETAS) + ["files-api-2025-04-14"]

            # v7 Beta: Emit start chunk
            yield json.dumps({"type": "start", "messageId": message_id}) + "\n"

            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=tokens,
                system=sys_prompt,
                messages=messages,
                betas=active_betas,
                container=skill.to_container(),
                tools=[CODE_EXECUTION_TOOL],
            ) as stream:
                # IMPORTANT: Buffer ALL text — do NOT stream it to the client yet.
                #
                # Claude's narration often contains the ephemeral Claude file ID URL
                # (e.g. "/files/file_011CZnXtx.../download") which we must strip before
                # sending to the user.  We only know whether files were produced AFTER
                # the full stream completes, so we cannot clean in real-time.
                #
                # For document-generation skills the user sees the Shimmer/"Thinking…"
                # indicator during this period — no UX regression.
                for text in stream.text_stream:
                    full_text += text

                # Get the final message to extract file artifacts
                final_msg = stream.get_final_message()

            elapsed = time.time() - start

            # Extract file artifacts from the final message
            files = self._extract_files(final_msg) if final_msg else []

            # ── Clean and emit buffered text ─────────────────────────────────
            # If the skill produced files, strip every reference to Claude's
            # ephemeral file IDs from the text before sending it to the client.
            # Those URLs (file_xxx) are now replaced by permanent Railway UUIDs
            # carried in the data-file_download event below.
            text_to_emit = full_text
            if files:
                # Remove any "/files/file_<id>/download" links Claude wrote
                text_to_emit = _re.sub(
                    r'/files/file_[A-Za-z0-9_-]+/download',
                    '',
                    text_to_emit,
                )
                # Also strip bare "file_<id>" references
                text_to_emit = _re.sub(
                    r'\bfile_[A-Za-z0-9]{20,}\b',
                    '',
                    text_to_emit,
                )
                # Collapse repeated blank lines left by the removal
                text_to_emit = _re.sub(r'\n{3,}', '\n\n', text_to_emit).strip()

            if text_to_emit:
                yield json.dumps({"type": "text-start", "id": text_id}) + "\n"
                yield json.dumps({"type": "text-delta", "id": text_id, "delta": text_to_emit}) + "\n"
                yield json.dumps({"type": "text-end", "id": text_id}) + "\n"

            # If files were produced, download them and emit download events
            if files:
                try:
                    from core.file_store import store_file
                    downloaded = self.download_files(files)
                    for dl in downloaded:
                        fname = dl.get("filename", "")
                        data = dl.get("content", b"")
                        claude_file_id = dl.get("file_id", "")
                        if data and fname:
                            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "bin"
                            entry = store_file(
                                data=data,
                                filename=fname,
                                file_type=ext,
                                tool_name=f"skill:{skill.slug}",
                                # Do NOT pass claude_file_id — let store_file generate
                                # a permanent backend UUID so the download URL is
                                # always served from Railway/Supabase, never from
                                # Claude's ephemeral Files API (expires in 72 h).
                            )
                            # v7 Beta: Emit file download event as data-{name}
                            yield json.dumps({
                                "type": "data-file_download",
                                "data": {
                                    "type": "file_download",
                                    "file_id": entry.file_id,
                                    "filename": entry.filename,
                                    "download_url": f"/files/{entry.file_id}/download",
                                    "file_type": entry.file_type,
                                    "size_kb": entry.size_kb,
                                    "tool_name": f"skill:{skill.slug}",
                                    "created_at": int(time.time())
                                }
                            }) + "\n"
                            logger.info(
                                "Skill %s stream produced file: %s (%.1f KB)",
                                skill_slug, fname, entry.size_kb
                            )
                except Exception as dl_err:
                    logger.warning("Failed to download streamed skill files: %s", dl_err)

            # v7 Beta: Emit finish message
            usage = {"promptTokens": 0, "completionTokens": 0}
            if final_msg and hasattr(final_msg, "usage"):
                usage = {
                    "promptTokens": final_msg.usage.input_tokens,
                    "completionTokens": final_msg.usage.output_tokens,
                }

            finish_data = {
                "finishReason": "stop",
                "usage": usage,
                "skill": skill.slug,
                "skillName": skill.name,
                "executionTime": round(elapsed, 2),
            }
            yield json.dumps({"type": "finish", **finish_data}) + "\n"

        except Exception as exc:
            logger.error("Skill %s AI SDK stream error: %s", skill_slug, exc, exc_info=True)
            # v7 Beta: Emit error chunk
            yield json.dumps({"type": "error", "errorText": str(exc)}) + "\n"

    # ------------------------------------------------------------------
    # Multi-skill execution
    # ------------------------------------------------------------------
    def execute_multi(
        self,
        skill_requests: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple skills sequentially and collect results.

        Each item in ``skill_requests`` should have at minimum:
        ``{"skill_slug": "…", "message": "…"}``, plus optional overrides.
        """
        results = []
        for req in skill_requests:
            slug = req["skill_slug"]
            message = req["message"]
            try:
                result = self.execute(
                    slug,
                    message,
                    system_prompt=req.get("system_prompt"),
                    max_tokens=req.get("max_tokens"),
                    extra_context=req.get("extra_context", ""),
                )
                results.append(result)
            except Exception as exc:
                results.append({
                    "skill": slug,
                    "error": str(exc),
                    "text": "",
                })
        return results

    # ------------------------------------------------------------------
    # Async wrappers for FastAPI / asyncio contexts  (FIX-14)
    # ------------------------------------------------------------------
    # SkillGateway uses the synchronous anthropic.Anthropic client, which
    # blocks the calling thread for the full duration of the API call.
    # When called directly from an async FastAPI route this stalls the
    # event loop, preventing other requests from being served.
    #
    # These thin wrappers run the synchronous methods in a thread-pool
    # executor so the event loop stays free.  Use them everywhere you
    # would previously have called execute() / execute_multi() from async
    # code.
    # ------------------------------------------------------------------

    async def execute_async(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Dict[str, Any]:
        """
        Async wrapper around ``execute()`` for use in FastAPI routes.

        Runs the synchronous Anthropic client call in a thread-pool executor
        so the asyncio event loop is not blocked.

        Example::

            result = await gateway.execute_async("backtest-expert", user_msg)
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute(
                skill_slug,
                user_message,
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                max_tokens=max_tokens,
                extra_context=extra_context,
            ),
        )

    async def execute_multi_async(
        self,
        skill_requests: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Async wrapper around ``execute_multi()`` for use in FastAPI routes.

        Each skill request runs sequentially in a thread-pool executor.
        For parallel execution, call ``execute_async()`` individually with
        ``asyncio.gather()``.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute_multi(skill_requests),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_skill(slug: str) -> SkillDefinition:
        """Look up a skill or raise ValueError."""
        skill = get_skill(slug)
        if skill is None:
            available = ", ".join(sorted(SKILL_REGISTRY.keys()))
            raise ValueError(
                f"Unknown skill '{slug}'. Available skills: {available}"
            )
        if not skill.enabled:
            raise ValueError(f"Skill '{slug}' is currently disabled.")
        return skill

    @staticmethod
    def _build_system_prompt(
        skill: SkillDefinition,
        override: Optional[str],
        extra_context: str,
    ) -> str:
        prompt = override or skill.system_prompt or ""
        if extra_context:
            prompt += f"\n\n## Additional Context\n{extra_context}"
        return prompt

    @staticmethod
    def _build_messages(
        user_message: str,
        history: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def _extract_text(response) -> str:
        """Concatenate all text blocks from a beta response.

        Handles the actual API response structure for code_execution_20250825:
          - text blocks → block.text
          - bash_code_execution_tool_result → block.content.stdout (only when
            NO file was produced — if a file exists, stdout is just narration
            noise from the generation script and should not be surfaced)
          - text_editor_code_execution_tool_result → ignored (file ops, no text)

        NOTE: For document-generation skills (docx/pptx) the stdout often
        contains the skill's own progress narration ("Reading skill...",
        directory listings, etc.).  We deliberately skip stdout when the
        response contains file artifacts so that narration doesn't leak into
        the returned text or, worse, get embedded in the document content.
        """
        # First pass: check whether any files were produced
        has_files = False
        for block in response.content:
            if getattr(block, "type", "") == "bash_code_execution_tool_result":
                inner = getattr(block, "content", None)
                if inner and getattr(inner, "type", "") == "bash_code_execution_result":
                    for item in getattr(inner, "content", []) or []:
                        if getattr(item, "file_id", None):
                            has_files = True
                            break

        parts = []
        for block in response.content:
            block_type = getattr(block, "type", "")

            # Standard text blocks (Claude's narrative response)
            if hasattr(block, "text"):
                parts.append(block.text)

            # Bash execution results — skip stdout when files were produced
            elif block_type == "bash_code_execution_tool_result":
                if has_files:
                    # stdout is just generation-script narration; don't surface it
                    continue
                inner = getattr(block, "content", None)
                if inner is None:
                    continue
                inner_type = getattr(inner, "type", "")
                if inner_type == "bash_code_execution_result":
                    stdout = getattr(inner, "stdout", "") or ""
                    if stdout.strip():
                        parts.append(stdout)
                elif inner_type == "bash_code_execution_tool_result_error":
                    err_code = getattr(inner, "error_code", "unknown")
                    logger.warning("Code execution error block: %s", err_code)

        return "\n".join(p for p in parts if p)

    @staticmethod
    def _extract_files(response) -> list:
        """Extract file_ids produced by code execution (docx/pptx skills).

        The API does NOT embed base64 file data in the response.  Instead it
        returns a ``file_id`` for each generated file; callers must download
        the content separately via ``client.beta.files.download(file_id)``.

        Actual response structure (code_execution_20250825):
            block.type == "bash_code_execution_tool_result"
              block.content.type == "bash_code_execution_result"
                block.content.content[n]  ← output item
                  .file_id  (str)  ← present when the script saved a file

        Returns
        -------
        list of dicts: [{"file_id": "file_abc123"}, ...]
        Callers are responsible for downloading via the Files API:
            bytes = client.beta.files.download(file_id)
        """
        files = []
        for block in response.content:
            if getattr(block, "type", "") != "bash_code_execution_tool_result":
                continue
            inner = getattr(block, "content", None)
            if inner is None:
                continue
            if getattr(inner, "type", "") != "bash_code_execution_result":
                continue
            for item in getattr(inner, "content", []) or []:
                file_id = getattr(item, "file_id", None)
                if file_id:
                    files.append({"file_id": file_id})
        return files