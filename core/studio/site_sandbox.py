"""
Content Studio — Site Sandbox Renderer.

Reuses the same ESM importmap + Babel standalone + Tailwind CDN approach as
``core.sandbox.node_sandbox._wrap_for_client_render`` but adapted for
multi-file React/JSX site bundles.

Public surface:

    wrap_react_site(files: dict[str, str]) -> dict[str, str]
        Takes the AI's React component files and returns a NEW files dict
        where index.html is a fully sandboxed, self-contained HTML page
        that loads all components via in-browser Babel + ESM importmap.
        CSS/image/font files are passed through unchanged.

    is_react_site(files: dict[str, str]) -> bool
        Heuristic: returns True if any file contains JSX or React imports.

    get_sandbox_html_template(entry_component: str, modules: dict) -> str
        Builds the sandboxed index.html string from the component map.

The generated index.html is identical in spirit to the ``execute_react``
tool's output — same CDN packages, same Babel config, same Tailwind,
same error boundary — but supports MULTIPLE component files and
CSS-in-bundle.

This means users can say "build me a React portfolio site with routing"
and the AI produces JSX files that work exactly like v0 / Lovable.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Re-use the ESM import map from the existing React sandbox
# ---------------------------------------------------------------------------

def _get_esm_import_map() -> Dict[str, str]:
    """Return the shared ESM importmap (same one as execute_react)."""
    try:
        from core.sandbox.node_sandbox import _ESM_IMPORT_MAP
        return dict(_ESM_IMPORT_MAP)
    except ImportError:
        # Fallback if the sandbox module can't be imported
        return {
            "react":              "https://esm.sh/react@18",
            "react-dom":          "https://esm.sh/react-dom@18?external=react",
            "react-dom/client":   "https://esm.sh/react-dom@18/client?external=react,react-dom",
            "react/jsx-runtime":  "https://esm.sh/react@18/jsx-runtime",
            "react/jsx-dev-runtime": "https://esm.sh/react@18/jsx-dev-runtime",
            "lucide-react":       "https://esm.sh/lucide-react?external=react",
            "recharts":           "https://esm.sh/recharts?external=react,react-dom",
            "framer-motion":      "https://esm.sh/framer-motion?external=react,react-dom",
            "react-router-dom":   "https://esm.sh/react-router-dom?external=react,react-dom",
            "clsx":               "https://esm.sh/clsx",
            "tailwind-merge":     "https://esm.sh/tailwind-merge",
            "date-fns":           "https://esm.sh/date-fns",
            "zustand":            "https://esm.sh/zustand",
            "zod":                "https://esm.sh/zod",
            "axios":              "https://esm.sh/axios",
            "lodash":             "https://esm.sh/lodash",
            "uuid":               "https://esm.sh/uuid",
            "d3":                 "https://esm.sh/d3",
            "chart.js":           "https://esm.sh/chart.js",
            "immer":              "https://esm.sh/immer",
        }


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

_JSX_PATTERNS = [
    r"<[A-Z][a-zA-Z]*[\s/>]",       # <Component ...>
    r"</[A-Z][a-zA-Z]+>",           # </Component>
    r"<>",                            # Fragment shorthand
    r"<React\.",                      # <React.Fragment>
    r"createElement\s*\(",           # React.createElement(
    r"from\s+['\"]react['\"]",       # import from 'react'
    r"from\s+['\"]react-dom['\"]",
    r"useState\s*\(",               # hook usage
    r"useEffect\s*\(",
    r"useRef\s*\(",
]

_JSX_RE = [re.compile(p) for p in _JSX_PATTERNS]


def is_react_site(files: Dict[str, str]) -> bool:
    """
    Heuristic: return True if any .jsx/.tsx file exists, OR if any file
    contains JSX syntax or React imports.
    """
    for path, content in files.items():
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("jsx", "tsx"):
            return True
        if ext in ("js", "ts", "html") and isinstance(content, str):
            if any(p.search(content) for p in _JSX_RE):
                return True
    return False


# ---------------------------------------------------------------------------
# React import stripping (same logic as node_sandbox)
# ---------------------------------------------------------------------------

_REACT_IMPORT_PATTERNS = [
    r"import\s+React\s*,?\s*(?:\{[^}]*\})?\s*from\s+['\"]react['\"][ \t]*;?[ \t]*\n?",
    r"import\s*\{[^}]*\}\s*from\s+['\"]react['\"][ \t]*;?[ \t]*\n?",
    r"import\s*\*\s*as\s+\w+\s+from\s+['\"]react['\"][ \t]*;?[ \t]*\n?",
    r"import\s+\w+\s+from\s+['\"]react-dom['\"][ \t]*;?[ \t]*\n?",
    r"import\s*\{[^}]*\}\s*from\s+['\"]react-dom(?:/client|/server)?['\"][ \t]*;?[ \t]*\n?",
]


def _strip_react_imports(code: str) -> str:
    for p in _REACT_IMPORT_PATTERNS:
        code = re.sub(p, "", code, flags=re.MULTILINE)
    return code


def _strip_export_default(code: str) -> Tuple[str, Optional[str]]:
    """Strip export default and return (code, component_name)."""
    # export default function Foo
    m = re.search(r"\bexport\s+default\s+(function)\s+(\w+)", code)
    if m:
        return code[:m.start()] + m.group(1) + " " + m.group(2) + code[m.end():], m.group(2)
    # export default class Foo
    m = re.search(r"\bexport\s+default\s+(class)\s+(\w+)", code)
    if m:
        return code[:m.start()] + m.group(1) + " " + m.group(2) + code[m.end():], m.group(2)
    # export default Foo;
    m = re.search(r"^\s*export\s+default\s+(\w+)\s*;?\s*$", code, re.MULTILINE)
    if m:
        return (code[:m.start()] + code[m.end():]).strip(), m.group(1)
    return code, None


def _strip_local_imports(code: str, local_modules: set) -> str:
    """
    Remove import statements that reference local files (e.g.
    import Header from './components/Header') — these will be
    inlined in the sandbox, not loaded as separate modules.
    """
    # import Foo from './path'
    pattern = r"import\s+\w+\s+from\s+['\"]\.\/[^'\"]+['\"][ \t]*;?[ \t]*\n?"
    code = re.sub(pattern, "", code, flags=re.MULTILINE)
    # import { Foo, Bar } from './path'
    pattern2 = r"import\s*\{[^}]*\}\s*from\s+['\"]\.\/[^'\"]+['\"][ \t]*;?[ \t]*\n?"
    code = re.sub(pattern2, "", code, flags=re.MULTILINE)
    return code


# ---------------------------------------------------------------------------
# The core template builder
# ---------------------------------------------------------------------------

def get_sandbox_html_template(
    *,
    entry_code: str,
    entry_component: str,
    inline_modules: Dict[str, str],
    css_blocks: list,
    title: str = "Site Preview",
) -> str:
    """
    Build a self-contained HTML page that renders a React app entirely
    in the browser using ESM importmap + Babel standalone.

    Args:
        entry_code:       The processed App/entry component source
        entry_component:  Name of the root component to mount (e.g. 'App')
        inline_modules:   {name: processed_source} for child components
        css_blocks:       List of raw CSS strings to inject
        title:            HTML <title>
    """
    import_map = _get_esm_import_map()
    import_map_json = json.dumps({"imports": import_map}, indent=2)

    # Build inline module scripts for each child component
    module_scripts = []
    for name, source in inline_modules.items():
        # Each module is a <script type="text/babel"> block that defines
        # the component as a global so the entry module can reference it.
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        module_scripts.append(f"""
    // ---- Module: {name} ----
    {source}
    // ---- End module: {name} ----""")

    modules_block = "\n".join(module_scripts)

    # CSS
    css_block = "\n".join(f"    /* {i} */\n    {css}" for i, css in enumerate(css_blocks))

    mount_call = f"root.render(React.createElement({entry_component}));"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script type="importmap">
{import_map_json}
  </script>
  <script src="https://unpkg.com/@babel/standalone@7.24.7/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }}
    #root {{ min-height: 100vh; }}
    #sandbox-error {{
      padding: 16px; background: #fee2e2; border: 1px solid #fca5a5;
      border-radius: 8px; margin: 16px; font-family: monospace;
      white-space: pre-wrap; color: #991b1b;
    }}
{css_block}
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel" data-type="module" data-presets="react">
    import React, {{ useState, useEffect, useRef, useCallback, useMemo, useReducer, useContext, createContext, forwardRef, memo, Suspense, lazy }} from 'react';
    import {{ createRoot }} from 'react-dom/client';

    {modules_block}

    // ---- Entry component ----
    {entry_code}
    // ---- End entry ----

    (function mountApp() {{
      const root = createRoot(document.getElementById('root'));
      {mount_call}
    }})();
  </script>
  <script>
    window.addEventListener('error', function(e) {{
      var el = document.getElementById('sandbox-error');
      if (!el) {{ el = document.createElement('div'); el.id = 'sandbox-error'; document.body.appendChild(el); }}
      el.textContent = 'Runtime error: ' + (e.message || String(e));
    }});
    window.addEventListener('unhandledrejection', function(e) {{
      var el = document.getElementById('sandbox-error');
      if (!el) {{ el = document.createElement('div'); el.id = 'sandbox-error'; document.body.appendChild(el); }}
      el.textContent = 'Unhandled promise: ' + (e.reason || String(e));
    }});
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public API: wrap_react_site
# ---------------------------------------------------------------------------

