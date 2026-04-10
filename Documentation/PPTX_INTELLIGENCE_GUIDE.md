# PPTX Intelligence Pipeline — Complete Guide

## Overview

The PPTX Intelligence Pipeline adds computer-vision powered slide understanding,
merging, reconstruction, and real-time revision to the Analyst by Potomac backend.

It solves the "boss email" problem:

> "Take slides 15-19 from the Meet Potomac deck and incorporate them into the
> Composite Details deck. Give that a first run today."

**Human time: 30-60 minutes. Our system: 10-15 seconds.**

---

## Architecture

```
User Upload (PPTX / PDF / HTML / Image)
            ↓
   SlideRenderer (core/vision/slide_renderer.py)
   • Fast path: python-pptx extracts embedded images from static-image slides
   • Fallback: LibreOffice → PDF → PyMuPDF → PNG
            ↓
   SlideManifest (list of per-slide PNG images)
            ↓
   VisionEngine (core/vision/vision_engine.py)
   • Sends each PNG to Claude Vision (claude-opus-4-5)
   • Returns SlideAnalysis JSON per slide
   • Detects: layout type, colors, text, elements, positions
            ↓
   ElementMatcher (core/vision/element_matcher.py)     [Phase 3 — after asset upload]
   • Perceptual hash matching against InDesign element library
   • Identifies exact brand assets used on each slide
            ↓
   ReconstructionEngine (core/vision/reconstruction_engine.py)
   • Maps SlideAnalysis → pptx_sandbox spec
   • High confidence (≥0.70): native pptxgenjs rebuild
   • Medium (0.40-0.70): image embed + native text overlay
   • Low (<0.40): pure image embed (pixel-perfect original)
            ↓
   PptxSandbox / AutomizerSandbox
   • Generates native editable .pptx file
            ↓
   Preview Render + Download URL
```

---

## API Endpoints

All endpoints are under `/pptx/` and require JWT authentication.

### POST /pptx/interpret-task ⭐ (The Main Endpoint)

The one-shot intelligent endpoint. Upload files + paste your task description.

```
Content-Type: multipart/form-data

files[]       : PPTX / PDF / HTML / image files (direct upload)
file_ids      : JSON array of previously-uploaded file IDs
context_text  : Boss email, task description, Slack message (any text)
instructions  : JSON overrides (optional)
analyze       : bool — also run Vision analysis (default: true)
```

**Example request (boss email scenario):**
```
POST /pptx/interpret-task
files[]: meet_potomac.pptx
files[]: composite_details.pptx
context_text: "Take slides 15-19 from the Meet Potomac deck and incorporate
               them into the Composite Details deck."
```

**Example response:**
```json
{
  "job_id": "abc-123",
  "action": "merge",
  "task_interpretation": {
    "action": "merge",
    "source_file": "meet_potomac.pptx",
    "target_file": "composite_details.pptx",
    "slide_range": [15, 19],
    "output_filename": "Composite_with_Strategy.pptx",
    "description": "Extract slides 15-19 from Meet Potomac deck and append to Composite Details deck",
    "confidence": 0.96
  },
  "success": true,
  "download_url": "/pptx/download/abc-123",
  "slide_count": 37,
  "preview_urls": [
    "/pptx/preview/abc-123/1",
    "/pptx/preview/abc-123/2",
    ...
  ],
  "source_file": "meet_potomac.pptx",
  "target_file": "composite_details.pptx",
  "slides_merged": [15, 16, 17, 18, 19],
  "elapsed_ms": 12340
}
```

---

### POST /pptx/analyze

Upload decks and get per-slide previews + structured Vision analysis.

```
files[]       : files to analyze
file_ids      : JSON array of file IDs
context_text  : optional context for better analysis
slide_range   : optional "15-19" to filter specific slides
vision        : bool — run Claude Vision analysis (default: true)
```

**Response:**
```json
{
  "job_id": "...",
  "files": [
    {
      "filename": "meet_potomac.pptx",
      "slide_count": 19,
      "slides": [
        {
          "index": 1,
          "preview_url": "/pptx/preview/{job_id}/1",
          "preview_b64": "data:image/png;base64,...",
          "width_px": 1920,
          "height_px": 1080,
          "source_type": "embedded"
        }
      ],
      "analyses": [
        {
          "slide_index": 1,
          "layout_type": "icon_grid",
          "background": "212121",
          "section_label": "STRATEGIES",
          "title": "OUR STRATEGIES ARE TACTICAL, UNCONSTRAINED, AND RISK-AWARE",
          "color_palette": ["FEC00F", "212121", "FFFFFF"],
          "elements": [
            {
              "type": "hexagon",
              "label": "Navigrowth",
              "sublabel": "2000",
              "icon": "globe",
              "fill_color": "FEC00F",
              "position": {"x_pct": 0.15, "y_pct": 0.45, "w_pct": 0.18, "h_pct": 0.35}
            }
          ],
          "reconstruction_strategy": "card_grid",
          "reconstruction_confidence": 0.87
        }
      ]
    }
  ]
}
```

