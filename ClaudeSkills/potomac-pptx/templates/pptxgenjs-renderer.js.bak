/**
 * PptxGenJS Renderer — DeckPlanner → Slide Templates Bridge
 *
 * Converts a DeckPlan (from core/vision/deck_planner.py) into a branded
 * PowerPoint file using the PotomacSlideTemplates system.
 *
 * Usage (Node.js CLI, called from Python via subprocess):
 *
 *   node pptxgenjs-renderer.js --input plan.json --output presentation.pptx
 *
 * Input JSON format (DeckPlan.to_pptx_specs() output):
 * {
 *   "title": "...",
 *   "audience": "investors",
 *   "tone": "executive",
 *   "palette": "STANDARD",
 *   "slides": [ { slide spec objects } ]
 * }
 *
 * Each slide spec has a "type" field matching DeckPlanner VALID_SLIDE_TYPES.
 */

'use strict';

const pptxgen = require('pptxgenjs');
const path    = require('path');
const fs      = require('fs');
const { PotomacSlideTemplates } = require('./slide-templates.js');

// ── CLI argument parsing ────────────────────────────────────────────────────
function parseArgs() {
  const args   = process.argv.slice(2);
  const result = { input: '', output: '', palette: 'STANDARD' };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--input')   result.input   = args[i + 1];
    if (args[i] === '--output')  result.output  = args[i + 1];
    if (args[i] === '--palette') result.palette = args[i + 1];
  }
  return result;
}


// ── Main renderer ───────────────────────────────────────────────────────────

/**
 * Render a deck plan to a PPTX buffer/file.
 *
 * @param {Object} plan   - DeckPlan dict (title, slides[], palette, etc.)
 * @param {string} [outFile] - Optional output path. If omitted returns buffer.
 * @returns {Promise<Buffer|void>}
 */
async function renderDeckPlan(plan, outFile = null) {
  const pptx      = new pptxgen();
  const palette   = plan.palette || 'STANDARD';
  const templates = new PotomacSlideTemplates(pptx, { palette });

  // Set presentation metadata
  pptx.author   = plan.author   || 'Potomac';
  pptx.company  = plan.company  || 'Potomac';
  pptx.title    = plan.title    || 'Potomac Presentation';
  pptx.subject  = plan.audience || '';
  pptx.revision = '1';

  // Standard 10"×7.5" layout
  pptx.layout = 'LAYOUT_16x9';

  // Define slide masters
  PotomacSlideTemplates.defineAllMasters(pptx, palette);

  const slides = Array.isArray(plan.slides) ? plan.slides : [];
  console.log(`🎨 Rendering ${slides.length} slide(s) — palette: ${palette}`);

  slides.forEach((spec, idx) => {
    try {
      renderSlide(templates, spec);
      console.log(`  ✓ Slide ${idx + 1}: ${spec.type} — "${spec.title || '(no title)'}"`);
    } catch (err) {
      console.error(`  ✗ Slide ${idx + 1} failed (${spec.type}): ${err.message} — falling back to content slide`);
      templates.createContentSlide(spec.title || `Slide ${idx + 1}`, spec.bullets || spec.body_text || '');
    }
  });

  if (outFile) {
    await pptx.writeFile({ fileName: outFile });
    console.log(`\n📄 Saved: ${outFile}  (${slides.length} slides)`);
    return;
  }

  return await pptx.write({ outputType: 'nodebuffer' });
}


/**
 * Route a single slide spec to the appropriate template method.
 * Handles all DeckPlanner VALID_SLIDE_TYPES.
 */
