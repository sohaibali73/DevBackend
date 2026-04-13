# Frontend Stress Test Prompts — Complete Suite

Copy-paste each prompt directly into the chat UI. Tests every tool, renderer, and edge case.

---

## 🟢 TIER 1 — SANDBOX: PYTHON BASICS

### 1.1 Hello World (smoke test)
```
Run this Python code and show me the output:
print("Hello from the sandbox!")
x = 2 ** 10
print(f"2^10 = {x}")
```
**Expected:** Text output block with two lines.

---

### 1.2 Statistics (standard library, no import needed)
```
Calculate the standard deviation, mean, and median of [14, 22, 5, 8, 31, 17, 9].
Use the built-in statistics module.
```
**Expected:** Numeric output — mean ~15.1, stdev ~9.0.

---

### 1.3 Pandas DataFrame
```
Create a pandas DataFrame with 5 rows of fake sales data (product name, quantity, price).
Calculate total revenue per product. Print the result.
```
**Expected:** Formatted table output.

---

### 1.4 NumPy Math
```
Using numpy, generate 1000 random samples from a normal distribution with mean=50 and std=10.
Print the actual mean, std, min, and max of the sample.
```
**Expected:** Values close to 50 / 10.

---

### 1.5 SciPy (built-in)
```
Using scipy.stats, perform a one-sample t-test on this dataset:
[102, 98, 105, 99, 107, 101, 96, 103, 100, 104]
Test if the true mean is significantly different from 100 (alpha=0.05).
Print the t-statistic, p-value, and your conclusion.
```
**Expected:** t-statistic, p-value, interpretation.

---

### 1.6 SymPy symbolic math
```
Using sympy, solve the quadratic equation x^2 - 5x + 6 = 0.
Also factor the expression. Print the roots and factored form.
```
**Expected:** roots [2, 3], factored form (x-2)(x-3).

---

### 1.7 Rich table output
```
Using the rich library, create a formatted table of 5 world capitals with columns:
Country, Capital, Population (millions), Currency.
Print it to the console.
```
**Expected:** Rich-formatted table in text output.

---

## 🟢 TIER 1 — SANDBOX: SESSION PERSISTENCE

### 2.1 Turn 1 — Store variables
```
Store the list [10, 20, 30, 40, 50] in a variable called my_data.
Also store the string "Alice" in user_name.
Confirm what's stored.
```
**Expected:** Confirmation of saved variables.

---

### 2.2 Turn 2 — Use stored variables (same conversation)
```
Now compute the sum and average of my_data.
Also greet the user using user_name.
```
**Expected:** Uses `my_data` and `user_name` from turn 1 — no redefinition.

---

### 2.3 Turn 3 — Mutate and store
```
Add 100 to each element of my_data using a list comprehension.
Store the result in scaled_data.
Print both lists side by side.
```
**Expected:** Both `my_data` (original) and `scaled_data` (new) shown.

---

### 2.4 Turn 4 — Complex calculation using prior session
```
Now create a pandas DataFrame using scaled_data as the 'value' column.
Add a 'label' column with letters A through E.
Sort by value descending and display it.
```
**Expected:** DataFrame using `scaled_data` from turn 3.

---

## 🟢 TIER 1 — SANDBOX: CHARTS (MATPLOTLIB)

### 3.1 Sine Wave (line chart)
```
Plot a sine wave from 0 to 4π using matplotlib.
Use 500 points. Add a title "Sine Wave" and axis labels.
Show the plot.
```
**Expected:** Image artifact (PNG) with sine wave.

---

### 3.2 Revenue Bar Chart with labels
```
Create a bar chart showing monthly revenue:
Jan=12000, Feb=15000, Mar=9000, Apr=18000, May=22000, Jun=19000
Use matplotlib. Add value labels on top of each bar. Color the bars navy blue.
```
**Expected:** Image artifact with labeled bars.

---

### 3.3 Multiple figures (2 images from one run)
```
Create two matplotlib figures:
1. A histogram of 500 random normal values (mean=0, std=1)
2. A scatter plot of 100 random x,y points colored by quadrant
Call plt.show() after each.
```
**Expected:** Two separate image artifacts.

---

### 3.4 Seaborn heatmap
```
Create a 10x10 correlation matrix of random data using seaborn as a heatmap.
Use a "coolwarm" color palette. Add a title.
```
**Expected:** Image artifact — heatmap.

---

