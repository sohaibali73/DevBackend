# Office Tools — Stress Test Prompts

Copy-paste these prompts directly into the chat. Each tests a specific tool or combination.

---

## POWERPOINT — generate_pptx

**1. Quick pitch deck (tests basic slide types)**
> "Create a 10-slide Potomac pitch deck for our Growth Strategy fund. Include an executive-style title slide, an executive summary slide saying we outperformed by 420 bps with 40% lower drawdown, a metrics slide showing +12.4% YTD return / 1.42 Sharpe / -6.1% max drawdown / $2.4B AUM, a two-column slide comparing our approach vs. traditional buy-and-hold, a process slide with our 4-step investment process (Assess, Allocate, Execute, Monitor), and a CTA closing slide."

**2. Comps table slide (tests the new `table` slide type)**
> "Build a PowerPoint presentation with a Potomac-branded comparable company analysis table slide. Include 6 companies: Apple (EV/EBITDA 18.2x, P/E 28.4x, Rev Growth +8.3%), Microsoft (22.1x, 31.7x, +11.2%), Google (19.8x, 24.1x, +7.6%), Amazon (25.3x, 60.2x, +12.1%), Meta (14.2x, 22.7x, +21.4%), Netflix (28.1x, 46.3x, +5.8%). Add a median row at the bottom."

**3. Waterfall chart (tests the new `chart` slide type)**
> "Create a Potomac slide with a waterfall chart showing our revenue bridge from FY2024 ($100M) to FY2025 ($128M). Breakdown: Organic growth +$18M, New client acquisitions +$12M, FX headwind -$4M, Management fee compression -$2M, performance fees +$4M. Label the chart in millions."

**4. Transaction timeline (tests the new `timeline` slide type)**
> "Make a Potomac M&A advisory pitch deck with a timeline slide showing a 6-month deal process: January 2026 - LOI Signed (complete), February 2026 - Management Presentations (complete), March 2026 - Due Diligence (in_progress), April 2026 - Final Bids Due (upcoming), May 2026 - Exclusivity (upcoming), June 2026 - Close (upcoming). Also add an executive summary slide and a CTA closing slide."

**5. BCG matrix (tests the new `matrix_2x2` slide type)**
> "Create a strategic portfolio assessment slide using a 2x2 matrix. X-axis is Market Share, Y-axis is Revenue Growth. Place 4 products: Growth Fund (high market share, high growth at position 0.85, 0.9), Income Strategy (high market share, low growth at 0.75, 0.2), Tactical Alternatives (low share, high growth at 0.3, 0.8), Legacy Fixed Income (low share, low growth at 0.2, 0.15). Make a full Potomac deck around it with title and CTA slides."

**6. RAG scorecard (tests the new `scorecard` slide type)**
> "Build a Potomac project health dashboard slide with 8 metrics in RAG status format: Q2 Performance Budget (green, $2.1M spent / $2.5M), Marketing Campaign Timeline (yellow, 2 weeks behind), Technology Migration (red, 3 critical blockers), AUM Growth Target (green, $2.4B vs $2.0B target), Compliance Review (green, all clear), New Hire Onboarding (yellow, 2 positions pending), Client Retention Rate (green, 98.2%), Regulatory Filing (red, 4 days late)."

**7. Competitor comparison (tests the new `comparison` slide type)**
> "Create a Potomac vs. competitors comparison slide showing why we're better than Vanguard and Fidelity. Compare: Investment approach, Downside protection, Active management, Response to market crises, Customization, Performance fee alignment. Potomac should be the winner on all categories. Build this into a 5-slide deck."

**8. Icon grid (tests the new `icon_grid` slide type)**
> "Make a 6-up icon grid slide showing Potomac's competitive advantages: Risk Management (shield icon), Data-Driven Alpha (chart icon), Real-Time Monitoring (clock icon), Tax Efficiency (dollar icon), Team Experience (people icon), Proven Track Record (trophy icon). Put it in a full Potomac presentation with title and CTA."

**9. Executive summary (tests the new `executive_summary` slide type)**
> "Build a Potomac board presentation. The first content slide must be an executive summary with the headline: POTOMAC TACTICAL STRATEGIES OUTPERFORMED ALL BENCHMARKS IN Q1 2026. Supporting points: (1) Growth Strategy returned +14.2% vs S&P benchmark +8.2%, top decile among all tactical managers (2) Maximum drawdown of -5.8%, 44% lower than benchmark's -10.3% (3) $2.4B AUM record high, +18% year-over-year (4) Zero client redemptions in Q1. Call to action: Approve Q2 expansion into international tactical strategies."

