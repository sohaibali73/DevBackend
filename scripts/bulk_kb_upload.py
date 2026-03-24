#!/usr/bin/env python3
"""
bulk_kb_upload.py — Local script to bulk-upload files to the shared KB.

Usage:
  # Upload every file in a directory
  python scripts/bulk_kb_upload.py --dir ./docs --url https://your-app.railway.app --key YOUR_SECRET

  # Upload specific files
  python scripts/bulk_kb_upload.py --files report.pdf notes.docx --url https://... --key YOUR_SECRET

  # Add category and tags
  python scripts/bulk_kb_upload.py --dir ./research --category research --tags "2024,earnings" ...

  # Dry-run (show what would be uploaded without actually uploading)
  python scripts/bulk_kb_upload.py --dir ./docs --dry-run ...

  # Use .env file for URL + key (no flags needed each time)
  python scripts/bulk_kb_upload.py --dir ./docs --env-file .env.local

Requirements:
  pip install requests tqdm python-dotenv
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# SUPPORTED EXTENSIONS
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv",
    ".txt", ".md", ".html", ".htm", ".pptx", ".ppt",
    ".json", ".xml", ".rtf",
}

# Files to skip outright
SKIP_PATTERNS = {
    ".DS_Store", "Thumbs.db", "desktop.ini",
    ".gitkeep", ".gitignore",
}

# How many files to POST in a single multipart request
BATCH_SIZE = 20

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _color(code: str, text: str) -> str:
    """ANSI colour helper (auto-disabled when not a TTY)."""
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

def ok(msg):   print(_color("32", f"  ✓ {msg}"))
def warn(msg): print(_color("33", f"  ~ {msg}"))
def err(msg):  print(_color("31", f"  ✗ {msg}"))
def info(msg): print(_color("36", f"  → {msg}"))


def _collect_files(paths: List[str], recursive: bool) -> List[Path]:
    """
    Expand directory paths and filter to supported extensions.
    Returns a list of unique file paths.
    """
    collected: List[Path] = []
    seen = set()

    for p_str in paths:
        p = Path(p_str)
        if p.is_file():
            if p.name not in SKIP_PATTERNS and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                if p not in seen:
                    collected.append(p)
                    seen.add(p)
        elif p.is_dir():
            glob_fn = p.rglob if recursive else p.glob
            for fp in sorted(glob_fn("*")):
                if (
                    fp.is_file()
                    and fp.name not in SKIP_PATTERNS
                    and fp.suffix.lower() in SUPPORTED_EXTENSIONS
                ):
                    if fp not in seen:
                        collected.append(fp)
                        seen.add(fp)
        else:
            warn(f"Path not found, skipping: {p_str}")

    return collected


def _chunked(lst: list, size: int):
    """Yield successive chunks of `size` from `lst`."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _post_batch(
    session,
    url: str,
    secret: str,
    file_paths: List[Path],
    category: str,
    tags: str,
    timeout: int,
) -> dict:
    """POST one batch of files and return the parsed JSON response."""
    file_handles = []
    try:
        files_field = []
        for fp in file_paths:
            fh = open(fp, "rb")
            file_handles.append(fh)
            files_field.append(("files", (fp.name, fh, _guess_mime(fp))))

        data = {"category": category}
        if tags:
            data["tags"] = tags

        resp = session.post(
            f"{url.rstrip('/')}/kb-admin/bulk-upload",
            headers={"X-Admin-Key": secret},
            files=files_field,
            data=data,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    finally:
        for fh in file_handles:
            try:
                fh.close()
            except OSError:
                pass


def _guess_mime(fp: Path) -> str:
    """Guess MIME type from extension."""
    mapping = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".ppt": "application/vnd.ms-powerpoint",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".json": "application/json",
        ".xml": "application/xml",
        ".rtf": "application/rtf",
    }
    return mapping.get(fp.suffix.lower(), "application/octet-stream")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Bulk-upload files to the shared KB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--dir",   nargs="+", metavar="DIR",  help="Directory (or directories) to upload")
    input_group.add_argument("--files", nargs="+", metavar="FILE", help="Specific files to upload")

    parser.add_argument("--recursive", action="store_true", default=True,
                        help="Recurse into subdirectories (default: True)")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false",
                        help="Do NOT recurse into subdirectories")

    # Server
    parser.add_argument("--url",     metavar="URL",    help="API base URL (e.g. https://your-app.railway.app)")
    parser.add_argument("--key",     metavar="SECRET", help="ADMIN_UPLOAD_SECRET value")
    parser.add_argument("--env-file",metavar="FILE",   help=".env file to read URL and KEY from")

    # Metadata
    parser.add_argument("--category", default="general", help="KB category (default: general)")
    parser.add_argument("--tags",     default="",        help='Comma-separated tags (e.g. "2024,research")')

    # Behaviour
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help=f"Files per HTTP request (default: {BATCH_SIZE})")
    parser.add_argument("--timeout",    type=int, default=120,
                        help="Request timeout in seconds (default: 120)")
    parser.add_argument("--dry-run",    action="store_true",
                        help="List files that WOULD be uploaded without actually uploading")
    parser.add_argument("--json-output", action="store_true",
                        help="Print a JSON summary at the end instead of human-readable output")
    parser.add_argument("--check",    action="store_true",
                        help="Query /kb-admin/stats and exit (verify connection + secret)")

    args = parser.parse_args()

    # ── Load env file ──────────────────────────────────────────────────────────
    if args.env_file:
        env_path = Path(args.env_file)
        if not env_path.exists():
            err(f"--env-file not found: {env_path}")
            sys.exit(1)
        try:
            from dotenv import dotenv_values
            env = dotenv_values(env_path)
        except ImportError:
            # manual parse if python-dotenv not installed
            env = {}
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip().strip('"').strip("'")

        args.url = args.url or env.get("KB_UPLOAD_URL") or env.get("API_URL")
        args.key = args.key or env.get("ADMIN_UPLOAD_SECRET") or env.get("KB_ADMIN_KEY")

    # ── Fallback to environment variables ─────────────────────────────────────
    args.url = args.url or os.getenv("KB_UPLOAD_URL") or os.getenv("API_URL")
    args.key = args.key or os.getenv("ADMIN_UPLOAD_SECRET") or os.getenv("KB_ADMIN_KEY")

    if not args.url:
        err("--url is required (or set KB_UPLOAD_URL / API_URL env var)")
        sys.exit(1)
    if not args.key:
        err("--key is required (or set ADMIN_UPLOAD_SECRET / KB_ADMIN_KEY env var)")
        sys.exit(1)

    # ── Import requests ────────────────────────────────────────────────────────
    try:
        import requests
    except ImportError:
        err("The 'requests' library is not installed. Run:  pip install requests")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({"User-Agent": "bulk_kb_upload/1.0"})

    # ── Connection check ───────────────────────────────────────────────────────
    if args.check:
        print(f"\nChecking connection to {args.url} …")
        try:
            resp = session.get(
                f"{args.url.rstrip('/')}/kb-admin/stats",
                headers={"X-Admin-Key": args.key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            ok("Connection successful!")
            print(json.dumps(data, indent=2))
        except requests.HTTPError as exc:
            err(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}")
            sys.exit(1)
        except Exception as exc:
            err(f"Connection failed: {exc}")
            sys.exit(1)
        return

    # ── Collect files ──────────────────────────────────────────────────────────
    paths = args.dir or args.files
    all_files = _collect_files(paths, recursive=args.recursive)

    if not all_files:
        warn("No supported files found. Supported extensions:")
        warn(", ".join(sorted(SUPPORTED_EXTENSIONS)))
        sys.exit(0)

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Found {len(all_files)} file(s) to upload\n")

    if args.dry_run:
        for fp in all_files:
            size_kb = fp.stat().st_size / 1024
            info(f"{fp.name}  ({size_kb:.1f} KB)  [{fp.parent}]")
        print(f"\nTotal: {len(all_files)} file(s) — dry run complete, nothing uploaded.")
        return

    # ── Upload in batches ──────────────────────────────────────────────────────
    batches = list(_chunked(all_files, args.batch_size))
    total = len(all_files)
    done = successful = duplicates = failed = 0
    all_results = []

    start_time = time.time()

    for batch_num, batch in enumerate(batches, 1):
        batch_label = f"Batch {batch_num}/{len(batches)} ({len(batch)} files)"
        print(f"\n{_color('35', batch_label)}")
        for fp in batch:
            info(fp.name)

        try:
            result = _post_batch(
                session=session,
                url=args.url,
                secret=args.key,
                file_paths=batch,
                category=args.category,
                tags=args.tags,
                timeout=args.timeout,
            )
        except requests.HTTPError as exc:
            body = exc.response.text[:500] if exc.response else "no body"
            err(f"HTTP {exc.response.status_code if exc.response else '?'}: {body}")
            for fp in batch:
                failed += 1
                all_results.append({"filename": fp.name, "status": "error", "error": body})
            done += len(batch)
            continue
        except Exception as exc:
            err(f"Request failed: {exc}")
            for fp in batch:
                failed += 1
                all_results.append({"filename": fp.name, "status": "error", "error": str(exc)})
            done += len(batch)
            continue

        summary = result.get("summary", {})
        successful += summary.get("successful", 0)
        duplicates += summary.get("duplicates", 0)
        failed     += summary.get("failed", 0)
        done       += len(batch)
        all_results.extend(result.get("results", []))

        # Print per-file results
        for r in result.get("results", []):
            s = r.get("status")
            fn = r.get("filename", "?")
            if s == "success":
                ok(f"{fn}  →  {r.get('chunks_created', 0)} chunks")
            elif s == "duplicate":
                warn(f"{fn}  (already exists, skipped)")
            else:
                err(f"{fn}  →  {r.get('error', 'unknown error')}")

        pct = int(done / total * 100)
        elapsed = time.time() - start_time
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(
            f"  Progress: {done}/{total} ({pct}%)  "
            f"| elapsed {elapsed:.0f}s  "
            + (f"| ETA ~{eta:.0f}s" if eta > 0 else "")
        )

    # ── Final summary ──────────────────────────────────────────────────────────
    elapsed_total = time.time() - start_time
    print("\n" + "─" * 50)
    print(_color("1", "Upload complete!"))

    if args.json_output:
        print(json.dumps({
            "summary": {
                "total": total,
                "successful": successful,
                "duplicates": duplicates,
                "failed": failed,
                "elapsed_seconds": round(elapsed_total, 1),
            },
            "results": all_results,
        }, indent=2))
    else:
        ok(f"Uploaded:   {successful}")
        warn(f"Duplicates: {duplicates} (skipped)")
        if failed:
            err(f"Failed:     {failed}")
        print(f"  Time: {elapsed_total:.1f}s\n")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