---

### POST /pptx/merge

Cherry-pick specific slides from one or more decks.

```
files[]           : source and target PPTX files
context_text      : optional NLP description of what to merge
merge_spec        : optional JSON spec (if you want explicit control)
output_filename   : desired output filename
```

**Explicit merge_spec example:**
```json
{
  "source_file": "meet_potomac.pptx",
  "target_file": "composite_details.pptx",
  "slide_range": [15, 19],
  "insert_after_slide": null,
  "output_filename": "Composite_Strategy_Combined.pptx"
}
```

**How it works:**
1. Uses `AutomizerSandbox` in assembly mode
2. Copies ALL slides from the target deck first
3. Appends (or inserts) slides from the source deck at the specified range
4. Pixel-perfect preservation — static image slides are copied exactly as-is
5. Renders preview of the merged output

---

### POST /pptx/reconstruct

Convert static-image slides into native editable PPTX elements.

```
files[]       : PPTX with static-image slides
slide_range   : optional "15-19" to reconstruct specific slides only
context_text  : context for better reconstruction
force_embed   : bool — if true, always embed as images (no reconstruction)
```

**Reconstruction workflow:**
1. SlideRenderer extracts embedded images
2. VisionEngine analyzes each image (Claude Vision)
3. ReconstructionEngine builds pptx_sandbox spec
4. PptxSandbox generates native editable .pptx

**Confidence levels:**
- ≥ 0.70: Full native rebuild (text, shapes, colors all editable)
- 0.40-0.70: Image background + editable text overlay
- < 0.40: Pure image embed (original image, no reconstruction)

---

### POST /pptx/revise

Apply a revision instruction to a previously generated deck.

```
job_id       : ID of the previous job
instruction  : revision instruction ("Move strategy slides before slide 10")
```

---

### GET /pptx/preview/{job_id}/{slide_index}

Serve a rendered slide PNG image. The frontend polls these as they're generated.

```
job_id       : job ID from any previous endpoint
slide_index  : 1-based slide number
```

Returns: `image/png`

---

### GET /pptx/download/{job_id}

Download the generated .pptx file.

Returns: `application/vnd.openxmlformats-officedocument.presentationml.presentation`

---

### GET /pptx/status/{job_id}

Poll job status.

```json
{
  "status": "complete",
  "action": "merge",
  "success": true,
  "download_url": "/pptx/download/abc-123",
  "slide_count": 37,
  "elapsed_ms": 12340
}
```

---

### POST /pptx/element-library/upload

Upload InDesign-exported PNG design elements to the matching library.

```
files[]       : PNG image files
category      : icons | logos | backgrounds | badges | dividers | shapes
tags          : comma-separated tags ("hexagon,strategy,yellow")
```

**When to use:** After you export elements from InDesign, upload them here.
The system will perceptually hash them and automatically use them in future
slide reconstructions to achieve higher fidelity matches.

---

### GET /pptx/element-library/catalog

Returns a catalog of all indexed design elements.

---

## Accepted File Formats

| Format | Support | Notes |
|--------|---------|-------|
| `.pptx` | ✅ Full | Fast path for static-image slides (InDesign exports) |
| `.ppt` | ✅ Full | Via LibreOffice conversion |
| `.pdf` | ✅ Full | PyMuPDF rendering at 150 DPI |
| `.html` | ✅ Full | Puppeteer screenshot |
| `.png` / `.jpg` | ✅ Full | Treated as single slide |
| `.webp` | ✅ Full | Normalized to PNG |
| `.docx` | ⚠️ Context only | Text extracted as context for Claude |
| `.txt` / `.md` | ⚠️ Context only | Used as task/context description |

**File size limit:** 100 MB per file for intelligence endpoints

---

## Rendering Strategy

### Fast Path (static-image PPTX from InDesign)
InDesign-exported PPTX files typically have each slide as a single full-bleed
image. `SlideRenderer` detects this pattern and extracts the embedded PNG directly
— no LibreOffice needed, instant and pixel-perfect.

### Fallback (editable PPTX)
For decks with native text/shapes:
```
python-pptx → detect no full-bleed image → LibreOffice headless
→ PPTX to PDF → PyMuPDF → PNG at 150 DPI
```

### Performance
| File type | Slides | Time |
|-----------|--------|------|
| Static image PPTX | 20 slides | ~2s |
| Editable PPTX (LibreOffice) | 20 slides | ~15s |
| PDF | 20 pages | ~3s |

---

## Slide Merge — How It Works Internally

