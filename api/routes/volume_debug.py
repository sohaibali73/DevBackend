"""
Volume Debug Router
====================
Full CRUD access to the Railway persistent volume mounted at /data.
Secured by a static VOLUME_DEBUG_KEY env var (set this in Railway variables).

Endpoints:
  GET    /volume/info                  — disk usage summary
  GET    /volume/ls                    — list root or any subdir
  GET    /volume/ls/{dirpath}          — list a specific subdirectory
  GET    /volume/download/{filepath}   — download any file as bytes
  POST   /volume/upload/{dirpath}      — upload a file into a directory
  DELETE /volume/delete/{filepath}     — delete a file or empty directory
  POST   /volume/mkdir/{dirpath}       — create a directory
  POST   /volume/move                  — move / rename a file or directory
"""

import os
import io
import zipfile
import shutil
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, StreamingResponse, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/volume", tags=["Volume Debug"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VOLUME_PATH = Path(os.getenv("VOLUME_PATH", "/data"))

# Secret key — set VOLUME_DEBUG_KEY in Railway environment variables.
# If the env var is not set the endpoints are DISABLED (returns 503).
_DEBUG_KEY: str = os.getenv("VOLUME_DEBUG_KEY", "")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _require_key(x_debug_key: Optional[str]) -> None:
    """Raise 401/503 if the debug key is wrong or not configured."""
    if not _DEBUG_KEY:
        raise HTTPException(
            status_code=503,
            detail="Volume debug endpoints are disabled. "
                   "Set VOLUME_DEBUG_KEY in Railway environment variables to enable.",
        )
    if not x_debug_key:
        raise HTTPException(
            status_code=401,
            detail="Missing auth key. Send X-Debug-Key header or ?key=… query param.",
        )
    if x_debug_key != _DEBUG_KEY:
        raise HTTPException(status_code=401, detail="Invalid auth key.")


def _resolve_key(
    header_key: Optional[str],
    query_key: Optional[str] = None,
    cookie_key: Optional[str] = None,
) -> Optional[str]:
    """Pick a key from header, query string, or cookie (in that order)."""
    return header_key or query_key or cookie_key


