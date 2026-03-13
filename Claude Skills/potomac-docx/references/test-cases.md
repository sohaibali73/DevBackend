# Test Cases for Potomac DOCX Skill

These test cases cover the main scenarios the skill should handle.

## Test Case 1: Strategy Write-Up from Template

**User Query:**
"Create a strategy write-up for my momentum rotation strategy. It's based on the research paper by Jegadeesh and Titman (1993). The thesis is that momentum persists in the S&P 500 over 6-12 month periods. I buy the top 20% performers from the previous 6 months and rebalance monthly. The AFL file is at /strategies/momentum_v2.afl and the Excel optimization is at /backtest/momentum_optimization.xlsx. The strategy returned 14.2% annually with a max drawdown of -22.3% versus S&P at 11.1% and -33.9%."

**Expected Behavior:**
1. Check for template file in uploads
2. If present, use template workflow
3. Ask for any missing information:
   - Date
   - Analyst name/title
   - Sell/exit rules
   - Optimization details
   - The final call/recommendation
4. Fill out template sections
5. Present completed document

**Success Criteria:**
- Document uses template structure
- All 8 sections are filled
- Potomac branding is applied
- Disclosures are included
- File is valid and opens correctly

---

## Test Case 2: Research Report from Scratch

**User Query:**
"Write a research report analyzing the relationship between VIX levels and forward S&P 500 returns. Include data showing that when VIX is above 30, the next 12-month returns average 15% versus 9% when VIX is below 20."

**Expected Behavior:**
1. Read docx and potomac-brand skills
2. Ask about logo preference
3. Ask for additional details:
   - Time period of analysis
   - Sample size
   - Any caveats or limitations
4. Create custom document with:
   - Executive summary
   - Key findings section
   - Analysis with data table
   - Conclusion
   - Proper Potomac branding
5. Present document

**Success Criteria:**
- Document built from scratch (no template)
- Proper Potomac styling (Rajdhani headers, Quicksand body)
- Logo included
- Yellow accent color used appropriately
- Table formatted with brand colors
- Disclosures included
- Validates successfully

---

## Test Case 3: Internal Memo

**User Query:**
"Create a memo to the investment team about implementing a new risk management protocol. We're adding a volatility filter that reduces position sizes by 50% when VIX exceeds 25. Effective March 1st. Need everyone to update their systems by Feb 28th."

**Expected Behavior:**
1. Read skills
2. Ask about logo preference
3. Confirm details:
   - Recipients (To:)
   - Author (From:)
   - Additional context needed
4. Create memo structure:
   - TO/FROM/DATE/RE header
   - Body sections
   - Action items
   - Branding
5. Present document

**Success Criteria:**
- Memo format with proper headers
- Clear action items
- Professional tone
- Potomac branding
- Validates successfully

---

## Test Case 4: Incomplete Information

**User Query:**
"Make me a strategy write-up"

**Expected Behavior:**
1. Recognize template is needed
2. Check for template upload
3. Ask comprehensive questions:
   - What strategy?
   - Where did idea come from?
   - What's the thesis?
   - What are the rules?
   - Do you have performance data?
   - AFL and Excel files?
4. Wait for responses before proceeding

**Success Criteria:**
- Does NOT create document with placeholder text
- Asks specific, relevant questions
- Waits for user input
- Provides guidance on what's needed

---

## Test Case 5: Logo Selection

**User Query:**
"Create a white paper on tactical asset allocation for our institutional clients. Use the formal logo."

**Expected Behavior:**
1. Interpret "formal logo" as black logo
2. Confirm: "I'll use the black logo for this formal document. Is that correct?"
3. Proceed with document creation using Potomac_Logo_Black.png
4. Build white paper structure with brand guidelines

**Success Criteria:**
- Correct logo selected and used
- Professional white paper structure
- Appropriate tone for institutional audience
- Full branding compliance

---

## Test Case 6: Template Not Uploaded

**User Query:**
"Create a strategy write-up for my trend-following system"

**Context:** Template file is NOT in /mnt/user-data/uploads

**Expected Behavior:**
1. Check for template
2. Inform user: "I don't see the Potomac strategy write-up template uploaded. Could you upload 'Potomac_WriteUp_Template_Final.docx' so I can use it? Or would you like me to create a custom document instead?"
3. Wait for user to either:
   - Upload template
   - Request custom document

**Success Criteria:**
- Clearly explains what's needed
- Offers alternatives
- Does not proceed without confirmation

---

## Test Case 7: Complex Research Report with Tables and Charts

**User Query:**
"Create a research report on diversification challenges. Include the performance table comparing S&P 500, bonds, gold, and tactical strategies. Use data from the Bear Market in Diversification document I uploaded."

**Expected Behavior:**
1. Read the uploaded PDF to extract data
2. Ask about logo preference
3. Create document with:
   - Multi-section structure
   - Properly formatted performance table
   - Yellow header row
   - Alternating row colors
   - Proper column widths
   - Data citations
4. Validate and present

**Success Criteria:**
- Data accurately extracted from source
- Table renders correctly in Word
- Yellow/gray color scheme
- Source attribution included
- Professional formatting throughout

---

## Test Case 8: Multiple Document Types in Session

**User Query Series:**
1. "Create a strategy write-up for momentum strategy"
2. "Now create a memo announcing this strategy to clients"
3. "And make a research report explaining the theory"

**Expected Behavior:**
- Correctly identify each document type
- Use template for strategy write-up
- Build custom structure for memo
- Build custom structure for research report
- Maintain context about the strategy across documents
- Apply consistent branding to all three

**Success Criteria:**
- Each document has appropriate structure
- Content is consistent across documents
- All three validate successfully
- Proper branding on each

---

## Test Case 9: Editing Existing Document

**User Query:**
"Update the strategy write-up I created earlier. Change the max drawdown from -22.3% to -19.8% and add a note about the recent optimization."

**Expected Behavior:**
1. Locate the previously created document
2. Unpack it
3. Find the performance statistics table
4. Update the specific value
5. Add the note in appropriate section
6. Repack and present

**Success Criteria:**
- Correct value updated
- Note added in logical location
- No other changes made
- Document still validates
- Formatting preserved

---

## Test Case 10: Brand Compliance Check

**User Query:**
"Create a research report but make the headers lowercase and use Helvetica font"

**Expected Behavior:**
1. Recognize request conflicts with brand guidelines
2. Politely explain: "I need to use Potomac's brand guidelines, which require Rajdhani font in ALL CAPS for headers. This ensures consistency with Potomac's professional image. I'll create the report with proper branding."
3. Create document with correct branding

**Success Criteria:**
- Uses correct fonts (Rajdhani, Quicksand)
- Headers are ALL CAPS
- Explains reasoning to user
- Document follows brand guidelines

---

## Evaluation Metrics

For each test case, score on:

1. **Correctness** (0-5): Does it produce the right output?
2. **Branding Compliance** (0-5): Are brand guidelines followed?
3. **User Experience** (0-5): Is the interaction smooth and helpful?
4. **Technical Quality** (0-5): Does the document validate and render correctly?
5. **Completeness** (0-5): Are all required elements present?

**Total Score:** 25 points per test case

**Target:** Average score of 20+ across all test cases (80% success rate)

---

## Edge Cases to Consider

- Very long strategy write-ups (>20 pages)
- Documents with multiple images
- Tables with many columns
- Special characters in content
- User provides conflicting information
- Template has been modified
- Logo files are missing
- User asks for non-standard paper size
- International date formats
- Multiple authors