### 3.5 Three charts at once
```
Create 3 different matplotlib plots:
1. A pie chart of market share (Apple 30%, Samsung 25%, Other 45%)
2. A line chart of temperature over 24 hours (smooth sine curve)
3. A scatter plot of 200 random data points with size proportional to a third variable

Call plt.show() after each. Return all 3 charts.
```
**Expected:** Three image artifacts in the response.

---

### 3.6 Mixed output + image
```
Create a pandas DataFrame of 10 random students with name, grade, and score.
Print the top 3 students (text output).
Also plot a bar chart of all scores sorted descending (image artifact).
```
**Expected:** Text output AND image artifact in same response.

---

## 🟢 TIER 1 — SANDBOX: PLOTLY (INTERACTIVE CHARTS)

### 4.1 Plotly bar chart
```
Using plotly, create an interactive bar chart showing Q1-Q4 revenue:
Q1: 45000, Q2: 62000, Q3: 58000, Q4: 71000.
Add a title and hover tooltips. Show it.
```
**Expected:** Plotly artifact rendered in an iframe (interactive).

---

### 4.2 Plotly line chart with multiple series
```
Using plotly.express, create a line chart showing the normalized stock performance of
AAPL, MSFT, and GOOGL over the last 60 trading days. Use yfinance to get the real data.
Normalize all to 100 at the start date. Add a legend.
```
**Expected:** Interactive plotly chart with 3 lines.

---

### 4.3 Plotly scatter with color groups
```
Using plotly, create a scatter plot of 200 random points.
Color them by group (5 groups, randomly assigned).
Add axis labels, a title "Cluster Distribution", and hover tooltips.
```
**Expected:** Plotly scatter artifact in iframe.

---

### 4.4 Plotly sunburst chart
```
Using plotly, create a sunburst chart showing Potomac's AUM breakdown:
- Total: $2.4B
- Growth Strategies ($1.1B): Navigrowth ($600M), Bull Bear ($500M)
- Income Strategies ($800M): Income Plus ($500M), Guardian ($300M)
- Alternatives ($500M): Tactical ($500M)
```
**Expected:** Interactive sunburst chart in iframe.

---

## 🟢 TIER 1 — SANDBOX: HTML / SVG / JSON DISPLAY

### 5.1 HTML styled table
```
Use the display(HTML(...)) helper to create an HTML table showing:
- Product: Apple, Banana, Cherry, Dragonfruit
- Price: $1.20, $0.50, $3.00, $4.50
- In Stock: Yes, No, Yes, Yes
Style it with inline CSS — dark header, alternating row colors, border-radius.
```
**Expected:** HTML artifact rendered in iframe.

---

### 5.2 SVG bar chart
```
Use display(SVG(...)) to draw a bar chart as SVG showing 4 bars:
Q1: 45, Q2: 62, Q3: 58, Q4: 71 (scale to fit in 400x300 viewBox).
Different color per bar. Add labels below each bar with the quarter name.
```
**Expected:** SVG image artifact.

---

### 5.3 JSON structured output
```
Analyze this data and return it as a structured JSON artifact using display(JSON(...)):
{"q1": 1200, "q2": 1800, "q3": 1500, "q4": 2200}
Include calculated metrics: total, average, max_quarter, min_quarter, growth_rate_q1_to_q4.
```
**Expected:** JSON artifact rendered as formatted tree.

---

## 🟢 TIER 1 — SANDBOX: REACT COMPONENTS

### 6.1 Counter component
```
Build a React counter component with:
- A number display starting at 0
- Increment (+) and Decrement (-) buttons  
- A Reset button
- Minimum value of -10, maximum of 100 (disable buttons at limits)
- Tailwind styling with a clean card layout
```
**Expected:** React iframe with working interactive buttons.

---

### 6.2 Filterable data table
```
Build a React component showing a filterable table of 10 employees:
name, department, salary, start_date.
Add a text input to filter by name or department (live filter).
Add sort buttons on the column headers.
Use Tailwind for styling with a dark header row.
```
**Expected:** Interactive table with filter + sort in iframe.

---

### 6.3 Recharts bar chart (CDN)
```
Build a React component using recharts showing quarterly revenue:
Q1: 45000, Q2: 62000, Q3: 58000, Q4: 71000.
Include a tooltip, axis labels, and a reference line at the average.
Use a gradient fill on the bars. Purple/indigo color scheme.
```
**Expected:** Recharts bar chart in iframe.