def _safe_path(rel: str) -> Path:
    """Resolve a relative path under VOLUME_PATH and guard against traversal."""
    # Normalise: strip leading slashes so Path doesn't treat it as absolute
    clean = rel.lstrip("/").lstrip("\\") if rel else ""
    resolved = (VOLUME_PATH / clean).resolve()
    try:
        resolved.relative_to(VOLUME_PATH.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal detected.")
    return resolved


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class MoveRequest(BaseModel):
    src: str   # relative path of source
    dst: str   # relative path of destination


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/info")
async def volume_info(
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Return volume existence, total size, and file count."""
    _require_key(_resolve_key(x_debug_key, key))
    if not VOLUME_PATH.exists():
        return {
            "volume_path": str(VOLUME_PATH),
            "exists": False,
            "total_files": 0,
            "total_size_bytes": 0,
            "total_size_mb": 0.0,
        }

    total_bytes = 0
    total_files = 0
    try:
        for p in VOLUME_PATH.rglob("*"):
            if p.is_file():
                total_files += 1
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
    except Exception as e:
        logger.warning("volume_info walk error: %s", e)

    # disk usage
    try:
        usage = shutil.disk_usage(str(VOLUME_PATH))
        disk_info = {
            "disk_total_gb": round(usage.total / 1e9, 2),
            "disk_used_gb":  round(usage.used  / 1e9, 2),
            "disk_free_gb":  round(usage.free  / 1e9, 2),
        }
    except Exception:
        disk_info = {}

    return {
        "volume_path": str(VOLUME_PATH),
        "exists": True,
        "total_files": total_files,
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_bytes / 1e6, 2),
        **disk_info,
    }


@router.get("/ls")
async def list_root(
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """List the root of the volume (non-recursive)."""
    return await _list_dir("", _resolve_key(x_debug_key, key))


@router.get("/ls/{dirpath:path}")
async def list_dir(
    dirpath: str,
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """List a specific directory inside the volume."""
    return await _list_dir(dirpath, _resolve_key(x_debug_key, key))


async def _list_dir(dirpath: str, x_debug_key: Optional[str]):
    _require_key(x_debug_key)
    target = _safe_path(dirpath)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {dirpath!r}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {dirpath!r}")

    items = []
    try:
        for p in sorted(target.iterdir()):
            rel = str(p.relative_to(VOLUME_PATH))
            try:
                st = p.stat()
                mtime = st.st_mtime
            except OSError:
                st = None
                mtime = None
            if p.is_dir():
                items.append({
                    "name": p.name,
                    "path": rel,
                    "type": "directory",
                    "size_bytes": None,
                    "mtime": mtime,
                })
            else:
                size = st.st_size if st else 0
                items.append({
                    "name": p.name,
                    "path": rel,
                    "type": "file",
                    "size_bytes": size,
                    "size_kb": round(size / 1024, 1),
                    "mtime": mtime,
                })
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return {
        "directory": dirpath or "/",
        "volume_path": str(VOLUME_PATH),
        "items": items,
        "count": len(items),
        "files": sum(1 for i in items if i["type"] == "file"),
        "directories": sum(1 for i in items if i["type"] == "directory"),
    }


@router.get("/download/{filepath:path}")
async def download_file(
    filepath: str,
    key: Optional[str] = Query(None),
    inline: bool = Query(False, description="If true, render inline (preview) instead of attachment"),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Download a file from the volume as a binary response."""
    _require_key(_resolve_key(x_debug_key, key))
    target = _safe_path(filepath)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath!r}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {filepath!r}")

    media_type, _ = mimetypes.guess_type(str(target))
    if not media_type:
        media_type = "application/octet-stream"

    headers = {}
    if not inline:
        headers["Content-Disposition"] = f'attachment; filename="{target.name}"'

    return FileResponse(
        path=str(target),
        filename=None if inline else target.name,
        media_type=media_type,
        headers=headers,
    )


@router.get("/zip/{dirpath:path}")
async def zip_directory(
    dirpath: str,
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Stream a ZIP archive of an entire directory."""
    _require_key(_resolve_key(x_debug_key, key))
    target = _safe_path(dirpath)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {dirpath!r}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {dirpath!r}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in target.rglob("*"):
            if p.is_file():
                try:
                    arcname = p.relative_to(target)
                    zf.write(p, arcname=str(arcname))
                except Exception as e:
                    logger.warning("zip skip %s: %s", p, e)
    buf.seek(0)

    folder_name = target.name or "volume"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder_name}.zip"'},
    )


@router.post("/upload/{dirpath:path}")
async def upload_file(
    dirpath: str,
    file: UploadFile = File(...),
    overwrite: bool = Query(False, description="Allow overwriting existing file"),
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Upload a file into a directory on the volume."""
    _require_key(_resolve_key(x_debug_key, key))
    target_dir = _safe_path(dirpath)

    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    elif not target_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {dirpath!r}")

    dest = target_dir / (file.filename or "upload")
    if dest.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"File already exists: {file.filename!r}. Use ?overwrite=true to replace.",
        )

    try:
        contents = await file.read()
        dest.write_bytes(contents)
    except Exception as e:
        logger.error("upload_file error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "path": str(dest.relative_to(VOLUME_PATH)),
        "filename": dest.name,
        "size_bytes": len(contents),
        "size_kb": round(len(contents) / 1024, 1),
    }


@router.post("/upload")
async def upload_file_root(
    file: UploadFile = File(...),
    overwrite: bool = Query(False),
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Upload a file into the volume root."""
    return await upload_file("", file, overwrite, key, x_debug_key)


@router.delete("/delete/{filepath:path}")
async def delete_path(
    filepath: str,
    recursive: bool = Query(False, description="Recursively delete non-empty directories"),
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Delete a file or directory from the volume.  Pass ?recursive=true to nuke a folder tree."""
    _require_key(_resolve_key(x_debug_key, key))
    target = _safe_path(filepath)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {filepath!r}")

    # Defensive: never let someone delete the volume root itself
    if target.resolve() == VOLUME_PATH.resolve():
        raise HTTPException(status_code=400, detail="Refusing to delete volume root.")

    try:
        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()  # only removes empty directories
            kind = "directory"
        else:
            target.unlink()
            kind = "file"
    except OSError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not delete: {e}. (Use ?recursive=true for non-empty directories.)",
        )

    return {"success": True, "deleted": filepath, "type": kind}


@router.post("/mkdir/{dirpath:path}")
async def make_directory(
    dirpath: str,
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Create a directory (and any missing parents) inside the volume."""
    _require_key(_resolve_key(x_debug_key, key))
    target = _safe_path(dirpath)
    target.mkdir(parents=True, exist_ok=True)
    return {
        "success": True,
        "created": str(target.relative_to(VOLUME_PATH)),
    }


@router.post("/move")
async def move_path(
    body: MoveRequest,
    key: Optional[str] = Query(None),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Move or rename a file/directory within the volume."""
    _require_key(_resolve_key(x_debug_key, key))
    src = _safe_path(body.src)
    dst = _safe_path(body.dst)

    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Source not found: {body.src!r}")
    if dst.exists():
        raise HTTPException(status_code=409, detail=f"Destination already exists: {body.dst!r}")

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "src": body.src,
        "dst": str(dst.relative_to(VOLUME_PATH)),
    }


# ---------------------------------------------------------------------------
# Web UI — full FTP-style file browser served at /volume/ui
# ---------------------------------------------------------------------------

_UI_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Volume Browser — Railway FTP</title>
<style>
  :root{
    --bg:#0b1020; --panel:#121a33; --panel2:#1a2444; --line:#27325a;
    --text:#e6eaf5; --muted:#8a96b8; --accent:#5b8cff; --accent2:#7c5bff;
    --ok:#27c08c; --warn:#e8b43a; --err:#ef5a6f;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;
       background:linear-gradient(180deg,#0a0f1f 0%,#0b1020 100%); color:var(--text);}
  header{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--line);
         background:rgba(255,255,255,.02);position:sticky;top:0;z-index:5;backdrop-filter:blur(8px)}
  header .logo{width:34px;height:34px;border-radius:8px;
       background:conic-gradient(from 200deg,var(--accent),var(--accent2));}
  header h1{font-size:16px;margin:0;letter-spacing:.3px}
  header .stats{margin-left:auto;color:var(--muted);font-size:12px}
  .container{max-width:1200px;margin:0 auto;padding:18px 20px 80px}

  .auth{display:flex;gap:8px;align-items:center;margin-bottom:16px}
  .auth input{flex:1;padding:10px 12px;border-radius:8px;border:1px solid var(--line);
              background:var(--panel);color:var(--text);font:inherit}
  button,.btn{cursor:pointer;border:1px solid var(--line);background:var(--panel2);color:var(--text);
              padding:8px 12px;border-radius:8px;font:inherit;transition:.15s}
  button:hover,.btn:hover{border-color:var(--accent);color:var(--accent)}
  button.primary{background:linear-gradient(180deg,var(--accent) 0%,var(--accent2) 100%);
                 border-color:transparent;color:#fff}
  button.primary:hover{filter:brightness(1.08);color:#fff}
  button.danger{color:var(--err);border-color:rgba(239,90,111,.4)}
  button.danger:hover{background:rgba(239,90,111,.12);border-color:var(--err);color:var(--err)}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}

  .crumbs{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:8px 0 14px;font-size:13px}
  .crumbs a{color:var(--accent);text-decoration:none;padding:4px 8px;border-radius:6px}
  .crumbs a:hover{background:rgba(91,140,255,.12)}
  .crumbs .sep{color:var(--muted)}

  .toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}

  .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
  table{width:100%;border-collapse:collapse}
  th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:13.5px;vertical-align:middle}
  th{font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);
     background:rgba(255,255,255,.02);font-weight:600}
  tr:last-child td{border-bottom:none}
  tr:hover td{background:rgba(91,140,255,.05)}
  .name{display:flex;gap:10px;align-items:center;min-width:0}
  .name .ico{width:22px;height:22px;flex:0 0 22px;display:grid;place-items:center;font-size:16px}
  .name a{color:var(--text);text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .name a:hover{color:var(--accent)}
  .actions{display:flex;gap:6px;justify-content:flex-end}
  .actions button{padding:5px 9px;font-size:12px}
  .size,.mtime{color:var(--muted);font-variant-numeric:tabular-nums;font-size:12.5px;white-space:nowrap}
  .empty{padding:40px;text-align:center;color:var(--muted)}
  th.sortable{cursor:pointer;user-select:none}
  th.sortable:hover{color:var(--accent)}
  th.sortable .arrow{display:inline-block;margin-left:4px;opacity:.5;font-size:10px}
  th.sortable.active{color:var(--accent)}
  th.sortable.active .arrow{opacity:1}

  .drop{border:2px dashed var(--line);border-radius:12px;padding:20px;margin:14px 0;text-align:center;color:var(--muted);
        transition:.2s}
  .drop.over{border-color:var(--accent);background:rgba(91,140,255,.06);color:var(--text)}
  .drop input{display:none}

  .toast{position:fixed;right:20px;bottom:20px;z-index:99;display:flex;flex-direction:column;gap:8px}
  .toast .t{padding:10px 14px;border-radius:8px;background:var(--panel2);border:1px solid var(--line);
            box-shadow:0 12px 40px rgba(0,0,0,.5);min-width:240px;animation:in .25s ease}
  .toast .t.ok{border-color:var(--ok)}
  .toast .t.err{border-color:var(--err)}
  @keyframes in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

  .hidden{display:none !important}
  .pill{display:inline-block;padding:2px 8px;border-radius:999px;background:var(--panel2);
        border:1px solid var(--line);font-size:11px;color:var(--muted)}
  .progress{height:4px;background:var(--line);border-radius:99px;overflow:hidden;margin-top:6px}
  .progress > div{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));width:0}

  @media (max-width:640px){
    th.col-size,td.col-size,
    th.col-mtime,td.col-mtime{display:none}
  }
