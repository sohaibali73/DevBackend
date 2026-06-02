"""
Skill Upload Pipeline
=====================
Pure(-ish) helpers for accepting a user-uploaded skill bundle:

    zip bytes  →  extract & validate  →  ParsedBundle
                                          ↓
                                  decide_storage_kind
                                          ↓
                                      materialize  →  on-disk folder

Two on-disk layouts are supported, auto-routed based on bundle contents:

  • lightweight  → core/skills/<slug>/   (skill.json + prompt.md)
  • bundle       → ClaudeSkills/<slug>/  (Anthropic SKILL.md format,
                                          may contain scripts/, references/,
                                          assets/, sub-skill folders)

This module never talks to the database or Supabase Storage — it only
manipulates bytes and the local filesystem. The HTTP route layer wires
those pieces together.
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # DevBackend/

LIGHTWEIGHT_ROOT = REPO_ROOT / "core" / "skills"
BUNDLE_ROOT = REPO_ROOT / "ClaudeSkills"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024          # 25 MB compressed
MAX_EXTRACTED_BYTES = 50 * 1024 * 1024       # 50 MB total uncompressed
MAX_FILE_COUNT = 500
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")

ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".json", ".yaml", ".yml",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs",
    ".csv", ".tsv",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".pdf",
    ".html", ".htm", ".css",
    ".xml",
}

# Folder names that, when present, automatically promote a skill to "bundle"
BUNDLE_INDICATOR_DIRS = {"scripts", "assets", "references", "examples", "templates"}

# ── Errors ─────────────────────────────────────────────────────────────────


class SkillUploadError(ValueError):
    """User-facing upload error. Carries an error code for the API layer."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class ExtractedFile:
    """A file within a parsed bundle, normalized to forward-slash relative path."""
    path: str          # e.g. "SKILL.md", "scripts/recalc.py"
    data: bytes


@dataclass
class ParsedBundle:
    """Fully validated, in-memory representation of an uploaded bundle."""
    slug: str
    name: str
    description: str
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    system_prompt: str = ""           # Body of SKILL.md (frontmatter stripped) or inline prompt
    skill_md_text: Optional[str] = None     # Raw SKILL.md including frontmatter, if present
    files: List[ExtractedFile] = field(default_factory=list)
    has_scripts: bool = False
    has_assets: bool = False
    has_references: bool = False
    warnings: List[str] = field(default_factory=list)
    bundle_size: int = 0

    @property
    def file_count(self) -> int:
        return len(self.files)


# ── Public API ─────────────────────────────────────────────────────────────