def wrap_react_site(files: Dict[str, str], title: str = "Site Preview") -> Dict[str, str]:
    """
    Transform a dict of React/JSX files into a sandboxed static-site bundle.

    Input files dict may contain:
      - App.jsx / App.tsx / index.jsx etc. — React components
      - components/Header.jsx, pages/Home.jsx etc. — child components
      - styles/main.css, globals.css etc. — CSS files
      - assets/logo.png etc. — binary assets (passed through)
      - index.html — if present AND already contains React scaffold, skip wrapping

    Output: a new files dict where index.html is a fully sandboxed page
    and all CSS/assets are preserved. JSX files are consumed into the HTML.

    If the input already has a complete index.html (no JSX, no React), it's
    returned unchanged — this function only activates for React sites.
    """
    if not is_react_site(files):
        return files

    # If the AI already produced a complete index.html with React scaffold,
    # check if it already has Babel + importmap. If so, trust it.
    existing_html = files.get("index.html", "")
    if existing_html and "babel" in existing_html.lower() and "importmap" in existing_html.lower():
        logger.info("wrap_react_site: index.html already has Babel+importmap — passing through")
        return files

    # Classify files
    jsx_files: Dict[str, str] = {}  # path → source
    css_files: list = []
    pass_through: Dict[str, str] = {}

    for path, content in files.items():
        if not isinstance(content, str):
            pass_through[path] = content
            continue
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("jsx", "tsx", "js", "ts"):
            # Check if it's actually a React component (vs a utility script)
            if any(p.search(content) for p in _JSX_RE) or ext in ("jsx", "tsx"):
                jsx_files[path] = content
            else:
                # Pure utility JS — will be inlined too
                jsx_files[path] = content
        elif ext == "css":
            css_files.append(content)
        elif path == "index.html":
            # Skip — we're generating our own
            pass
        else:
            pass_through[path] = content

    if not jsx_files:
        # No JSX files found — return unchanged
        return files

    # Find the entry component file
    entry_path, entry_source = _find_entry_component(jsx_files)

    # Process the entry component
    entry_source = _strip_react_imports(entry_source)
    local_names = set(jsx_files.keys())
    entry_source = _strip_local_imports(entry_source, local_names)
    entry_source, entry_name = _strip_export_default(entry_source)
    if not entry_name:
        entry_name = "App"

    # Strip named exports from entry
    entry_source = re.sub(r"\bexport\s+(?:const|let|var|function|class)\s+", "", entry_source)

    # Process child modules (everything except the entry)
    inline_modules: Dict[str, str] = {}
    for path, source in jsx_files.items():
        if path == entry_path:
            continue
        processed = _strip_react_imports(source)
        processed = _strip_local_imports(processed, local_names)
        processed, comp_name = _strip_export_default(processed)
        # Strip named exports
        processed = re.sub(r"\bexport\s+(?:const|let|var|function|class)\s+", "", processed)
        name = comp_name or _component_name_from_path(path)
        inline_modules[name] = processed

    # Build the sandbox HTML
    sandbox_html = get_sandbox_html_template(
        entry_code=entry_source,
        entry_component=entry_name,
        inline_modules=inline_modules,
        css_blocks=css_files,
        title=title,
    )

    # Build the output files dict
    output: Dict[str, str] = {"index.html": sandbox_html}
    output.update(pass_through)
    # Keep CSS files as standalone too (for non-Tailwind users who want <link>)
    for path, content in files.items():
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext == "css":
            output[path] = content

    return output