</style>
</head>
<body>

<header>
  <div class="logo"></div>
  <h1>Volume Browser</h1>
  <div class="stats" id="stats">—</div>
</header>

<div class="container">

  <div class="panel" id="loginPanel">
    <div style="padding:18px">
      <h2 style="margin:0 0 6px 0;font-size:15px">Authentication</h2>
      <p style="margin:0 0 12px 0;color:var(--muted);font-size:12.5px">
        Paste your <code>VOLUME_DEBUG_KEY</code>. It is stored in localStorage on this device only.
      </p>
      <div class="auth">
        <input id="keyInput" type="password" placeholder="VOLUME_DEBUG_KEY" autocomplete="off"/>
        <button class="primary" id="loginBtn">Connect</button>
      </div>
    </div>
  </div>

  <div id="app" class="hidden">
    <div class="row" style="justify-content:space-between;margin-bottom:6px">
      <div class="crumbs" id="crumbs"></div>
      <div class="row">
        <span class="pill" id="diskPill">disk —</span>
        <button id="refreshBtn">↻ Refresh</button>
        <button id="logoutBtn">Logout</button>
      </div>
    </div>

    <div class="toolbar">
      <button class="primary" id="uploadBtn">⬆ Upload files</button>
      <button id="mkdirBtn">📁 New folder</button>
      <button id="zipBtn">🗜 Download folder as ZIP</button>
    </div>

    <label class="drop" id="drop">
      <strong>Drop files here</strong> or click to choose. They upload into the current folder.
      <input type="file" id="fileInput" multiple />
      <div class="progress hidden" id="progress"><div></div></div>
    </label>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th class="sortable" data-sort="name"   style="width:38%">Name<span class="arrow"></span></th>
            <th class="sortable col-size"  data-sort="size"   style="width:110px">Size<span class="arrow"></span></th>
            <th class="sortable col-mtime" data-sort="mtime"  style="width:170px">Modified<span class="arrow"></span></th>
            <th style="width:90px">Type</th>
            <th style="width:240px;text-align:right">Actions</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
      <div class="empty hidden" id="empty">This folder is empty.</div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const $ = (s) => document.querySelector(s);
