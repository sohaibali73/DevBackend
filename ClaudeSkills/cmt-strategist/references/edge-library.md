# Edge Library — palette for inventing strategies

Use this to span genuinely different edge families in idea-menu mode and to
build non-obvious systems. Each family lists the *mechanism* (why an edge could
exist) and *seed ideas*. Combine orthogonal families for ensembles — that's
often where the high-MAR, low-drawdown systems live, because uncorrelated edges
smooth the equity curve.

## 1. Trend / momentum (building block — give it a twist)
- Mechanism: under-reaction to information, herding, risk-premium harvesting.
- Beyond textbook: dual-timeframe agreement; trend *only when volatility is
  expanding*; momentum gated by breadth confirmation; time-series momentum with
  a volatility-target overlay; "trend of trends" across a basket.

## 2. Mean reversion (building block — give it a twist)
- Mechanism: liquidity provision, overreaction, short-term order-flow imbalance.
- Beyond textbook: reversion *only inside an established uptrend* (buy-the-dip
  with a 200-day filter); z-score of price vs a band, scaled by ATR; reversion
  conditioned on a panic-breadth or VIX-spike trigger; close-vs-open intraday
  reversion on indexes.

## 3. Volatility regime
- Mechanism: volatility clusters and is more forecastable than direction; risk
  premia differ by regime.
- Seed: trade trend in low-vol regimes and reversion in high-vol regimes
  (regime switch on realized vol percentile or VIX term structure); volatility
  breakout (NR7 / inside-day / ATR expansion); "buy when VIX > N and falling."

## 4. Breadth / market internals
- Mechanism: the average stock leads/confirms the cap-weighted index; thrusts
  mark durable lows.
- Seed: advance/decline thrust signals (Zweig breadth thrust, % above 200-day),
  new-high/new-low diffusion, McClellan oscillator regime filter as a *gate* on
  a long-only index system.

## 5. Intermarket & term structure
- Mechanism: cross-asset lead/lag, roll yield, carry, real structural linkages.
- Seed: bonds/stocks risk-on-off filter; copper or credit spreads as a growth
  gate; futures **roll yield / backwardation-contango** as a long/short signal
  (especially commodities); yield-curve slope regime for equity timing.

## 6. Seasonality / calendar
- Mechanism: structural flows (payrolls, dividends, tax, rebalancing), behavioral
  calendar effects.
- Seed: turn-of-month effect, day-of-week, "sell in May" overlay, pre-holiday
  drift, FOMC-day / pre-announcement drift, end-of-quarter window dressing. Best
  as a *filter or tilt*, not a standalone system.

## 7. Sentiment & positioning
- Mechanism: crowding and capitulation create mean-reverting extremes.
- Seed: **COT** (Commitments of Traders) commercial-vs-speculator extremes on
  futures; put/call ratio extremes; AAII / fund-flow extremes as contrarian
  gates; VIX term-structure inversion as fear signal.

## 8. Cycles & time-based
- Mechanism: dominant cycles, presidential/seasonal cycles, periodicity.
- Seed: detrended price oscillator phase, Hurst-exponent regime detection
  (trending vs mean-reverting), spectral/dominant-cycle length to set adaptive
  lookbacks. Treat cycle claims skeptically — easy to overfit.

## 9. Relative strength / rotation
- Mechanism: momentum persists cross-sectionally; capital chases leaders.
- Seed: rank a basket (sectors, index futures, country ETFs) by N-month return
  and hold top-k, rebalanced monthly; dual-momentum (absolute + relative) with a
  cash/bond defensive switch to cap drawdown.

## 10. Statistical / microstructure
- Mechanism: short-horizon inefficiencies, gaps, opening-range dynamics.
- Seed: gap-fade / gap-continuation on indexes conditioned by prior-day range;
  opening-range breakout (where applicable); z-score pairs/spread reversion on
  cointegrated futures; first-hour vs last-hour close behavior.

## 11. Ensembles & regime-switching (where MAR is won)
- Mechanism: combining *orthogonal* edges reduces drawdown more than it reduces
  return, lifting CAR/MaxDD.
- Seed: vote/weight a trend sleeve + a reversion sleeve + a breadth gate;
  switch strategy by detected regime (vol percentile, Hurst, curve slope);
  volatility-target the *portfolio* of sleeves to hold MaxDD near a budget.

## Inventing a fresh edge — checklist
1. Name a *real* market participant whose behavior or constraint creates the
   inefficiency (forced sellers, hedgers, index funds, leveraged ETFs, options
   dealers' gamma).
2. State the timescale of that behavior → sets your lookback.
3. Find the cleanest mechanical proxy for it in price/volume/breadth/positioning.
4. Add a regime gate so you only trade when the edge should be present.
5. Define how it *decays or crowds out* — that's your kill-switch and your
   robustness test target.
