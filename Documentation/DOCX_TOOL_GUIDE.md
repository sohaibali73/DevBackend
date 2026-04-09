# `generate_docx` Tool — Implementation Guide

## Overview

`generate_docx` is a **server-side Potomac DOCX generator** that runs entirely on the Railway server using Node.js + the `docx` npm package.

| Feature | `generate_docx` | Old `invoke_skill` path |
|---|---|---|
| Claude API cost | **Zero** | Costs tokens |
| Generation time | **3–10 s** | 20–60 s |
| Logo assets | **Mounted from repo** | Mounted in container |
| Node.js required | Yes (pre-installed on Railway) | No |
| Availability | Always | Requires active API key |

---

## Architecture

```
LLM (Claude)
  └─ calls generate_docx({title, sections, ...})
       └─ core/tools.py → handle_tool_call("generate_docx")
            └─ core/tools_v2/document_tools.py → handle_generate_docx()
                 └─ core/sandbox/docx_sandbox.py → DocxSandbox.generate()
                      ├─ Writes spec.json to temp dir
                      ├─ Mounts ClaudeSkills/potomac-docx/assets/ → ./assets/
                      ├─ Symlinks ~/.sandbox/docx_cache/node_modules
                      ├─ Runs: node document_builder.js
                      └─ Reads output.docx bytes → store_file()
                           └─ Railway volume + Supabase Storage
```

The `document_builder.js` is **embedded** in `docx_sandbox.py` as a string constant. It reads `spec.json` and the logo PNGs from `./assets/`, builds the `Document` using the `docx` library, and writes the output `.docx`.

---

## Tool Schema Reference

```json
{
  "name": "generate_docx",
  "input": {
    "title":        "string (required) — ALL CAPS recommended",
    "sections":     "array (required) — see Section Types below",
    "filename":     "string — e.g. 'Potomac_Q1_Report.docx'",
    "subtitle":     "string",
    "date":         "string — e.g. 'Q1 2026'",
    "author":       "string — e.g. 'Potomac Research Team'",
    "logo_variant": "'standard' | 'black' | 'white'",
    "header_line_color": "'yellow' | 'dark'",
    "footer_text":  "string — overrides 'Potomac | Built to Conquer Risk®'",
    "include_disclosure": "boolean (default true)",
    "disclosure_text":    "string — overrides default disclosure"
  }
}
```

### Section Types

| `type` | Extra fields |
|--------|-------------|
| `heading` | `level` (1/2/3), `text` |
| `paragraph` | `text` OR `runs: [{text, bold, italics, color}]` |
| `bullets` | `items: [string, ...]` |
| `numbered` | `items: [string, ...]` |
| `table` | `headers: [string]`, `rows: [[string]]`, `col_widths?: [int]` |
| `divider` | *(no extra fields — draws yellow rule)* |
| `spacer` | `size?: int` (twips, default 240) |
| `page_break` | *(no extra fields)* |

---

## Tool Response

On **success**:
```json
{
  "status": "success",
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "Potomac_Q1_Commentary.docx",
  "size_kb": 84.2,
  "download_url": "/files/550e8400-e29b-41d4-a716-446655440000/download",
  "exec_time_ms": 5430,
  "message": "✅ Document 'Potomac_Q1_Commentary.docx' generated successfully (84.2 KB). Download: /files/550e8400/download"
}
```

On **error**:
```json
{
  "status": "error",
  "error": "Node.js builder failed: Cannot read property 'text' of undefined"
}
```

---

## Frontend Wiring

### 1. Detect `generate_docx` tool result in your stream handler

The LLM calls `generate_docx` as a tool. After the tool result is returned to Claude, Claude emits a text response. The `download_url` is present in the tool result JSON.

### 2. Render a download card

When Claude's text response mentions a document was created OR when you detect the tool result contains `download_url`, show a download card.

**React / TypeScript example:**

```tsx
// types.ts
interface DocxArtifact {
  file_id: string;
  filename: string;
  size_kb: number;
  download_url: string;   // "/files/{uuid}/download"
}

// DocxDownloadCard.tsx
import { FileText, Download } from 'lucide-react';

export function DocxDownloadCard({ artifact }: { artifact: DocxArtifact }) {
  const fullUrl = `${process.env.NEXT_PUBLIC_BACKEND_URL}${artifact.download_url}`;

  return (
    <div className="flex items-center gap-3 p-4 border border-yellow-400 rounded-lg bg-gray-900">
      <FileText className="text-yellow-400 w-8 h-8 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-white font-medium truncate">{artifact.filename}</p>
        <p className="text-gray-400 text-sm">{artifact.size_kb.toFixed(1)} KB • Word Document</p>
      </div>
      <a
        href={fullUrl}
        download={artifact.filename}
        className="flex items-center gap-2 px-4 py-2 bg-yellow-400 text-black rounded-md font-semibold hover:bg-yellow-300 transition"
      >
        <Download className="w-4 h-4" />
        Download
      </a>
    </div>
  );
}
```

