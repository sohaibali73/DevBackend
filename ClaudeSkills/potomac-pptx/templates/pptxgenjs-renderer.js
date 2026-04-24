/**
 * PptxGenJS Renderer — DeckPlanner → Slide Templates Bridge
 *
 * Converts a DeckPlan (from core/vision/deck_planner.py) into a branded
 * PowerPoint file using the PotomacSlideTemplates system.
 *
 * Usage (Node.js CLI, called from Python via subprocess):
 *
 *   node pptxgenjs-renderer.js --input plan.json --output presentation.pptx [--palette STANDARD|DARK|INVESTMENT|FUNDS]
 *
 * Input JSON format (DeckPlan.to_pptx_specs() output):
 * {
 *   "title":    "...",
 *   "audience": "investors",
 *   "tone":     "executive",
 *   "palette":  "STANDARD",
 *   "slides":   [ { slide spec objects } ]
 * }
 *
 * All layout dimensions are derived at runtime from pptx.presLayout so that
 * nothing is hardcoded.  Changing pptx.layout automatically propagates to
 * every helper that asks for W / H.
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


// ── Layout geometry helper ──────────────────────────────────────────────────

/**
 * Returns the live slide dimensions from the pptx instance.
 * All callers use this instead of any literal number so that switching
 * layouts (LAYOUT_WIDE → custom, etc.) only requires changing one line.
 *
 * @param {pptxgen} pptx
 * @returns {{ W: number, H: number }}
 */
function getDims(pptx) {
  const { width: W, height: H } = pptx.presLayout;
  return { W, H };
}

/**
 * Compute a set of commonly needed geometry values from the slide dimensions.
 * All values are in inches.  No number literal appears outside this function.
 *
 * @param {pptxgen} pptx
 * @param {object}  [opts]
 * @param {number}  [opts.marginX=0.4]   - left/right margin
 * @param {number}  [opts.marginY=0.3]   - top/bottom margin
 * @param {number}  [opts.titleH=0.65]   - standard title bar height
 * @param {number}  [opts.gap=0.15]      - standard inter-element gap
 * @returns {object}
 */
function geo(pptx, opts = {}) {
  const { W, H } = getDims(pptx);
  const mX    = opts.marginX ?? 0.40;
  const mY    = opts.marginY ?? 0.30;
  const titleH = opts.titleH ?? 0.65;
  const gap    = opts.gap    ?? 0.15;

  const contentX = mX;
  const contentY = mY + titleH + gap;
  const contentW = W - mX * 2;
  const contentH = H - contentY - mY;

  return {
    W, H,
    mX, mY,
    titleH,
    gap,
    titleX: mX,
    titleY: mY,
    titleW: W - mX * 2,
    contentX,
    contentY,
    contentW,
    contentH,
  };
}


// ── Main renderer ───────────────────────────────────────────────────────────

/**
 * Render a deck plan to a PPTX buffer/file.
 *
 * @param {object}  plan       - DeckPlan dict (title, slides[], palette, …)
 * @param {string}  [outFile]  - Optional output path. Omit to return Buffer.
 * @returns {Promise<Buffer|void>}
 */
async function renderDeckPlan(plan, outFile = null) {
  const pptx      = new pptxgen();
  const palette   = plan.palette || 'STANDARD';
  const templates = new PotomacSlideTemplates(pptx, { palette });

  // ── Presentation metadata ────────────────────────────────────────────────
  pptx.author   = plan.author   || 'Potomac';
  pptx.company  = plan.company  || 'Potomac';
  pptx.title    = plan.title    || 'Potomac Presentation';
  pptx.subject  = plan.audience || '';
  pptx.revision = '1';

  // ── Layout — LAYOUT_WIDE = 13.3 × 7.5 in ────────────────────────────────
  // All downstream code reads pptx.presLayout so this is the single source.
  pptx.layout = 'LAYOUT_WIDE';

  // ── Slide masters ────────────────────────────────────────────────────────
  PotomacSlideTemplates.defineAllMasters(pptx, palette);

  // ── Slide rendering ──────────────────────────────────────────────────────
  const slides = Array.isArray(plan.slides) ? plan.slides : [];
  const { W, H } = getDims(pptx);
  console.log(`🎨 Rendering ${slides.length} slide(s) — palette: ${palette}  layout: ${W}"×${H}"`);

  slides.forEach((spec, idx) => {
    try {
      renderSlide(pptx, templates, spec);
      console.log(`  ✓ Slide ${idx + 1}: ${spec.type} — "${spec.title || '(no title)'}"`);
    } catch (err) {
      console.error(`  ✗ Slide ${idx + 1} failed (${spec.type}): ${err.message} — falling back to content slide`);
      templates.createContentSlide(
        spec.title  || `Slide ${idx + 1}`,
        spec.bullets || spec.body_text || ''
      );
    }
  });

  // ── Output ───────────────────────────────────────────────────────────────
  if (outFile) {
    await pptx.writeFile({ fileName: outFile });
    console.log(`\n📄 Saved: ${outFile}  (${slides.length} slides)`);
    return;
  }

  return await pptx.write({ outputType: 'nodebuffer' });
}


