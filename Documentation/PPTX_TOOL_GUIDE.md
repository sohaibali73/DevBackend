# `generate_pptx` Tool Guide

Server-side Potomac-branded PowerPoint generator. Runs entirely on Railway via
**Node.js + pptxgenjs**. No Claude Skills container, no API cost.

---

## Architecture

```
Claude (AI)
  └─ generate_pptx({title, slides: [...]})
       └─ handle_generate_pptx()          # core/tools_v2/document_tools.py
            └─ PptxSandbox.generate()     # core/sandbox/pptx_sandbox.py
                 ├─ _resolve_image_slides()  # file_id → base64 (Python)
                 ├─ _ensure_pptx_modules()   # npm cache ~/.sandbox/pptx_cache/
                 ├─ writes presentation_builder.js + spec.json to temp dir
                 ├─ node presentation_builder.js  (pptxgenjs)
                 └─ returns .pptx bytes
                      └─ store_file() → /files/{uuid}/download
```

**Assets** (logos): `ClaudeSkills/potomac-pptx/brand-assets/logos/`  
`startup_copy_pptx_assets()` in `main.py` copies them to `$STORAGE_ROOT/pptx_assets/` at boot.

---

## Slide Types

| Type | Required Fields | Optional Fields |
|------|----------------|-----------------|
| `title` | `title` | `subtitle`, `tagline`, `style` (`standard`\|`executive`) |
| `content` | `title`, `bullets:[str]` or `text:str` | — |
| `two_column` | `title`, `left_content`, `right_content` | `left_header`, `right_header`, or `columns:[l,r]` |
| `three_column` | `title`, `columns:[c1,c2,c3]` | `column_headers:[h1,h2,h3]` |
| `metrics` | `title`, `metrics:[{value,label}]` | `context` (disclaimer text) |
| `process` | `title`, `steps:[{title,description}]` | — |
| `quote` | `quote` | `attribution`, `context` |
| `section_divider` | `title` | `description` |
| `cta` | `title` | `action_text`, `button_text`, `contact_info` |
| `image` | `file_id` (or `data`) | `title`, `format`, `width`, `height`, `align`, `caption` |

---

## Brand Palette

| Color | Hex | Use |
|-------|-----|-----|
| Potomac Yellow | `#FEC00F` | Accent bars, metric values, buttons |
| Dark Gray | `#212121` | All text, left accent bar |
| White | `#FFFFFF` | Standard slide background |
| Yellow 20% | `#FEF7D8` | Quote slide, section divider background |
| Gray 60% | `#999999` | Subtitles, captions, context |
| Gray 20% | `#DDDDDD` | Column dividers, process connectors |

---

## Full Spec Example

```json
{
  "title": "POTOMAC Q1 2026 MARKET OUTLOOK",
  "filename": "Potomac_Q1_2026_Outlook.pptx",
  "slides": [
    {
      "type": "title",
      "title": "Q1 2026 Market Outlook",
      "subtitle": "Navigating Uncertainty with Confidence",
      "tagline": "Built to Conquer Risk®",
      "style": "executive"
    },
    {
      "type": "section_divider",
      "title": "Market Environment",
      "description": "Current conditions and key themes shaping Q1 2026"
    },
    {
      "type": "content",
      "title": "Key Market Themes",
      "bullets": [
        "Federal Reserve expected to hold rates through Q2",
        "Equity valuations remain elevated relative to historical averages",
        "Credit spreads have narrowed to pre-2022 levels",
        "International diversification increasingly attractive"
      ]
    },
    {
      "type": "two_column",
      "title": "Current vs. Our Outlook",
      "left_header": "Market Challenges",
      "right_header": "Potomac's View",
      "left_content": "• Persistent inflation pressure\n• Geopolitical uncertainty\n• Rate environment volatility\n• Elevated equity multiples",
      "right_content": "• Selective opportunities in value\n• Defensive positioning preferred\n• Active management advantage\n• Real assets as inflation hedge"
    },
    {
      "type": "metrics",
      "title": "Portfolio Performance",
      "metrics": [
        {"value": "+12.4%", "label": "YTD Return"},
        {"value": "0.82", "label": "Sharpe Ratio"},
        {"value": "-6.1%", "label": "Max Drawdown"},
        {"value": "94%", "label": "Win Rate"}
      ],
      "context": "Past performance is not indicative of future results."
    },
    {
      "type": "process",
      "title": "Our Investment Process",
      "steps": [
        {"title": "Assess", "description": "Macro regime identification and risk environment analysis"},
        {"title": "Allocate", "description": "Dynamic asset allocation based on risk-adjusted opportunities"},
        {"title": "Execute", "description": "Systematic implementation with discipline and precision"},
        {"title": "Monitor", "description": "Continuous risk management and portfolio rebalancing"}
    ]
    },
    {
      "type": "quote",
      "quote": "Our systematic approach removes emotion from decision-making, allowing us to capitalize on opportunities others miss.",
      "attribution": "Derek Bruton, Managing Director",
      "context": "Potomac Investment Symposium, January 2026"
    },
    {
      "type": "three_column",
      "title": "Asset Class Outlook",
      "column_headers": ["Equities", "Fixed Income", "Alternatives"],
      "columns": [
        "• US Large Cap: Neutral\n• Small Cap: Underweight\n• International: Overweight\n• Emerging Markets: Selective",
        "• Duration: Short\n• Credit Quality: High\n• TIPS: Overweight\n• High Yield: Underweight",
        "• Real Assets: Overweight\n• Commodities: Neutral\n• Private Credit: Selective\n• Hedge Strategies: Overweight"
      ]
    },
    {
      "type": "cta",
      "title": "Let's Build Your Strategy",
      "action_text": "Ready to position your portfolio for the opportunities ahead? Our team is available to discuss a customized approach for your specific objectives.",
      "button_text": "Schedule a Consultation",
      "contact_info": "potomac.com  |  (305) 824-2702  |  info@potomac.com"
    }
  ]
}
```

