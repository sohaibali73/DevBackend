# Performance Card — Frontend Integration Guide

A guide for the frontend team to (1) render a premium GenUI card for the
`calculate_performance` tool, and (2) make sure the backend always invokes
the tool whenever a performance/risk metric is requested.

---

## 1. What the backend emits

### 1.1 Tool result (raw)

When the agent calls the `calculate_performance` tool, the backend returns
this JSON inside the standard `tool_result` event:

```json
{
  "status": "ok",
  "success": true,
  "tool": "calculate_performance",
  "ticker": "SPY",
  "frequency": "daily",
  "meta": {
    "start_date": "1993-01-29",
    "end_date": "2026-05-13",
    "bars": 8379,
    "start_price": 24.18,
    "end_price": 743.18,
    "initial_capital": 100000,
    "years": 33.31
  },
  "returns": {
    "annual_return_pct": 10.83,
    "total_return_pct": 2974.12,
    "net_profit_usd": 2974118.6,
    "net_profit_pct": 2974.12,
    "final_equity_usd": 3074118.6,
    "exposure_pct": 100,
    "risk_adj_return_pct": 10.83
  },
  "drawdown": {
    "max_system_drawdown_pct": -55.19,
    "max_system_drawdown_usd": 253750.13,
    "peak_date": "2007-10-09",
    "trough_date": "2009-03-09",
    "recovery_date": "2012-08-16",
    "dd_duration_days": 517,
    "recovery_bars": 869
  },
  "risk_ratios": {
    "net_risk_adj_return": 53.89,
    "recovery_factor": 11.72,
    "car_maxdd": 0.20,
    "rar_maxdd": 0.20
  },
  "statistics": {
    "ann_volatility_pct": 18.59,
    "sharpe_ratio": 0.58,
    "risk_reward_ratio": 0.58,
    "std_error_pct": 24.93,
    "k_ratio": 0.035
  },
  "ulcer": {
    "ulcer_index": 14.50,
    "ulcer_performance_index": 0.75
  },
  "trade_stats": {
    "avg_win_pct": 3.46,
    "avg_loss_pct": -3.45,
    "win_loss_ratio": 1.01,
    "win_rate_pct": 63.57,
    "profit_factor": 1.75
  }
}
```

### 1.2 GenUI card envelope

The system prompt also instructs Claude to emit a single-line JSON card
envelope at the start of its assistant message. Your existing GenUI parser
that handles `data-card_stock`, `data-card_weather`, etc. should also match
`data-card_performance`:

```json
{"type":"data-card_performance","data":{
  "ticker":"SPY","frequency":"daily",
  "start_date":"1993-01-29","end_date":"2026-05-13","years":33.31,
  "start_price":24.18,"end_price":743.18,
  "annual_return_pct":10.83,"total_return_pct":2974.12,
  "net_profit_usd":2974118.6,"final_equity_usd":3074118.6,
  "max_drawdown_pct":-55.19,"max_drawdown_usd":253750.13,
  "peak_date":"2007-10-09","trough_date":"2009-03-09","recovery_date":"2012-08-16",
  "dd_duration_days":517,
  "sharpe_ratio":0.58,"ann_volatility_pct":18.59,
  "recovery_factor":11.72,"car_maxdd":0.20,"rar_maxdd":0.20,
  "ulcer_index":14.50,"ulcer_performance_index":0.75,"k_ratio":0.035,
  "win_rate_pct":63.57,"profit_factor":1.75,"win_loss_ratio":1.01,
  "avg_win_pct":3.46,"avg_loss_pct":-3.45,
  "initial_capital":100000,
  "summary":"SPY returned 10.83% CAGR over 33 years with a -55.2% max drawdown."
}}
```

You can render the card from EITHER the raw tool result OR the GenUI
envelope. Recommendation: render from the **tool result** (richer, always
present, no parsing risk) and use the envelope only as a hint that a card
should appear.

---

## 2. Card UI spec (Potomac brand)

Use Potomac yellow `#FEC00F` and dark-gray `#212121` as the brand palette.
Numbers come from the tool result verbatim — DO NOT recompute, DO NOT round
beyond display.

### 2.1 Layout (16:9 card, ~640px wide)

