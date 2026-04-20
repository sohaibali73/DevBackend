# Potomac Automizer Templates

This directory contains pre-designed Potomac-branded `.pptx` template files used by the `generate_pptx_template` tool via `pptx-automizer`.

## How It Works

The `AutomizerSandbox` (`core/sandbox/automizer_sandbox.py`) automatically copies any `.pptx` file from this directory into the Node.js temp workspace when it is referenced in a spec's `source_file` or `root_template` field.

## Adding Templates

Place any professionally designed `.pptx` file here. Shape names (visible via ALT+F10 in PowerPoint) become the target identifiers for modifications.

**Recommended template files to add:**
- `potomac-root.pptx` — Blank slide with Potomac slide master / theme (use as root_template)
- `potomac-content-slides.pptx` — Pre-built content slide types with named shapes
- `potomac-chart-slides.pptx` — Slides with pre-styled embedded charts
- `potomac-table-slides.pptx` — Slides with pre-styled tables
- `potomac-fund-fact-sheet.pptx` — Fund fact sheet with {{tagged}} placeholders

## Bootstrap: Generating Templates

Templates can be generated using the existing `generate_pptx` tool and then uploaded back to the server, or created directly in PowerPoint.

**Step 1:** Use `generate_pptx` to create a well-designed presentation.
**Step 2:** Download the `.pptx`, open in PowerPoint, name all shapes via ALT+F10.
**Step 3:** Place the file here.
**Step 4:** Reference it as `"source_file": "potomac-content-slides.pptx"` in `generate_pptx_template` specs.

## Shape Naming Convention

Use descriptive names in the PowerPoint Selection Pane (ALT+F10):
- `TitleText` — Main slide title
- `BodyText` — Main body text box
- `PerformanceChart` — Performance chart object
- `HoldingsTable` — Top holdings table
- `SubtitleText` — Slide subtitle
- `LogoImage` — Potomac logo image placeholder

## Usage Example

```json
{
  "mode": "assembly",
  "filename": "Q1_2026_Report.pptx",
  "root_template": "potomac-root.pptx",
  "slides": [
    {
      "source_file": "potomac-content-slides.pptx",
      "slide_number": 1,
      "modifications": [
        {"op": "set_text", "shape": "TitleText", "text": "Q1 2026 FUND OVERVIEW"},
        {"op": "replace_tagged", "shape": "BodyText", "tags": [
          {"find": "date", "by": "March 31, 2026"}
        ]}
      ]
    },
    {
      "source_file": "potomac-chart-slides.pptx",
      "slide_number": 2,
      "modifications": [
        {"op": "set_chart_data", "shape": "PerformanceChart",
         "series": [{"label": "Fund"}, {"label": "Benchmark"}],
         "categories": [
           {"label": "Jan", "values": [2.1, 1.8]},
           {"label": "Feb", "values": [0.9, 1.1]},
           {"label": "Mar", "values": [1.5, 1.3]}
         ]}
      ]
    }
  ]
}
```
