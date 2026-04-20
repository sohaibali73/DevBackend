# PPTX Sandbox v2 — Complete Guide

> Last updated: 2026-04-17
> Replaces the monolithic single-file renderer with a modular layout engine,
> reusable primitives, a named-template library, an asset library, and
> a versioned "program" store for editable presentations.

---

## 1. What changed

| Concern                 | v1 (legacy)                    | v2 (current)                                      |
|-------------------------|--------------------------------|---------------------------------------------------|
| Canvas                  | `pres.layout = 'LAYOUT_WIDE'` (silent fallback possible → rendered at 10"×7.5") | `pres.defineLayout({name:'POTOMAC_CUSTOM', width, height}) + pres.layout = 'POTOMAC_CUSTOM'` — enforced 13.333"×7.5" |
| Measurements            | Hardcoded inch/pt values everywhere | Layout engine (`engine.grid / stack / row / tokens`) — **zero hardcoded measurements in templates** |
| Templates               | ~21 inline functions           | `templates.js` registry — `title`, `title_card`, `hex_row`, `team_triad`, `cta_framed`, `stat_cards`, `metrics`, `two_column`, `table`, `chart`, `quote`, `section_divider`, `image`, `content` (+legacy aliases) |
| Primitives              | None (re-written per slide)    | `primitives.js`: `pill`, `hexTile`, `framedSlide`, `standardChrome`, `accentBar`, `roundRect`, `glyph`, etc. |
| Assets                  | Only the 6 logos from the repo | User-uploadable asset library + global brand seed |
| Edit memory             | None — regenerate from scratch | Versioned program store (Supabase + Railway volume) with JSON-patch edits |
| API                     | Tool-only via `generate_pptx` | Dedicated REST routes (`/api/pptx/*`, `/api/pptx/assets/*`) |
| Modes per slide         | Single "type" field            | `template` / `hybrid` (template + customize JS) / `freestyle` (raw JS) |

---

## 2. Architecture

```
core/sandbox/
├── pptx_sandbox.py          # Python orchestrator (thin)
├── pptx_program_store.py    # Supabase + volume persistence
├── pptx_assets.py           # Icon/graphic/logo library
└── js/
    ├── brand.js             # palette, fonts, logo registry
    ├── layout-engine.js     # canvas, grid, stack, tokens, autoFit
    ├── primitives.js        # pill, hexTile, framedSlide, standardChrome, …
    ├── templates.js         # named templates + registry + aliases
    └── runtime.js           # entry point (reads spec.json, calls pptxgenjs)
```

### Renderer flow

1. Python caller invokes `PptxSandbox().generate(spec)` (or `.generate_and_store_program()` to persist).
2. Python:
   - Installs `pptxgenjs` into `$SANDBOX_DATA_DIR/pptx_cache` (once).
   - Copies brand logos + JS module dir into a temp workspace.
   - Resolves `asset_keys` + `icon_key`/`image_key` references via `pptx_assets.resolve_assets()`.
   - Writes `spec.json` and spawns `node js/runtime.js spec.json`.
3. `runtime.js`:
   - `createEngine(canvas)` → layout engine with the exact slide size.
   - **Explicitly** calls `pres.defineLayout({name:'POTOMAC_CUSTOM', width, height})` then sets `pres.layout = 'POTOMAC_CUSTOM'`.  This prevents PptxGenJS silently falling back to `LAYOUT_STANDARD` (the root cause of the pre-v2 "slides are the wrong size" bug).
   - Iterates spec slides; for each:
     - `template` → `templates.get(name)(slide, data)`
     - `hybrid`   → template + run user `customize` code with `new Function`
     - `freestyle` → `new Function` sandbox with `slide, pres, engine, prim, data, PALETTE, FONTS, logos, resolveAsset`
   - Captures `WARN:…` lines from stderr and reports them back to Python.
4. Python parses stdout JSON ack → returns `PptxResult(success, data, warnings, canvas, program_id, version)`.

### Canvas presets (layout-engine.js)

| Preset         | Width × Height (inches) | Use                                   |
|----------------|-------------------------|---------------------------------------|
| `wide`         | 13.333 × 7.5            | 16:9 widescreen — **default**         |
| `standard`     | 10.0   × 7.5            | 4:3 legacy                            |
| `hd16_9`       | 10.0   × 5.625          | 16:9 HD (smaller canvas)              |
| `a4_landscape` | 11.69  × 8.27           | A4 print layout                       |
| custom         | `{width, height}`       | any size                              |

---

## 3. Spec schema

```json
{
  "title": "Q3 2026 Strategy Review",
  "filename": "q3_review.pptx",
  "canvas": { "preset": "wide" },
  "asset_keys": ["growth_icon", "shield_swords"],
  "slides": [
    { "mode": "template", "template": "title_card", "data": { "title": "…", "title_accent": "…", "subtitle": "…" } },
    { "mode": "template", "template": "team_triad",  "data": { "title": "…", "cards": [ { "pill": "…", "body": "…" }, … ] } },
    { "mode": "template", "template": "hex_row",     "data": { "title": "…", "tiles": [ { "label": "…", "subline": "…", "icon_key": "growth_icon" } ] } },
    { "mode": "hybrid",   "template": "content",     "data": { "title": "…", "bullets": ["…"] }, "customize": "slide.addText('footer', {x:0.5,y:7,w:12.3,h:0.3});" },
    { "mode": "freestyle", "code": "const b = prim.standardChrome(slide,{title:'Custom'}); prim.pill(slide, engine.grid(3,1,b).cell(1,0), {label:'Yo'});" }
  ]
}
```

