#!/usr/bin/env python3
"""
KB Uploader GUI — Parse Locally, Upload Fast
=============================================
• Parses every document locally (PDF/DOCX/XLSX/PPTX/CSV/HTML/…)
• Preview panel shows extracted text before you upload
• Uploads pre-parsed text only (no binary transfer, server skips parsing)
  → typical upload: ~200 ms/doc instead of 5-30 s

Requirements:
    pip install requests pypdf python-docx openpyxl python-pptx

Optional (faster PDF):
    pip install PyMuPDF

Run:
    python scripts/kb_uploader_gui.py
"""

# ─── stdlib ──────────────────────────────────────────────────────────────────
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

# ─── make sure the scripts dir is on sys.path so local_parser is importable ──
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & COLOURS
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_EXT = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv",
    ".txt", ".md", ".html", ".htm", ".pptx", ".ppt",
    ".json", ".xml", ".rtf",
}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep", ".gitignore"}

CONFIG_FILE = Path.home() / ".kb_uploader_config.json"
CHUNK_SIZE   = 500    # must match server
MAX_CHUNKS   = 100

COLORS = {
    "bg":       "#1e1e2e",
    "surface":  "#2a2a3d",
    "panel":    "#252538",
    "accent":   "#7c3aed",
    "accent2":  "#a855f7",
    "success":  "#22c55e",
    "warning":  "#f59e0b",
    "error":    "#ef4444",
    "text":     "#e2e8f0",
    "subtext":  "#94a3b8",
    "border":   "#3f3f5a",
    "input":    "#16162a",
}

# ─────────────────────────────────────────────────────────────────────────────
# FILE STATE
# ─────────────────────────────────────────────────────────────────────────────

STATUS_PENDING   = "pending"
STATUS_PARSING   = "parsing"
STATUS_READY     = "ready"
STATUS_PARSE_ERR = "parse_error"
STATUS_UPLOADING = "uploading"
STATUS_UPLOADED  = "uploaded"
STATUS_DUPLICATE = "duplicate"
STATUS_UP_ERR    = "upload_error"

STATUS_ICON = {
    STATUS_PENDING:   "⏳",
    STATUS_PARSING:   "🔄",
    STATUS_READY:     "✓",
    STATUS_PARSE_ERR: "✗",
    STATUS_UPLOADING: "↑",
    STATUS_UPLOADED:  "✓",
    STATUS_DUPLICATE: "~",
    STATUS_UP_ERR:    "✗",
}

STATUS_COLOR = {
    STATUS_PENDING:   COLORS["subtext"],
    STATUS_PARSING:   COLORS["warning"],
    STATUS_READY:     COLORS["success"],
    STATUS_PARSE_ERR: COLORS["error"],
    STATUS_UPLOADING: COLORS["warning"],
    STATUS_UPLOADED:  COLORS["success"],
    STATUS_DUPLICATE: COLORS["warning"],
    STATUS_UP_ERR:    COLORS["error"],
}

@dataclass
class KBFile:
    path: Path
    status: str  = STATUS_PENDING
    text: str    = ""
    error: str   = ""
    hash_: str   = ""
    size: int    = 0
    chunks: int  = 0            # estimated from local text


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def load_cfg() -> dict:
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except Exception:
        pass
    return {"url": "", "key": "", "category": "general", "tags": ""}