// ── Slide router ────────────────────────────────────────────────────────────

/**
 * Route a single slide spec to the appropriate template method.
 * `pptx` is passed through so every template can call geo(pptx) and derive
 * all positions from the live presLayout — no hardcoded inches anywhere.
 *
 * @param {pptxgen}               pptx
 * @param {PotomacSlideTemplates} templates
 * @param {object}                spec
 */
function renderSlide(pptx, templates, spec) {
  const type = (spec.type || 'content').toLowerCase();

  switch (type) {

    // ── Title variants ───────────────────────────────────────────────────
    case 'title': {
      const style = spec.style || spec.background;
      if (style === 'executive' || style === 'dark') {
        return templates.createExecutiveTitleSlide(
          spec.title,
          spec.subtitle || spec.tagline || null,
          spec.tagline  || null
        );
      }
      return templates.createStandardTitleSlide(
        spec.title,
        spec.subtitle || null
      );
    }

    case 'section_divider':
      return templates.createSectionDividerSlide(
        spec.title,
        spec.description || spec.body_text || spec.subtitle || null
      );

    // ── Content variants ─────────────────────────────────────────────────
    case 'content':
      return templates.createContentSlide(
        spec.title,
        bulletOrText(spec)
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
        spec.left_content  || columnAt(spec, 0) || '',
        spec.right_content || columnAt(spec, 1) || '',
        {
          leftHeader:  spec.left_header  || null,
          rightHeader: spec.right_header || null,
        }
      );

    case 'three_column':
      return templates.createThreeColumnSlide(
        spec.title,
        spec.left_content   || columnAt(spec, 0) || '',
        spec.center_content || columnAt(spec, 1) || '',
        spec.right_content  || columnAt(spec, 2) || '',
        { headers: spec.column_headers || [] }
      );

    case 'metrics':
      return templates.createMetricSlide(
        spec.title,
        spec.metrics || bulletsToMetrics(spec.bullets),
        spec.context || null
      );

    case 'process':
      return templates.createProcessSlide(
        spec.title,
        spec.steps || bulletsToSteps(spec.bullets),
        { layout: spec.layout || 'horizontal' }
      );

    case 'quote':
      return templates.createQuoteSlide(
        spec.quote || spec.body_text || '',
        spec.attribution || spec.subtitle || null,
        spec.context     || null
      );

    case 'card_grid':
      return templates.createCardGridSlide(
        spec.title,
        spec.cards || bulletsToCards(spec.bullets)
      );

    case 'icon_grid':
      return templates.createIconGridSlide(
        spec.title,
        spec.items || bulletsToIconItems(spec.bullets)
      );

    case 'hub_spoke':
      return templates.createHubSpokeSlide(
        spec.title,
        {
          title:    spec.center_title    || 'POTOMAC',
          subtitle: spec.center_subtitle || '',
        },
        (spec.nodes || spec.columns || []).map(n =>
          typeof n === 'string' ? { label: n } : n
        )
      );

    case 'timeline':
      return templates.createTimelineSlide(
        spec.title,
        spec.milestones || bulletsToMilestones(spec.bullets)
      );

    case 'matrix_2x2':
      return templates.createMatrix2x2Slide(
        spec.title,
        spec.x_axis_label || '',
        spec.y_axis_label || '',
        spec.quadrants    || []
      );

    case 'scorecard':
      return templates.createScorecardSlide(
        spec.title,
        spec.metrics  || [],
        spec.subtitle || null
      );

    case 'comparison':
      return templates.createComparisonSlide(
        spec.title,
        spec.left_label  || 'OPTION A',
        spec.right_label || 'OPTION B',
        spec.rows   || [],
        spec.winner || null
      );

    case 'table':
      return templates.createTableSlide(
        spec.title,
        spec.headers      || spec.table_headers || [],
        spec.rows         || spec.table_rows    || [],
        {
          highlightColumn: spec.highlight_column ?? null,
          disclaimer:      spec.disclaimer       || null,
        }
      );

    case 'chart':
      return templates.createChartSlide(
        spec.title,
        spec.chart_type  || 'bar',
        spec.chart_data  || spec.data || [],
        {
          showLegend:  spec.show_legend  ?? true,
          showValue:   spec.show_value   ?? false,
          source:      spec.source       || null,
          chartColors: spec.chart_colors || null,
        }
      );

    case 'image_content':
      return templates.createImageContentSlide(
        spec.title,
        spec.image_path    || null,
        bulletOrText(spec),
        spec.image_position || 'left'
      );

    case 'image':
      return templates.createImageSlide(
        spec.image_path || null,
        spec.title      || null,
        spec.overlay    !== false
      );

    // ── Closing variants ─────────────────────────────────────────────────
    case 'closing':
      return templates.createClosingSlide(
        spec.title        || 'THANK YOU',
        spec.contact_info || null
      );

    case 'call_to_action':
    case 'cta':
      return templates.createCallToActionSlide(
        spec.title,
        spec.action_text  || spec.body_text    || '',
        spec.contact_info || 'potomac.com | (305) 824-2702 | info@potomac.com',
        spec.button_text  || 'GET STARTED'
      );

    // ── Fallback ─────────────────────────────────────────────────────────
    default:
      console.warn(`  ⚠  Unknown slide type "${type}", falling back to content slide`);
      return templates.createContentSlide(
        spec.title || 'SLIDE',
        bulletOrText(spec)
      );
  }
}