const els = {
  login: $('#loginPanel'), app: $('#app'),
  keyInput: $('#keyInput'), loginBtn: $('#loginBtn'), logoutBtn: $('#logoutBtn'),
  refreshBtn: $('#refreshBtn'), uploadBtn: $('#uploadBtn'),
  mkdirBtn: $('#mkdirBtn'), zipBtn: $('#zipBtn'),
  crumbs: $('#crumbs'), rows: $('#rows'), empty: $('#empty'),
  drop: $('#drop'), fileInput: $('#fileInput'),
  progress: $('#progress'), progressBar: $('#progress > div'),
  stats: $('#stats'), disk: $('#diskPill'), toast: $('#toast'),
};

const KEY_STORAGE = 'volume_debug_key';
const SORT_STORAGE = 'volume_sort';
let KEY = localStorage.getItem(KEY_STORAGE) || '';
let CWD = ''; // relative path within volume
let SORT = JSON.parse(localStorage.getItem(SORT_STORAGE) || 'null') || {by:'mtime', dir:'desc'};
let LAST_ITEMS = [];

function toast(msg, kind='ok'){
  const el = document.createElement('div');
  el.className = 't ' + kind;
  el.textContent = msg;
  els.toast.appendChild(el);
  setTimeout(()=>{ el.style.opacity='0'; el.style.transition='.4s'; setTimeout(()=>el.remove(),400); }, 2800);
}