---

### 6.4 Dark mode toggle with framer-motion
```
Build a React settings panel with:
- Dark/light mode toggle (switches background color)
- Font size slider (small/medium/large)
- A preview area showing sample text at the selected size/theme
Use framer-motion for smooth transitions. Tailwind styling.
```
**Expected:** Animated React app in iframe.

---

### 6.5 Dashboard cards with Lucide icons
```
Build a React dashboard card layout with 4 metric cards using lucide-react icons:
- Total Users: 12,847 (Users icon, blue)
- Monthly Revenue: $284,590 (DollarSign icon, green)
- Active Orders: 1,293 (ShoppingCart icon, orange)
- Conversion Rate: 4.7% (TrendingUp icon, purple)
Each card should show: colored icon, metric name, value, and a sparkline trend indicator.
Tailwind styling with a grid layout.
```
**Expected:** 4-card dashboard in iframe with Lucide icons.

---

### 6.6 D3 force graph (complex CDN)
```
Build a React component using d3 to show a force-directed network graph.
Create 8 nodes (departments) connected with 12 edges (relationships).
Nodes: Engineering, Sales, Marketing, Finance, HR, Design, Legal, Operations.
Draggable nodes, colored by department, with labels.
```
**Expected:** Interactive D3 force graph in iframe.

---

### 6.7 Zustand state management
```
Build a React shopping cart using zustand for state management.
Show 5 products with names, prices, and Add to Cart buttons.
Show the cart summary on the side with item count and total.
Allow removing items from the cart.
Use Tailwind for styling.
```
**Expected:** Shopping cart with persistent zustand state in iframe.

---

## 🟢 TIER 1 — SANDBOX: JAVASCRIPT

### 7.1 Basic JS execution
```
Run this JavaScript code:
const nums = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const doubled = nums.map(n => n * 2);
const evens = doubled.filter(n => n % 4 === 0);
const sum = evens.reduce((a, b) => a + b, 0);
console.log("Doubled:", doubled.join(", "));
console.log("Evens divisible by 4:", evens.join(", "));
console.log("Sum:", sum);
```
**Expected:** JavaScript output block with three lines.

---

### 7.2 Async/await + fetch (network)
```
Run this JavaScript code that fetches the current Bitcoin price from a public API:
const res = await fetch('https://api.coindesk.com/v1/bpi/currentprice.json');
const data = await res.json();
console.log("Bitcoin Price (USD):", data.bpi.USD.rate);
console.log("Last updated:", data.time.updated);
```
**Expected:** Live Bitcoin price output.

---

### 7.3 Lodash groupBy and orderBy
```
Using lodash in JavaScript:
const data = [
  { name: "Alice", dept: "Engineering", score: 85 },
  { name: "Bob", dept: "Sales", score: 92 },
  { name: "Carol", dept: "Engineering", score: 78 },
  { name: "Dave", dept: "Sales", score: 95 },
  { name: "Eve", dept: "Marketing", score: 88 }
];
Group by department, then within each department sort by score descending.
Log a ranked list showing dept → name → score.
```
**Expected:** Grouped and sorted output using lodash.

---

## 🟢 TIER 1 — SANDBOX: FILE DOWNLOADS

### 8.1 CSV download
```
Create a pandas DataFrame of 15 sample investment holdings:
columns: Ticker, Company, Shares, Price, MarketValue, Weight_pct
Use realistic ticker symbols and prices.
Save it as "potomac_holdings.csv".
The user should be able to download the file.
```
**Expected:** File artifact with ⬇ Download button (CSV).

---

### 8.2 Excel download
```
Create a pandas DataFrame of quarterly revenue by region (Q1-Q4, 5 regions).
Save it as "quarterly_revenue.xlsx" using openpyxl.
```
**Expected:** File artifact with ⬇ Download button (.xlsx).

---

### 8.3 PPTX download (python-pptx in sandbox)
```
Using python-pptx, create a simple 3-slide presentation:
- Slide 1: Title "Potomac Q2 2026 Update", subtitle "Confidential"
- Slide 2: Title "Performance", content bullet points for returns
- Slide 3: Title "Thank You"
Save as "quick_deck.pptx" so the user can download it.
```
**Expected:** File artifact with ⬇ Download button (.pptx).

---

