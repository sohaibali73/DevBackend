# Optuma Scripting Functions — Full A–Z Reference

Source: https://www.optuma.com/kb/optuma/scripting/optuma-scripting-functions-table

---

## A

| Function | Name | Notes |
|---|---|---|
| `ABS` | Absolute Value | Forces output to positive number |
| `ACC` | Accumulate | Sum values over period (like SUM) |
| `ACCB` | Acceleration Bands | Price Headley; 20-bar default |
| `ACCSINCESIGNAL(V1, V2)` | Accumulate Since Signal | Accumulate V1, reset on V2 boolean |
| `ADL` | Accumulation/Distribution Line | Volume/price interaction; divergence tool |
| `ADX(BARS=14)` | Avg Directional Movement Index | Trend strength; includes +DI, -DI |
| `ALPHA` | Alpha | Performance vs benchmark |
| `AMA` | Adaptive Moving Average | Kaufman; dynamic 2–30 period |
| `ARCCOS` / `ARCSIN` / `ARCTAN` | Inverse trig | Standard math |
| `AROON(BARS=25)` | Aroon | 0–100; Tushar Chande 1995 |
| `AROONOSC` | Aroon Oscillator | Aroon Up minus Aroon Down |
| `ARR` | Annual Rate of Return | User-defined period |
| `ATR(BARS=14)` | Average True Range | Volatility measure; Wilder |
| `ATRTSCAN` | ATR Trailing Stop Scan | Scan version of ATR trailing stop |
| `AUTOCORR` | Auto Correlation | Repeating pattern detection |
| `AVWAP` | Anchored VWAP | Anchored to specific bar; Brian Shannon |

## B

| Function | Name | Notes |
|---|---|---|
| `BARCOUNT` | Bar Count | Average of all bars loaded |
| `BARDATE` | Bar Date | Date as integer (e.g. 42902) |
| `BARSTRUE(BARS=10)` | Bars True | Count of true bars in lookback |
| `BARTYPES` | Bar Types | Inside Bar, Outside Bar, Higher High, etc. |
| `BB(BARS=20, MULT=2)` | Bollinger Bands | ±std dev bands around MA |
| `BBW` | Bollinger Bandwidth | Width as % of midband; squeeze detection |
| `BETA` | Beta Coefficient | Volatility vs market |
| `BPB` | Bollinger %B | Price position within bands; can exceed 0–100 |
| `BREADTHDATA` | Breadth Data | Index advance/decline data |

## C

| Function | Name | Notes |
|---|---|---|
| `CAD` | Chaikin A/D Line | Cumulative money flow |
| `CANDLESTICKPATTERN` | Candlestick Pattern | Bullish Engulfing, Doji, Hammer, etc. |
| `CCI(BARS=20)` | Commodity Channel Index | Distance from statistical mean |
| `CHANGE(BARS=1)` | Percentage Change | % change over N bars |
| `CHANGESINCESIGNAL(V1)` | Change Since Signal | Price change since V1 triggered |
| `CHARTPATTERN` | Chart Pattern | AB=CD, Gartley, Head & Shoulders, etc. |
| `CHOPPINESSINDEX` | Choppiness Index | Dreiss; trending (<31.8) vs choppy (>61.8) |
| `CHST` | Chandelier Stop | ATR trailing stop; Le Beau |
| `CI` | Composite Index | Constance Brown proprietary |
| `CLOSE()` | Close | Closing price |
| `CMF(BARS=21)` | Chaikin Money Flow | Buying/selling pressure ±1 |
| `COI` | Coppock Indicator | Long-term buy signals |
| `CORREL(CODE="$SPX", BARS=50)` | Pearson Correlation | Relationship to comparison code |
| `COSC` | Chaikin Oscillator | MACD of AD Line |
| `COTDATA` | COT Report | CFTC commitments of traders |
| `COUNTMATCH` | Count Match | True count in lookback (default 15) |
| `COUNTMATCHSINCESIGNAL(V1,V2)` | Count Match Since Signal | How many times V2 occurred since V1 |

## D

| Function | Name | Notes |
|---|---|---|
| `DARVASBOXSCAN` | Darvas Box Scan | Box breakout detection |
| `DATAFIELD` | External Data Field | Bloomberg EDFs, Fundamental data, Excel |
| `DATATOLOAD` | Data To Load | Limit historical data for calculation |
| `DAY` | Daily Data | Force daily timeframe override |
| `DAYNUM` | Day Number | Day of month integer (1–31) |
| `DAYOFWEEK` | Day of Week | Sun=1, Mon=2 … Sat=7 |
| `DD` | Days Down | Consecutive down days count |
| `DONCH(BARS=20)` | Donchian Channel | Highest high / lowest low channel |
| `DRAWDOWNSTOP` | Drawdown Trailing Stop | Hull; trailing % below highest close |
| `DU` | Days Up | Consecutive up days count |

## E

| Function | Name | Notes |
|---|---|---|
| `EXP` | Exponential | e^x math function |

