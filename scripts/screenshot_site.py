"""
Screenshot Script for https://analystbypotomac.vercel.app
-------------------------------------------------------
Logs in with test credentials, crawls every discoverable page/route,
takes full-page screenshots AND individual element screenshots,
and saves everything in an organised folder tree under screenshots/.

Folder layout:
  screenshots/
    YYYY-MM-DD_HH-MM-SS/
      00_login/
        01_landing_page_full.png
        02_login_page_full.png
        03_email_field.png
        04_password_field.png
        05_form_filled.png
        06_submit_button.png
        07_after_login_full.png
      01_<page-name>/
        01_full_page.png
        02_scrolled_midpoint.png
        03_after_interactions.png
        elements/
          001_nav_sidebar_1.png
          002_header_1.png
          ...
      ZZ_modals_and_dialogs/
        01_modal_<name>.png
      manifest.json
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "https://analystbypotomac.vercel.app"
EMAIL    = "Sohaib.ali@potomac.com"
PASSWORD = "Potomac1234"

VIEWPORT = {"width": 1440, "height": 900}

# Elements worth capturing individually (CSS selectors -> friendly name)
ELEMENT_SELECTORS = {
    "nav_sidebar":    "nav, aside, [class*='sidebar'], [class*='nav'], [role='navigation']",
    "header":         "header, [class*='header'], [class*='topbar'], [class*='navbar']",
    "main_content":   "main, [class*='main'], [class*='content'], [role='main']",
    "buttons":        "button:visible",
    "forms":          "form:visible",
    "input_fields":   "input:visible, textarea:visible, select:visible",
    "cards":          "[class*='card']:visible",
    "tables":         "table:visible",
    "modals":         "[class*='modal']:visible, [role='dialog']:visible",
    "charts":         "[class*='chart']:visible, canvas:visible, svg[class*='chart']:visible",
    "dropdowns":      "[class*='dropdown']:visible, [class*='select']:visible",
    "alerts_banners": "[class*='alert']:visible, [class*='banner']:visible, [class*='toast']:visible",
    "footer":         "footer:visible",
}

# Known routes to seed the crawl (auto-discovery adds more from nav links)
SEED_ROUTES = [
    "/",
    "/dashboard",
    "/chat",
    "/research",
    "/analyst",
    "/upload",
    "/settings",
    "/profile",
    "/admin",
    "/brain",
    "/skills",
    "/backtest",
    "/presentations",
    "/history",
    "/login",
    "/signup",
    "/register",
    "/afl",
    "/train",
]

MAX_PAGES    = 60   # safety cap on total pages visited
ACTION_DELAY = 0.5  # seconds between actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitise(text: str, max_len: int = 50) -> str:
    """Convert arbitrary text into a safe filename fragment."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_len] or "unnamed"


def route_to_name(route: str) -> str:
    """Turn /foo/bar?x=1 into a directory-safe string."""
    path = route.split("?")[0].strip("/") or "home"
    return sanitise(path.replace("/", "__"))


async def wait_stable(page: Page, delay: float = ACTION_DELAY) -> None:
    """Wait for network idle then a short fixed delay."""
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    await asyncio.sleep(delay)


async def shot_full(page: Page, path: Path, label: str = "") -> dict:
    """Take a full-page screenshot; return a manifest entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)
    tag = f"({label}) " if label else ""
    print(f"  [SHOT] full-page {tag}-> {path.name}")
    return {
        "type": "full_page",
        "label": label,
        "file": str(path),
        "url": page.url,
        "timestamp": datetime.now().isoformat(),
    }


async def shot_elements(page: Page, elem_dir: Path, page_url: str) -> list:
    """Screenshot each interesting visible element; return manifest entries."""
    entries = []
    elem_dir.mkdir(parents=True, exist_ok=True)
    idx = 0

    for name, css in ELEMENT_SELECTORS.items():
        try:
            locs = await page.locator(css).all()
            for i, loc in enumerate(locs[:8]):   # cap 8 per group
                try:
                    if not await loc.is_visible():
                        continue
                    box = await loc.bounding_box()
                    if not box or box["width"] < 10 or box["height"] < 10:
                        continue
                    idx += 1
                    fname = f"{idx:03d}_{sanitise(name)}_{i+1}.png"
                    fpath = elem_dir / fname
                    await loc.screenshot(path=str(fpath))
                    print(f"    [ELEM] {name}[{i}] -> {fname}")
                    entries.append({
                        "type": "element",
                        "selector_group": name,
                        "index": i,
                        "file": str(fpath),
                        "url": page_url,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception:
                    pass
        except Exception:
            pass

    return entries


async def collect_links(page: Page, base_url: str) -> list:
    """Return all same-origin href paths found on the current page."""
    try:
        hrefs = await page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')]
                   .map(a => a.getAttribute('href'));
        }""")
    except Exception:
        return []

    routes = set()
    for href in hrefs:
        if not href:
            continue
        if href.startswith(base_url):
            href = href[len(base_url):]
        if href.startswith("/") and "#" not in href:
            routes.add(href.split("?")[0])
    return list(routes)