def _find_entry_component(jsx_files: Dict[str, str]) -> Tuple[str, str]:
    """
    Find the entry/root component from the file map. Priority:
    1. App.jsx / App.tsx / App.js
    2. index.jsx / index.tsx / index.js
    3. main.jsx / main.tsx / main.js
    4. The first JSX file that exports a default
    5. The first file alphabetically
    """
    priority_names = [
        "App.jsx", "App.tsx", "App.js",
        "src/App.jsx", "src/App.tsx", "src/App.js",
        "index.jsx", "index.tsx", "index.js",
        "src/index.jsx", "src/index.tsx", "src/index.js",
        "main.jsx", "main.tsx", "main.js",
    ]
    for name in priority_names:
        if name in jsx_files:
            return name, jsx_files[name]

    # Look for any file with export default
    for path, source in jsx_files.items():
        if re.search(r"\bexport\s+default\b", source):
            return path, source

    # Last resort: first file
    first_path = sorted(jsx_files.keys())[0]
    return first_path, jsx_files[first_path]


def _component_name_from_path(path: str) -> str:
    """Extract a PascalCase component name from a file path."""
    # components/Header.jsx → Header
    name = path.rsplit("/", 1)[-1]  # filename
    name = name.rsplit(".", 1)[0]    # strip extension
    # PascalCase
    return name[0].upper() + name[1:] if name else "Component"