**10. Mega pitch book (tests all slide types in one deck)**
> "Create a complete 18-slide Potomac M&A advisory pitch book for a $500M sell-side mandate. Include: executive-style title slide, executive summary, situation overview (two-column), our M&A track record (metrics slide with deal count, average premium, close rate, average timeline), comparable transactions table (5 deals with EV, EV/EBITDA, premium paid), revenue bridge waterfall chart, deal process timeline with 6 milestones, strategic alternatives matrix 2x2, buyer universe analysis (three-column), valuation football field (two-column with ranges), our team icon grid, our process flow (5 steps), client testimonial quote slide, a scorecard showing 5 deal KPIs in RAG status, next steps section divider, and a CTA closing slide."

---

## POWERPOINT — analyze_pptx

**11. Analyze uploaded deck**
> *(Upload any .pptx file first, then say)*: "Analyze this PowerPoint and tell me what slides are in it, how many slides total, what the Potomac brand compliance score is, and list any brand violations."

**12. Analyze before revising**
> *(Upload a .pptx first)*: "First analyze this deck to understand its structure, then update the Q1 references to Q2, change all instances of 2025 to 2026, and add a new metrics slide at the end with Q2 performance."

---

## POWERPOINT — revise_pptx

**13. Quarterly data refresh (biggest time saver test)**
> *(Upload a .pptx first)*: "Update this deck for Q2 2026. Change all Q1 2026 to Q2 2026, replace +12.4% with +14.7%, replace +8.2% with +9.1%, replace -6.1% to -5.8%, replace $2.1B with $2.4B AUM, and replace January-March with April-June throughout."

**14. Add slides to existing deck**
> *(Upload a .pptx first)*: "Take this existing deck and append 2 new slides to the end: a timeline slide showing our Q3 2026 roadmap with 4 milestones, and a new CTA closing slide."

**15. Delete and reorder**
> *(Upload a .pptx first)*: "Remove slide 8 from this deck (the appendix), delete slide 11, then move the CTA slide to be the last slide."

---

## EXCEL — generate_xlsx

**16. Performance report with formulas**
> "Create a Potomac Excel performance report for Q1 2026 with 3 sheets. Sheet 1 PERFORMANCE: monthly returns for Jan (5.2%), Feb (3.8%), Mar (6.1%) vs S&P 500 (3.1%, 2.2%, 4.4%), plus an AVERAGE row using =AVERAGE() formulas. Sheet 2 RISK: Sharpe ratio 1.42, Sortino 2.18, Max DD -6.1%, Beta 0.78, Alpha 6.2%. Sheet 3 HOLDINGS: top 5 positions with ticker, name, shares, price, market value, weight %. Format percentages as 0.0% and currency as $#,##0."

**17. Multi-sheet workbook with charts and conditional formatting**
> "Build a Potomac portfolio tracker Excel with 2 sheets. Sheet 1 called HOLDINGS with columns Ticker, Company, Shares, Price, Market Value, Weight %, P&L %. Add zebra striping, freeze the header row, include a bar chart of market values by position, add a color scale on the Weight % column (green = high weight), and highlight negative P&L in red. Sheet 2 called RISK METRICS with VaR 95%, VaR 99%, Sharpe, Sortino, Max Drawdown — add RAG-style conditional formatting. Use actual sample data for 8 positions."

**18. Fee schedule with tiered rates**
> "Create a Potomac fee schedule Excel showing AUM tiers: Under $1M = 100bps, $1M-$5M = 75bps, $5M-$25M = 60bps, $25M-$100M = 50bps, Over $100M = 40bps. For each tier show: Annual Rate, Annual Fee for median AUM in that tier, Monthly Fee, Quarterly Fee. Use =FORMULA() for all fee calculations. Format as dollar amounts."

**19. Excel Table with totals row**
> "Generate a Potomac trade log Excel for Q1 2026. Make it a proper Excel Table (as_table: true) with auto-filter, columns: Date, Ticker, Action, Shares, Entry Price, Exit Price, Gross P&L, P&L %. Add a TOTAL row at the bottom with =SUM() for P&L. Include at least 12 sample trades. Format the P&L % column with 0.0% and the P&L column as $#,##0. Tab should be red (#EB2F5C) to indicate risk."

---

## EXCEL — analyze_xlsx

**20. Profile uploaded file**
> *(Upload any .xlsx or .csv)*: "Analyze this Excel file and tell me: how many sheets, what columns are in each sheet, the data types, how many rows, any null values or duplicates, and show me the numeric statistics for all numeric columns."

**21. Find data quality issues**
> *(Upload a file with messy data)*: "Analyze this file and identify any data quality issues — null values, duplicates, columns with unexpected data types, or any anomalies I should know about before cleaning it."

---

## EXCEL — transform_xlsx