def save_cfg(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD WORKER  (background thread — sends pre-parsed JSON)
# ─────────────────────────────────────────────────────────────────────────────

def upload_worker(url, key, files: List[KBFile], category, tag_list,
                  batch_size, timeout, msg_q, stop_evt):
    """
    First tries POST /kb-admin/upload-preparsed (text-only JSON, fast).
    On 404 (server not yet redeployed) automatically falls back to
    POST /kb-admin/bulk-upload (multipart binary, slower but always works).

    Messages: ("log", text, color)  ("progress", done, total)  ("done", summary)
              ("file_status", path_str, status)
    """
    try:
        import requests
    except ImportError:
        msg_q.put(("error", "requests not installed — pip install requests"))
        return

    session = requests.Session()
    session.headers["User-Agent"] = "kb_uploader_gui/2.0"

    ready = [f for f in files if f.status == STATUS_READY]
    total = len(ready)
    done = successful = duplicates = failed = 0

    if not ready:
        msg_q.put(("done", {"total": 0, "successful": 0, "duplicates": 0, "failed": 0}))
        return

    # ── detect which endpoint the server supports ─────────────────────────────
    use_preparsed = True   # optimistic; flipped to False on first 404
    msg_q.put(("log", f"Starting upload of {total} file(s)…", "info"))

    batches = [ready[i: i + batch_size] for i in range(0, len(ready), batch_size)]

    for batch in batches:
        if stop_evt.is_set():
            msg_q.put(("log", "⚠ Upload cancelled.", "warning"))
            break

        if use_preparsed:
            result, use_preparsed = _try_preparsed(
                session, url, key, batch, category, tag_list,
                timeout, msg_q, use_preparsed)
            if result is None:
                # fell back — re-try this batch with binary upload
                result = _binary_upload(
                    session, url, key, batch, category, tag_list,
                    timeout, msg_q)
        else:
            result = _binary_upload(
                session, url, key, batch, category, tag_list,
                timeout, msg_q)

        if result is None:
            # hard failure — whole batch failed
            for f in batch:
                failed += 1
                msg_q.put(("file_status", str(f.path), STATUS_UP_ERR))
            done += len(batch)
            msg_q.put(("progress", done, total))
            continue

        for r in result.get("results", []):
            s  = r.get("status")
            fn = r.get("filename", "?")
            kb = next((f for f in batch if f.path.name == fn), None)
            p  = str(kb.path) if kb else ""
            if s == "success":
                successful += 1
                chunks = r.get("chunks_created", 0)
                chars  = r.get("text_length", 0) or r.get("chunks_created", 0) * 500
                msg_q.put(("log", f"✓ {fn}  ({chunks} chunks)", "success"))
                msg_q.put(("file_status", p, STATUS_UPLOADED))
            elif s == "duplicate":
                duplicates += 1
                msg_q.put(("log", f"~ {fn}  (duplicate, skipped)", "warning"))
                msg_q.put(("file_status", p, STATUS_DUPLICATE))
            else:
                failed += 1
                msg_q.put(("log", f"✗ {fn}  — {r.get('error', 'unknown')}", "error"))
                msg_q.put(("file_status", p, STATUS_UP_ERR))

        done += len(batch)
        msg_q.put(("progress", done, total))

    msg_q.put(("done", {
        "total": total,
        "successful": successful,
        "duplicates": duplicates,
        "failed": failed,
    }))


def _try_preparsed(session, url, key, batch, category, tag_list,
                   timeout, msg_q, use_preparsed):
    """
    Attempt /kb-admin/upload-preparsed.
    Returns (result_dict, True) on success.
    Returns (None, False) if the server returns 404 (endpoint not deployed yet).
    Returns (None, True) for other errors (so caller marks batch as failed).
    """
    import requests as _req

    docs_payload = [
        {
            "filename": f.path.name,
            "file_type": _mime(f.path),
            "file_size": f.size,
            "extracted_text": f.text,
            "content_hash": f.hash_,
            "category": category,
            "tags": tag_list,
        }
        for f in batch
    ]

    try:
        resp = session.post(
            f"{url.rstrip('/')}/kb-admin/upload-preparsed",
            headers={"X-Admin-Key": key, "Content-Type": "application/json"},
            json={"documents": docs_payload},
            timeout=timeout,
        )
        if resp.status_code == 404:
            msg_q.put(("log",
                "Server does not have /upload-preparsed yet — "
                "falling back to binary upload (slower). "
                "Deploy the updated server to unlock fast uploads.",
                "warning"))
            return None, False   # signal: retry with binary
        resp.raise_for_status()
        return resp.json(), True
    except _req.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            msg_q.put(("log",
                "Server does not have /upload-preparsed yet — "
                "falling back to binary upload.",
                "warning"))
            return None, False
        body = ""
        try:
            body = exc.response.json().get("detail", exc.response.text[:300])
        except Exception:
            body = str(exc)
        msg_q.put(("log", f"✗ HTTP error: {body}", "error"))
        return None, True   # hard error, don't retry
    except Exception as exc:
        msg_q.put(("log", f"✗ Request failed: {exc}", "error"))
        return None, True


def _binary_upload(session, url, key, batch, category, tag_list, timeout, msg_q):
    """
    Fallback: POST /kb-admin/bulk-upload with raw file bytes (original method).
    Works on every deployed version of the server.
    """
    import requests as _req

    file_handles = []
    try:
        files_field = []
        for f in batch:
            try:
                fh = open(f.path, "rb")
                file_handles.append(fh)
                files_field.append(("files", (f.path.name, fh, _mime(f.path))))
            except OSError as exc:
                msg_q.put(("log", f"✗ Cannot open {f.path.name}: {exc}", "error"))

        if not files_field:
            return None

        tags_str = ",".join(tag_list)
        resp = session.post(
            f"{url.rstrip('/')}/kb-admin/bulk-upload",
            headers={"X-Admin-Key": key},
            files=files_field,
            data={"category": category, "tags": tags_str},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except _req.HTTPError as exc:
        body = ""
        try:
            body = exc.response.json().get("detail", exc.response.text[:300])
        except Exception:
            body = str(exc)
        msg_q.put(("log", f"✗ HTTP {exc.response.status_code}: {body}", "error"))
        return None
    except Exception as exc:
        msg_q.put(("log", f"✗ Binary upload failed: {exc}", "error"))
        return None
    finally:
        for fh in file_handles:
            try:
                fh.close()
            except OSError:
                pass


def _mime(path: Path) -> str:
    m = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc":  "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls":  "application/vnd.ms-excel",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".ppt":  "application/vnd.ms-powerpoint",
        ".csv":  "text/csv",
        ".txt":  "text/plain",
        ".md":   "text/markdown",
        ".html": "text/html",
        ".htm":  "text/html",
        ".json": "application/json",
        ".xml":  "application/xml",
        ".rtf":  "application/rtf",
    }
    return m.get(path.suffix.lower(), "application/octet-stream")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("KB Uploader  ·  Railway")
        self.geometry("1100x720")
        self.minsize(900, 580)
        self.configure(bg=COLORS["bg"])

        self._cfg = load_cfg()

        # ── state ─────────────────────────────────────────────────────────────
        self._files: Dict[str, KBFile] = {}   # key = str(path)
        self._uploading = False
        self._stop_evt  = threading.Event()
        self._q: queue.Queue = queue.Queue()

        # local_parser import (lazy, with fallback)
        self._parser_ok = False
        try:
            import local_parser as _lp
            self._lp = _lp
            self._parser_ok = True
        except ImportError:
            self._lp = None

        self._build_ui()
        self._poll()

    # ─────────────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── header bar ────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=COLORS["accent"], height=4)
        hdr.pack(fill="x")

        title_bar = tk.Frame(self, bg=COLORS["bg"], pady=10)
        title_bar.pack(fill="x", padx=16)
        tk.Label(title_bar, text="KB Uploader", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 17, "bold")).pack(side="left")
        tk.Label(title_bar, text="Railway  ·  Local Parse  ·  Fast Upload",
                 bg=COLORS["bg"], fg=COLORS["subtext"],
                 font=("Segoe UI", 9)).pack(side="left", padx=10)

        if not self._parser_ok:
            tk.Label(title_bar, text="⚠ local_parser.py not found",
                     bg=COLORS["bg"], fg=COLORS["warning"],
                     font=("Segoe UI", 9)).pack(side="right", padx=8)

        # ── body: left sidebar + right notebook ────────────────────────────────
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # left sidebar (fixed width)
        left = tk.Frame(body, bg=COLORS["bg"], width=340)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        # right notebook
        right = tk.Frame(body, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True)

        self._build_sidebar(left)
        self._build_notebook(right)

    # ── sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        # Connection
        conn = self._card(parent, "Connection")
        self._lbl_entry(conn, "Railway URL", "url_var",
                        self._cfg.get("url", ""), "https://…")
        self._lbl_entry(conn, "Admin Key", "key_var",
                        self._cfg.get("key", ""), "ADMIN_UPLOAD_SECRET", show="*")
        f = tk.Frame(conn, bg=COLORS["surface"])
        f.pack(fill="x", padx=10, pady=(4, 10))
        self._btn(f, "⚡ Test", self._test_conn, COLORS["accent"]).pack(side="right")

        # Upload settings
        opts = self._card(parent, "Upload Settings")
        self._lbl_entry(opts, "Category", "cat_var",
                        self._cfg.get("category", "general"), "research")
        self._lbl_entry(opts, "Tags", "tags_var",
                        self._cfg.get("tags", ""), "2024,earnings")

        row = tk.Frame(opts, bg=COLORS["surface"])
        row.pack(fill="x", padx=10, pady=(4, 4))
        tk.Label(row, text="Batch", bg=COLORS["surface"], fg=COLORS["subtext"],
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        self.batch_var = tk.IntVar(value=10)
        tk.Spinbox(row, from_=1, to=100, textvariable=self.batch_var, width=5,
                   bg=COLORS["input"], fg=COLORS["text"],
                   buttonbackground=COLORS["border"], relief="flat", bd=1,
                   insertbackground=COLORS["text"]).pack(side="left", padx=(0, 14))
        tk.Label(row, text="Timeout(s)", bg=COLORS["surface"], fg=COLORS["subtext"],
                 font=("Segoe UI", 9), width=10, anchor="w").pack(side="left")
        self.timeout_var = tk.IntVar(value=60)
        tk.Spinbox(row, from_=15, to=600, increment=15,
                   textvariable=self.timeout_var, width=5,
                   bg=COLORS["input"], fg=COLORS["text"],
                   buttonbackground=COLORS["border"], relief="flat", bd=1,
                   insertbackground=COLORS["text"]).pack(side="left")

        # Action buttons
        btn_frame = tk.Frame(opts, bg=COLORS["surface"])
        btn_frame.pack(fill="x", padx=10, pady=10)
        self._upload_btn = self._btn(btn_frame, "🚀  Upload to KB",
                                     self._start_upload, COLORS["accent"],
                                     height=2)
        self._upload_btn.pack(fill="x", pady=(0, 6))
        self._stop_btn = self._btn(btn_frame, "⏹  Stop",
                                   self._stop_upload, COLORS["error"])
        self._stop_btn.pack(fill="x")
        self._stop_btn.config(state="disabled")

        # File list
        fl = self._card(parent, "Files", expand=True)
        br = tk.Frame(fl, bg=COLORS["surface"])
        br.pack(fill="x", padx=10, pady=(0, 6))
        self._btn(br, "＋ Files",  self._add_files).pack(side="left", padx=(0, 4))
        self._btn(br, "📁 Folder", self._add_folder).pack(side="left", padx=(0, 4))
        self._btn(br, "✕ Clear",   self._clear_files,
                  COLORS["border"]).pack(side="right")

        lb_frame = tk.Frame(fl, bg=COLORS["surface"])
        lb_frame.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        sb = tk.Scrollbar(lb_frame, bg=COLORS["border"],
                          troughcolor=COLORS["input"])
        sb.pack(side="right", fill="y")
        self._lb = tk.Listbox(
            lb_frame,
            bg=COLORS["input"], fg=COLORS["text"],
            selectbackground=COLORS["accent"], selectforeground="#fff",
            activestyle="none", relief="flat", bd=0,
            font=("Consolas", 9),
            yscrollcommand=sb.set,
        )
        self._lb.pack(fill="both", expand=True)
        sb.config(command=self._lb.yview)
        self._lb.bind("<<ListboxSelect>>", self._on_file_select)

        self._count_var = tk.StringVar(value="No files")
        tk.Label(fl, textvariable=self._count_var,
                 bg=COLORS["surface"], fg=COLORS["subtext"],
                 font=("Segoe UI", 8)).pack(padx=10, pady=(0, 6), anchor="w")

    # ── right notebook ────────────────────────────────────────────────────────

    def _build_notebook(self, parent):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.TNotebook",
                        background=COLORS["bg"],
                        borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background=COLORS["surface"],
                        foreground=COLORS["subtext"],
                        padding=[12, 4],
                        font=("Segoe UI", 9))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", COLORS["accent"])],
                  foreground=[("selected", "#fff")])

        self._nb = ttk.Notebook(parent, style="Dark.TNotebook")
        self._nb.pack(fill="both", expand=True)

        # Tab 1: Preview
        preview_tab = tk.Frame(self._nb, bg=COLORS["bg"])
        self._nb.add(preview_tab, text="  📄 Preview  ")
        self._build_preview_tab(preview_tab)

        # Tab 2: Upload log
        log_tab = tk.Frame(self._nb, bg=COLORS["bg"])
        self._nb.add(log_tab, text="  📊 Upload Log  ")
        self._build_log_tab(log_tab)

    # ── Preview tab ───────────────────────────────────────────────────────────

    def _build_preview_tab(self, parent):
        # file info strip
        info_frame = tk.Frame(parent, bg=COLORS["surface"],
                              highlightbackground=COLORS["border"],
                              highlightthickness=1)
        info_frame.pack(fill="x", padx=10, pady=(10, 4))

        self._prev_name = tk.StringVar(value="Select a file from the list to preview")
        self._prev_meta = tk.StringVar(value="")

        tk.Label(info_frame, textvariable=self._prev_name,
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=("Segoe UI", 10, "bold"),
                 anchor="w", pady=6, padx=10).pack(fill="x")
        tk.Label(info_frame, textvariable=self._prev_meta,
                 bg=COLORS["surface"], fg=COLORS["subtext"],
                 font=("Segoe UI", 8),
                 anchor="w", padx=10).pack(fill="x", pady=(0, 6))

        # status strip
        self._prev_status = tk.Label(
            parent, text="", bg=COLORS["bg"],
            fg=COLORS["subtext"], font=("Segoe UI", 9),
            anchor="w")
        self._prev_status.pack(fill="x", padx=10)

        # text area
        txt_frame = tk.Frame(parent, bg=COLORS["bg"])
        txt_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        v_sb = tk.Scrollbar(txt_frame, bg=COLORS["border"],
                            troughcolor=COLORS["input"])
        v_sb.pack(side="right", fill="y")
        h_sb = tk.Scrollbar(txt_frame, orient="horizontal",
                            bg=COLORS["border"], troughcolor=COLORS["input"])
        h_sb.pack(side="bottom", fill="x")

        self._prev_txt = tk.Text(
            txt_frame,
            bg=COLORS["input"], fg=COLORS["text"],
            relief="flat", bd=0,
            font=("Consolas", 9),
            state="disabled", wrap="none",
            yscrollcommand=v_sb.set,
            xscrollcommand=h_sb.set,
        )
        self._prev_txt.pack(fill="both", expand=True)
        v_sb.config(command=self._prev_txt.yview)
        h_sb.config(command=self._prev_txt.xview)

        self._prev_txt.tag_config("header",
                                   foreground=COLORS["accent2"],
                                   font=("Segoe UI", 9, "bold"))
        self._prev_txt.tag_config("error_txt",
                                   foreground=COLORS["error"])

    # ── Upload log tab ────────────────────────────────────────────────────────

    def _build_log_tab(self, parent):
        # progress
        prog_frame = tk.Frame(parent, bg=COLORS["surface"],
                              highlightbackground=COLORS["border"],
                              highlightthickness=1)
        prog_frame.pack(fill="x", padx=10, pady=(10, 4))

        style = ttk.Style()
        style.configure("KB.Horizontal.TProgressbar",
                        troughcolor=COLORS["input"],
                        background=COLORS["accent"],
                        darkcolor=COLORS["accent"],
                        lightcolor=COLORS["accent"],
                        bordercolor=COLORS["border"])
        self._prog_var = tk.DoubleVar()
        ttk.Progressbar(prog_frame, variable=self._prog_var,
                        style="KB.Horizontal.TProgressbar",
                        maximum=100).pack(fill="x", padx=10, pady=(8, 2))

        self._prog_lbl = tk.Label(prog_frame, text="Ready",
                                  bg=COLORS["surface"], fg=COLORS["subtext"],
                                  font=("Segoe UI", 9))
        self._prog_lbl.pack(anchor="w", padx=10, pady=(0, 8))

        # stats row
        stats = tk.Frame(parent, bg=COLORS["bg"])
        stats.pack(fill="x", padx=10, pady=(0, 6))
        self._stat_vars: Dict[str, tk.StringVar] = {}
        for lbl, key, col in [
            ("Uploaded",  "ok",  "success"),
            ("Duplicate", "dup", "warning"),
            ("Failed",    "err", "error"),
        ]:
            box = tk.Frame(stats, bg=COLORS["surface"],
                           highlightbackground=COLORS["border"],
                           highlightthickness=1)
            box.pack(side="left", expand=True, fill="x", padx=3)
            var = tk.StringVar(value="—")
            self._stat_vars[key] = var
            tk.Label(box, textvariable=var, bg=COLORS["surface"],
                     fg=COLORS[col], font=("Segoe UI", 14, "bold")).pack(pady=(6, 0))
            tk.Label(box, text=lbl, bg=COLORS["surface"],
                     fg=COLORS["subtext"], font=("Segoe UI", 8)).pack(pady=(0, 6))

        # log text
        log_frame = tk.Frame(parent, bg=COLORS["bg"])
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        log_sb = tk.Scrollbar(log_frame, bg=COLORS["border"],
                              troughcolor=COLORS["input"])
        log_sb.pack(side="right", fill="y")
        self._log = tk.Text(
            log_frame, bg=COLORS["input"], fg=COLORS["text"],
            relief="flat", bd=0, font=("Consolas", 9),
            state="disabled", wrap="word",
            yscrollcommand=log_sb.set,
        )
        self._log.pack(fill="both", expand=True)
        log_sb.config(command=self._log.yview)
        self._log.tag_config("success", foreground=COLORS["success"])
        self._log.tag_config("warning", foreground=COLORS["warning"])
        self._log.tag_config("error",   foreground=COLORS["error"])
        self._log.tag_config("info",    foreground=COLORS["accent2"])
        self._log.tag_config("normal",  foreground=COLORS["text"])

        self._btn(parent, "Clear Log", self._clear_log,
                  COLORS["border"]).pack(anchor="e", padx=10, pady=(0, 4))

    # ─────────────────────────────────────────────────────────────────────────
    # WIDGET HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _card(self, parent, title, expand=False):
        outer = tk.Frame(parent, bg=COLORS["bg"])
        outer.pack(fill="both", expand=expand, pady=(0, 8))
        tk.Frame(outer, bg=COLORS["accent"], height=2).pack(fill="x")
        inner = tk.Frame(outer, bg=COLORS["surface"],
                         highlightbackground=COLORS["border"],
                         highlightthickness=1)
        inner.pack(fill="both", expand=expand)
        tk.Label(inner, text=title, bg=COLORS["surface"], fg=COLORS["text"],
                 font=("Segoe UI", 10, "bold"), pady=7, padx=10).pack(anchor="w")
        tk.Frame(inner, bg=COLORS["border"], height=1).pack(fill="x", padx=10)
        return inner

    def _btn(self, parent, text, cmd, color=None, height=1):
        c = color or COLORS["surface"]
        b = tk.Button(parent, text=text, command=cmd,
                      bg=c, fg=COLORS["text"],
                      activebackground=COLORS["accent2"],
                      activeforeground="#fff",
                      relief="flat", cursor="hand2",
                      font=("Segoe UI", 9),
                      padx=10, pady=3, height=height, bd=0)
        b.bind("<Enter>", lambda e: b.configure(bg=COLORS["accent2"]))
        b.bind("<Leave>", lambda e: b.configure(bg=c))
        return b

    def _lbl_entry(self, parent, label, attr, default, placeholder="", show=""):
        row = tk.Frame(parent, bg=COLORS["surface"])
        row.pack(fill="x", padx=10, pady=(5, 2))
        tk.Label(row, text=label, bg=COLORS["surface"], fg=COLORS["subtext"],
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        var = tk.StringVar(value=default)
        setattr(self, attr, var)
        kw = dict(textvariable=var, bg=COLORS["input"], fg=COLORS["text"],
                  insertbackground=COLORS["text"], relief="flat", bd=4,
                  font=("Segoe UI", 9))
        if show:
            kw["show"] = show
        tk.Entry(row, **kw).pack(side="left", fill="x", expand=True)

    def _log_msg(self, text, tag="normal"):
        self._log.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self._log.insert("end", f"[{ts}] {text}\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # FILE MANAGEMENT + LOCAL PARSING
    # ─────────────────────────────────────────────────────────────────────────

    def _add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXT))
        paths = filedialog.askopenfilenames(
            title="Select files",
            filetypes=[("Supported documents", exts), ("All files", "*.*")])
        new = []
        for p in paths:
            fp = Path(p)
            k  = str(fp)
            if k not in self._files:
                kbf = KBFile(path=fp, size=fp.stat().st_size)
                self._files[k] = kbf
                new.append(kbf)
        self._refresh_list()
        if new:
            self._parse_batch(new)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select folder")
        if not folder:
            return
        new = []
        for fp in sorted(Path(folder).rglob("*")):
            if (fp.is_file() and fp.name not in SKIP_NAMES
                    and fp.suffix.lower() in SUPPORTED_EXT):
                k = str(fp)
                if k not in self._files:
                    kbf = KBFile(path=fp, size=fp.stat().st_size)
                    self._files[k] = kbf
                    new.append(kbf)
        self._refresh_list()
        if new:
            self._log_msg(f"Added {len(new)} file(s) — parsing…", "info")
            self._nb.select(1)   # switch to log tab
            self._parse_batch(new)

    def _clear_files(self):
        self._files.clear()
        self._refresh_list()
        self._clear_preview()

    def _refresh_list(self):
        sel_idx = self._lb.curselection()
        sel_key = None
        if sel_idx:
            cur_text = self._lb.get(sel_idx[0])
            # Try to find the key from the displayed filename
            for k, f in self._files.items():
                if f.path.name in cur_text:
                    sel_key = k
                    break

        self._lb.delete(0, "end")
        idx_to_select = None
        for i, (k, f) in enumerate(self._files.items()):
            icon  = STATUS_ICON.get(f.status, "?")
            sz    = f"{f.size / 1024:.1f} KB"
            extra = ""
            if f.status == STATUS_READY:
                extra = f"  {f.chunks}ch"
            elif f.status == STATUS_PARSE_ERR:
                extra = "  !"
            elif f.status in (STATUS_UPLOADED, STATUS_DUPLICATE):
                extra = "  ✓"
            label = f" {icon} {f.path.name}  ({sz}){extra}"
            self._lb.insert("end", label)
            if k == sel_key:
                idx_to_select = i

        if idx_to_select is not None:
            self._lb.selection_set(idx_to_select)
            self._lb.see(idx_to_select)

        ready = sum(1 for f in self._files.values() if f.status == STATUS_READY)
        total = len(self._files)
        self._count_var.set(
            f"{total} file(s)  ·  {ready} parsed"
            if total else "No files"
        )

    # ── Local parsing ─────────────────────────────────────────────────────────

    def _parse_batch(self, files: List[KBFile]):
        """Parse a list of KBFiles in a background thread pool."""
        if not self._parser_ok:
            self._log_msg("local_parser.py not found — using server-side parsing "
                          "(slower). Place local_parser.py in scripts/.", "warning")
            # mark all as ready with empty text so server parses
            for f in files:
                f.status = STATUS_READY
                f.text   = "__USE_SERVER__"   # sentinel (not sent)
            self._refresh_list()
            return

        for f in files:
            f.status = STATUS_PARSING
        self._refresh_list()

        def _worker():
            lp = self._lp
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(self._parse_one, f, lp): f for f in files}
                for fut in as_completed(futures):
                    kbf = futures[fut]
                    try:
                        result = fut.result()
                    except Exception as exc:
                        result = ("", str(exc), "", False)
                    self._q.put(("parse_done", str(kbf.path), result))

        threading.Thread(target=_worker, daemon=True).start()

    @staticmethod
    def _parse_one(kbf: KBFile, lp):
        """Run in thread pool. Returns (text, error, hash_, truncated)."""
        h = lp.file_hash(kbf.path)
        r = lp.parse_file(kbf.path)
        return r.text, r.error, h, r.truncated

    # ── Preview ───────────────────────────────────────────────────────────────

    def _on_file_select(self, _event=None):
        sel = self._lb.curselection()
        if not sel:
            return
        keys = list(self._files.keys())
        if sel[0] >= len(keys):
            return
        kbf = self._files[keys[sel[0]]]
        self._show_preview(kbf)

    def _show_preview(self, kbf: KBFile):
        self._prev_name.set(kbf.path.name)
        sz_kb = kbf.size / 1024
        if kbf.status == STATUS_READY:
            chars = len(kbf.text)
            meta = (f"{sz_kb:.1f} KB  ·  {chars:,} chars  ·  "
                    f"~{kbf.chunks} chunks  ·  {kbf.path.suffix.upper()}")
            self._prev_status.config(
                text="✓ Parsed locally",
                fg=COLORS["success"])
        elif kbf.status == STATUS_PARSING:
            meta = f"{sz_kb:.1f} KB  ·  parsing…"
            self._prev_status.config(text="🔄 Parsing…", fg=COLORS["warning"])
        elif kbf.status == STATUS_PARSE_ERR:
            meta = f"{sz_kb:.1f} KB"
            self._prev_status.config(
                text=f"✗ Parse error: {kbf.error[:120]}",
                fg=COLORS["error"])
        elif kbf.status == STATUS_UPLOADED:
            meta = f"{sz_kb:.1f} KB  ·  uploaded"
            self._prev_status.config(text="✓ Uploaded", fg=COLORS["success"])
        elif kbf.status == STATUS_DUPLICATE:
            meta = f"{sz_kb:.1f} KB  ·  duplicate"
            self._prev_status.config(text="~ Already in KB", fg=COLORS["warning"])
        else:
            meta = f"{sz_kb:.1f} KB  ·  {kbf.status}"
            self._prev_status.config(text="", fg=COLORS["subtext"])

        self._prev_meta.set(meta)

        # populate text area
        self._prev_txt.config(state="normal")
        self._prev_txt.delete("1.0", "end")

        if kbf.status == STATUS_PARSE_ERR:
            self._prev_txt.insert("end",
                f"Parse error:\n{kbf.error}\n\nFile: {kbf.path}",
                "error_txt")
        elif kbf.status == STATUS_PENDING:
            self._prev_txt.insert("end",
                "File not yet parsed.\nAdd it and parsing will start automatically.",
                "normal")
        elif kbf.status == STATUS_PARSING:
            self._prev_txt.insert("end", "Parsing in progress…", "normal")
        elif kbf.text:
            # show first 100 k chars to keep the widget fast
            preview = kbf.text[:100_000]
            truncated_note = "\n\n… [preview truncated — full text will be uploaded]" if len(kbf.text) > 100_000 else ""
            self._prev_txt.insert("end", preview + truncated_note)
        else:
            self._prev_txt.insert("end", "[No text extracted]", "normal")

        self._prev_txt.config(state="disabled")
        self._nb.select(0)   # switch to preview tab

    def _clear_preview(self):
        self._prev_name.set("Select a file from the list to preview")
        self._prev_meta.set("")
        self._prev_status.config(text="", fg=COLORS["subtext"])
        self._prev_txt.config(state="normal")
        self._prev_txt.delete("1.0", "end")
        self._prev_txt.config(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTION TEST
    # ─────────────────────────────────────────────────────────────────────────

    def _test_conn(self):
        url = self.url_var.get().strip()
        key = self.key_var.get().strip()
        if not url or not key:
            messagebox.showwarning("Missing fields", "Enter URL and Admin Key first.")
            return
        self._log_msg(f"Testing {url} …  (Railway may take 30-60 s to wake)", "info")
        self._nb.select(1)

        def _run():
            import requests

            base = url.rstrip("/")

            # ── Step 1: wake the server with a lightweight health ping ─────────
            for attempt in range(1, 4):
                try:
                    ping = requests.get(f"{base}/health", timeout=45)
                    if ping.status_code < 500:
                        break   # server is up
                except requests.exceptions.Timeout:
                    self._q.put(("log",
                        f"  Server still waking… attempt {attempt}/3 (may take up to 60 s)",
                        "warning"))
                except Exception:
                    break  # non-timeout error — move on
            else:
                self._q.put(("log",
                    "✗ Server did not respond after 3 attempts (135 s). "
                    "Check Railway dashboard.",
                    "error"))
                return

            # ── Step 2: hit the real stats endpoint ───────────────────────────
            try:
                r = requests.get(f"{base}/kb-admin/stats",
                                 headers={"X-Admin-Key": key}, timeout=45)
                r.raise_for_status()
                d = r.json()
                self._q.put(("log",
                    f"✓ Connected  ·  {d.get('total_documents','?')} docs  "
                    f"{d.get('total_chunks','?')} chunks  "
                    f"{d.get('total_size_disk_mb','?')} MB on disk",
                    "success"))
            except requests.exceptions.Timeout:
                self._q.put(("log",
                    "✗ Stats endpoint timed out (server is up but slow). "
                    "Try again in 10 s.",
                    "error"))
            except Exception as exc:
                msg = str(exc)
                try:
                    if hasattr(exc, "response") and exc.response is not None:
                        msg = exc.response.json().get("detail", exc.response.text[:200])
                except Exception:
                    pass
                self._q.put(("log", f"✗ {msg}", "error"))

        threading.Thread(target=_run, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # UPLOAD
    # ─────────────────────────────────────────────────────────────────────────

    def _start_upload(self):
        url = self.url_var.get().strip()
        key = self.key_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Enter the Railway URL.")
            return
        if not key:
            messagebox.showwarning("No Key", "Enter the Admin Key.")
            return

        ready = [f for f in self._files.values() if f.status == STATUS_READY]
        if not ready:
            pending = sum(1 for f in self._files.values()
                         if f.status in (STATUS_PENDING, STATUS_PARSING))
            if pending:
                messagebox.showinfo("Still parsing",
                    f"{pending} file(s) are still being parsed. "
                    "Wait for parsing to finish before uploading.")
            else:
                messagebox.showwarning("No files ready",
                    "No files are ready to upload.\n"
                    "Add files — they are parsed automatically.")
            return

        save_cfg({
            "url": url, "key": key,
            "category": self.cat_var.get(),
            "tags": self.tags_var.get(),
        })

        self._uploading = True
        self._stop_evt.clear()
        self._upload_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        for v in self._stat_vars.values():
            v.set("0")
        self._prog_var.set(0)
        self._prog_lbl.config(text=f"Uploading {len(ready)} file(s)…")
        self._log_msg(f"Uploading {len(ready)} file(s) (pre-parsed, text-only)…", "info")
        self._nb.select(1)

        tag_list = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]

        threading.Thread(
            target=upload_worker,
            args=(url, key, list(self._files.values()),
                  self.cat_var.get().strip() or "general",
                  tag_list,
                  self.batch_var.get(),
                  self.timeout_var.get(),
                  self._q, self._stop_evt),
            daemon=True,
        ).start()

    def _stop_upload(self):
        self._stop_evt.set()
        self._log_msg("Stop requested…", "warning")

    # ─────────────────────────────────────────────────────────────────────────
    # QUEUE POLL — all cross-thread UI updates go here
    # ─────────────────────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]

                if kind == "log":
                    _, text, color = msg
                    self._log_msg(text, color)

                elif kind == "parse_done":
                    _, path_str, result = msg
                    text, error, hash_, truncated = result
                    kbf = self._files.get(path_str)
                    if kbf:
                        if error:
                            kbf.status = STATUS_PARSE_ERR
                            kbf.error  = error
                            self._log_msg(f"✗ Parse error: {kbf.path.name}  — {error[:80]}",
                                          "error")
                        else:
                            kbf.status = STATUS_READY
                            kbf.text   = text
                            kbf.hash_  = hash_
                            kbf.chunks = min(
                                MAX_CHUNKS,
                                max(1, len(text) // 500) if text else 0
                            )
                            note = "  [truncated]" if truncated else ""
                            self._log_msg(
                                f"✓ Parsed: {kbf.path.name}  "
                                f"({len(text):,} chars  ~{kbf.chunks} chunks){note}",
                                "success")
                    self._refresh_list()
                    # refresh preview if this file is selected
                    sel = self._lb.curselection()
                    if sel:
                        keys = list(self._files.keys())
                        if sel[0] < len(keys) and keys[sel[0]] == path_str:
                            self._show_preview(kbf)

                elif kind == "file_status":
                    _, path_str, new_status = msg
                    kbf = self._files.get(path_str)
                    if kbf:
                        kbf.status = new_status
                    self._refresh_list()

                elif kind == "progress":
                    _, done, total = msg
                    pct = int(done / total * 100) if total else 0
                    self._prog_var.set(pct)
                    self._prog_lbl.config(text=f"{done} / {total}  ({pct}%)")

                elif kind == "done":
                    _, summary = msg
                    self._stat_vars["ok"].set(str(summary["successful"]))
                    self._stat_vars["dup"].set(str(summary["duplicates"]))
                    self._stat_vars["err"].set(str(summary["failed"]))
                    self._prog_var.set(100)
                    self._prog_lbl.config(text="Done ✓")
                    self._log_msg(
                        f"Finished — {summary['successful']} uploaded  "
                        f"{summary['duplicates']} duplicates  "
                        f"{summary['failed']} failed",
                        "info")
                    self._uploading = False
                    self._upload_btn.config(state="normal")
                    self._stop_btn.config(state="disabled")
                    self._refresh_list()

                elif kind == "error":
                    _, text = msg
                    self._log_msg(f"✗ {text}", "error")
                    self._uploading = False
                    self._upload_btn.config(state="normal")
                    self._stop_btn.config(state="disabled")

        except queue.Empty:
            pass

        self.after(80, self._poll)

    # ─────────────────────────────────────────────────────────────────────────

    def on_close(self):
        if self._uploading:
            if not messagebox.askyesno("Upload in progress", "Quit anyway?"):
                return
        self._stop_evt.set()
        save_cfg({
            "url":      self.url_var.get(),
            "key":      self.key_var.get(),
            "category": self.cat_var.get(),
            "tags":     self.tags_var.get(),
        })
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        import requests  # noqa
    except ImportError:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Missing dependency",
            "Install requests first:\n  pip install requests")
        sys.exit(1)

    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
