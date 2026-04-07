"""
Railway Volume Browser — Local GUI Client
==========================================
A Tkinter desktop app to browse, upload, download, and delete files
on the Railway persistent volume via the /volume/* debug endpoints.

Requirements (all stdlib or one pip install):
    pip install requests

Usage:
    python utilities/volume_gui.py

On first run fill in the API URL and debug key in the Settings panel,
then click "Connect".  Your settings are auto-saved to
~/.volume_browser_config.json between sessions.
"""

import json
import os
import threading
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import tkinter.simpledialog as sd
import tkinter.ttk as ttk
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config persistence
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".volume_browser_config.json"

DEFAULT_CONFIG = {
    "api_url": "https://developer-potomaac.up.railway.app",
    "debug_key": "",
}


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text())}
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# API Client
# ─────────────────────────────────────────────────────────────────────────────

class VolumeClient:
    def __init__(self, base_url: str, debug_key: str, timeout: int = 30):
        self.base = base_url.rstrip("/")
        self.headers = {"X-Debug-Key": debug_key}
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base}/volume/{path.lstrip('/')}"

    def info(self) -> dict:
        r = requests.get(self._url("info"), headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def ls(self, dirpath: str = "") -> dict:
        path = f"ls/{dirpath}" if dirpath else "ls"
        r = requests.get(self._url(path), headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def download(self, filepath: str) -> bytes:
        r = requests.get(
            self._url(f"download/{filepath}"),
            headers=self.headers,
            timeout=120,
            stream=True,
        )
        r.raise_for_status()
        return r.content

    def upload(self, dirpath: str, local_path: Path, overwrite: bool = False) -> dict:
        params = {"overwrite": "true"} if overwrite else {}
        endpoint = f"upload/{dirpath}" if dirpath else "upload"
        with open(local_path, "rb") as f:
            r = requests.post(
                self._url(endpoint),
                headers=self.headers,
                files={"file": (local_path.name, f)},
                params=params,
                timeout=120,
            )
        r.raise_for_status()
        return r.json()

    def delete(self, filepath: str) -> dict:
        r = requests.delete(
            self._url(f"delete/{filepath}"),
            headers=self.headers,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def mkdir(self, dirpath: str) -> dict:
        r = requests.post(
            self._url(f"mkdir/{dirpath}"),
            headers=self.headers,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def move(self, src: str, dst: str) -> dict:
        r = requests.post(
            self._url("move"),
            headers=self.headers,
            json={"src": src, "dst": dst},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

DARK_BG  = "#1e1e2e"
PANEL_BG = "#2a2a3e"
ACCENT   = "#7c6af7"          # purple
TEXT     = "#cdd6f4"
MUTED    = "#6c7086"
GREEN    = "#a6e3a1"
RED      = "#f38ba8"
YELLOW   = "#f9e2af"
BLUE     = "#89b4fa"

ICON_FILE   = "📄"
ICON_FOLDER = "📁"
ICON_UP     = "⬆"
ICON_DL     = "⬇"
ICON_DEL    = "🗑"
ICON_MK     = "➕"
ICON_MV     = "✏"
ICON_REF    = "🔄"
ICON_CONN   = "🔌"
ICON_INFO   = "ℹ"


class VolumeBrowser(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Railway Volume Browser")
        self.geometry("1050x680")
        self.configure(bg=DARK_BG)
        self.resizable(True, True)

        self.cfg = load_config()
        self.client: Optional[VolumeClient] = None
        self._current_dir = ""          # relative path being shown
        self._items: list[dict] = []    # current listing

        self._build_ui()
        self._apply_theme()

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar: connection settings ──────────────────────────────────
        top = tk.Frame(self, bg=PANEL_BG, pady=6, padx=10)
        top.pack(fill=tk.X, side=tk.TOP)

        tk.Label(top, text="API URL:", bg=PANEL_BG, fg=TEXT, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._url_var = tk.StringVar(value=self.cfg["api_url"])
        url_entry = tk.Entry(top, textvariable=self._url_var, width=42, bg="#313244",
                             fg=TEXT, insertbackground=TEXT, relief=tk.FLAT, font=("Segoe UI", 9))
        url_entry.pack(side=tk.LEFT, padx=(4, 12))

        tk.Label(top, text="Debug Key:", bg=PANEL_BG, fg=TEXT, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._key_var = tk.StringVar(value=self.cfg["debug_key"])
        key_entry = tk.Entry(top, textvariable=self._key_var, width=28, show="•", bg="#313244",
                             fg=TEXT, insertbackground=TEXT, relief=tk.FLAT, font=("Segoe UI", 9))
        key_entry.pack(side=tk.LEFT, padx=(4, 12))

        self._conn_btn = tk.Button(top, text=f"{ICON_CONN} Connect", command=self._connect,
                                   bg=ACCENT, fg="white", relief=tk.FLAT,
                                   font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10)
        self._conn_btn.pack(side=tk.LEFT)

        self._status_lbl = tk.Label(top, text="Not connected", bg=PANEL_BG,
                                    fg=MUTED, font=("Segoe UI", 9))
        self._status_lbl.pack(side=tk.LEFT, padx=14)

        # disk info on the right
        self._disk_lbl = tk.Label(top, text="", bg=PANEL_BG, fg=MUTED, font=("Segoe UI", 8))
        self._disk_lbl.pack(side=tk.RIGHT, padx=8)

        # ── Path bar ──────────────────────────────────────────────────────
        path_bar = tk.Frame(self, bg=DARK_BG, pady=4, padx=10)
        path_bar.pack(fill=tk.X)

        tk.Label(path_bar, text="Path:", bg=DARK_BG, fg=MUTED, font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self._path_lbl = tk.Label(path_bar, text="/", bg=DARK_BG, fg=BLUE,
                                  font=("Segoe UI", 9, "bold"))
        self._path_lbl.pack(side=tk.LEFT, padx=6)

        tk.Button(path_bar, text="⬅ Back", command=self._go_up,
                  bg=PANEL_BG, fg=TEXT, relief=tk.FLAT, font=("Segoe UI", 8),
                  cursor="hand2").pack(side=tk.LEFT, padx=4)

        tk.Button(path_bar, text=f"{ICON_REF} Refresh", command=self._refresh,
                  bg=PANEL_BG, fg=TEXT, relief=tk.FLAT, font=("Segoe UI", 8),
                  cursor="hand2").pack(side=tk.LEFT, padx=4)

        # ── Main pane: tree on left, detail on right ───────────────────────
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=DARK_BG,
                              sashwidth=5, sashrelief=tk.FLAT)
        pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # File tree frame
        tree_frame = tk.Frame(pane, bg=PANEL_BG)
        pane.add(tree_frame, minsize=500)

        # Toolbar above tree
        toolbar = tk.Frame(tree_frame, bg=PANEL_BG, pady=4)
        toolbar.pack(fill=tk.X, padx=6)

        for label, cmd in [
            (f"{ICON_UP} Upload",   self._upload),
            (f"{ICON_DL} Download", self._download),
            (f"{ICON_DEL} Delete",  self._delete),
            (f"{ICON_MK} Mkdir",    self._mkdir),
            (f"{ICON_MV} Rename",   self._rename),
        ]:
            tk.Button(toolbar, text=label, command=cmd, bg="#313244", fg=TEXT,
                      relief=tk.FLAT, font=("Segoe UI", 8), cursor="hand2",
                      padx=8, pady=2).pack(side=tk.LEFT, padx=3)

        # Treeview
        cols = ("name", "type", "size")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   selectmode="browse")
        self._tree.heading("name", text="Name", anchor=tk.W)
        self._tree.heading("type", text="Type", anchor=tk.W)
        self._tree.heading("size", text="Size", anchor=tk.E)
        self._tree.column("name", width=320, anchor=tk.W, stretch=True)
        self._tree.column("type", width=80,  anchor=tk.W, stretch=False)
        self._tree.column("size", width=80,  anchor=tk.E, stretch=False)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=(6, 0), pady=(0, 6))
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Detail / log panel on right
        detail_frame = tk.Frame(pane, bg=PANEL_BG)
        pane.add(detail_frame, minsize=220)

        tk.Label(detail_frame, text="Log / Details", bg=PANEL_BG,
                 fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, padx=8, pady=(6, 2))

        self._log = tk.Text(detail_frame, bg="#181825", fg=TEXT, insertbackground=TEXT,
                            font=("Consolas", 8), relief=tk.FLAT, wrap=tk.WORD,
                            state=tk.DISABLED)
        log_vsb = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self._log.yview)
        self._log.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 6))
        self._log.pack(fill=tk.BOTH, expand=True, padx=(8, 0), pady=(0, 6))

        # ── Status bar ────────────────────────────────────────────────────
        status_bar = tk.Frame(self, bg="#181825", pady=3)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._bottom_lbl = tk.Label(status_bar, text="Ready", bg="#181825",
                                    fg=MUTED, font=("Segoe UI", 8), anchor=tk.W)
        self._bottom_lbl.pack(side=tk.LEFT, padx=10)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Treeview",
                         background=PANEL_BG,
                         foreground=TEXT,
                         fieldbackground=PANEL_BG,
                         rowheight=22,
                         font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                         background="#313244",
                         foreground=MUTED,
                         font=("Segoe UI", 9, "bold"),
                         relief=tk.FLAT)
        style.map("Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])
        style.configure("Vertical.TScrollbar",
                         background=PANEL_BG, troughcolor=DARK_BG,
                         arrowcolor=MUTED, bordercolor=DARK_BG)

    # ── Logging ──────────────────────────────────────────────────────────

    def _log_msg(self, msg: str, color: str = TEXT):
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, msg + "\n")
        self._log.tag_add(f"c{id(msg)}", f"end-{len(msg)+1}c", "end-1c")
        self._log.tag_configure(f"c{id(msg)}", foreground=color)
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _set_status(self, msg: str, color: str = MUTED):
        self._bottom_lbl.configure(text=msg, fg=color)

    # ── Connection ────────────────────────────────────────────────────────

    def _connect(self):
        url = self._url_var.get().strip()
        key = self._key_var.get().strip()
        if not url:
            mb.showerror("Missing", "Please enter an API URL.")
            return

        self._save_settings()
        self.client = VolumeClient(url, key)
        self._status_lbl.configure(text="Connecting…", fg=YELLOW)
        self._set_status("Connecting…", YELLOW)
        self._run_async(self._do_connect)

    def _do_connect(self):
        try:
            info = self.client.info()
            self.after(0, self._connected, info)
        except Exception as e:
            self.after(0, self._connect_failed, str(e))

    def _connected(self, info: dict):
        exists = info.get("exists", False)
        total_mb = info.get("total_size_mb", 0)
        files    = info.get("total_files", 0)
        free_gb  = info.get("disk_free_gb", "?")
        used_gb  = info.get("disk_used_gb", "?")
        vol      = info.get("volume_path", "/data")

        if not exists:
            self._status_lbl.configure(text=f"⚠ Volume {vol} not mounted", fg=YELLOW)
            self._log_msg(f"⚠ Volume path {vol} does not exist on the server.", YELLOW)
        else:
            self._status_lbl.configure(text=f"✔ Connected  |  {vol}", fg=GREEN)
            self._disk_lbl.configure(text=f"Used {used_gb} GB / Free {free_gb} GB  |  {files} files  {total_mb} MB")
            self._log_msg(f"✔ Connected to {self.client.base}", GREEN)
            self._log_msg(f"   Volume: {vol}  |  {files} files  |  {total_mb} MB used", MUTED)

        self._set_status("Connected", GREEN)
        self._load_dir("")

    def _connect_failed(self, err: str):
        self._status_lbl.configure(text="✘ Connection failed", fg=RED)
        self._set_status("Connection failed", RED)
        self._log_msg(f"✘ Connection error: {err}", RED)
        mb.showerror("Connection Error", err)

    # ── Directory listing ─────────────────────────────────────────────────

    def _load_dir(self, dirpath: str):
        self._set_status(f"Loading {dirpath or '/'}…", YELLOW)
        self._run_async(self._do_load_dir, dirpath)

    def _do_load_dir(self, dirpath: str):
        try:
            result = self.client.ls(dirpath)
            self.after(0, self._show_dir, dirpath, result)
        except Exception as e:
            self.after(0, self._log_msg, f"✘ ls error: {e}", RED)
            self.after(0, self._set_status, str(e), RED)

    def _show_dir(self, dirpath: str, result: dict):
        self._current_dir = dirpath
        display = "/" + dirpath if dirpath else "/"
        self._path_lbl.configure(text=display)

        self._tree.delete(*self._tree.get_children())
        self._items = result.get("items", [])

        for item in self._items:
            icon  = ICON_FOLDER if item["type"] == "directory" else ICON_FILE
            name  = f"{icon}  {item['name']}"
            kind  = item["type"].capitalize()
            size  = f"{item['size_kb']} KB" if item.get("size_kb") is not None else "—"
            self._tree.insert("", tk.END, values=(name, kind, size), tags=(item["path"],))

        n = result.get("count", 0)
        self._set_status(f"{n} items in {display}", GREEN)
        self._log_msg(f"Listed {display}  ({n} items)", MUTED)

    def _refresh(self):
        if self.client:
            self._load_dir(self._current_dir)

    def _go_up(self):
        if not self._current_dir:
            return
        parent = str(Path(self._current_dir).parent)
        if parent == ".":
            parent = ""
        self._load_dir(parent)

    # ── Tree interaction ──────────────────────────────────────────────────

    def _selected_item(self) -> Optional[dict]:
        sel = self._tree.selection()
        if not sel:
            return None
        idx = self._tree.index(sel[0])
        return self._items[idx] if idx < len(self._items) else None

    def _on_double_click(self, _event):
        item = self._selected_item()
        if item and item["type"] == "directory":
            self._load_dir(item["path"])

    def _on_select(self, _event):
        item = self._selected_item()
        if item:
            self._set_status(f"{item['type'].capitalize()}: {item['path']}", BLUE)

    # ── File operations ───────────────────────────────────────────────────

    def _require_client(self) -> bool:
        if not self.client:
            mb.showwarning("Not Connected", "Connect to the backend first.")
            return False
        return True

    # Upload
    def _upload(self):
        if not self._require_client():
            return
        paths = fd.askopenfilenames(title="Select files to upload")
        if not paths:
            return
        overwrite = mb.askyesno("Overwrite?", "Allow overwriting existing files?")
        for p in paths:
            local = Path(p)
            self._set_status(f"Uploading {local.name}…", YELLOW)
            self._run_async(self._do_upload, local, overwrite)

    def _do_upload(self, local: Path, overwrite: bool):
        try:
            result = self.client.upload(self._current_dir, local, overwrite)
            self.after(0, self._log_msg,
                       f"✔ Uploaded {result['filename']}  ({result['size_kb']} KB) → {result['path']}", GREEN)
            self.after(0, self._refresh)
        except requests.HTTPError as e:
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            self.after(0, self._log_msg, f"✘ Upload failed: {detail}", RED)
            self.after(0, mb.showerror, "Upload Error", detail)

    # Download
    def _download(self):
        if not self._require_client():
            return
        item = self._selected_item()
        if not item:
            mb.showwarning("No selection", "Select a file first.")
            return
        if item["type"] != "file":
            mb.showwarning("Not a file", "Select a file (not a directory) to download.")
            return

        dest = fd.asksaveasfilename(
            initialfile=item["name"],
            title="Save as…",
            defaultextension="",
        )
        if not dest:
            return

        self._set_status(f"Downloading {item['name']}…", YELLOW)
        self._run_async(self._do_download, item["path"], Path(dest))

    def _do_download(self, remote_path: str, local_dest: Path):
        try:
            data = self.client.download(remote_path)
            local_dest.write_bytes(data)
            self.after(0, self._log_msg,
                       f"✔ Downloaded {remote_path}  ({round(len(data)/1024, 1)} KB) → {local_dest}", GREEN)
            self.after(0, self._set_status, f"Saved to {local_dest.name}", GREEN)
        except Exception as e:
            self.after(0, self._log_msg, f"✘ Download failed: {e}", RED)
            self.after(0, mb.showerror, "Download Error", str(e))

    # Delete
    def _delete(self):
        if not self._require_client():
            return
        item = self._selected_item()
        if not item:
            mb.showwarning("No selection", "Select an item first.")
            return
        if not mb.askyesno("Confirm Delete",
                           f"Delete {item['type']} '{item['path']}'?\nThis cannot be undone."):
            return
        self._set_status(f"Deleting {item['path']}…", YELLOW)
        self._run_async(self._do_delete, item["path"])

    def _do_delete(self, remote_path: str):
        try:
            self.client.delete(remote_path)
            self.after(0, self._log_msg, f"🗑 Deleted {remote_path}", YELLOW)
            self.after(0, self._refresh)
        except requests.HTTPError as e:
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            self.after(0, self._log_msg, f"✘ Delete failed: {detail}", RED)
            self.after(0, mb.showerror, "Delete Error", detail)

    # Mkdir
    def _mkdir(self):
        if not self._require_client():
            return
        name = sd.askstring("New Folder", "Directory name (relative to current path):")
        if not name:
            return
        new_path = f"{self._current_dir}/{name}".lstrip("/")
        self._run_async(self._do_mkdir, new_path)

    def _do_mkdir(self, dirpath: str):
        try:
            self.client.mkdir(dirpath)
            self.after(0, self._log_msg, f"➕ Created directory: {dirpath}", GREEN)
            self.after(0, self._refresh)
        except Exception as e:
            self.after(0, self._log_msg, f"✘ mkdir failed: {e}", RED)
            self.after(0, mb.showerror, "Mkdir Error", str(e))

    # Rename / Move
    def _rename(self):
        if not self._require_client():
            return
        item = self._selected_item()
        if not item:
            mb.showwarning("No selection", "Select an item first.")
            return
        new_path = sd.askstring(
            "Move / Rename",
            f"Current path: {item['path']}\n\nNew path (relative to volume root):",
            initialvalue=item["path"],
        )
        if not new_path or new_path == item["path"]:
            return
        self._run_async(self._do_move, item["path"], new_path)

    def _do_move(self, src: str, dst: str):
        try:
            self.client.move(src, dst)
            self.after(0, self._log_msg, f"✏ Moved {src}  →  {dst}", GREEN)
            self.after(0, self._refresh)
        except requests.HTTPError as e:
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            self.after(0, self._log_msg, f"✘ Move failed: {detail}", RED)
            self.after(0, mb.showerror, "Move Error", detail)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _run_async(self, fn, *args):
        """Run a function in a background thread (Tkinter isn't thread-safe for widgets)."""
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _save_settings(self):
        cfg = {
            "api_url": self._url_var.get().strip(),
            "debug_key": self._key_var.get().strip(),
        }
        save_config(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = VolumeBrowser()
    app.mainloop()