The merge uses `pptx-automizer` in **assembly mode**, which copies slide XML
verbatim from source PPTX files. This means:

- Static image slides copy exactly — pixel-for-pixel
- Native element slides preserve all formatting
- Slide masters are imported automatically
- No content is re-rendered or re-compressed

### Assembly Spec Example
```json
{
  "mode": "assembly",
  "filename": "merged_output.pptx",
  "root_template": "composite_details.pptx",
  "remove_existing_slides": true,
  "slides": [
    { "source_file": "composite_details.pptx", "slide_number": 1 },
    { "source_file": "composite_details.pptx", "slide_number": 2 },
    ...
    { "source_file": "meet_potomac.pptx", "slide_number": 15 },
    { "source_file": "meet_potomac.pptx", "slide_number": 16 },
    { "source_file": "meet_potomac.pptx", "slide_number": 17 },
    { "source_file": "meet_potomac.pptx", "slide_number": 18 },
    { "source_file": "meet_potomac.pptx", "slide_number": 19 }
  ]
}
```

---

## Vision Analysis — Detected Properties

Claude Vision analyzes each slide and extracts:

| Property | Example |
|----------|---------|
| `layout_type` | `icon_grid`, `dark_hero`, `two_column` |
| `background` | `212121` (dark gray), `FFFFFF` (white) |
| `section_label` | `STRATEGIES`, `INVESTMENT PROCESS` |
| `title` | Verbatim slide title text |
| `color_palette` | `["FEC00F", "212121", "FFFFFF", "999999"]` |
| `elements[]` | List of detected visual elements with positions |
| `reconstruction_strategy` | `card_grid`, `hub_spoke`, `full_image_embed` |
| `reconstruction_confidence` | `0.87` |

---

## Element Library — Perceptual Hashing

When you upload InDesign PNG assets, they are indexed with three hash types:

| Hash | Description | Use case |
|------|-------------|----------|
| pHash | DCT-based perceptual hash | Best overall, used with 2x weight |
| aHash | Average hash | Fast fallback |
| dHash | Difference hash | Edge/gradient sensitive |

Combined distance = `2×pHash_dist + aHash_dist + dHash_dist`
Similarity score = `1 - (distance / 128)`

Match threshold: **0.50** (50% similarity minimum)

---

## Job Storage

All job data is stored at `$STORAGE_ROOT/pptx_jobs/{job_id}/`:
```
{job_id}/
  meta.json             → job metadata + result summary
  slide_0001.png        → rendered preview for slide 1
  slide_0002.png        → rendered preview for slide 2
  ...
  merged_output.pptx    → generated PPTX output
```

Jobs are NOT automatically cleaned up — implement a cleanup cron if needed.

---

## Frontend Integration Example

```typescript
// 1. Upload files + task description
const formData = new FormData();
formData.append('files', meetPotomacFile);
formData.append('files', compositeFile);
formData.append('context_text', bossEmailText);

const response = await fetch('/pptx/interpret-task', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: formData,
});

const result = await response.json();
// { job_id, action: "merge", download_url, preview_urls: [...] }

// 2. Show previews as they arrive
for (const previewUrl of result.preview_urls) {
  const img = new Image();
  img.src = `${API_BASE}${previewUrl}`;
  slidesContainer.appendChild(img);
}

// 3. Download button
downloadBtn.href = `${API_BASE}${result.download_url}`;

// 4. Revision
const revResponse = await fetch('/pptx/revise', {
  method: 'POST',
  body: new URLSearchParams({
    job_id: result.job_id,
    instruction: "Move the strategy slides before slide 10, not at the end"
  }),
  headers: { 'Authorization': `Bearer ${token}` },
});
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_ROOT` | `/data` | Railway volume mount for job storage |
| `ANTHROPIC_API_KEY` | required | For Claude Vision analysis |
| `VISION_MODEL` | `claude-opus-4-5` | Model for slide analysis |
| `VISION_FAST_MODEL` | `claude-sonnet-4-5` | Model for bulk analysis |
| `SANDBOX_DATA_DIR` | `~/.sandbox` | npm cache + element index dir |

---

## New Files Created

```
core/vision/
  __init__.py                  Module init + exports
  slide_renderer.py            PPTX/PDF/HTML → per-slide PNG
  vision_engine.py             Claude Vision → SlideAnalysis JSON
  element_matcher.py           Perceptual hash element library
  reconstruction_engine.py     SlideAnalysis → pptx_sandbox spec

api/routes/
  pptx_intelligence.py         All REST endpoints

ClaudeSkills/potomac-pptx/element-library/
  README.md                    This guide
  icons/                       Icon PNG assets
  logos/                       Logo variants
  backgrounds/                 Background assets
  badges/                      Badge templates
  dividers/                    Divider elements
  shapes/                      Shape templates
```