## F

| Function | Name | Notes |
|---|---|---|
| `FI` | Force Index | Price change × volume |
| `FIRST(V1)` | First Value | Returns only the first value of V1 |
| `FLOOR(V1)` | Floor | Round down |
| `FO` | Forecast Oscillator | Price vs Time Series Forecast % |
| `FOURIER` | Fourier Wave | Dominant cycle analysis |
| `FT` | Fisher Transform | Pinpoints price extremes |

## G

| Function | Name | Notes |
|---|---|---|
| `GANNSWING` | Gann Swing | Swing Start, Swing End, etc. |
| `GETDATA("CODE", FIELD=Close)` | GetData | Pull data from any instrument code |

## H

| Function | Name | Notes |
|---|---|---|
| `HAC` | Heikin-Ashi Candles | Convert to Heikin-Ashi values |
| `HIGH()` | High | High price |
| `HIGHESTHIGH(BARS=52)` | Highest High | Highest value over N bars |
| `HIGHESTSINCE(V1, V2)` | Highest Since Signal | Highest of V1 after V2 triggers |
| `HMA(BARS=20)` | Hull Moving Average | Alan Hull weighted MA |
| `HV(BARS=30)` | Historical Volatility | Std dev of log returns |
| `HVB` | Historical Volatility Bands | HV + delta bands |

## I

| Function | Name | Notes |
|---|---|---|
| `ICHIMOKUCLOUD` | Ichimoku Cloud | Full Ichimoku system |
| `IF(cond, true, false)` | If | Conditional logic |
| `INDEX(FIELD=Close)` | Index | Charts underlying primary index data |
| `INV` | Inverse | Invert a plot's value |
| `ISMEMBER("$SPX")` | Is Member | True if in selected index |
| `ISTICKER("AAPL")` | Is Ticker | True if source matches code |

## K

| Function | Name | Notes |
|---|---|---|
| `KC(BARS=20, MULT=1.5)` | Keltner Channel | ATR-based bands |
| `KST` | Pring Know Sure Thing | Multi-timeframe momentum |

## L

| Function | Name | Notes |
|---|---|---|
| `LAST(V1)` | Last Value | Only the last value of V1 |
| `LN` | Natural Log | Logarithm base e |
| `LOG` | Log 10 | Logarithm base 10 |
| `LOW()` | Low | Low price |
| `LOWESTLOW(BARS=52)` | Lowest Low | Lowest value over N bars |
| `LOWESTSINCE(V1, V2)` | Lowest Since Signal | Lowest of V1 after V2 triggers |
| `LRINT` | Linear Regression Intercept | Best-fit line intercept |
| `LRSLOPE` | Linear Regression Slope | Normalized slope histogram |
| `LRVAL(BARS=20)` | Linear Regression Value | Correlation around regression line |

## M

| Function | Name | Notes |
|---|---|---|
| `MA(BARS=20, STYLE=Exponential, CALC=Close)` | Moving Average | Simple (default), Exponential, Weighted, Hull |
| `MACD(FAST=12, SLOW=26, SIGNAL=9)` | MACD | MA convergence/divergence histogram |
| `MAX(V1, V2)` | Maximum | Higher of two values |
| `MFI(BARS=14)` | Money Flow Index | RSI using volume |
| `MIN(V1, V2)` | Minimum | Lower of two values |
| `MINUTE` | Minute Data | Intraday timeframe override |
| `MOD(V1, N)` | Modulo | Remainder of V1 ÷ N |
| `MOMENTUM(BARS=12)` | Momentum | Price momentum |
| `MONTH` | Monthly Data | Monthly timeframe override |
| `MONTHNUM` | Month Number | 1 (Jan) – 12 (Dec) |
| `MVWAP(BARS=20)` | Moving VWAP | Averaged VWAP over N periods |

## N

| Function | Name | Notes |
|---|---|---|
| `NEARESTALERT` | Nearest Alert | Proximity to nearest alert level |
| `NLRSX` | NonLag Inverse Fisher RSX | ±1 oscillator; extremes at ±0.9 |
| `NONZERO(V1)` | Non-Zero | True when V1 ≠ 0 |
| `NOREPEAT(V1, BARS=5)` | No Repeat | Suppress signal for N bars after trigger |
| `NOT` | Not | Boolean negation |

## O

| Function | Name | Notes |
|---|---|---|
| `OBV` | On-Balance Volume | Cumulative volume direction |
| `OBVP` | On-Balance Volume % | OBV as percentage |
| `OFFSET(V1, BARS=1)` | Offset | Shift plot N bars (positive=forward) |
| `OI` | Open Interest | Futures/options open contracts |
| `OPEN()` | Open | Opening price |
| `OSC(FAST=10, SLOW=30)` | Oscillator | Difference between two MAs |

## P