### 8.4 Multiple file artifacts in one run
```
Generate three files in one code run:
1. A CSV of 10 sample trades ("trades.csv")
2. A JSON summary of the portfolio stats ("portfolio_stats.json")
3. A text report ("summary.txt") with a formatted summary
Print a completion message.
```
**Expected:** Text output + 3 separate file artifacts with download buttons.

---

## 🟡 TIER 2 — SANDBOX: FINANCIAL DATA (LIVE)

### 9.1 Live stock price + chart
```
Fetch Apple (AAPL) stock data for the last 30 days using yfinance.
Calculate: starting price, ending price, percentage change, highest and lowest close.
Plot the closing price as a line chart with a 5-day moving average overlay.
```
**Expected:** Text stats + image artifact.

---

### 9.2 Multi-stock comparison
```
Compare AAPL, MSFT, and GOOGL stock performance over the last 60 days using yfinance.
Normalize all three to 100 at the start date.
Plot them on the same chart with a legend. Use seaborn style.
```
**Expected:** Multi-line normalized comparison chart.

---

### 9.3 Volatility analysis + plotly
```
Fetch SPY (S&P 500 ETF) data for the last 6 months.
Calculate the 20-day rolling volatility (annualized).
Plot two subplots: price on top, rolling volatility on bottom, using plotly.
```
**Expected:** Plotly artifact with dual-panel chart.

---

## 🟡 TIER 2 — PACKAGE INSTALLATION

### 10.1 Install Faker and generate data
```
Install the Python package "faker" and use it to generate:
- 10 fake client names
- 10 fake company names
- 10 fake US addresses
- 10 fake email addresses
Print them in a formatted table using tabulate.
```
**Expected:** Install first, then tabulate output.

---

### 10.2 Install Polars and use it
```
Check if polars is installed. If not, install it.
Then create a polars DataFrame with 5 columns and 10 rows of sample financial data.
Show the describe() statistics and filter to rows where value > 50.
```
**Expected:** Polars DataFrame output after install.

---

### 10.3 Install statsmodels
```
Install statsmodels if needed.
Then load the built-in "longley" dataset and run an OLS regression.
Print the full regression summary table.
```
**Expected:** Full statsmodels OLS summary output.

---

## 🟡 TIER 2 — OFFICE TOOLS: POWERPOINT

### 11.1 Quick pitch deck (10 slides)
```
Create a 10-slide Potomac pitch deck for our Growth Strategy fund. Include: an executive-style title slide, an executive summary saying we outperformed by 420 bps with 40% lower drawdown, a metrics slide showing +12.4% YTD return / 1.42 Sharpe / -6.1% max drawdown / $2.4B AUM, a two-column slide comparing our approach vs. traditional buy-and-hold, a process slide with our 4-step investment process (Assess, Allocate, Execute, Monitor), and a CTA closing slide.
```
**Expected:** PPTX file generated and downloadable.

---

### 11.2 Table slide — comps analysis
```
Build a PowerPoint presentation with a Potomac-branded comparable company analysis table slide. Include 6 companies: Apple (EV/EBITDA 18.2x, P/E 28.4x, Rev Growth +8.3%), Microsoft (22.1x, 31.7x, +11.2%), Google (19.8x, 24.1x, +7.6%), Amazon (25.3x, 60.2x, +12.1%), Meta (14.2x, 22.7x, +21.4%), Netflix (28.1x, 46.3x, +5.8%). Add a median row at the bottom.
```
**Expected:** PPTX with branded table slide.

---

### 11.3 Timeline slide
```
Make a Potomac M&A advisory pitch deck with a timeline slide showing a 6-month deal process: January 2026 - LOI Signed (complete), February 2026 - Management Presentations (complete), March 2026 - Due Diligence (in_progress), April 2026 - Final Bids Due (upcoming), May 2026 - Exclusivity (upcoming), June 2026 - Close (upcoming). Also add an executive summary slide and a CTA closing slide.
```
**Expected:** PPTX with timeline slide.

---

### 11.4 Scorecard / RAG status slide
```
Build a Potomac project health dashboard slide with 8 metrics in RAG status format: Q2 Performance Budget (green, $2.1M spent / $2.5M), Marketing Campaign Timeline (yellow, 2 weeks behind), Technology Migration (red, 3 critical blockers), AUM Growth Target (green, $2.4B vs $2.0B target), Compliance Review (green, all clear), New Hire Onboarding (yellow, 2 positions pending), Client Retention Rate (green, 98.2%), Regulatory Filing (red, 4 days late).
```
**Expected:** PPTX with RAG scorecard slide.