### Slide modes

| Mode        | Required fields                | Behavior                                                     |
|-------------|--------------------------------|--------------------------------------------------------------|
| `template`  | `template`, `data`, `overrides?` | Call `templates.get(template)(slide, {...data, ...overrides})` |
| `hybrid`    | `template`, `data`, `customize` | Run the template, then execute `customize` (raw JS) on the same slide |
| `freestyle` | `code`                          | New blank slide, run `code` in a sandboxed `new Function` with `slide, pres, engine, prim, data, PALETTE, FONTS, logos, resolveAsset` |

Legacy specs (`{type: "title", …}`) are automatically normalized to `{mode:"template", template:"title", data:{…}}`.

### Built-in template names

`title`, `title_card`, `content`, `two_column`, `three_column`, `metrics`, `stat_cards`, `hex_row`, `team_triad`, `cta_framed`, `table`, `chart`, `quote`, `section_divider`, `image`.

Aliases: `cta → cta_framed`, `executive_summary → title_card`, `icon_grid → hex_row`, `agenda → content`, `comparison → two_column`, `scorecard → table`, `card_grid → stat_cards`, `image_content → image`, … (see `templates.js` registry).

---

## 4. REST API

### 4.1 Programs  (`/api/pptx/*`, authenticated)

| Method | Path                                   | Purpose                                      |
|--------|----------------------------------------|----------------------------------------------|
| POST   | `/api/pptx/generate`                   | Create a program + render (returns download URL) |
| POST   | `/api/pptx/{program_id}/edit`          | Apply JSON patches + re-render               |
| POST   | `/api/pptx/{program_id}/render`        | Re-render latest (or specified version)      |
| POST   | `/api/pptx/{program_id}/revert/{ver}`  | Revert to a prior version + re-render        |
| GET    | `/api/pptx/{program_id}`               | Load program source                          |
| GET    | `/api/pptx/{program_id}/versions`      | List version history                         |
| GET    | `/api/pptx/programs`                   | List the user's programs                     |

**Generate request body** (same as Spec schema above):

```json
{
  "title": "…",
  "filename": "…",
  "canvas": { "preset": "wide" },
  "slides": [ … ],
  "asset_keys": [ … ]
}
```

**Response**:

```json
{
  "success": true,
  "program_id": "uuid",
  "version": 1,
  "file_id": "uuid",
  "filename": "Potomac_Deck.pptx",
  "size_kb": 142.3,
  "download_url": "/files/<file_id>/download",
  "canvas": { "width": 13.333, "height": 7.5 },
  "warnings": [],
  "exec_time_ms": 1894.2
}
```

### 4.2 Edit patches

```json
{
  "patches": [
    { "op": "update", "slide": 0, "path": "data.title", "value": "NEW TITLE" },
    { "op": "insert", "index": 2, "slide": { "mode": "template", "template": "content", "data": {...} } },
    { "op": "delete", "slide": 3 },
    { "op": "reorder", "from": 4, "to": 1 },
    { "op": "set_canvas", "canvas": { "preset": "hd16_9" } },
    { "op": "set_title",  "title": "Q4 Deck" }
  ]
}
```

Dotted path syntax supports array indices via either `data.tiles.0.label` or `data.tiles[0].label`.

### 4.3 Assets  (`/api/pptx/assets/*`, authenticated)

| Method | Path                            | Purpose                                       |
|--------|---------------------------------|-----------------------------------------------|
| POST   | `/api/pptx/assets/upload`       | Multipart upload (user-scoped)                |
| GET    | `/api/pptx/assets`              | List visible assets (global + own)            |
| GET    | `/api/pptx/assets/manifest`     | Compact manifest for LLM agents               |
| DELETE | `/api/pptx/assets/{key}`        | Delete one of your own assets                 |

**Upload form fields**: `file` (multipart), `key` (string), `kind` (`icon`/`graphic`/`background`/`logo`), `tags` (CSV), `use_when` (string), `on_colors` (CSV of palette keys).

**Manifest shape**:

```json
{
  "icons":       [{ "key": "growth_icon", "tags": ["growth"], "use_when": "…", "on_colors": ["YELLOW"], "aspect": 1, "scope": "user" }],
  "logos":       [ … ],
  "graphics":    [ … ],
  "backgrounds": [ … ]
}
```

---

## 5. Using assets inside templates / freestyle

When `asset_keys` or tile `icon_key` is present in the spec, the Python side injects an `asset_registry` into the spec:

```json
"asset_registry": {
  "growth_icon":  { "dataUrl": "data:image/png;base64,…", "aspect": 1, "mime": "image/png" },
  "shield_swords": { "dataUrl": "data:image/svg+xml;base64,…", "aspect": 1.2, "mime": "image/svg+xml" }
}
```

