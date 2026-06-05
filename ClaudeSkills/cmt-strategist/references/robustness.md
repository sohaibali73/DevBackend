# Robustness & Anti-Overfit Checklist

Cite the relevant items in every dossier's "Robustness & anti-overfit plan"
section. The goal is a system whose edge survives outside the exact data it was
built on. A modest, stable edge beats a spectacular fragile one.

## Design-time discipline
- **Minimize parameters.** Every free parameter is a chance to overfit. Justify
  each one by the thesis.
- **Prefer plateaus, not peaks.** A good parameter has *good neighbors*. If
  performance collapses one notch away from the chosen value, it's fit.
- **Round, defensible values** (10/20/50/100/200) over oddly specific ones.
- **Volatility-scaled** thresholds/stops so the system is unit-free across
  markets and eras.

## Validation tests to specify
- **In-sample / out-of-sample split** (e.g. build on first 60–70%, validate on
  the rest, untouched).
- **Walk-forward analysis** — re-optimize on a rolling window, trade the next
  window; report only the stitched out-of-sample equity.
- **Parameter sensitivity / heatmap** — performance should vary smoothly; report
  the surface, not the single best cell.
- **Cross-market / cross-instrument** — does the same logic work on related
  indexes or futures without re-tuning? Real edges generalize.
- **Sub-period stability** — bull, bear, chop, and high/low-vol regimes
  separately. Look for an edge that's *positive-ish everywhere*, not one decade
  carrying the record.
- **Monte Carlo** — randomize trade order / bootstrap returns to get a
  *distribution* of MaxDD and CAR, not a single path. Plan position sizing
  against the worst-case MaxDD, not the historical one.
- **Trade count** — enough trades for statistical meaning (rule of thumb: 100+
  for a discretionary-light system; more for higher-frequency).

## Realism / bias guards
- **Costs & slippage** — model commissions and realistic slippage; many "edges"
  die here, especially higher-frequency or wide-stop systems.
- **Look-ahead bias** — every input must be known at the decision bar. Watch
  same-bar close used for both signal and fill, restated fundamentals, and
  future-anchored indicators.
- **Survivorship bias** — use indexes / continuous futures with proper history;
  beware tested-on-current-constituents stock baskets.
- **Back-adjustment artifacts** — continuous futures can show false absolute
  price levels (even negatives); prefer percent/ratio-based logic or
  volatility-scaled rules; respect roll dates.
- **Data-mining bias** — if you tried N ideas to find this one, the best one is
  upward-biased; haircut expectations and demand out-of-sample confirmation.

## Decision rule of thumb
Trust a system in proportion to: stable parameter plateaus × out-of-sample
holding up × working across markets × surviving costs × a believable thesis.
Weakness in any one is a yellow flag; weakness in the thesis *plus* a single
narrow optimum is a red flag.
