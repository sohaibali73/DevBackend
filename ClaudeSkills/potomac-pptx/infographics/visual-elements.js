/**
 * Potomac Visual Elements & Infographics - Phase 3
 * Converts complex Adobe Illustrator infographics to native PowerPoint shapes
 * 
 * This system recreates the firm structure diagrams, process flows, 
 * and visual communication elements as scalable PowerPoint graphics.
 */

const { POTOMAC_COLORS } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS } = require('../brand-assets/fonts/potomac-fonts.js');

class PotomacVisualElements {
  constructor(pptxGenerator, options = {}) {
    this.pptx = pptxGenerator;
    this.options = options;
    
    // Standard visual element styles
    this.elementStyles = {
      primaryIcon: {
        fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW },
        line: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY, width: 2 }
      },
      secondaryIcon: {
        fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE },
        line: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY, width: 1 }
      },
      connector: {
        line: { color: POTOMAC_COLORS.TONES.GRAY_40, width: 2, dashType: 'solid' }
      },
      accentConnector: {
        line: { color: POTOMAC_COLORS.PRIMARY.YELLOW, width: 3, dashType: 'solid' }
      },
      textLabel: {
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 12,
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center',
        valign: 'middle'
      }
    };
  }

  /**
   * Create Investment Process Flow (Simplified)
   * Visual representation of the investment methodology
   */
  createInvestmentProcessFlow(slide, config = {}) {
    console.log('🔄 Creating Investment Process Flow...');
    
    const settings = {
      startX: 0.8,
      startY: 2.5,
      width: 8.4,
      height: 2.5,
      ...config
    };
    
    const processSteps = [
      { title: 'RESEARCH', desc: 'Market Analysis\n& Due Diligence' },
      { title: 'STRATEGY', desc: 'Portfolio Design\n& Construction' },
      { title: 'EXECUTION', desc: 'Trade Implementation\n& Monitoring' },
      { title: 'REVIEW', desc: 'Performance Analysis\n& Optimization' }
    ];
    
    const stepWidth = settings.width / processSteps.length;
    
    processSteps.forEach((step, index) => {
      const stepX = settings.startX + index * stepWidth + stepWidth / 2;
      const stepY = settings.startY;
      
      // Step circle
      slide.addShape('ellipse', {
        x: stepX - 0.4,
        y: stepY - 0.4,
        w: 0.8,
        h: 0.8,
        fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW },
        line: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY, width: 2 }
      });
      
      // Step number
      slide.addText((index + 1).toString(), {
        x: stepX - 0.4,
        y: stepY - 0.4,
        w: 0.8,
        h: 0.8,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 24,
        fontWeight: 'bold',
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center',
        valign: 'middle'
      });
      
      // Step title
      slide.addText(step.title, {
        x: stepX - 0.6,
        y: stepY + 0.6,
        w: 1.2,
        h: 0.4,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 14,
        fontWeight: 'bold',
        color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
        align: 'center'
      });
      
      // Step description
      slide.addText(step.desc, {
        x: stepX - 0.8,
        y: stepY + 1.1,
        w: 1.6,
        h: 1,
        fontFace: POTOMAC_FONTS.BODY.family,
        fontSize: 11,
        color: POTOMAC_COLORS.TONES.GRAY_60,
        align: 'center',
        lineSpacing: 16
      });
      
      // Connection line (except for last step)
      if (index < processSteps.length - 1) {
        const lineX = stepX + 0.5;
        const nextStepX = settings.startX + (index + 1) * stepWidth + stepWidth / 2 - 0.5;
        
        slide.addShape('line', {
          x: lineX,
          y: stepY,
          w: nextStepX - lineX,
          h: 0,
          line: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE, width: 3 }
        });
      }
    });
    
    // Add process flow title
    slide.addText('POTOMAC INVESTMENT PROCESS', {
      x: settings.startX,
      y: settings.startY - 1,
      w: settings.width,
      h: 0.6,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 20,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create Strategy Performance Visualization (Simplified)
   * Bull/Bear market performance comparison
   */
  createStrategyPerformanceViz(slide, data, config = {}) {
    console.log('📈 Creating Strategy Performance Visualization...');
    
    const settings = {
      startX: 1,
      startY: 1.5,
      width: 8,
      height: 4,
      ...config
    };
    
    // Performance data
    const performanceData = data || {
      bullMarket: { return: '+18.5%', period: '2021-2022' },
      bearMarket: { return: '+3.2%', period: '2022-2023' },
      benchmark: { bull: '+12.8%', bear: '-15.6%' }
    };
    
    // Bull market section (left side)
    slide.addShape('rect', {
      x: settings.startX,
      y: settings.startY,
      w: settings.width / 2 - 0.2,
      h: settings.height,
      fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE, transparency: 20 },
      line: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE, width: 2 }
    });
    
    // Bear market section (right side)
    slide.addShape('rect', {
      x: settings.startX + settings.width / 2 + 0.2,
      y: settings.startY,
      w: settings.width / 2 - 0.2,
      h: settings.height,
      fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW, transparency: 20 },
      line: { color: POTOMAC_COLORS.PRIMARY.YELLOW, width: 2 }
    });
    
    // Bull market content
    slide.addText('BULL MARKET\nPERFORMANCE', {
      x: settings.startX + 0.2,
      y: settings.startY + 0.3,
      w: settings.width / 2 - 0.4,
      h: 0.8,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 16,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    slide.addText(performanceData.bullMarket.return, {
      x: settings.startX + 0.2,
      y: settings.startY + 1.4,
      w: settings.width / 2 - 0.4,
      h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 32,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.SECONDARY.TURQUOISE,
      align: 'center',
      valign: 'middle'
    });
    
    // Bear market content
    slide.addText('BEAR MARKET\nPERFORMANCE', {
      x: settings.startX + settings.width / 2 + 0.4,
      y: settings.startY + 0.3,
      w: settings.width / 2 - 0.4,
      h: 0.8,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 16,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    slide.addText(performanceData.bearMarket.return, {
      x: settings.startX + settings.width / 2 + 0.4,
      y: settings.startY + 1.4,
      w: settings.width / 2 - 0.4,
      h: 1,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 32,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.YELLOW,
      align: 'center',
      valign: 'middle'
    });
    
    // Benchmark comparison
    slide.addText(`Benchmark: ${performanceData.benchmark.bull}`, {
      x: settings.startX + 0.2,
      y: settings.startY + 2.8,
      w: settings.width / 2 - 0.4,
      h: 0.4,
      fontFace: POTOMAC_FONTS.BODY.family,
      fontSize: 10,
      color: POTOMAC_COLORS.TONES.GRAY_60,
      align: 'center'
    });
    
    slide.addText(`Benchmark: ${performanceData.benchmark.bear}`, {
      x: settings.startX + settings.width / 2 + 0.4,
      y: settings.startY + 2.8,
      w: settings.width / 2 - 0.4,
      h: 0.4,
      fontFace: POTOMAC_FONTS.BODY.family,
      fontSize: 10,
      color: POTOMAC_COLORS.TONES.GRAY_60,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create Communication Flow Network (Simplified)
   * Visual representation of communication flow
   */
  createCommunicationFlow(slide, config = {}) {
    console.log('💬 Creating Communication Flow Diagram...');
    
    const settings = {
      startX: 1,
      startY: 1.8,
      width: 8,
      height: 3.5,
      ...config
    };
    
    // Communication nodes (simplified without complex connections)
    const nodes = [
      { label: 'CLIENT', x: settings.startX + 1, y: settings.startY + 1.5, type: 'client' },
      { label: 'ADVISOR', x: settings.startX + 4, y: settings.startY + 0.5, type: 'advisor' },
      { label: 'POTOMAC', x: settings.startX + 7, y: settings.startY + 1.5, type: 'potomac' },
      { label: 'RESEARCH', x: settings.startX + 4, y: settings.startY + 2.5, type: 'research' }
    ];
    
    // Add nodes
    nodes.forEach(node => {
      const nodeColor = node.type === 'potomac' ? POTOMAC_COLORS.PRIMARY.YELLOW : 
                      node.type === 'advisor' ? POTOMAC_COLORS.SECONDARY.TURQUOISE :
                      POTOMAC_COLORS.TONES.GRAY_60;
      
      // Node circle
      slide.addShape('ellipse', {
        x: node.x - 0.5,
        y: node.y - 0.4,
        w: 1,
        h: 0.8,
        fill: { color: nodeColor },
        line: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY, width: 2 }
      });
      
      // Node label
      slide.addText(node.label, {
        x: node.x - 0.5,
        y: node.y - 0.4,
        w: 1,
        h: 0.8,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 10,
        fontWeight: 'bold',
        color: node.type === 'potomac' ? POTOMAC_COLORS.PRIMARY.DARK_GRAY : POTOMAC_COLORS.PRIMARY.WHITE,
        align: 'center',
        valign: 'middle'
      });
    });
    
    // Add title
    slide.addText('COMMUNICATION & COLLABORATION NETWORK', {
      x: settings.startX,
      y: settings.startY - 0.8,
      w: settings.width,
      h: 0.6,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 18,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create Simple Network Diagram (Simplified)
   * Simplified version of firm structure
   */
  createFirmStructureInfographic(slide, config = {}) {
    console.log('🏗️ Creating Firm Structure Network Diagram...');
    
    const settings = {
      startX: 0.5,
      startY: 1.5,
      width: 9,
      height: 4.5,
      ...config
    };
    
    // Central hub (Potomac core)
    const centerX = settings.startX + settings.width / 2;
    const centerY = settings.startY + settings.height / 2;
    
    // Central Potomac hub
    slide.addShape('ellipse', {
      x: centerX - 0.8,
      y: centerY - 0.6,
      w: 1.6,
      h: 1.2,
      fill: { color: POTOMAC_COLORS.PRIMARY.YELLOW },
      line: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY, width: 3 }
    });
    
    slide.addText('POTOMAC', {
      x: centerX - 0.8,
      y: centerY - 0.6,
      w: 1.6,
      h: 1.2,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 14,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center',
      valign: 'middle'
    });
    
    // Connected service nodes (simplified)
    const serviceNodes = [
      { label: 'INVESTMENT\nSTRATEGIES', x: centerX - 2.5, y: centerY - 1.2 },
      { label: 'RESEARCH &\nANALYTICS', x: centerX + 2.5, y: centerY - 1.2 },
      { label: 'TAMP\nPLATFORMS', x: centerX - 2.5, y: centerY + 1.2 },
      { label: 'GUARDRAILS\nTECHNOLOGY', x: centerX + 2.5, y: centerY + 1.2 }
    ];
    
    // Add service nodes
    serviceNodes.forEach(node => {
      slide.addShape('ellipse', {
        x: node.x - 0.6,
        y: node.y - 0.5,
        w: 1.2,
        h: 1,
        fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE },
        line: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY, width: 2 }
      });
      
      slide.addText(node.label, {
        x: node.x - 0.6,
        y: node.y - 0.5,
        w: 1.2,
        h: 1,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 9,
        fontWeight: 'bold',
        color: POTOMAC_COLORS.PRIMARY.WHITE,
        align: 'center',
        valign: 'middle'
      });
    });
    
    // Add title
    slide.addText('POTOMAC FIRM STRUCTURE & CAPABILITIES', {
      x: settings.startX,
      y: settings.startY - 0.8,
      w: settings.width,
      h: 0.6,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 24,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }

  /**
   * Create OCIO Triangle Visualization (Simplified)
   * Simplified version of OCIO triangle
   */
  createOCIOTriangle(slide, config = {}) {
    console.log('🔺 Creating OCIO Triangle Visualization...');
    
    const settings = {
      centerX: 5,
      centerY: 3.5,
      size: 2.5,
      ...config
    };
    
    // Triangle labels positioned around the triangle
    const labels = [
      { text: 'INVESTMENT\nSTRATEGY', x: settings.centerX, y: settings.centerY - 1.5 },
      { text: 'RISK\nMANAGEMENT', x: settings.centerX - 2, y: settings.centerY + 1 },
      { text: 'PERFORMANCE\nMONITORING', x: settings.centerX + 2, y: settings.centerY + 1 }
    ];
    
    labels.forEach(label => {
      // Label background circle
      slide.addShape('ellipse', {
        x: label.x - 0.6,
        y: label.y - 0.4,
        w: 1.2,
        h: 0.8,
        fill: { color: POTOMAC_COLORS.SECONDARY.TURQUOISE },
        line: { color: POTOMAC_COLORS.PRIMARY.DARK_GRAY, width: 1 }
      });
      
      // Label text
      slide.addText(label.text, {
        x: label.x - 0.6,
        y: label.y - 0.4,
        w: 1.2,
        h: 0.8,
        fontFace: POTOMAC_FONTS.HEADERS.family,
        fontSize: 10,
        fontWeight: 'bold',
        color: POTOMAC_COLORS.PRIMARY.WHITE,
        align: 'center',
        valign: 'middle'
      });
    });
    
    // Center OCIO text
    slide.addText('OCIO', {
      x: settings.centerX - 0.5,
      y: settings.centerY - 0.3,
      w: 1,
      h: 0.6,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 20,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center',
      valign: 'middle'
    });
    
    // Title
    slide.addText('OUTSOURCED CHIEF INVESTMENT OFFICER MODEL', {
      x: 1,
      y: 0.8,
      w: 8,
      h: 0.6,
      fontFace: POTOMAC_FONTS.HEADERS.family,
      fontSize: 18,
      fontWeight: 'bold',
      color: POTOMAC_COLORS.PRIMARY.DARK_GRAY,
      align: 'center'
    });
    
    return slide;
  }
}

// Export visual elements system
module.exports = {
  PotomacVisualElements
};