def extract_and_validate(
    zip_bytes: bytes,
    *,
    metadata_overrides: Optional[dict] = None,
) -> ParsedBundle:
    """
    Validate & parse an uploaded zip into a ParsedBundle.

    Raises SkillUploadError on any validation failure.
    """
    if zip_bytes is None or len(zip_bytes) == 0:
        raise SkillUploadError("EMPTY_UPLOAD", "Upload is empty.")
    if len(zip_bytes) > MAX_UPLOAD_BYTES:
        raise SkillUploadError(
            "BUNDLE_TOO_LARGE",
            f"Upload exceeds maximum size of {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r")
    except zipfile.BadZipFile as e:
        raise SkillUploadError("INVALID_ZIP", f"Not a valid zip file: {e}") from e

    files, warnings = _safe_extract(zf)
    files = _strip_common_prefix(files)

    if len(files) == 0:
        raise SkillUploadError("EMPTY_UPLOAD", "Zip contains no usable files.")

    # Locate metadata sources
    skill_md = _find_file(files, "SKILL.md")
    skill_json = _find_file(files, "skill.json")
    prompt_md = _find_file(files, "prompt.md")

    metadata: dict = {}
    skill_md_text: Optional[str] = None
    body_text = ""

    if skill_md is not None:
        skill_md_text = skill_md.data.decode("utf-8", errors="replace")
        fm, body = _parse_frontmatter(skill_md_text)
        metadata.update(fm)
        body_text = body
    elif skill_json is not None:
        try:
            metadata.update(json.loads(skill_json.data.decode("utf-8", errors="replace")))
        except json.JSONDecodeError as e:
            raise SkillUploadError("INVALID_SKILL_JSON",
                                   f"skill.json is not valid JSON: {e}") from e
        if prompt_md is not None:
            body_text = prompt_md.data.decode("utf-8", errors="replace").strip()
    else:
        raise SkillUploadError(
            "MISSING_SKILL_MD",
            "Bundle must contain either SKILL.md (with YAML frontmatter) "
            "or skill.json (+ optional prompt.md) at its root.",
        )

    # Apply caller overrides on top of file-based metadata
    if metadata_overrides:
        for k, v in metadata_overrides.items():
            if v is not None and v != "":
                metadata[k] = v

    # Normalize fields
    name = str(metadata.get("name") or "").strip()
    if not name:
        raise SkillUploadError("MISSING_NAME", "Skill metadata is missing required field: name.")
    description = str(metadata.get("description") or "").strip()
    if not description:
        raise SkillUploadError("MISSING_DESCRIPTION",
                               "Skill metadata is missing required field: description.")

    slug = str(metadata.get("slug") or "").strip().lower() or _slugify(name)
    if not SLUG_RE.match(slug):
        raise SkillUploadError(
            "BAD_SLUG",
            f"Slug '{slug}' is invalid. Must be kebab-case, 3–64 chars, "
            f"lowercase letters/digits/hyphens only, starting with a letter.",
        )

    category = str(metadata.get("category") or "general").strip().lower() or "general"
    tags_raw = metadata.get("tags") or []
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in re.split(r"[,;\s]+", tags_raw) if t.strip()]
    else:
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]

    # Detect indicator dirs
    has_scripts = any(f.path.startswith("scripts/") for f in files)
    has_assets = any(f.path.startswith("assets/") for f in files)
    has_references = any(f.path.startswith("references/") for f in files)

    bundle = ParsedBundle(
        slug=slug,
        name=name,
        description=description,
        category=category,
        tags=tags,
        system_prompt=body_text.strip(),
        skill_md_text=skill_md_text,
        files=files,
        has_scripts=has_scripts,
        has_assets=has_assets,
        has_references=has_references,
        warnings=warnings,
        bundle_size=sum(len(f.data) for f in files),
    )
    return bundle


def synthesize_inline_bundle(
    *,
    name: str,
    description: str,
    system_prompt: str,
    slug: Optional[str] = None,
    category: str = "general",
    tags: Optional[List[str]] = None,
) -> Tuple[bytes, ParsedBundle]:
    """
    Build a minimal SKILL.md bundle from inline form fields and return
    BOTH the raw zip bytes (for archival in Supabase Storage) and the
    parsed bundle (for materialization).
    """
    name = (name or "").strip()
    description = (description or "").strip()
    system_prompt = (system_prompt or "").strip()
    if not name:
        raise SkillUploadError("MISSING_NAME", "Skill name is required.")
    if not description:
        raise SkillUploadError("MISSING_DESCRIPTION", "Skill description is required.")
    if not system_prompt:
        raise SkillUploadError("MISSING_PROMPT", "Skill system prompt is required.")

    slug = (slug or "").strip().lower() or _slugify(name)
    if not SLUG_RE.match(slug):
        raise SkillUploadError("BAD_SLUG", f"Invalid slug '{slug}'.")

    tags = tags or []
    # Emit human `name` (YAML-quoted) and `slug` separately — see _synthesize_skill_md.
    fm_lines = [
        "---",
        f"name: {_yaml_dq(name)}",
        f"slug: {slug}",
        "description: >",
    ]
    for line in _wrap_yaml_block(description, indent=2):
        fm_lines.append(line)
    fm_lines.append(f"category: {category}")
    if tags:
        fm_lines.append(f"tags: [{', '.join(tags)}]")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(f"# {name}")
    fm_lines.append("")
    fm_lines.append(system_prompt)
    skill_md = "\n".join(fm_lines).strip() + "\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_md)

    zip_bytes = buf.getvalue()
    parsed = extract_and_validate(
        zip_bytes,
        metadata_overrides={
            "slug": slug, "name": name, "description": description,
            "category": category, "tags": tags,
        },
    )
    parsed.system_prompt = system_prompt
    return zip_bytes, parsed


