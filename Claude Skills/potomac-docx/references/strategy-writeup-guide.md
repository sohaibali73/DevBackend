# Strategy Write-Up Template Reference

This document provides detailed guidance on filling out the Potomac Strategy Write-Up Template.

## Template Structure

The template contains 8 main sections that must be completed:

### 01 TITLE
**Strategy Name:** The official name of the system or strategy

Example: "SPY Momentum Rotation Strategy"

### 02 INSPIRATION
**Source / Origin:** Where did this idea come from?

Cite:
- Academic papers
- Books
- Conference presentations
- Personal insights
- Industry research

**References & Links:** Complete citations

Format as table:
| Source / Author | URL / Link |
|-----------------|------------|
| Paper name / Author | https://... |

### 03 THESIS
**Core Thesis Statement:** What are you trying to prove?

Format: "I believe that [clear hypothesis]"

Example: "I believe that momentum persistence in the S&P 500 can be exploited using a 6-month lookback period with monthly rebalancing to generate alpha with reduced drawdowns."

**Supporting Hypotheses:** Secondary assumptions that must be true

List the key assumptions:
- Market conditions
- Data reliability
- Execution assumptions
- Risk parameters

### 04 PARAMETERS & RULES

This is the most critical section. Every rule must be precisely defined.

**Buy Parameters & Rules:**
- Exact entry conditions
- Signal generation
- Position sizing
- Market timing

**Sell / Exit Parameters & Rules:**
- Exact exit conditions
- Stop losses
- Profit targets
- Time-based exits

**Short / Cover Parameters & Rules** (if applicable):
- Short entry conditions
- Cover conditions
- Short-specific rules

**Market Timing & Regime Filters:**
- Macro conditions
- Volatility filters
- Trend filters
- When strategy is active vs inactive

**Optimization Summary:**
Table format:
| Parameter | Value / Range | Optimized? | Notes |
|-----------|---------------|------------|-------|
| Lookback | 126 days | Yes | Tested 20-252 days |
| Rebalance | Monthly | No | Fixed a priori |

### 05 LINK TO AFL
**AFL File Path / URL:** Complete path to the AFL file

**AFL Header Checklist:**
Verify the AFL file documents:
- ☐ Strategy Title
- ☐ Inspiration / Source
- ☐ Thesis Statement
- ☐ Parameters & Rules

### 06 LINK TO OPTIMIZATION IN EXCEL
**Excel File Path / URL:** Path to optimization workbook

**Sheet / Tab Name:** Specific worksheet name

**Last Updated:** Date of last modification

**Optimization Notes:** Description of the workbook
- In-sample vs out-of-sample split
- Walk-forward methodology
- Key outputs and metrics

### 07 WRITE-UP & FINDINGS

**Summary of Findings:** 3-5 sentences summarizing key results

Be direct and honest about:
- What worked
- What didn't work
- Limitations discovered
- Unexpected findings

**Key Performance Statistics:**
Table format:
| Metric | Strategy Value | Benchmark / B&H |
|--------|----------------|-----------------|
| Annualized Return (CAR) | X.XX% | X.XX% |
| Maximum Drawdown | -XX.XX% | -XX.XX% |
| Win Rate | XX% | XX% |
| Profit Factor | X.XX | X.XX |
| Market Exposure | XX% | 100% |
| Risk-Adjusted Return | X.XX | X.XX |
| Recovery Factor | X.XX | X.XX |
| Total Trades | XXX | N/A |

**The Call:** Clear recommendation

Choose one:
1. **Viable for deployment** - Strategy is ready for live trading
2. **Further development** - Shows promise but needs refinement
3. **Rejection** - Strategy does not meet criteria

Provide reasoning for the call.

**Risks & Limitations:**
- Market condition dependencies
- Data limitations
- Execution challenges
- Scalability concerns
- Overfitting risks

**Suggested Next Steps:**
- Additional testing needed
- Parameters to refine
- Markets to test
- Monitoring requirements

### 08 APPENDIX

