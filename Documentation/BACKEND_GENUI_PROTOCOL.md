# Backend Generative UI Protocol

## Complete Reference for SwiftUI Card Rendering

This document is the **single source of truth** for all structured events emitted by the backend. Every event is designed to be directly mapped to SwiftUI components.

---

## **🔹 Protocol Overview**

All events follow the Vercel AI SDK v7 stream format. Each event has a `type` field starting with `data-*`.

All events are JSON objects that can be directly decoded into Swift structs.

---

## **🔹 All Supported Generative UI Events**

---

### ✅ `data-file_download`
**Purpose:** Render file download card
```json
{
  "type": "data-file_download",
  "data": {
    "type": "file_download",
    "file_id": "550e8400-e29b-41d4-a716-446655440000",
    "filename": "Fund_Fact_Sheet_Q1_2026.docx",
    "download_url": "/files/550e8400-e29b-41d4-a716-446655440000/download",
    "file_type": "docx",
    "size_kb": 124.7,
    "tool_name": "skill:potomac-docx-skill",
    "created_at": 1743871200
  }
}
```

**SwiftUI Card:**
- File icon for `file_type`
- Filename bold
- File size in trailing corner
- Download button
- Bounce-in entrance animation

---

### ✅ `data-skill_execution` → `skill_start`
**Purpose:** Render active skill execution header
```json
{
  "type": "data-skill_execution",
  "data": {
    "type": "skill_start",
    "slug": "potomac-docx-skill",
    "name": "Potomac DOCX Skill",
    "category": "document",
    "description": "Creating professional Word document..."
  }
}
```

**SwiftUI Card:**
- Left: SF Symbol for category
- Middle: Skill name + description
- Right: Animated progress indicator
- Yellow accent border (Potomac brand)

---

### ✅ `data-skill_execution` → `skill_complete`
**Purpose:** Render completed skill state
```json
{
  "type": "data-skill_execution",
  "data": {
    "type": "skill_complete",
    "slug": "potomac-docx-skill",
    "name": "Potomac DOCX Skill",
    "execution_time": 18.4,
    "input_tokens": 1247,
    "output_tokens": 3892
  }
}
```

**SwiftUI Card:**
- ✅ Checkmark icon
- Execution time displayed
- Fade out after 3 seconds

---

### ✅ `data-chart`
**Purpose:** Render interactive chart
```json
{
  "type": "data-chart",
  "data": {
    "type": "line_chart",
    "title": "Cumulative Returns",
    "x_label": "Date",
    "y_label": "Return %",
    "series": [
      {
        "name": "Strategy",
        "color": "#FEC00F",
        "values": [ {"x": "2025-01-01", "y": 0.0}, {"x": "2025-06-01", "y": 12.7} ]
      }
    ]
  }
}
```

**Chart Types:**
- `line_chart`
- `bar_chart`
- `area_chart`
- `scatter_chart`
- `waterfall_chart`

---

### ✅ `data-metric_card`
**Purpose:** Render performance metric card
```json
{
  "type": "data-metric_card",
  "data": {
    "title": "Sharpe Ratio",
    "value": 1.87,
    "format": "number:2",
    "description": "Annualized risk adjusted return",
    "trend": "positive",
    "benchmark": 1.2
  }
}
```

**Format Values:**
- `number:X` - decimal places
- `percent:X` - percentage
- `currency` - USD currency
- `ratio` - ratio format

**Trend values:** `positive`, `negative`, `neutral`

---

### ✅ `data-table`
**Purpose:** Render formatted data table
```json
{
  "type": "data-table",
  "data": {
    "title": "Monthly Performance",
    "columns": ["Month", "Return", "Drawdown"],
    "rows": [
      ["Jan", "+2.4%", "-1.2%"],
      ["Feb", "-0.8%", "-3.7%"],
      ["Mar", "+5.1%", "0.0%"]
    ],
    "footer": ["Total", "+6.7%", "-3.7%"]
  }
}
```

---