```
┌────────────────────────────────────────────────────────────────────┐
│  SPY · S&P 500 ETF                    daily · since 1993-01-29     │  ← header bar
│  Performance Engine · live yfinance data                           │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   +10.83%        +2,974.12%       $2,974,119                       │  ← HERO row
│   CAGR           Total Return     Net Profit                       │
│                                                                    │
├──────────────────────┬─────────────────────────────────────────────┤
│  RISK                │  RATIOS                                     │
│  Max Drawdown        │  Sharpe Ratio            0.58               │
│   -55.19%            │  Recovery Factor         11.72              │
│   $253,750           │  CAR / MaxDD (MAR)       0.20               │
│  Peak  2007-10-09    │  Ulcer Index             14.50              │
│  Trough 2009-03-09   │  UPI                     0.75               │
│  Recovery 2012-08-16 │  K-Ratio                 0.035              │
│  Duration 517 days   │  Volatility (ann)        18.59%             │
├──────────────────────┴─────────────────────────────────────────────┤
│  TRADE STATS (monthly roll-up)                                     │
│  Win Rate 63.6%    Profit Factor 1.75    W/L 1.01                  │
│  Avg Win +3.46%    Avg Loss -3.45%                                 │
├────────────────────────────────────────────────────────────────────┤
│  SPY returned 10.83% CAGR over 33 years with a -55.2% max drawdown.│  ← summary line
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Visual rules

- **Hero numbers** — Rajdhani / display font, 32–40px, bold. Positive returns
  in green (`#22C55E`), negative in red (`#EB2F5C`), neutral in yellow.
- **Headers** — `RISK`, `RATIOS`, `TRADE STATS` in uppercase Rajdhani 11px
  with yellow underline.
- **Body** — Quicksand / sans-serif 14px, dark-gray.
- **Drawdown date strip** — small monospace, gray, with subtle yellow
  underline.
- **Rounding for display only** — % to 2dp, ratios to 2dp, K-Ratio to 4dp,
  dollars with thousands separator.
- **Null handling** — if a metric is `null`, show `—` (em dash), never `0`.

### 2.3 Optional: equity curve sparkline

If you want to add a tiny chart, fetch the price series client-side from your
existing `get_stock_chart` flow or extend the engine to return the equity
curve. Not required for v1.

---

## 3. Minimal React/TSX implementation