async def expand_interactive(page: Page) -> None:
    """Best-effort: click dropdowns/accordions to reveal hidden content."""
    triggers = [
        "[class*='dropdown'] button",
        "[class*='accordion'] button",
        "[class*='collapse'] button",
        "[data-toggle]",
        "[aria-expanded='false']",
        "summary",
    ]
    for sel in triggers:
        try:
            for loc in (await page.locator(sel).all())[:5]:
                if await loc.is_visible():
                    await loc.click(timeout=2000)
                    await asyncio.sleep(0.3)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

async def do_login(page: Page, root_dir: Path, manifest: list) -> bool:
    """Go to the site, log in, screenshot every step."""
    login_dir = root_dir / "00_login"
    login_dir.mkdir(parents=True, exist_ok=True)

    print("\n[LOGIN] Navigating to base URL ...")
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
    await wait_stable(page, 1.5)

    manifest.append(await shot_full(page, login_dir / "01_landing_page_full.png", "Landing page"))

    # Locate email input
    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[placeholder*='email' i]",
        "input[id*='email' i]",
    ]

    email_loc = None
    for sel in email_selectors:
        loc = page.locator(sel).first
        if await loc.count() > 0 and await loc.is_visible():
            email_loc = loc
            break

    # Maybe we need to click a Login link first
    if not email_loc:
        for link_sel in [
            "a[href*='login']",
            "button:has-text('Login')",
            "button:has-text('Sign in')",
            "a:has-text('Login')",
        ]:
            lnk = page.locator(link_sel).first
            if await lnk.count() > 0:
                await lnk.click()
                await wait_stable(page, 1.0)
                break
        for sel in email_selectors:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                email_loc = loc
                break

    if not email_loc:
        print("[LOGIN] WARNING: Could not find email input. May already be logged in.")
        manifest.append(await shot_full(
            page, login_dir / "02_no_login_form_found.png", "No login form"))
        return False

    manifest.append(await shot_full(page, login_dir / "02_login_page_full.png", "Login form"))

    # Screenshot email field
    try:
        await email_loc.screenshot(path=str(login_dir / "03_email_field.png"))
        print("  [SHOT] element: email_field")
    except Exception:
        pass

    await email_loc.click()
    await email_loc.fill(EMAIL)
    await asyncio.sleep(0.3)

    # Locate password input
    pwd_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[placeholder*='password' i]",
    ]
    pwd_loc = None
    for sel in pwd_selectors:
        loc = page.locator(sel).first
        if await loc.count() > 0 and await loc.is_visible():
            pwd_loc = loc
            break

    if pwd_loc:
        try:
            await pwd_loc.screenshot(path=str(login_dir / "04_password_field.png"))
            print("  [SHOT] element: password_field")
        except Exception:
            pass
        await pwd_loc.click()
        await pwd_loc.fill(PASSWORD)
        await asyncio.sleep(0.3)

    manifest.append(await shot_full(page, login_dir / "05_form_filled.png", "Form filled"))

    # Submit
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
    ]
    submitted = False
    for sel in submit_selectors:
        btn = page.locator(sel).first
        if await btn.count() > 0 and await btn.is_visible():
            try:
                await btn.screenshot(path=str(login_dir / "06_submit_button.png"))
                print("  [SHOT] element: submit_button")
            except Exception:
                pass
            await btn.click()
            submitted = True
            break

    if not submitted:
        await page.keyboard.press("Enter")

    await wait_stable(page, 2.5)
    manifest.append(await shot_full(page, login_dir / "07_after_login_full.png", "After login"))
    print(f"[LOGIN] URL after login: {page.url}")
    return True


# ---------------------------------------------------------------------------
# Page visitor
# ---------------------------------------------------------------------------