From freestyle/hybrid code:

```js
const asset = resolveAsset('growth_icon');     // { dataUrl, aspect, mime }
if (asset) {
  slide.addImage({ data: asset.dataUrl, x: 1, y: 1, w: 1, h: 1 });
}
```

From templates: `hex_row` accepts `icon_key` per tile; `image` template accepts `image_key` or `data` (base64).

---

## 6. Persistence layout

### Supabase tables (migration `020_pptx_programs_and_assets.sql`)

- `pptx_programs` — one row per deck: `{id, user_id, title, canvas, program, asset_snapshot, version, file_id, …}`. RLS: users only read/write their own.
- `pptx_program_versions` — append-only per-save snapshot, `UNIQUE(program_id, version)`. RLS: inherits from parent program.
- `pptx_assets` — icon/graphic/logo library. Scopes: `global` (backend-seeded), `user` (own uploads), `org` (reserved). RLS: read global + own; write own-user only.

### Railway volume

```
$STORAGE_ROOT/
├── pptx_programs/{program_id}/
│   ├── program.json                   # mirror of the latest program row
│   ├── versions/v{n}.json             # per-version snapshots
│   └── renders/v{n}.pptx + latest.pptx
├── pptx_assets/
│   ├── global/…                        # seeded brand logos
│   ├── user/{user_id}/{key}_{sha}.ext  # uploaded user assets
│   └── org/{org_id}/…                  # reserved
```

---

## 7. Developer quickstart

### Smoke test (local Windows PowerShell)

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python scripts/smoke_test_pptx.py
```

Expected output:

```
→ Generating presentation via PptxSandbox v2 …
✓ Generated 145848 bytes in 1894ms
✓ Wrote …\smoke_out.pptx
✓ Detected canvas: 13.333" × 7.5"
✅ PASS: canvas is 16:9 widescreen (13.333 × 7.5)
```

### Minimal curl flow

```bash
# 1. Upload a custom icon
curl -X POST "$API/api/pptx/assets/upload" \
  -H "Authorization: Bearer $JWT" \
  -F "file=@./growth.svg" \
  -F "key=growth_icon" \
  -F "kind=icon" \
  -F "tags=growth,strategy" \
  -F "use_when=Use on strategy hex row for growth sleeves"

# 2. Generate a deck that uses it
curl -X POST "$API/api/pptx/generate" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Q3 Strategy Review",
    "asset_keys": ["growth_icon"],
    "slides": [
      { "mode": "template", "template": "title_card",
        "data": { "title": "STRATEGY", "title_accent": "REVIEW" } },
      { "mode": "template", "template": "hex_row",
        "data": { "title": "STRATEGIES",
          "tiles": [{ "label": "GROWTH", "subline": "2025", "icon_key": "growth_icon" }] } }
    ]
  }'

# 3. Edit slide 0 title later
curl -X POST "$API/api/pptx/{program_id}/edit" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{ "patches": [ { "op": "update", "slide": 0, "path": "data.title", "value": "NEW TITLE" } ] }'
```

---

## 8. Troubleshooting

| Symptom                                                   | Cause / Fix                                                         |
|-----------------------------------------------------------|---------------------------------------------------------------------|
| Slide content bunched into left half of slide             | Old code using `pres.layout='LAYOUT_WIDE'` — v2 fixes via `defineLayout({name, width, height})`. |
| `pptxgenjs unavailable` log                               | Node/npm missing, or npm failed first-time install. On Windows this required `shell=True`; already handled. |
| `"Template not found"` (or unexpected rendering)          | Template name unknown — fell through to `content` fallback. Check `templates.js` registry. |
| `WARN:shape clipped (x+w>W)`                              | Layout engine detected a box exceeding canvas. Review measurements in template/freestyle code; templates should never produce these. |
| Uploaded asset doesn't appear in manifest                 | Verify the upload route returned 200 and `scope='user'`. Global logos are seeded automatically at startup. |
| Edit produces an empty slide                              | `update` with `path` operates in-place on the slide's `data` dict. To replace a whole slide use `{op:"update", slide:i, value:{…}}` (no `path`). |

---

## 9. Tests / CI

- `scripts/smoke_test_pptx.py` — renders a multi-slide deck (title, title_card, team_triad, hex_row, cta_framed) and asserts canvas is 13.333×7.5 via `<p:sldSz>` XML inspection.  Returns exit code 0 on pass.
- Node syntax check: `node -e "new Function(fs.readFileSync('core/sandbox/js/runtime.js','utf8'))"` (run inside CI to catch JS parse errors early).
- Python syntax check: `python -c "import ast; ast.parse(open('core/sandbox/pptx_sandbox.py').read())"`.

---

## 10. Pending / future

- `org` scope for assets (DB + RLS in place, routes not yet exposed).
- Per-program named "themes" (palette overrides persisted alongside the program).
- Streaming render progress over WebSocket for large decks.
- Automated visual regression (headless preview render → PNG → pixel diff against baseline).