// ── Data coercion helpers ───────────────────────────────────────────────────

/**
 * Return bullets array if non-empty, else fall back to body text string.
 * @param {object} spec
 * @returns {string[]|string}
 */
function bulletOrText(spec) {
  if (Array.isArray(spec.bullets) && spec.bullets.length > 0) return spec.bullets;
  return spec.text || spec.body_text || '';
}

/**
 * Safe column accessor — returns spec.columns[idx] or empty string.
 * @param {object} spec
 * @param {number} idx
 * @returns {string}
 */
function columnAt(spec, idx) {
  return (Array.isArray(spec.columns) && spec.columns[idx]) || '';
}

/**
 * Split "VALUE : LABEL" bullets into metric objects.
 * @param {string[]} bullets
 * @returns {{ value: string, label: string }[]}
 */
function bulletsToMetrics(bullets = []) {
  return bullets.slice(0, 6).map(b => {
    const parts = String(b).split(':');
    return {
      value: parts[0].trim(),
      label: parts.slice(1).join(':').trim(),
    };
  });
}

/**
 * Convert plain bullets into numbered step objects.
 * @param {string[]} bullets
 * @returns {{ title: string, description: string }[]}
 */
function bulletsToSteps(bullets = []) {
  return bullets.slice(0, 5).map((b, i) => ({
    title:       `Step ${i + 1}`,
    description: String(b),
  }));
}

/**
 * Convert plain bullets into card objects with alternating palette colors.
 * @param {string[]} bullets
 * @returns {{ title: string, text: string, color: string }[]}
 */
function bulletsToCards(bullets = []) {
  const colors = ['yellow', 'dark', 'white', 'turquoise'];
  return bullets.slice(0, 4).map((b, i) => {
    const [head, ...rest] = String(b).split(':');
    return {
      title: head.trim(),
      text:  rest.join(':').trim(),
      color: colors[i % colors.length],
    };
  });
}

/**
 * Convert plain bullets into icon-grid item objects.
 * @param {string[]} bullets
 * @returns {{ icon: string, title: string, description: string }[]}
 */
function bulletsToIconItems(bullets = []) {
  return bullets.slice(0, 6).map((b, i) => {
    const [head, ...rest] = String(b).split(':');
    return {
      icon:        String(i + 1),
      title:       head.trim(),
      description: rest.join(':').trim(),
    };
  });
}

/**
 * Convert plain bullets into timeline milestone objects.
 * @param {string[]} bullets
 * @returns {{ label: string, status: string }[]}
 */
function bulletsToMilestones(bullets = []) {
  return bullets.slice(0, 8).map(b => ({
    label:  String(b),
    status: 'pending',
  }));
}


// ── Exported geometry utilities (consumed by slide-templates.js) ────────────
// slide-templates.js should import { geo, getDims } and use them instead of
// any literal inch values so that all slides remain layout-agnostic.

module.exports = {
  renderDeckPlan,
  renderSlide,
  // geometry helpers — re-exported so slide-templates.js can share them
  geo,
  getDims,
};


// ── CLI entry point ─────────────────────────────────────────────────────────

if (require.main === module) {
  const args = parseArgs();

  if (!args.input || !args.output) {
    console.error(
      'Usage: node pptxgenjs-renderer.js ' +
      '--input plan.json --output output.pptx ' +
      '[--palette STANDARD|DARK|INVESTMENT|FUNDS]'
    );
    process.exit(1);
  }

  const planPath = path.resolve(args.input);
  if (!fs.existsSync(planPath)) {
    console.error(`Input file not found: ${planPath}`);
    process.exit(1);
  }

  const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));

  // CLI --palette flag overrides whatever is in the JSON
  if (args.palette) plan.palette = args.palette;

  renderDeckPlan(plan, path.resolve(args.output))
    .then(() => process.exit(0))
    .catch(err => {
      console.error('Renderer error:', err.message);
      process.exit(1);
    });
}