---

## Stress Test Prompts

Use these in the chat to test `generate_pptx` end-to-end:

**1. Quick 5-slide deck:**
> "Create a 5-slide PowerPoint on Potomac's tactical asset management approach. Include a title slide, an overview of our investment philosophy, key performance metrics (15% return, 0.9 Sharpe, -8% max DD), our 4-step process, and a closing CTA slide."

**2. Executive-style market briefing:**
> "Build a Potomac board presentation on Q1 2026 market conditions. Use the executive dark style for the title slide. Include two-column slides comparing bull vs. bear scenarios, a metrics slide with macro indicators, and a section divider."

**3. Client pitch with three columns:**
> "Generate a client pitch deck for Potomac's multi-strategy fund. Show why we're different from competitors using a three-column slide (Experience, Innovation, Service). Include a quote from a client testimonial and a process flow."

**4. Quote-heavy testimonial deck:**
> "Create a 6-slide Potomac testimonial presentation with 3 client quote slides, a metrics slide showing client AUM growth, and a CTA closing slide."

**5. Section-divider heavy outline:**
> "Make a Potomac educational presentation on risk management with 4 section dividers (Introduction, Identifying Risk, Managing Risk, Case Studies), each followed by 1-2 content slides."

**6. Full 12-slide research presentation:**
> "Generate a complete Potomac market research presentation for Q2 2026 covering: macro environment, equity outlook, fixed income analysis, alternatives, our model portfolio allocation, and performance attribution. Use all slide types — title, content, two-column, metrics, process, and CTA."

---

## Frontend Download Card

```tsx
// React component — uses native <a download> to trigger browser download
// No blob URL, no CSP issues

interface PptxResult {
  status: "success" | "error";
  file_id: string;
  filename: string;
  size_kb: number;
  download_url: string;
  exec_time_ms: number;
  message: string;
}

function PptxDownloadCard({ result }: { result: PptxResult }) {
  if (result.status !== "success") return null;

  const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`;

  return (
    <div className="flex items-center gap-3 p-4 bg-yellow-50 border border-yellow-200 rounded-xl">
      <div className="text-3xl">📊</div>
      <div className="flex-1">
        <p className="font-semibold text-gray-900">{result.filename}</p>
        <p className="text-sm text-gray-500">
          {result.size_kb.toFixed(1)} KB · Generated in {(result.exec_time_ms / 1000).toFixed(1)}s
        </p>
      </div>
      <a
        href={downloadUrl}
        download={result.filename}
        className="px-4 py-2 bg-yellow-400 hover:bg-yellow-500 text-gray-900 font-semibold rounded-lg text-sm transition-colors"
      >
        Download
      </a>
    </div>
  );
}
```

---

## Key Files

| File | Purpose |
|------|---------|
| `core/sandbox/pptx_sandbox.py` | PptxSandbox class + embedded `presentation_builder.js` |
| `core/tools_v2/document_tools.py` | `GENERATE_PPTX_TOOL_DEF` + `handle_generate_pptx()` |
| `core/tools.py` | TOOL_DEFINITIONS entry + `elif tool_name == "generate_pptx"` dispatch |
| `main.py` | `startup_copy_pptx_assets()` startup event |
| `ClaudeSkills/potomac-pptx/brand-assets/logos/` | `potomac-full-logo.png`, `potomac-icon-black.png`, `potomac-icon-yellow.png` |

---

## npm Cache

First invocation installs `pptxgenjs@^3.12.0` into `~/.sandbox/pptx_cache/` (~45 s).  
All subsequent calls symlink the cached `node_modules` (O(1)).  
On Railway, the cache persists in the volume between deployments.