**Figures and Charts:**
- Equity curves
- Drawdown charts
- Trade distribution
- Monte Carlo simulations
- Parameter sensitivity

Label each:
- Figure 1 - [Description]
- Figure 2 - [Description]

## XML Editing Tips

When filling out the template via XML editing:

### Finding Placeholders

Common placeholders in the template:
- `[Strategy Title]`
- `[Month DD, 2026]`
- `[Analyst Name]`
- `[Title]`

Use str_replace to update these:
```bash
str_replace <path> "[Strategy Title]" "SPY Momentum Rotation"
```

### Maintaining Tables

The template uses Word tables extensively. When editing:

1. Find the table structure:
```xml
<w:tbl>
  <w:tr>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>Cell content</w:t>
        </w:r>
      </w:p>
    </w:tc>
  </w:tr>
</w:tbl>
```

2. Replace content inside `<w:t>` tags
3. Keep all formatting tags intact
4. Don't modify table structure unless necessary

### Adding Content to Blank Sections

Some sections have empty space. To fill them:

1. Find the section heading
2. Locate the empty paragraph after it
3. Replace the empty `<w:t>` with your content

Example:
```xml
<!-- Before -->
<w:t></w:t>

<!-- After -->
<w:t>Your content here</w:t>
```

### Preserving Formatting

When replacing text, preserve the surrounding formatting:

```xml
<w:r>
  <w:rPr>
    <w:b/>  <!-- Bold -->
    <w:sz w:val="24"/>  <!-- 12pt font -->
  </w:rPr>
  <w:t>Your text</w:t>
</w:r>
```

Keep the `<w:rPr>` block intact when replacing `<w:t>` content.

## Common Questions

**Q: What if I don't have all the information?**
A: Ask the user for the missing pieces. Never fabricate data.

**Q: What if the AFL or Excel files don't exist yet?**
A: Note "In development" or "Pending" in those sections.

**Q: How detailed should the parameters be?**
A: Extremely detailed. Someone should be able to replicate the strategy from the parameters alone.

**Q: What if the strategy failed?**
A: Be honest. Document what was learned and why it didn't work.

**Q: Should I include the full disclosure at the end?**
A: Yes, the template includes it. Don't remove or modify it.

## Best Practices

1. **Be precise** - Ambiguity invalidates backtests
2. **Be honest** - Document failures as learning opportunities
3. **Be complete** - Fill every section thoroughly
4. **Be consistent** - Use standard terminology
5. **Be compliant** - Include all required disclosures

## Example Content

### Example Thesis
"I believe that the Swiss franc serves as a leading indicator for gold prices based on their historical correlation during inflationary periods. By monitoring CHF/USD movements, we can anticipate gold price changes with a 2-week lead time, allowing for tactical positioning."

### Example Parameters
**Buy Rule:**
- Calculate 20-day correlation between CHF/USD and GLD
- When correlation drops below 0.3 AND CHF/USD rises >2% in 5 days
- Enter long GLD position at next open
- Position size: 20% of portfolio

**Exit Rule:**
- Exit when correlation returns above 0.6
- OR 10% stop loss
- OR 30% profit target
- OR 30 trading days elapsed

### Example Call
"**Viable for deployment with monitoring**

The strategy demonstrates consistent alpha generation with acceptable drawdown characteristics. The 6-month lookback period shows robustness across multiple market regimes. However, market exposure of only 45% may not be suitable for all clients. Recommend deployment for risk-averse clients seeking reduced volatility. Monitor correlation stability quarterly and reduce position sizes during extreme volatility events (VIX > 30)."

## Validation Checklist

Before finalizing the document, verify:

- [ ] All 8 sections are complete
- [ ] No placeholders remain (search for `[` and `]`)
- [ ] Tables are properly formatted
- [ ] Statistics are accurate and match Excel output
- [ ] AFL header includes required documentation
- [ ] The Call is clear and actionable
- [ ] Risks are honestly documented
- [ ] Disclosures are intact
- [ ] Date and author are correct
- [ ] Logo is visible