### 3. Parse tool results from the chat stream

Your chat message handler should check for `generate_docx` tool results:

```tsx
// In your stream/message handler
function handleToolResult(toolName: string, result: Record<string, unknown>) {
  if (toolName === 'generate_docx' && result.status === 'success') {
    const artifact: DocxArtifact = {
      file_id:      result.file_id as string,
      filename:     result.filename as string,
      size_kb:      result.size_kb as number,
      download_url: result.download_url as string,
    };
    // Add to message artifacts list to render DocxDownloadCard
    addArtifact(artifact);
  }
}
```

### 4. Direct download endpoint

The download endpoint is already wired in `api/routes/files_router.py` (the existing `/files/{file_id}/download` route served by `file_store`).

```bash
# Direct download
GET https://your-railway-app.railway.app/files/{file_id}/download
# → Content-Disposition: attachment; filename="Potomac_Q1_Commentary.docx"
# → Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

### 5. Vercel AI SDK (`useChat`) integration

If you're using the Vercel AI SDK v4/v7, intercept `data-file_download` events from the stream:

```tsx
const { messages, data } = useChat({ api: '/api/chat' });

// data events emitted by the backend stream
useEffect(() => {
  const last = data?.[data.length - 1];
  if (last?.type === 'file_download' && last.filename?.endsWith('.docx')) {
    setDocxArtifact(last as DocxArtifact);
  }
}, [data]);
```

---

## Stress Test Prompts

Use these prompts to test every feature of `generate_docx`. Each prompt should trigger the tool automatically via the AI system.

---

### Test 1 — Basic Document (all section types)

```
Create a Potomac fund fact sheet for April 2026 using the generate_docx tool. Include:
- Title: "POTOMAC TACTICAL FUND" with subtitle "April 2026 Fact Sheet"
- An executive summary paragraph
- A bullet list of 5 key highlights
- A performance table with columns: Period, Fund Return, Benchmark, Alpha — with 5 rows of data
- A numbered list of 3 investment process steps
- A section heading for "RISK METRICS"
- Another table with columns: Metric, Value — showing Sharpe Ratio, Max Drawdown, Beta, Volatility
- A divider before the disclosure
- Use the standard Potomac logo and yellow header line
Author: Potomac Research Team
Date: April 2026
```

---

### Test 2 — Multi-page Research Report (page breaks + mixed runs)

```
Generate a Potomac research report titled "BEAR MARKET IN DIVERSIFICATION" using generate_docx. Make it comprehensive with:
1. Title page (title, subtitle: "Investment Research", date: "April 2026", author: "Potomac Research")
2. A heading "EXECUTIVE SUMMARY" with 2 paragraphs of text about diversification failing
3. A heading "KEY FINDINGS" with 6 bullet points about bonds, gold, managed futures underperformance
4. A page_break
5. A heading "ANALYSIS" with a subheading (H2) "ROLLING RETURNS CONTEXT"
6. 2 paragraphs — first paragraph should use mixed runs: some text bold, some italic
7. A heading "TRADITIONAL DIVERSIFIERS PERFORMANCE"
8. A table with these exact columns: Asset, 10-Year, 15-Year, Max DD, Correlation, Beta
   Rows: S&P 500 (11.10%, 11.76%, -33.92%, 1.00, 1.00), Gold (-1.26%, -0.42%, -23.31%, 0.01, 0.00), Bonds (-1.14%, 2.63%, -48.35%, -0.29, -0.26)