---

### 11.5 Icon grid slide
```
Make a 6-up icon grid slide showing Potomac's competitive advantages: Risk Management (shield icon), Data-Driven Alpha (chart icon), Real-Time Monitoring (clock icon), Tax Efficiency (dollar icon), Team Experience (people icon), Proven Track Record (trophy icon). Put it in a full Potomac presentation with title and CTA.
```
**Expected:** PPTX with icon grid layout.

---

### 11.6 Executive summary slide
```
Build a Potomac board presentation. The first content slide must be an executive summary with headline: POTOMAC TACTICAL STRATEGIES OUTPERFORMED ALL BENCHMARKS IN Q1 2026. Supporting points: (1) Growth Strategy returned +14.2% vs S&P benchmark +8.2%, top decile (2) Maximum drawdown -5.8%, 44% lower than benchmark's -10.3% (3) $2.4B AUM record high, +18% YoY (4) Zero client redemptions in Q1. Call to action: Approve Q2 expansion into international tactical strategies.
```
**Expected:** PPTX with executive summary slide.

---

### 11.7 2x2 Matrix slide
```
Create a strategic portfolio assessment slide using a 2x2 matrix. X-axis is Market Share, Y-axis is Revenue Growth. Place 4 products: Growth Fund (high share, high growth at 0.85, 0.9), Income Strategy (high share, low growth at 0.75, 0.2), Tactical Alternatives (low share, high growth at 0.3, 0.8), Legacy Fixed Income (low share, low growth at 0.2, 0.15). Make a full Potomac deck around it.
```
**Expected:** PPTX with 2x2 matrix slide.

---

### 11.8 Mega pitch book (all slide types)
```
Create a complete 18-slide Potomac M&A advisory pitch book for a $500M sell-side mandate. Include: executive-style title slide, executive summary, situation overview (two-column), M&A track record metrics slide (deal count, average premium, close rate, timeline), comparable transactions table (5 deals with EV/EBITDA, premium paid), revenue bridge waterfall chart, deal process timeline with 6 milestones, strategic alternatives 2x2 matrix, buyer universe analysis (three-column), valuation ranges (two-column), team icon grid, our process flow (5 steps), client quote slide, RAG scorecard for 5 KPIs, section divider slide, and CTA closing slide.
```
**Expected:** 18-slide PPTX with all slide type variations.

---

## 🟡 TIER 2 — OFFICE TOOLS: EXCEL

### 12.1 Performance report with formulas
```
Create a Potomac Excel performance report for Q1 2026 with 3 sheets. Sheet 1 PERFORMANCE: monthly returns for Jan (5.2%), Feb (3.8%), Mar (6.1%) vs S&P 500 (3.1%, 2.2%, 4.4%), plus an AVERAGE row using =AVERAGE() formulas. Sheet 2 RISK: Sharpe ratio 1.42, Sortino 2.18, Max DD -6.1%, Beta 0.78, Alpha 6.2%. Sheet 3 HOLDINGS: top 5 positions with ticker, name, shares, price, market value, weight %. Format percentages as 0.0% and currency as $#,##0.
```
**Expected:** Multi-sheet XLSX download.

---

### 12.2 Excel with charts and conditional formatting
```
Build a Potomac portfolio tracker Excel with 2 sheets. Sheet 1 HOLDINGS with columns Ticker, Company, Shares, Price, Market Value, Weight %, P&L %. Add zebra striping, freeze the header row, include a bar chart of market values by position, add a color scale on the Weight % column (green=high), and highlight negative P&L in red. Sheet 2 RISK METRICS with VaR 95%, VaR 99%, Sharpe, Sortino, Max Drawdown — RAG-style conditional formatting. Use sample data for 8 positions.
```
**Expected:** Advanced XLSX with charts + conditional formatting.

---

### 12.3 Fee schedule with calculations
```
Create a Potomac fee schedule Excel showing AUM tiers: Under $1M = 100bps, $1M-$5M = 75bps, $5M-$25M = 60bps, $25M-$100M = 50bps, Over $100M = 40bps. For each tier show: Annual Rate, Annual Fee for median AUM in that tier, Monthly Fee, Quarterly Fee. Use =FORMULA() for all fee calculations.
```
**Expected:** Fee schedule XLSX with formula calculations.

---

