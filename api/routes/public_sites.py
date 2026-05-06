"""
Public, anonymous routes that serve published Content Studio sites.

Two access patterns — both ultimately resolve to the same site_root_path:

  Path-based (always works, no DNS setup required):
      GET /s/{subdomain}/
      GET /s/{subdomain}/{path:path}

  Host-header (subdomain) — wired via a FastAPI middleware in main.py
  once wildcard DNS is configured, e.g. *.sites.potomacai.com → Railway:
      GET /                              (Host: my-portfolio.sites.potomacai.com)
      GET /{path:path}                   (Host: my-portfolio.sites.potomacai.com)

Both code paths use core.studio.sites.serve_site_file() which honours an
SPA fallback (unknown paths → /index.html, status 200) so client-side
routers in a built site work correctly.

NOTE: There is NO authentication on this router — these sites are intended
for the public internet. Sensitive endpoints elsewhere remain auth-gated.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

from fastapi import APIRouter, Path, Request
from fastapi.responses import Response, JSONResponse

from core.studio import sites as sites_mod

logger = logging.getLogger(__name__)
router = APIRouter(tags=["public-sites"])


# -----------------------------------------------------------------------------
# Subdomain configuration (used by the Host-header middleware)
# -----------------------------------------------------------------------------

# Comma-separated list of base domains under which subdomains are served, e.g.
#   PUBLIC_SITES_BASE_DOMAINS="sites.potomacai.com,preview.potomacai.com"
# A request with Host=my-portfolio.sites.potomacai.com will be matched and
# routed to the published_sites row with subdomain='my-portfolio'.
_BASE_DOMAINS = [
    d.strip().lower()
    for d in (os.getenv("PUBLIC_SITES_BASE_DOMAINS") or "").split(",")
    if d.strip()
]


def extract_subdomain_from_host(host: str) -> Optional[str]:
    """
    Given a Host header, return the leading subdomain when the host matches
    one of the configured PUBLIC_SITES_BASE_DOMAINS, else None.

    Examples (with PUBLIC_SITES_BASE_DOMAINS=sites.potomacai.com):
      "my-portfolio.sites.potomacai.com:443"  → "my-portfolio"
      "sites.potomacai.com"                   → None  (the apex itself)
      "api.potomacai.com"                     → None
    """
    if not host or not _BASE_DOMAINS:
        return None
    h = host.split(":", 1)[0].strip().lower().rstrip(".")
    if not h:
        return None
    for base in _BASE_DOMAINS:
        if h == base:
            return None  # exact apex — not a tenant subdomain
        suffix = "." + base
        if h.endswith(suffix):
            sub = h[: -len(suffix)]
            # We only handle a single label as the tenant key
            if sub and "." not in sub:
                return sub
    return None


# -----------------------------------------------------------------------------
# Shared resolver used by both path-based and Host-header serving
# -----------------------------------------------------------------------------

def _serve_subdomain(subdomain: str, path: str) -> Response:
    """Resolve subdomain → site_root and serve the requested file."""
    pub = sites_mod.resolve_subdomain(subdomain)
    if not pub:
        return JSONResponse({"error": "site not found"}, status_code=404)

    site_root = pub.get("site_root_path") or ""
    if not site_root or not os.path.isdir(site_root):
        # The DB row exists but the bundle directory is gone (e.g. fresh
        # container). Fall back to the published-alias dir.
        alias = os.path.join(sites_mod.PUBLISHED_ROOT, subdomain)
        if os.path.isdir(alias):
            site_root = alias
        else:
            return JSONResponse(
                {"error": "site files unavailable", "subdomain": subdomain},
                status_code=503,
            )

    body, mime, status = sites_mod.serve_site_file(site_root, path)
    if body is None:
        return JSONResponse({"error": "not found"}, status_code=status or 404)

    # Best-effort metric (fire-and-forget)
    try:
        sites_mod.record_request(pub["id"])
    except Exception:
        pass

    headers = {
        # Public sites are pure static content; CSP blocks server-side scripts
        # while still permitting inline + same-origin assets typical of an
        # AI-generated site.
        "Content-Security-Policy": (
            "default-src 'self' data: blob: https:; "
            "img-src 'self' data: blob: https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            "font-src 'self' data: https:; "
            "frame-ancestors 'self';"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy":        "strict-origin-when-cross-origin",
        # Short cache so updates after re-publish are picked up quickly
        "Cache-Control":          "public, max-age=60",
    }
    return Response(content=body, media_type=mime, status_code=status, headers=headers)


# -----------------------------------------------------------------------------
# Path-based public access (works without any DNS setup)
# -----------------------------------------------------------------------------

@router.get("/s/{subdomain}", include_in_schema=False)
@router.get("/s/{subdomain}/", include_in_schema=False)
@router.get("/s/{subdomain}/{path:path}", include_in_schema=False)
async def serve_path_subdomain(
    subdomain: str = Path(...),
    path: str = "",
):
    """Serve published_sites[subdomain]/{path} (defaults to index.html)."""
    sub = (subdomain or "").lower().strip()
    return _serve_subdomain(sub, path)


# -----------------------------------------------------------------------------
# Host-header (true wildcard subdomain) — used by the middleware in main.py
# -----------------------------------------------------------------------------

async def serve_host_routed(request: Request) -> Optional[Response]:
    """
    Inspect the request's Host header. If it matches a configured base
    domain (e.g. *.sites.potomacai.com), serve the corresponding site
    and return the Response. Otherwise return None so the normal API
    routes handle the request.

    Wired in main.py as a middleware that calls this BEFORE downstream
    routers run.
    """
    if not _BASE_DOMAINS:
        return None
    host = request.headers.get("host", "")
    sub = extract_subdomain_from_host(host)
    if not sub:
        return None
    # Strip the leading slash; FastAPI gives us the full path
    path = request.url.path.lstrip("/")
    return _serve_subdomain(sub, path)