9. A divider
10. A heading "CONCLUSION" with a closing paragraph
Set include_disclosure=true
Filename: Potomac_Bear_Market_Diversification.docx
```

---

### Test 3 — Internal Memo (no disclosure, dark header)

```
Create an internal Potomac memo using generate_docx with:
- Title: "PORTFOLIO REBALANCING NOTICE"
- Subtitle: "Internal Communication — Q2 2026"
- Date: "April 9, 2026"
- Author: "Investment Committee"
- header_line_color: "dark"
- logo_variant: "black"
- include_disclosure: false
- Sections: H1 heading "PURPOSE", a paragraph, H2 heading "AFFECTED ACCOUNTS", a numbered list of 4 account types, H2 heading "TIMELINE", a table with columns: Phase, Date, Action (3 rows), a spacer, a divider, a paragraph with italic text saying "For questions contact the investment team"
Filename: Internal_Rebalancing_Notice_Q2.docx
```

---

### Test 4 — Wide Table Stress Test

```
Use generate_docx to create a Potomac performance attribution report. Include a 7-column table showing attribution by sector. Table headers: Sector, Weight%, Return%, Contrib%, Bench%, Active%, IR. Include 10 rows of sector data (Technology, Healthcare, Financials, Consumer, Energy, Materials, Industrials, Utilities, Real Estate, Communication). Use col_widths to distribute evenly across 9360 DXA (about 1337 each). Title: "PERFORMANCE ATTRIBUTION REPORT Q1 2026". Set col_widths: [2000, 1000, 1000, 1000, 1000, 1000, 1360]
```

---

### Test 5 — Full DDQ Document (long document, multiple page breaks)

```
Generate a complete Potomac Due Diligence Questionnaire using generate_docx. Title: "POTOMAC DUE DILIGENCE QUESTIONNAIRE". Include sections:
1. H1: "FIRM OVERVIEW" — paragraph about Potomac being a tactical fund manager
2. H2: "AUM and Client Base" — table: Metric, Value with rows for AUM, Number of Clients, Founded, Employees
3. page_break
4. H1: "INVESTMENT PROCESS" — paragraph + H2 "Signal Generation" + bullets (5 items about tactical signals) + H2 "Risk Management" + bullets (4 items)
5. page_break
6. H1: "PERFORMANCE TRACK RECORD" — table: Year, Gross Return%, Net Return%, Benchmark%, Alpha% for years 2020-2024
7. divider
8. H1: "FEES AND TERMS" — table: Fee Type, Amount for Management Fee, Performance Fee, Minimum Investment, Redemption Notice
9. page_break
10. H1: "COMPLIANCE AND REGULATORY" — numbered list with 5 compliance points
Author: Potomac Investor Relations
Date: April 2026
Filename: Potomac_DDQ_April_2026.docx
```

---

### Test 6 — White Logo + Custom Footer

```
Create a client-facing Potomac proposal using generate_docx. Use logo_variant: "white" and a custom footer_text: "Potomac Fund Management  |  Confidential". Title: "INVESTMENT PROPOSAL FOR [CLIENT NAME]". Include an executive summary, investment objectives table, proposed allocation table (5 asset classes with % weights), risk/return expectations paragraph, and a service agreement section. Date: April 2026. Filename: Potomac_Client_Proposal.docx
```

---

## Troubleshooting

### First run is slow (~30-60 seconds)
**Normal.** The `docx` npm package is being installed to `~/.sandbox/docx_cache/` for the first time. Every subsequent call takes 3-10 s using the symlinked cache.

### `Node.js not found`
Ensure `node` and `npm` are on the Railway service PATH. The standard Railway Node.js buildpack includes both.

### `Output .docx not found`
Check the `spec.json` `filename` field. The builder writes the file with exactly that name. If `filename` is omitted it writes `output.docx`.

### Logo missing from header
Check that `ClaudeSkills/potomac-docx/assets/Potomac_Logo_clean.png` exists. The sandbox copies logos to the temp dir before running Node. If logos are missing the document generates without a logo (no error).

### `ERROR:Cannot read property 'text' of undefined`
A `paragraph` section is missing both `text` and `runs`. Every `paragraph` needs either `"text": "..."` or a `runs` array with at least one item.

### `npm install` timeout on Railway
Set `SANDBOX_DATA_DIR` env var to a persistent volume path (default: `/root/.sandbox`). On Railway, mount a volume at `/data` and set `SANDBOX_DATA_DIR=/data/sandbox`.

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SANDBOX_DATA_DIR` | `~/.sandbox` | Parent dir for `docx_cache/` node_modules cache |
| `STORAGE_ROOT` | `/data` | Railway volume root for `file_store` |

---

## Files Created / Modified

| File | Change |
|---|---|
| `core/sandbox/docx_sandbox.py` | **New** — DocxSandbox class + embedded JS builder |
| `core/tools_v2/document_tools.py` | **New** — Tool definition + sync handler |
| `core/tools_v2/registry.py` | **Modified** — Fixed `handle_tool_call` to check `_handlers` dict first |
| `core/tools.py` | **Modified** — Added `generate_docx` to `TOOL_DEFINITIONS` + `handle_tool_call` dispatch |

The existing `invoke_skill`, `create_word_document`, `potomac-docx-skill`, and all other tools are **untouched**.