async def visit_page(page: Page, url: str, page_dir: Path, manifest: list) -> list:
    """
    Visit one URL: full-page shot, scroll shot, element shots.
    Returns a list of newly discovered internal route strings.
    """
    print(f"\n[PAGE] {url}")
    page_dir.mkdir(parents=True, exist_ok=True)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
    except Exception as exc:
        print(f"  WARNING: Navigation failed: {exc}")
        return []

    await wait_stable(page, 1.0)

    current = page.url
    # Skip if we got redirected to login
    if "login" in current.lower() and "login" not in url.lower():
        print("  WARNING: Redirected to login - skipping")
        return []

    manifest.append(await shot_full(page, page_dir / "01_full_page.png", "top"))

    # Scrolled mid-point shot for tall pages
    page_height = await page.evaluate("document.body.scrollHeight")
    if page_height > VIEWPORT["height"] * 1.5:
        await page.evaluate(f"window.scrollTo(0, {page_height // 2})")
        await asyncio.sleep(0.4)
        manifest.append(await shot_full(page, page_dir / "02_scrolled_midpoint.png", "mid"))
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.3)

    # Expand interactive elements, then element screenshots
    await expand_interactive(page)
    await asyncio.sleep(0.5)

    elem_entries = await shot_elements(page, page_dir / "elements", current)
    manifest.extend(elem_entries)

    if elem_entries:
        manifest.append(await shot_full(
            page, page_dir / "03_after_interactions.png", "after interactions"))

    return await collect_links(page, BASE_URL)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    root_dir  = Path(__file__).parent.parent / "screenshots" / timestamp
    root_dir.mkdir(parents=True, exist_ok=True)

    manifest = []

    print("=" * 60)
    print(" Potomac Analyst Workbench - Screenshot Crawler")
    print(f" Output: {root_dir}")
    print("=" * 60)

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=False, slow_mo=80)
        context: BrowserContext = await browser.new_context(
            viewport=VIEWPORT,
            ignore_https_errors=True,
        )
        page: Page = await context.new_page()

        # 1. Login
        await do_login(page, root_dir, manifest)

        # 2. Seed the visit queue
        post_login_links = await collect_links(page, BASE_URL)

        visited  = set()
        to_visit = []

        all_seeds = SEED_ROUTES + [l for l in post_login_links if l not in SEED_ROUTES]
        for r in all_seeds:
            url = BASE_URL + r if r.startswith("/") else r
            if url not in to_visit:
                to_visit.append(url)

        # 3. Crawl
        page_counter = 0
        while to_visit and len(visited) < MAX_PAGES:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            route    = url.replace(BASE_URL, "") or "/"
            dir_name = f"{page_counter+1:02d}_{route_to_name(route)}"
            page_dir = root_dir / dir_name

            new_links = await visit_page(page, url, page_dir, manifest)
            page_counter += 1

            for lnk in new_links:
                full = BASE_URL + lnk if lnk.startswith("/") else lnk
                if full not in visited and full not in to_visit:
                    to_visit.append(full)

        # 4. Modals / dialogs
        print("\n[MODALS] Attempting to capture modal/dialog states ...")
        modal_triggers = [
            "button:has-text('New')",
            "button:has-text('Create')",
            "button:has-text('Add')",
            "button:has-text('Upload')",
            "button:has-text('Settings')",
            "button[aria-haspopup='dialog']",
            "[data-modal-trigger]",
        ]
        modal_dir = root_dir / "ZZ_modals_and_dialogs"
        modal_dir.mkdir(parents=True, exist_ok=True)
        modal_idx = 0

        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15_000)
            await wait_stable(page, 1.5)
        except Exception:
            pass

        for sel in modal_triggers:
            try:
                btns = await page.locator(sel).all()
                for btn in btns[:3]:
                    if not await btn.is_visible():
                        continue
                    txt = (await btn.inner_text()).strip()[:30]
                    await btn.click(timeout=3000)
                    await asyncio.sleep(0.8)
                    modal = page.locator("[role='dialog']:visible, [class*='modal']:visible").first
                    if await modal.count() > 0:
                        modal_idx += 1
                        fname = f"{modal_idx:02d}_modal_{sanitise(txt)}.png"
                        manifest.append(await shot_full(
                            page, modal_dir / fname, f"Modal: {txt}"))
                        closed = False
                        for close_sel in [
                            "[aria-label='Close']",
                            "button:has-text('Cancel')",
                            "button:has-text('Close')",
                            ".modal-close",
                            "[data-dismiss='modal']",
                        ]:
                            cls = page.locator(close_sel).first
                            if await cls.count() > 0 and await cls.is_visible():
                                await cls.click(timeout=2000)
                                closed = True
                                await asyncio.sleep(0.5)
                                break
                        if not closed:
                            await page.keyboard.press("Escape")
                            await asyncio.sleep(0.4)
            except Exception:
                pass

        # 5. Write manifest
        manifest_path = root_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": timestamp,
                "base_url": BASE_URL,
                "pages_visited": page_counter,
                "total_screenshots": len(manifest),
                "screenshots": manifest,
            }, f, indent=2)

        await browser.close()

    print("\n" + "=" * 60)
    print(f" DONE!  {len(manifest)} screenshots saved.")
    print(f"    Folder  : {root_dir}")
    print(f"    Manifest: {manifest_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