```tsx
// components/cards/PerformanceCard.tsx
import { motion } from "framer-motion";

const YELLOW = "#FEC00F";
const DARK   = "#212121";
const GREEN  = "#22C55E";
const RED    = "#EB2F5C";

interface PerformanceData {
  ticker: string;
  frequency: string;
  meta:    any;
  returns: any;
  drawdown: any;
  risk_ratios: any;
  statistics: any;
  ulcer: any;
  trade_stats: any;
}

const fmtPct  = (v: number | null, dp = 2) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}%`;
const fmtUSD  = (v: number | null) =>
  v == null ? "—" : `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const fmtNum  = (v: number | null, dp = 2) =>
  v == null ? "—" : v.toFixed(dp);

const colorFor = (v: number | null) =>
  v == null ? DARK : v > 0 ? GREEN : v < 0 ? RED : DARK;

export function PerformanceCard({ data }: { data: PerformanceData }) {
  const m = data.meta, r = data.returns, d = data.drawdown;
  const s = data.statistics, u = data.ulcer, t = data.trade_stats;
  const rr = data.risk_ratios;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border border-gray-200 bg-white shadow-md overflow-hidden"
      style={{ maxWidth: 720 }}
    >
      {/* Header bar */}
      <div className="px-5 py-3 flex justify-between items-baseline"
           style={{ background: DARK, color: "white" }}>
        <div>
          <div className="text-lg font-bold tracking-wide">{data.ticker}</div>
          <div className="text-xs opacity-70">
            Performance Engine · live yfinance · {data.frequency} bars · since {m.start_date}
          </div>
        </div>
        <div className="text-xs opacity-80">
          {m.years?.toFixed(1)} yrs · {m.bars} bars
        </div>
      </div>

      {/* Hero metrics */}
      <div className="grid grid-cols-3 gap-3 px-5 py-5 border-b border-gray-100">
        <Hero label="CAGR"        value={fmtPct(r.annual_return_pct)}    color={colorFor(r.annual_return_pct)}/>
        <Hero label="Total Return" value={fmtPct(r.total_return_pct)}    color={colorFor(r.total_return_pct)}/>
        <Hero label="Net Profit"  value={fmtUSD(r.net_profit_usd)}        color={colorFor(r.net_profit_usd)}/>
      </div>

      {/* Risk + Ratios grid */}
      <div className="grid grid-cols-2 gap-0 border-b border-gray-100">
        <Section title="Risk">
          <Row k="Max Drawdown" v={
            <span style={{ color: RED }}>
              {fmtPct(d.max_system_drawdown_pct)} · {fmtUSD(d.max_system_drawdown_usd)}
            </span>
          }/>
          <Row k="Peak"        v={d.peak_date || "—"}/>
          <Row k="Trough"      v={d.trough_date || "—"}/>
          <Row k="Recovery"    v={d.recovery_date || "Not yet recovered"}/>
          <Row k="Duration"    v={d.dd_duration_days != null ? `${d.dd_duration_days} days` : "—"}/>
        </Section>

        <Section title="Ratios" leftBorder>
          <Row k="Sharpe"           v={fmtNum(s.sharpe_ratio)}/>
          <Row k="Volatility (ann)" v={fmtPct(s.ann_volatility_pct)}/>
          <Row k="Recovery Factor"  v={fmtNum(rr.recovery_factor)}/>
          <Row k="CAR / MaxDD"      v={fmtNum(rr.car_maxdd)}/>
          <Row k="Ulcer Index"      v={fmtNum(u.ulcer_index)}/>
          <Row k="UPI"              v={fmtNum(u.ulcer_performance_index)}/>
          <Row k="K-Ratio"          v={fmtNum(s.k_ratio, 4)}/>
        </Section>
      </div>

      {/* Trade stats */}
      <div className="px-5 py-3 grid grid-cols-5 gap-2 text-sm border-b border-gray-100">
        <Tile k="Win Rate"      v={fmtPct(t.win_rate_pct, 1)}/>
        <Tile k="Profit Factor" v={fmtNum(t.profit_factor)}/>
        <Tile k="W/L Ratio"     v={fmtNum(t.win_loss_ratio)}/>
        <Tile k="Avg Win"       v={fmtPct(t.avg_win_pct)} color={GREEN}/>
        <Tile k="Avg Loss"      v={fmtPct(t.avg_loss_pct)} color={RED}/>
      </div>

      {/* Footer summary */}
      <div className="px-5 py-3 text-sm text-gray-700"
           style={{ borderTop: `2px solid ${YELLOW}` }}>
        {data.ticker} returned {fmtPct(r.annual_return_pct)} CAGR over{" "}
        {m.years?.toFixed(1)} years with a {fmtPct(d.max_system_drawdown_pct)} max drawdown.
      </div>
    </motion.div>
  );
}

const Hero = ({ label, value, color }: any) => (
  <div className="text-center">
    <div className="text-3xl font-bold" style={{ color, fontFamily: "Rajdhani" }}>
      {value}
    </div>
    <div className="text-[10px] uppercase tracking-widest text-gray-500 mt-1">{label}</div>
  </div>
);

const Section = ({ title, leftBorder, children }: any) => (
  <div className={`p-5 ${leftBorder ? "border-l border-gray-100" : ""}`}>
    <div className="text-[10px] uppercase tracking-widest font-bold mb-2"
         style={{ color: DARK, borderBottom: `2px solid ${YELLOW}`, paddingBottom: 4, display: "inline-block" }}>
      {title}
    </div>
    {children}
  </div>
);

const Row = ({ k, v }: any) => (
  <div className="flex justify-between text-sm py-1">
    <span className="text-gray-500">{k}</span>
    <span className="font-mono">{v}</span>
  </div>
);

const Tile = ({ k, v, color }: any) => (
  <div className="text-center">
    <div className="text-base font-bold" style={{ color: color || DARK }}>{v}</div>
    <div className="text-[10px] uppercase text-gray-500">{k}</div>
  </div>
);
```

### 3.1 Router patch

Wherever your GenUI router dispatches card types, add:

```tsx
// In your CardRouter / ToolResultRenderer
switch (toolName) {
  // ...
  case "calculate_performance":
    return <PerformanceCard data={toolResult} />;
}

// AND in your card-envelope renderer:
switch (envelope.type) {
  // ...
  case "data-card_performance":
    return <PerformanceCard data={envelope.data} />;
}
```

---

## 4. Always-invoke enforcement (frontend role)

The backend already forces invocation in three layers:

1. **Tool always loaded** — `TOOL_SEARCH_NON_DEFERRED` includes
   `calculate_performance`, so it is never hidden behind tool-search.
2. **System prompt** — `core/prompts/base.py` marks it MANDATORY at the top
   of the MARKET / TRADING TOOLS section.
3. **GenUI schema** — instructs the model to emit a `data-card_performance`
   envelope whenever the tool runs.

The frontend can reinforce this in three additional ways:

### 4.1 Quick-action chips on the composer

Add a "Performance" chip below the chat input. When clicked, it prefills:

```
Calculate performance metrics for {ticker}
```

This nudges the user into queries that always trigger the tool.

### 4.2 Auto-invoke from ticker badges

When the user clicks a ticker badge anywhere in the chat (e.g. from a stock
card or news card), fire an automatic message:

```ts
sendMessage(`Show full performance and risk metrics for ${ticker} since inception.`);
```

The backend will then call `calculate_performance` and emit the card.

### 4.3 Detection guardrail (defence-in-depth)

If you want a belt-and-braces guardrail in case the model ever forgets,
intercept the final assistant message and check for performance keywords
without a tool call. Pseudo-logic:

```ts
const PERF_TERMS = [
  "cagr", "sharpe", "drawdown", "ulcer", "k-ratio",
  "profit factor", "win rate", "recovery factor", "mar ratio"
];

function looksLikePerformanceClaim(text: string, toolCalls: ToolCall[]): boolean {
  const lower = text.toLowerCase();
  const mentionsMetric = PERF_TERMS.some(t => lower.includes(t));
  const calledPerf = toolCalls.some(c => c.name === "calculate_performance");
  return mentionsMetric && !calledPerf;
}

// If true → show a banner: "Numbers not verified by Performance Engine.
// Refresh to recompute." with a "Recompute" button that re-sends the query
// with an explicit instruction: "Use the calculate_performance tool."
```

This is optional but recommended for institutional accuracy.

### 4.4 Telemetry

Log every `calculate_performance` invocation with `{ ticker, freq,
duration_ms }` to your analytics so you can audit:
- How often it's called
- Average response time
- Tickers that error out (Yahoo Finance occasionally throttles)

---

## 5. Error states

The engine returns `{"status":"error","error":"..."}` on failure. Render an
inline error card:

```tsx
if (toolResult.status === "error") {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
      <div className="text-sm font-bold text-red-700">
        Performance data unavailable
      </div>
      <div className="text-xs text-red-600 mt-1">{toolResult.error}</div>
      <button className="mt-2 text-xs underline text-red-700"
              onClick={() => retry()}>
        Retry
      </button>
    </div>
  );
}
```

Common error reasons:
- `No data returned for ticker 'XYZ'.` — bad symbol
- `Insufficient data for 'XYZ': only N bars available.` — newly listed
- `Data fetch failed: ...` — Yahoo Finance throttle / network

---

## 6. Acceptance checklist

- [ ] `PerformanceCard.tsx` added and exported.
- [ ] CardRouter handles both `tool_name === "calculate_performance"` AND
  `envelope.type === "data-card_performance"`.
- [ ] Hero metrics use Potomac yellow / Rajdhani / brand palette.
- [ ] Null values render as `—` not `0`.
- [ ] Negative returns/drawdowns are red, positive green.
- [ ] Drawdown date strip shows peak / trough / recovery / duration.
- [ ] Quick-action chip "Performance" added to composer.
- [ ] Ticker badge click → auto-invoke message.
- [ ] (Optional) Detection guardrail banner for unverified claims.
- [ ] Error state card implemented for `status: "error"`.
- [ ] Telemetry hook firing on every invocation.

When all boxes are checked, the model can never fabricate a performance
number that reaches the user — every figure is rendered from real
yfinance data, in a card the user immediately recognises.