**22. Full clean pipeline**
> *(Upload a messy CSV or Excel)*: "Clean this file: remove duplicate rows (dedup on Ticker column), fill null prices with 0, convert all ticker symbols to uppercase, filter to only rows where Weight % is greater than 0.5%, sort by Market Value descending, and drop the Notes column. Output it as a clean Potomac Excel."

**23. Group and aggregate**
> *(Upload a holdings file)*: "Group this portfolio by Sector and calculate: total Market Value per sector, average Weight % per sector, count of positions per sector. Show the results sorted by total Market Value descending."

**24. Pivot table**
> *(Upload a returns file with columns Date, Strategy, Return)*: "Create a pivot table from this data showing each Strategy as rows and each quarter as columns, with Average Return as the values."

**25. Add calculated columns**
> *(Upload a holdings file with Price and Shares)*: "Add 3 new calculated columns to this file: Market_Value = SHARES * PRICE, Portfolio_Weight = Market_Value / sum(Market_Value), and Daily_PnL = (PRICE - PREV_CLOSE) * SHARES. Then sort by Market_Value descending."

---

## WORD — generate_docx

**26. Market commentary report**
> "Write a Potomac Q2 2026 market commentary document with the following sections: Executive Summary, Market Environment (Fed policy, equity valuations, fixed income outlook), Potomac Portfolio Positioning, Risk Factors, and Outlook. Include a table comparing our Q1 vs Q2 positioning across 6 asset classes. Add a numbered list of 5 key themes we're monitoring. Include the standard Potomac disclosure block."

**27. Fund fact sheet**
> "Create a Potomac Growth Strategy fact sheet document as a Word doc. Use the fund_fact_sheet template. Include: 3-year annualized return 12.4%, benchmark S&P 500, Sharpe 1.42, AUM $2.4B, inception date Jan 2015, investment minimum $500K, management fee 0.75% AUM. Add a table showing calendar year returns for 2021-2025."

---

## COMBINATION TESTS (hardest)

**28. Analyze → Transform → Generate report**
> *(Upload a messy CSV)*: "Analyze this CSV file first, then clean it (remove duplicates, normalize ticker symbols to uppercase, filter to positions > 1% weight), then generate a branded Potomac Excel report from the cleaned data, AND also create a PowerPoint presentation showing the top 10 holdings in a table slide and a pie chart slide of sector allocation."

**29. Full quarterly update workflow**
> *(Upload last quarter's .pptx AND a new Excel with updated numbers)*: "Analyze the PowerPoint deck structure, then analyze the Excel file to extract the new Q2 numbers, then revise the PowerPoint to update all Q1 data to Q2 data from the Excel file."

**30. Complete pitch book in one shot**
> "Create everything for a Potomac Growth Strategy client pitch: (1) A PowerPoint pitch book with 15 slides covering strategy overview, performance, risk metrics, process, team, and CTA. (2) A companion Excel data workbook with 3 sheets: quarterly returns going back 3 years, current holdings (sample data for 15 positions), and risk metrics table. Both files should be fully Potomac branded. Do it all in one go."

---

## EDGE CASES

**31. Minimal input (robustness)**
> "Make a quick PowerPoint about Potomac."

**32. Very large deck**
> "Create a 30-slide Potomac investor day presentation covering: opening, agenda, company overview, market opportunity, investment philosophy, portfolio construction, risk management (3 slides), performance attribution (4 slides), case studies (3 slides), team bios (2 slides), ESG approach, technology platform, client service model, financial summary, appendix (5 slides), closing CTA."

**33. Revision with many find-replaces**
> *(Upload any .pptx)*: "Update this deck: change every instance of 'Q1' to 'Q2', '2025' to '2026', '$2.1B' to '$2.4B', '+12.4%' to '+14.7%', '+8.2%' to '+9.1%', '-6.1%' to '-5.8%', 'January' to 'April', 'February' to 'May', 'March' to 'June', 'first quarter' to 'second quarter', 'First Quarter' to 'Second Quarter'."

**34. Image injection (tests file_id resolution)**
> *(Upload a PNG logo or chart image)*: "Create a Potomac pitch deck with the image I just uploaded embedded as a full-slide image on slide 3 with the caption 'Proprietary Risk Management Framework'."

**35. Excel with everything**
> "Build the most advanced Potomac Excel workbook possible: 4 sheets (PERFORMANCE, HOLDINGS, RISK, DISCLOSURES), charts on the performance sheet, conditional formatting (color scale + data bars + highlight negatives), an Excel Table with totals row on the holdings sheet, freeze panes on all data sheets, proper number formats throughout, and =SUM(), =AVERAGE(), =STDEV() formulas on the risk sheet. Use realistic Potomac data."