| Function | Name | Notes |
|---|---|---|
| `PARENT` | Parent | Source data of the applied tool |
| `PEAKTROUGH` | Peak Trough | True when peak or trough formed |
| `PERCENTSWING(PCT=5)` | Percent Swing | Swing chart by % reversal |
| `PERFORMANCE(BARS=20)` | Performance | % move over N bars |
| `PIVOTS` | Pivots | Standard/Fibonacci/Camarilla pivot points |
| `PSAR` | Parabolic SAR | Wilder trailing stop |
| `PREVIOUS` | Previous | Prior bar value of current script |
| `PRICEATSIGNAL(V1)` | Price At Signal | Close when V1 triggered |

## Q

| Function | Name | Notes |
|---|---|---|
| `QQE` | Quantitative Qualitative Estimation | Smoothed RSI with trigger lines |
| `QUARTERNUM` | Quarter Number | 1–4 |

## R

| Function | Name | Notes |
|---|---|---|
| `RATCHET(V1)` | Ratchet | Plot only moves in one direction (for stops) |
| `RFE(BACKTYPE=Months, BARS=6, DEFAULT=High)` | Range From Extremes | % / std dev from N-period high or low |
| `RIC(CODE="$SPX")` | Relative Index Comparison | Relative strength vs index |
| `ROC(BARS=12)` | Rate of Change | Momentum as % |
| `ROUND(V1, DECIMALS=2)` | Round | Round to N decimal places |
| `RSI(BARS=14)` | RSI | 0–100 momentum oscillator; Wilder |
| `RV` | Relative Volatility | True when short ATR > long ATR |
| `RVI` | Relative Vigor Index | Close vs range momentum |

## S

| Function | Name | Notes |
|---|---|---|
| `SCRIPT("Name")` | Script Function | Reference saved script by name |
| `SECURITY` | Security | Primary security of chart |
| `SELF` | Self | Script references its own previous value |
| `SIGNALAFTER(V2, V1)` | Signal After | V2 only fires after V1 has fired |
| `SMI(BARS=14)` | Stochastic Momentum Index | Midpoint-relative stochastic |
| `SQRT(V1)` | Square Root | Standard math |
| `STD(V1, BARS=20, MULT=1)` | Standard Deviation | Statistical volatility |
| `STLB(BARS=20)` | Stoller Bands | ATR-based MA bands; Manning Stoller |
| `STOCH(BARS=14)` | Stochastic | Slow %K and %D |
| `STOCHSCAN` | Stochastic Scan | %K cross %D etc. |
| `SWITCH(V1, HIGH=70, LOW=30)` | Switch | Hysteresis latch; overbought/oversold |
| `SWINGDOWN` / `SWINGUP` | Swing Direction | 1 when swing is in that direction |
| `SWINGEND` / `SWINGSTART` | Swing Points | Value at swing start/end |
| `SWINGSTAT` | Swing Statistics | Std dev / mean of swing history |

## T

| Function | Name | Notes |
|---|---|---|
| `TIMESINCESIGNAL(V1)` | Time Since Signal | Bars/days/weeks since V1 last true |
| `TO` | Turn Over | Dollar volume |
| `TRET` | Total Return | Price + dividends total return data |
| `TRIX(BARS=14)` | TRIX | Triple-smoothed momentum oscillator |
| `TROC` | True Rate of Change | Absolute price move per bar |
| `TRUERANGE()` | True Range | Max of (H-L), (H-Cp), (L-Cp); unsmoothed |
| `TSI` | True Strength Index | Double-EMA momentum; 25/13/7 default |

## U

| Function | Name | Notes |
|---|---|---|
| `UO(BARS1=7, BARS2=14, BARS3=28)` | Ultimate Oscillator | Larry Williams; three timeframes |

## V

| Function | Name | Notes |
|---|---|---|
| `VALUEWHEN(V1, V2)` | Value When Signal | Value of V2 at last V1 trigger |
| `VERGENCE(V1, V2)` | Vergence | Divergence or convergence detection |
| `VOL()` / `VOLUME()` | Volume | Bar volume |
| `VPCI` | Volume Price Confirmation | Buff Dormeier; price/volume validation |
| `VTS` | Volatility Trailing Stop | ATR-based trailing stop |
| `VWAP` | VWAP | Intraday volume-weighted average price |
| `VWMA(BARS=20)` | Volume Weighted MA | Volume-adjusted moving average |

## W

| Function | Name | Notes |
|---|---|---|
| `WEEK` | Weekly Data | Weekly timeframe override |
| `WITHINRANGE(V1, PCT=5)` | Within Range | True if within N% of V1 |
| `WR(BARS=14)` | Williams %R | Overbought/oversold ±100 scale |
| `WVS` | Wilder Volatility Stop | ATR trailing stop; Wilder |

## Y

| Function | Name | Notes |
|---|---|---|
| `YEAR` | Yearly Data | Yearly timeframe override |
| `YEARNUM` | Year Number | Year as integer |

## Z

| Function | Name | Notes |
|---|---|---|
| `ZSCORE(BARS=20)` | Z-Score | Standard deviations from mean |