### 12.4 Excel Table with totals row
```
Generate a Potomac trade log Excel for Q1 2026. Make it a proper Excel Table (as_table: true) with auto-filter. Columns: Date, Ticker, Action, Shares, Entry Price, Exit Price, Gross P&L, P&L %. Add a TOTAL row at the bottom with =SUM() for P&L. Include at least 12 sample trades. Format P&L % as 0.0% and P&L as $#,##0. Use a red tab color.
```
**Expected:** XLSX with proper Excel Table formatting.

---

## 🟡 TIER 2 — OFFICE TOOLS: WORD

### 13.1 Market commentary report
```
Write a Potomac Q2 2026 market commentary document with the following sections: Executive Summary, Market Environment (Fed policy, equity valuations, fixed income outlook), Potomac Portfolio Positioning, Risk Factors, and Outlook. Include a table comparing our Q1 vs Q2 positioning across 6 asset classes. Add a numbered list of 5 key themes we're monitoring. Include the standard Potomac disclosure block.
```
**Expected:** Formatted DOCX download.

---

### 13.2 Fund fact sheet
```
Create a Potomac Growth Strategy fact sheet as a Word document. Include: 3-year annualized return 12.4%, benchmark S&P 500, Sharpe 1.42, AUM $2.4B, inception date January 2015, investment minimum $500K, management fee 0.75% AUM. Add a table showing calendar year returns for 2021-2025. Include a brief investment philosophy section and the standard disclaimer.
```
**Expected:** Branded DOCX fact sheet.

---

## 🔴 TIER 3 — COMBINATION TESTS (hardest)

### 14.1 Python → Excel file in sandbox
```
Using Python in the sandbox:
1. Fetch AAPL, MSFT, NVDA, GOOGL closing prices for the last 30 trading days with yfinance
2. Calculate daily returns, rolling 20-day volatility, and cumulative return for each
3. Save everything to "multi_stock_analysis.xlsx" with separate sheets per stock
4. Also plot a comparison line chart (normalized to 100) and save "comparison.png"
Show both files as downloadable artifacts and display the chart.
```
**Expected:** XLSX file artifact + PNG image artifact.

---

### 14.2 Python analysis → React visualization
```
First, using Python:
Analyze this portfolio data and calculate sector allocations:
Technology: $450K, Healthcare: $280K, Finance: $320K, Energy: $190K, Consumer: $260K
Print the percentages.

Then, build a React component using recharts that displays this allocation as both:
1. A pie chart with labels and percentages
2. A horizontal bar chart below it
Use a professional color scheme and Tailwind styling.
```
**Expected:** Python text output + React component in iframe.

---

### 14.3 Session → Chart → File download
```
Turn 1: Store this quarterly data in a Python variable called q_data:
{"Q1": {"revenue": 45000, "cost": 32000}, "Q2": {"revenue": 62000, "cost": 41000}, 
 "Q3": {"revenue": 58000, "cost": 39000}, "Q4": {"revenue": 71000, "cost": 45000}}

Turn 2: Using q_data, calculate profit margin for each quarter.
Create a matplotlib chart showing revenue, cost, and profit as grouped bars.
Also save the results as "quarterly_summary.csv" for download.
```
**Expected:** Turn 2 uses session data → image artifact + CSV file artifact.

---

### 14.4 Full quarterly update workflow (upload-based)
```
[After generating the pitch deck from prompt 11.1 and downloading it, re-upload the .pptx]
Update this deck for Q2 2026:
- Change all Q1 2026 to Q2 2026
- Replace +12.4% with +14.7%
- Replace +8.2% with +9.1%  
- Replace -6.1% with -5.8%
- Replace $2.1B with $2.4B AUM
```
**Expected:** Revised PPTX download with all replacements applied.

---

### 14.5 Analyze + Transform + Generate (upload-based)
```
[Upload any CSV with financial data]
1. Analyze this CSV file — tell me the column names, data types, row count, null values, and numeric statistics
2. Clean it: remove duplicate rows, normalize all text columns to uppercase, remove rows where any numeric column is negative
3. Generate a Potomac-branded Excel report from the cleaned data
4. Also create a PowerPoint presentation with a table slide showing the top 10 rows
```
**Expected:** Analysis text → XLSX → PPTX (three outputs).

---