function fmtSize(b){
  if(b == null) return '';
  if(b < 1024) return b + ' B';
  if(b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
  if(b < 1024*1024*1024) return (b/1048576).toFixed(2) + ' MB';
  return (b/1073741824).toFixed(2) + ' GB';
}
function fmtDate(secs){
  if(!secs) return '';
  const d = new Date(secs * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const opts = sameDay
    ? {hour:'2-digit', minute:'2-digit'}
    : (d.getFullYear() === now.getFullYear()
        ? {month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit'}
        : {year:'numeric', month:'short', day:'2-digit'});
  return d.toLocaleString(undefined, opts);
}

function sortItems(items){
  // Always: directories first, then files; within each group, apply SORT.
  const dirs  = items.filter(i => i.type === 'directory');
  const files = items.filter(i => i.type !== 'directory');
  const cmp = (a,b) => {
    let av, bv;
    if(SORT.by === 'name'){ av = (a.name||'').toLowerCase(); bv = (b.name||'').toLowerCase(); }
    else if(SORT.by === 'size'){ av = a.size_bytes ?? -1; bv = b.size_bytes ?? -1; }
    else { av = a.mtime ?? 0; bv = b.mtime ?? 0; }
    if(av < bv) return SORT.dir === 'asc' ? -1 :  1;
    if(av > bv) return SORT.dir === 'asc' ?  1 : -1;
    return (a.name||'').localeCompare(b.name||'');
  };
  dirs.sort(cmp); files.sort(cmp);
  return [...dirs, ...files];
}

function updateSortHeaders(){
  document.querySelectorAll('th.sortable').forEach(th => {
    const isActive = th.dataset.sort === SORT.by;
    th.classList.toggle('active', isActive);
    th.querySelector('.arrow').textContent = isActive ? (SORT.dir === 'asc' ? '▲' : '▼') : '';
  });
}
function iconFor(item){
  if(item.type === 'directory') return '📁';
  const ext = (item.name.split('.').pop() || '').toLowerCase();
  const map = {
    pdf:'📕', doc:'📄', docx:'📄', txt:'📄', md:'📝', json:'🧾', yaml:'🧾', yml:'🧾',
    zip:'🗜', tar:'🗜', gz:'🗜',
    png:'🖼', jpg:'🖼', jpeg:'🖼', gif:'🖼', svg:'🖼', webp:'🖼',
    mp3:'🎵', wav:'🎵', flac:'🎵',
    mp4:'🎬', mov:'🎬', mkv:'🎬',
    py:'🐍', js:'📜', ts:'📜', html:'📜', css:'📜',
    xlsx:'📊', xls:'📊', csv:'📊', pptx:'📊',
  };
  return map[ext] || '📦';
}

async function api(path, opts={}){
  const url = new URL(path, location.origin);
  // Always send key on the URL too — works for downloads/streams.
  if(KEY) url.searchParams.set('key', KEY);
  const headers = Object.assign({'X-Debug-Key': KEY || ''}, opts.headers || {});
  const res = await fetch(url, Object.assign({headers}, opts));
  if(!res.ok){
    let detail = res.statusText;
    try{ detail = (await res.json()).detail || detail; }catch{}
    throw new Error(detail);
  }
  if(opts.raw) return res;
  const ct = res.headers.get('content-type') || '';
  if(ct.includes('json')) return res.json();
  return res.text();
}

function downloadUrl(path, kind='download'){
  const u = new URL(`/volume/${kind}/${encodeURIComponent(path).replace(/%2F/g,'/')}`, location.origin);
  if(KEY) u.searchParams.set('key', KEY);
  return u.toString();
}

function renderCrumbs(){
  const parts = CWD ? CWD.split('/').filter(Boolean) : [];
  const frags = [`<a href="#" data-path="">📦 /</a>`];
  let acc = '';
  parts.forEach((p,i)=>{
    acc = acc ? acc + '/' + p : p;
    frags.push(`<span class="sep">/</span><a href="#" data-path="${encodeURI(acc)}">${escapeHtml(p)}</a>`);
  });
  els.crumbs.innerHTML = frags.join('');
  els.crumbs.querySelectorAll('a').forEach(a => a.onclick = e => {
    e.preventDefault(); CWD = decodeURI(a.getAttribute('data-path')||''); load();
  });
}
function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }

async function load(){
  renderCrumbs();
  els.rows.innerHTML = `<tr><td colspan="5" style="color:var(--muted);padding:24px;text-align:center">Loading…</td></tr>`;
  els.empty.classList.add('hidden');
  try {
    const data = await api(`/volume/ls/${encodeURI(CWD)}`);
    LAST_ITEMS = data.items || [];
    renderRows();
    els.stats.textContent = `${data.directories || 0} folders · ${data.files || 0} files`;
  } catch(e){
    els.rows.innerHTML = `<tr><td colspan="5" style="color:var(--err);padding:24px;text-align:center">${escapeHtml(e.message)}</td></tr>`;
  }

  // disk info (best-effort)
  try{
    const info = await api('/volume/info');
    if(info.disk_used_gb != null)
      els.disk.textContent = `disk ${info.disk_used_gb} / ${info.disk_total_gb} GB`;
    else
      els.disk.textContent = `${info.total_files || 0} files · ${info.total_size_mb || 0} MB`;
  }catch{}
}

function renderRows(){
  updateSortHeaders();
  if(!LAST_ITEMS.length){
    els.rows.innerHTML = '';
    els.empty.classList.remove('hidden');
    return;
  }
  els.empty.classList.add('hidden');
  const sorted = sortItems(LAST_ITEMS);
  els.rows.innerHTML = sorted.map(it => row(it)).join('');
  bindRowEvents();
}

function row(it){
  const isDir = it.type === 'directory';
  const safe = encodeURI(it.path);
  return `<tr data-path="${safe}" data-type="${it.type}">
    <td class="name">
      <span class="ico">${iconFor(it)}</span>
      ${isDir
        ? `<a href="#" class="open">${escapeHtml(it.name)}</a>`
        : `<a href="${downloadUrl(it.path)}" download>${escapeHtml(it.name)}</a>`}
    </td>
    <td class="col-size size">${isDir ? '—' : fmtSize(it.size_bytes)}</td>
    <td class="col-mtime mtime">${fmtDate(it.mtime)}</td>
    <td><span class="pill">${isDir ? 'folder' : 'file'}</span></td>
    <td class="actions">
      ${isDir
        ? `<a class="btn" href="${downloadUrl(it.path,'zip')}">⬇ ZIP</a>`
        : `<a class="btn" href="${downloadUrl(it.path)}" download>⬇ Download</a>
           <a class="btn" href="${downloadUrl(it.path)+'&inline=true'}" target="_blank">👁 View</a>`}
      <button class="rename">✎</button>
      <button class="danger del">🗑</button>
    </td>
  </tr>`;
}
function bindRowEvents(){
  els.rows.querySelectorAll('tr').forEach(tr=>{
    const path = decodeURI(tr.getAttribute('data-path'));
    const type = tr.getAttribute('data-type');
    const open = tr.querySelector('a.open');
    if(open) open.onclick = e => { e.preventDefault(); CWD = path; load(); };
    tr.querySelector('.rename').onclick = ()=> renameItem(path);
    tr.querySelector('.del').onclick    = ()=> deleteItem(path, type);
  });
}

async function renameItem(path){
  const base = path.split('/').pop();
  const newName = prompt('New name (or new relative path):', base);
  if(!newName || newName === base) return;
  const parent = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
  const dst = newName.includes('/') ? newName : (parent ? parent + '/' + newName : newName);
  try{
    await api('/volume/move', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({src: path, dst}),
    });
    toast('Renamed');
    load();
  }catch(e){ toast(e.message,'err'); }
}

async function deleteItem(path, type){
  const recursive = type === 'directory';
  const msg = recursive
    ? `Recursively DELETE folder "${path}"?\nThis cannot be undone.`
    : `Delete file "${path}"?`;
  if(!confirm(msg)) return;
  try{
    const url = `/volume/delete/${encodeURI(path)}` + (recursive ? '&recursive=true' : '');
    // url already gets ?key=… added by api(); fix the join:
    const u = new URL(`/volume/delete/${encodeURI(path)}`, location.origin);
    if(KEY) u.searchParams.set('key', KEY);
    if(recursive) u.searchParams.set('recursive','true');
    const res = await fetch(u, {method:'DELETE', headers:{'X-Debug-Key': KEY}});
    if(!res.ok){ throw new Error((await res.json()).detail || res.statusText); }
    toast('Deleted');
    load();
  }catch(e){ toast(e.message,'err'); }
}

async function mkdir(){
  const name = prompt('New folder name:');
  if(!name) return;
  const target = CWD ? CWD + '/' + name : name;
  try{
    const u = new URL(`/volume/mkdir/${encodeURI(target)}`, location.origin);
    const res = await fetch(u, {method:'POST', headers:{'X-Debug-Key': KEY}});
    if(!res.ok) throw new Error((await res.json()).detail || res.statusText);
    toast('Folder created');
    load();
  }catch(e){ toast(e.message,'err'); }
}

async function uploadFiles(files){
  if(!files || !files.length) return;
  els.progress.classList.remove('hidden');
  els.progressBar.style.width = '0%';
  let i = 0;
  for(const f of files){
    try{
      await uploadOne(f, (p)=> { 
        const total = ((i + p) / files.length) * 100;
        els.progressBar.style.width = total.toFixed(1) + '%';
      });
      i++;
    }catch(e){ toast(`${f.name}: ${e.message}`,'err'); i++; }
  }
  els.progressBar.style.width = '100%';
  setTimeout(()=>els.progress.classList.add('hidden'), 600);
  toast(`Uploaded ${files.length} file${files.length>1?'s':''}`);
  load();
}

function uploadOne(file, onProgress){
  return new Promise((resolve, reject)=>{
    const fd = new FormData();
    fd.append('file', file);
    const xhr = new XMLHttpRequest();
    const url = `/volume/upload/${encodeURI(CWD)}?overwrite=true`;
    xhr.open('POST', url);
    xhr.setRequestHeader('X-Debug-Key', KEY || '');
    xhr.upload.onprogress = e => {
      if(e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if(xhr.status >= 200 && xhr.status < 300) resolve();
      else { try{ reject(new Error(JSON.parse(xhr.responseText).detail || xhr.statusText)); }
             catch{ reject(new Error(xhr.statusText)); } }
    };
    xhr.onerror = () => reject(new Error('Network error'));
    xhr.send(fd);
  });
}

// ── login flow ────────────────────────────────────────────────────────────────
function showApp(){
  els.login.classList.add('hidden');
  els.app.classList.remove('hidden');
  load();
}
function showLogin(){
  els.login.classList.remove('hidden');
  els.app.classList.add('hidden');
  els.keyInput.focus();
}
async function tryLogin(k){
  KEY = (k||'').trim();
  if(!KEY) return toast('Enter a key first','err');
  try{
    await api('/volume/info');
    localStorage.setItem(KEY_STORAGE, KEY);
    showApp();
  }catch(e){
    toast('Auth failed: ' + e.message, 'err');
  }
}

// ── wiring ────────────────────────────────────────────────────────────────────
els.loginBtn.onclick = () => tryLogin(els.keyInput.value);
els.keyInput.addEventListener('keydown', e => { if(e.key==='Enter') tryLogin(els.keyInput.value); });
els.logoutBtn.onclick = () => { localStorage.removeItem(KEY_STORAGE); KEY=''; showLogin(); };
els.refreshBtn.onclick = () => load();
els.mkdirBtn.onclick = () => mkdir();
els.zipBtn.onclick = () => {
  const u = downloadUrl(CWD || '', 'zip');
  window.location.href = u;
};
els.uploadBtn.onclick = () => els.fileInput.click();
els.fileInput.addEventListener('change', e => uploadFiles(Array.from(e.target.files)));

// Sortable column headers
document.querySelectorAll('th.sortable').forEach(th => {
  th.addEventListener('click', () => {
    const by = th.dataset.sort;
    if(SORT.by === by){
      SORT.dir = SORT.dir === 'asc' ? 'desc' : 'asc';
    } else {
      SORT.by = by;
      // Sensible defaults: name asc, size/mtime desc
      SORT.dir = (by === 'name') ? 'asc' : 'desc';
    }
    localStorage.setItem(SORT_STORAGE, JSON.stringify(SORT));
    renderRows();
  });
});

['dragenter','dragover'].forEach(ev =>
  els.drop.addEventListener(ev, e => { e.preventDefault(); els.drop.classList.add('over'); }));
['dragleave','drop'].forEach(ev =>
  els.drop.addEventListener(ev, e => { e.preventDefault(); els.drop.classList.remove('over'); }));
els.drop.addEventListener('drop', e => {
  const files = Array.from(e.dataTransfer.files || []);
  if(files.length) uploadFiles(files);
});

// boot
if(KEY) tryLogin(KEY); else showLogin();
</script>

</body>
</html>
"""


@router.get("/ui", response_class=HTMLResponse)
async def volume_ui():
    """
    Browser-based FTP-style file manager for the Railway volume.

    No auth required to load the page itself — but every API call from the page
    sends X-Debug-Key (or ?key=) and must match VOLUME_DEBUG_KEY.
    The user is prompted for the key on first load and it's stored in localStorage.
    """
    return HTMLResponse(_UI_HTML)