function renderSlide(templates, spec) {
  const type = spec.type || 'content';

  switch (type) {

    // ── Title variants ────────────────────────────────────────────────────
    case 'title': {
      const style = spec.style || spec.background;
      if (style === 'executive' || style === 'dark') {
        return templates.createExecutiveTitleSlide(
          spec.title, spec.subtitle || spec.tagline, spec.tagline
        );
      }
      return templates.createStandardTitleSlide(spec.title, spec.subtitle);
    }

    case 'section_divider':
      return templates.createSectionDividerSlide(
        spec.title,
        spec.description || spec.body_text || spec.subtitle || null
      );

    // ── Content variants ──────────────────────────────────────────────────
    case 'content':
      return templates.createContentSlide(
        spec.title,
        spec.bullets && spec.bullets.length > 0 ? spec.bullets : (spec.text || spec.body_text || '')
      );

    case 'executive_summary':
      return templates.createExecutiveSummarySlide(
        spec.headline || spec.title,
        spec.supporting_points || spec.bullets || [],
        spec.body_text || null
      );

    case 'two_column':
      return templates.createTwoColumnSlide(
        spec.title,
        spec.left_content  || (spec.columns && spec.columns[0]) || '',
        spec.right_content || (spec.columns && spec.columns[1]) || '',
        {
          leftHeader:  spec.left_header  || null,
          rightHeader: spec.right_header || null,
        }
      );

    case 'three_column':
      return templates.createThreeColumnSlide(
        spec.title,
        (spec.columns && spec.columns[0]) || spec.left_content   || '',
        (spec.columns && spec.columns[1]) || spec.center_content || '',
        (spec.columns && spec.columns[2]) || spec.right_content  || '',
        { headers: spec.column_headers || [] }
      );

    case 'metrics':
      return templates.createMetricSlide(
        spec.title,
        spec.metrics || _bulletsToMetrics(spec.bullets),
        spec.context || null
      );

    case 'process':
      return templates.createProcessSlide(
        spec.title,
        spec.steps || _bulletsToSteps(spec.bullets),
        { layout: spec.layout || 'horizontal' }
      );

    case 'quote':
      return templates.createQuoteSlide(
        spec.quote || spec.body_text || '',
        spec.attribution || spec.subtitle || null,
        spec.context || null
      );

    // ── New DeckPlanner types ─────────────────────────────────────────────
    case 'card_grid':
      return templates.createCardGridSlide(
        spec.title,
        spec.cards || _bulletsToCards(spec.bullets)
      );

    case 'icon_grid':
      return templates.createIconGridSlide(
        spec.title,
        spec.items || _bulletsToIconItems(spec.bullets)
      );

    case 'hub_spoke':
      return templates.createHubSpokeSlide(
        spec.title,
        { title: spec.center_title || 'POTOMAC', subtitle: spec.center_subtitle || '' },
        (spec.nodes || spec.columns || []).map(n =>
          typeof n === 'string' ? { label: n } : n
        )
      );

    case 'timeline':
      return templates.createTimelineSlide(
        spec.title,
        spec.milestones || _bulletsToMilestones(spec.bullets)
      );

    case 'matrix_2x2':
      return templates.createMatrix2x2Slide(
        spec.title,
        spec.x_axis_label || '',
        spec.y_axis_label || '',
        spec.quadrants || []
      );

    case 'scorecard':
      return templates.createScorecardSlide(
        spec.title,
        spec.metrics || [],
        spec.subtitle || null
      );

    case 'comparison':
      return templates.createComparisonSlide(
        spec.title,
        spec.left_label  || 'OPTION A',
        spec.right_label || 'OPTION B',
        spec.rows || [],
        spec.winner || null
      );

    case 'table':
      return templates.createTableSlide(
        spec.title,
        spec.headers      || spec.table_headers || [],
        spec.rows         || spec.table_rows    || [],
        { highlightColumn: spec.highlight_column, disclaimer: spec.disclaimer }
      );

    case 'chart':
      return templates.createChartSlide(
        spec.title,
        spec.chart_type || 'bar',
        spec.chart_data || spec.data || [],
        {
          showLegend:  spec.show_legend,
          showValue:   spec.show_value,
          source:      spec.source || null,
          chartColors: spec.chart_colors || null,
        }
      );

    case 'image_content':
      return templates.createImageContentSlide(
        spec.title,
        spec.image_path || null,
        spec.bullets && spec.bullets.length > 0 ? spec.bullets : (spec.text || spec.body_text || ''),
        spec.image_position || 'left'
      );

    case 'image':
      return templates.createImageSlide(
        spec.image_path || null,
        spec.title || null,
        spec.overlay !== false
      );

    // ── Closing variants ──────────────────────────────────────────────────
    case 'closing':
      return templates.createClosingSlide(
        spec.title || 'THANK YOU',
        spec.contact_info || null
      );

    case 'call_to_action':
    case 'cta':
      return templates.createCallToActionSlide(
        spec.title,
        spec.action_text || spec.body_text || '',
        spec.contact_info || 'potomac.com | (305) 824-2702 | info@potomac.com',
        spec.button_text || 'GET STARTED'
      );

    // ── Fallback ──────────────────────────────────────────────────────────
    default:
      console.warn(`  ⚠  Unknown slide type "${type}", using content slide`);
      return templates.createContentSlide(
        spec.title || 'SLIDE',
        spec.bullets && spec.bullets.length > 0 ? spec.bullets : (spec.body_text || spec.text || '')
      );
  }
}


// ── Data coercion helpers ───────────────────────────────────────────────────

function _bulletsToMetrics(bullets = []) {
  return bullets.slice(0, 6).map(b => {
    const parts = String(b).split(':');
    return { value: parts[0].trim(), label: (parts[1] || '').trim() };
  });
}

function _bulletsToSteps(bullets = []) {
  return bullets.slice(0, 5).map((b, i) => ({
    title: `Step ${i + 1}`,
    description: String(b),
  }));
}

function _bulletsToCards(bullets = []) {
  const colors = ['yellow', 'dark', 'white', 'turquoise'];
  return bullets.slice(0, 4).map((b, i) => ({
    title: String(b).split(':')[0].trim(),
    text:  String(b).split(':').slice(1).join(':').trim() || '',
    color: colors[i % 4],
  }));
}

function _bulletsToIconItems(bullets = []) {
  return bullets.slice(0, 6).map((b, i) => ({
    icon:        String(i + 1),
    title:       String(b).split(':')[0].trim(),
    description: String(b).split(':').slice(1).join(':').trim() || '',
  }));
}

function _bulletsToMilestones(bullets = []) {
  return bullets.slice(0, 8).map(b => ({
    label:  String(b),
    status: 'pending',
  }));
}


// ── CLI entry point ─────────────────────────────────────────────────────────
if (require.main === module) {
  const args = parseArgs();

  if (!args.input || !args.output) {
    console.error('Usage: node pptxgenjs-renderer.js --input plan.json --output output.pptx [--palette STANDARD|DARK|INVESTMENT|FUNDS]');
    process.exit(1);
  }

  const planPath = path.resolve(args.input);
  if (!fs.existsSync(planPath)) {
    console.error(`Input file not found: ${planPath}`);
    process.exit(1);
  }

  const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
  if (args.palette) plan.palette = args.palette;

  renderDeckPlan(plan, path.resolve(args.output))
    .then(() => process.exit(0))
    .catch(err => {
      console.error('Renderer error:', err.message);
      process.exit(1);
    });
}


module.exports = { renderDeckPlan, renderSlide };