### 14.6 Complete pitch + companion data workbook
```
Create everything for a Potomac Growth Strategy client pitch:
(1) A PowerPoint pitch book with 15 slides covering: strategy overview, performance metrics, risk analysis, process flow, team credentials, and CTA
(2) A companion Excel data workbook with 3 sheets: quarterly returns going back 3 years, current holdings (15 sample positions), and risk metrics table
Both files fully Potomac-branded. Do it all in one response.
```
**Expected:** Both PPTX + XLSX generated and downloadable.

---

## 🔴 TIER 3 — SECURITY TESTS (should all FAIL safely)

### 15.1 Blocked: os module
```
Run: import os; print(os.listdir('/'))
```
**Expected:** `success: false` — "Forbidden import: os"

---

### 15.2 Blocked: subprocess
```
Run: import subprocess; subprocess.run(['ls', '-la'])
```
**Expected:** `success: false` — "Forbidden import: subprocess"

---

### 15.3 Blocked: eval()
```
Run: eval("__import__('os').system('whoami')")
```
**Expected:** `success: false` — "Forbidden call: eval()"

---

### 15.4 Blocked: open() to read system files
```
Run: f = open('/etc/passwd', 'r'); print(f.read())
```
**Expected:** `success: false` — "Forbidden call: open()"

---

### 15.5 Blocked: __import__ bypass
```
Run: __import__('os').environ
```
**Expected:** `success: false` — "Forbidden import via __import__: os"

---

## 🔴 TIER 3 — EDGE CASES & STRESS

### 16.1 Large output
```
Generate a 20x20 multiplication table and print it formatted with aligned columns using tabulate.
```
**Expected:** Large text block captured correctly — no truncation.

---

### 16.2 Timeout handling
```
Run a loop that counts to 1 billion and prints the final result.
```
**Expected:** `success: false` — "timed out"

---

### 16.3 Complex React with Recharts + framer-motion
```
Build a full React analytics dashboard with:
- A top nav bar (Potomac branding, dark theme)
- 4 KPI cards with animated number counters (framer-motion)
- A recharts bar chart of monthly revenue (6 months)
- A recharts area chart of portfolio growth (12 months)
- A sortable table of top 5 holdings below
All Tailwind styling, responsive grid layout.
```
**Expected:** Complex React app in iframe with all components.

---

### 16.4 Plotly + matplotlib in same session
```
In the same run:
1. Create a matplotlib heatmap of a 8x8 correlation matrix
2. Create a plotly 3D surface plot of z = sin(x) * cos(y) over a grid
Both should appear as artifacts.
```
**Expected:** One image artifact (matplotlib) + one plotly artifact.

---

### 16.5 Very large PPTX deck
```
Create a 30-slide Potomac investor day presentation covering: opening (1), agenda (1), company overview (2), market opportunity (2), investment philosophy (2), portfolio construction (2), risk management (3), performance attribution (4), case studies (3), team bios (2), ESG approach (1), technology platform (1), client service model (1), financial summary (1), appendix (2), closing CTA (1).
```
**Expected:** 30-slide PPTX without error.

---

### 16.6 Excel with everything
```
Build the most advanced Potomac Excel workbook possible: 4 sheets (PERFORMANCE, HOLDINGS, RISK, DISCLOSURES), charts on the performance sheet, conditional formatting (color scale + data bars + highlight negatives), an Excel Table with totals row on the holdings sheet, freeze panes on all data sheets, proper number formats throughout, =SUM(), =AVERAGE(), =STDEV() formulas on the risk sheet. Use realistic Potomac data.
```
**Expected:** Advanced XLSX with all features.

---

## 📋 QUICK REFERENCE — What to Check Per Test

| Category | Key Things to Verify |
|---|---|
| Python text | Output appears in dark code block, text is readable |
| Image artifacts | PNG renders inline, no broken image icon |
| Plotly | Iframe loads, chart is interactive (hover works) |
| React iframe | Component renders, buttons/interactions work, auto-height |
| HTML iframe | Table/content visible, no blank iframe |
| JSON | Formatted tree view (or pre block) |
| File download | Download button visible, clicking downloads correct file type |
| Session persistence | Turn 2+ uses variables from turn 1 without error |
| Security blocks | Error message, NOT a Python traceback |
| Timeout | Error message with "timed out", not a hang |
| Multi-artifact | All artifacts shown (not just the first) |
| Office tools | File downloads correctly, opens in Office app |

---

*Generated: April 2026 — covers Sandbox v3 (Python, JS, React, Plotly, File artifacts) + Office Tools (PPTX, XLSX, DOCX)*