### ✅ `data-risk_meter`
**Purpose:** Render risk indicator gauge
```json
{
  "type": "data-risk_meter",
  "data": {
    "level": 3,
    "max_level": 5,
    "label": "Portfolio Risk",
    "description": "Moderate volatility"
  }
}
```

---

### ✅ `data-progress_bar`
**Purpose:** Render progress indicator
```json
{
  "type": "data-progress_bar",
  "data": {
    "label": "Backtest Progress",
    "value": 0.72,
    "status": "running"
  }
}
```

**Status values:** `pending`, `running`, `complete`, `failed`

---

### ✅ `data-alert`
**Purpose:** Render alert banner
```json
{
  "type": "data-alert",
  "data": {
    "severity": "warning",
    "title": "Drawdown Warning",
    "message": "Strategy exceeded 5% maximum drawdown threshold"
  }
}
```

**Severity values:** `info`, `success`, `warning`, `error`

---

## **🔹 SwiftUI Rendering Rules**

1.  **Event Ordering:**
    - Events are guaranteed to arrive in the order they are generated
    - Render events in arrival sequence
    - Subsequent events can update existing UI components

2.  **Positioning:**
    - All `data-*` events render **inline** in the message stream
    - Events appear exactly where they are inserted in the text flow
    - Text continues to stream above and below UI cards

3.  **Animation Timing:**
    - All cards have 0.3s ease-in entrance animation
    - File cards have extra bounce effect
    - Progress bars animate smoothly from previous value

4.  **Styling:**
    - All cards use consistent corner radius: 12pt
    - All cards use standard shadow
    - Brand color: `#FEC00F` for all positive/primary elements
    - Dark mode support automatic

---

## **🔹 Event State Machine**

```
User Request →
  ├─ start
  ├─ data-skill_execution (skill_start)
  ├─ text-start
  ├─ text-delta (repeated)
  ├─ text-end
  ├─ [data-chart, data-table, data-metric_card, etc.]
  ├─ data-file_download (if file generated)
  ├─ data-skill_execution (skill_complete)
  └─ finish
```

---

## **🔹 Swift Implementation Pattern**

```swift
protocol GenUIComponent {
    init(from data: [String: Any])
    func makeView() -> AnyView
}

struct GenUIFactory {
    static func component(for event: StreamEvent) -> GenUIComponent? {
        switch event.type {
        case "data-file_download": return FileDownloadCard(data: event.data)
        case "data-chart": return ChartCard(data: event.data)
        case "data-metric_card": return MetricCard(data: event.data)
        case "data-table": return DataTableCard(data: event.data)
        case "data-risk_meter": return RiskMeterCard(data: event.data)
        case "data-progress_bar": return ProgressBarCard(data: event.data)
        case "data-alert": return AlertCard(data: event.data)
        case "data-skill_execution": 
            if event.data["type"] == "skill_start" {
                return SkillExecutionCard(data: event.data)
            }
            return nil
        default:
            return nil
        }
    }
}
```

---

## **🔹 Production Status**

✅ All events documented here are already implemented on backend  
✅ All existing skills emit these events  
✅ This protocol is frozen - no breaking changes will be made  
✅ New event types will be added in backwards compatible way  
✅ All events are fully type-safe

---

## **🔹 Reference Cheat Sheet**

| Event Type | SwiftUI Component | Animation |
|------------|-------------------|-----------|
| `data-file_download` | FileDownloadCard | Bounce |
| `data-skill_execution` | SkillExecutionCard | Slide in |
| `data-chart` | ChartCard | Fade in |
| `data-metric_card` | MetricCard | Pop |
| `data-table` | DataTableCard | Fade in |
| `data-risk_meter` | RiskMeterCard | Animate gauge |
| `data-progress_bar` | ProgressBarCard | Smooth animate |
| `data-alert` | AlertCard | Slide down |

This is the complete list of all GenUI elements currently supported by the backend. Every element can be mapped 1:1 directly to a SwiftUI Card component.