def decide_storage_kind(p: ParsedBundle) -> str:
    """Auto-route a parsed bundle to 'lightweight' or 'bundle' on-disk layout."""
    if p.has_scripts or p.has_assets or p.has_references:
        return "bundle"
    # Any nested folders at all → treat as bundle
    if any("/" in f.path for f in p.files):
        return "bundle"
    return "lightweight"


def materialize(p: ParsedBundle, kind: str) -> Path:
    """
    Write a ParsedBundle to disk under the appropriate root.

    Atomic-ish: writes to a sibling temp dir, then os.replace's it into place.
    Refuses to overwrite an existing folder — caller must delete first.
    """
    if kind not in ("lightweight", "bundle"):
        raise ValueError(f"Unknown storage kind: {kind}")

    root = LIGHTWEIGHT_ROOT if kind == "lightweight" else BUNDLE_ROOT
    target = root / p.slug
    if target.exists():
        raise SkillUploadError(
            "SLUG_TAKEN",
            f"Skill folder already exists at {target.relative_to(REPO_ROOT)}. "
            f"Delete it first or pick a different slug.",
        )

    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{p.slug}-", dir=str(root)))

    try:
        if kind == "lightweight":
            _write_lightweight(p, tmp)
        else:
            _write_bundle(p, tmp)

        # Atomic move into place
        import os
        os.replace(str(tmp), str(target))
    except Exception:
        # Cleanup on failure
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        raise

    return target


def delete_on_disk(slug: str) -> Optional[Path]:
    """
    Remove a user skill folder. Returns the deleted path, or None if not found.
    Refuses to touch anything outside the two known roots.
    """
    if not SLUG_RE.match(slug):
        raise SkillUploadError("BAD_SLUG", f"Invalid slug: {slug}")

    for root in (LIGHTWEIGHT_ROOT, BUNDLE_ROOT):
        candidate = (root / slug).resolve()
        # Defense-in-depth: ensure resolved path is *inside* the root
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.exists() and candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=False)
            return candidate
    return None


def repack_folder_to_zip(folder: Path) -> bytes:
    """Re-zip an existing skill folder into a single zip blob."""
    folder = folder.resolve()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in folder.rglob("*"):
            if entry.is_file():
                arcname = str(entry.relative_to(folder)).replace("\\", "/")
                zf.write(entry, arcname=arcname)
    return buf.getvalue()


# ── Internals ──────────────────────────────────────────────────────────────


def _safe_extract(zf: zipfile.ZipFile) -> Tuple[List[ExtractedFile], List[str]]:
    """Stream-extract zip contents into memory with validation."""
    files: List[ExtractedFile] = []
    warnings: List[str] = []
    total_uncompressed = 0

    infos = zf.infolist()
    if len(infos) > MAX_FILE_COUNT:
        raise SkillUploadError(
            "TOO_MANY_FILES",
            f"Bundle contains {len(infos)} entries (max {MAX_FILE_COUNT}).",
        )

    for info in infos:
        name = info.filename
        if info.is_dir():
            continue

        # Reject path traversal & absolute paths
        norm = name.replace("\\", "/")
        if norm.startswith("/") or ".." in Path(norm).parts:
            raise SkillUploadError("UNSAFE_PATH",
                                   f"Refusing unsafe path in zip: {name}")

        # Reject symlinks (zipfile encodes via external_attr top byte 0xA0)
        try:
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:  # S_IFLNK
                raise SkillUploadError("UNSAFE_PATH",
                                       f"Symlinks are not allowed: {name}")
        except Exception:
            pass

        ext = Path(norm).suffix.lower()
        if ext and ext not in ALLOWED_EXTENSIONS:
            warnings.append(f"Skipped disallowed file: {norm}")
            continue
        if not ext and Path(norm).name not in {"LICENSE", "README"}:
            warnings.append(f"Skipped extension-less file: {norm}")
            continue

        # Size guard per file (prevent zip-bomb single entry)
        if info.file_size > MAX_EXTRACTED_BYTES:
            raise SkillUploadError(
                "BUNDLE_TOO_LARGE",
                f"File {norm} is too large ({info.file_size} bytes).",
            )

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_EXTRACTED_BYTES:
            raise SkillUploadError(
                "BUNDLE_TOO_LARGE",
                f"Total uncompressed size exceeds "
                f"{MAX_EXTRACTED_BYTES // (1024*1024)} MB.",
            )

        with zf.open(info, "r") as fh:
            data = fh.read()
        files.append(ExtractedFile(path=norm, data=data))

    return files, warnings


def _strip_common_prefix(files: List[ExtractedFile]) -> List[ExtractedFile]:
    """If every file shares a single top-level folder, strip it."""
    if not files:
        return files
    tops = {f.path.split("/", 1)[0] for f in files if "/" in f.path}
    # Only strip if there is exactly one top-level dir AND no root-level files
    root_files = [f for f in files if "/" not in f.path]
    if len(tops) == 1 and not root_files:
        prefix = next(iter(tops)) + "/"
        return [
            ExtractedFile(path=f.path[len(prefix):], data=f.data)
            for f in files
            if f.path.startswith(prefix) and len(f.path) > len(prefix)
        ]
    return files


def _find_file(files: List[ExtractedFile], name: str) -> Optional[ExtractedFile]:
    for f in files:
        if f.path == name:
            return f
    # Case-insensitive fallback
    target = name.lower()
    for f in files:
        if f.path.lower() == target:
            return f
    return None


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Extract YAML frontmatter from a markdown string. Returns (metadata, body)."""
    m = _FRONTMATTER_RE.match(text.lstrip("\ufeff"))
    if not m:
        return {}, text
    yaml_text, body = m.group(1), m.group(2)
    try:
        import yaml  # PyYAML
        meta = yaml.safe_load(yaml_text) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception as e:
        logger.warning("Frontmatter YAML parse failed: %s", e)
        meta = {}
    return meta, body


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        s = "skill"
    if not s[0].isalpha():
        s = "s-" + s
    return s[:64]


def _wrap_yaml_block(text: str, *, indent: int = 2, width: int = 80) -> Iterable[str]:
    """Wrap a long string into a YAML folded-block style body."""
    pad = " " * indent
    line: list[str] = []
    cur = 0
    for word in text.split():
        if cur + len(word) + 1 > width and line:
            yield pad + " ".join(line)
            line = [word]
            cur = len(word)
        else:
            line.append(word)
            cur += len(word) + 1
    if line:
        yield pad + " ".join(line)


def _write_lightweight(p: ParsedBundle, target_dir: Path) -> None:
    """Write a lightweight skill (skill.json + prompt.md) into target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    skill_json_obj = {
        "slug": p.slug,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "tags": p.tags,
        "tools": [],
        "output_type": "text",
        "max_tokens": 8192,
        "timeout": 120,
        "enabled": True,
        "aliases": [],
    }
    (target_dir / "skill.json").write_text(
        json.dumps(skill_json_obj, indent=2), encoding="utf-8"
    )
    (target_dir / "prompt.md").write_text(
        (p.system_prompt or "").strip() + "\n", encoding="utf-8"
    )


def _write_bundle(p: ParsedBundle, target_dir: Path) -> None:
    """Write a full bundle (verbatim file tree) into target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    have_skill_md = False
    for f in p.files:
        out = target_dir / f.path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(f.data)
        if f.path == "SKILL.md":
            have_skill_md = True

    # Ensure SKILL.md exists at root (synthesize if user uploaded skill.json bundle)
    if not have_skill_md:
        (target_dir / "SKILL.md").write_text(
            _synthesize_skill_md(p), encoding="utf-8"
        )


def _yaml_dq(s: str) -> str:
    """Render a string as a YAML double-quoted scalar (handles names with
    colons, quotes, etc.). The loader reads the display name straight from
    this frontmatter, so it must round-trip safely."""
    return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def _synthesize_skill_md(p: ParsedBundle) -> str:
    # Emit the human `name` and the kebab `slug` as SEPARATE fields. The loader
    # derives the display name from `name` and the id from `slug`; collapsing
    # them (name = slug) made uploaded skills show their slug as their name.
    lines = [
        "---",
        f"name: {_yaml_dq(p.name)}",
        f"slug: {p.slug}",
        "description: >",
    ]
    for line in _wrap_yaml_block(p.description, indent=2):
        lines.append(line)
    lines.append(f"category: {p.category}")
    if p.tags:
        lines.append(f"tags: [{', '.join(p.tags)}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {p.name}")
    lines.append("")
    lines.append(p.system_prompt or "")
    return "\n".join(lines).rstrip() + "\n"
