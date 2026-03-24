// Example: Creating a Potomac Research Report
// This demonstrates how to build a research report from scratch with proper branding

const { Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
        AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType, 
        LevelFormat, PageBreak } = require('docx');
const fs = require('fs');

// Load logo (adjust path as needed)
const logoPath = '/mnt/user-data/uploads/Potomac_Logo.png';
const logoBuffer = fs.readFileSync(logoPath);

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { 
          font: "Quicksand", 
          size: 22, // 11pt
          color: "212121" 
        },
        paragraph: {
          spacing: { line: 360 } // 1.5 line spacing
        }
      }
    },
    paragraphStyles: [
      // Heading 1 - Main sections
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: {
          font: "Rajdhani",
          size: 36, // 18pt
          bold: true,
          color: "212121",
          allCaps: true
        },
        paragraph: {
          spacing: { before: 480, after: 240 },
          outlineLevel: 0
        }
      },
      // Heading 2 - Subsections
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: {
          font: "Rajdhani",
          size: 32, // 16pt
          bold: true,
          color: "212121",
          allCaps: true
        },
        paragraph: {
          spacing: { before: 360, after: 180 },
          outlineLevel: 1
        }
      },
      // Heading 3 - Sub-subsections
      {
        id: "Heading3",
        name: "Heading 3",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: {
          font: "Rajdhani",
          size: 28, // 14pt
          bold: true,
          color: "212121",
          allCaps: true
        },
        paragraph: {
          spacing: { before: 240, after: 120 },
          outlineLevel: 2
        }
      }
    ]
  },
  numbering: {
    config: [
      {
        reference: "potomac-bullets",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: {
              paragraph: {
                indent: { left: 720, hanging: 360 }
              }
            }
          }
        ]
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: {
          width: 12240,   // US Letter
          height: 15840
        },
        margin: {
          top: 1440,
          right: 1440,
          bottom: 1440,
          left: 1440
        }
      }
    },
    children: [
      // ===== HEADER SECTION =====
      
      // Logo
      new Paragraph({
        alignment: AlignmentType.LEFT,
        children: [
          new ImageRun({
            data: logoBuffer,
            transformation: {
              width: 200,
              height: 41
            },
            type: "png"
          })
        ],
        spacing: { after: 480 }
      }),

      // ===== TITLE =====
      
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("BEAR MARKET IN DIVERSIFICATION")]
      }),

      // Date and metadata
      new Paragraph({
        children: [
          new TextRun({
            text: "February 2026",
            italics: true,
            size: 20
          })
        ],
        spacing: { after: 360 }
      }),

      // ===== EXECUTIVE SUMMARY =====
      
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("EXECUTIVE SUMMARY")]
      }),

      new Paragraph({
        children: [
          new TextRun("The most recent 10-15 years have been a historic run for the U.S. stock market, particularly the S&P 500. During this period, traditional diversifiers have underperformed significantly, both on an absolute basis and when investors needed them most.")
        ],
        spacing: { after: 240 }
      }),

      // ===== KEY FINDINGS =====
      
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("KEY FINDINGS")]
      }),

      new Paragraph({
        numbering: { reference: "potomac-bullets", level: 0 },
        children: [
          new TextRun("10-year rolling returns for the S&P 500 are at historic peaks, comparable only to the Roaring Twenties, Nifty Fifty era, and Dot-com boom")
        ]
      }),

      new Paragraph({
        numbering: { reference: "potomac-bullets", level: 0 },
        children: [
          new TextRun("Traditional diversifiers (bonds, gold, commodities, managed futures) have severely underperformed relative to stocks")
        ]
      }),

      new Paragraph({
        numbering: { reference: "potomac-bullets", level: 0 },
        children: [
          new TextRun("The 2022 bond market crash exposed the vulnerability of stock-bond diversification")
        ]
      }),

      new Paragraph({
        numbering: { reference: "potomac-bullets", level: 0 },
        children: [
          new TextRun("Historical patterns suggest future returns are likely to be more challenging than the recent past")
        ],
        spacing: { after: 360 }
      }),

      // ===== ANALYSIS SECTION =====
      
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("ANALYSIS")]
      }),

      new Paragraph({
        heading: HeadingLevel.HEADING_3,
        children: [new TextRun("ROLLING RETURNS CONTEXT")]
      }),

      new Paragraph({
        children: [
          new TextRun("A rolling return is a backward-looking measure which quotes the compounded yearly return from exactly 10 years before to the latest data point. This metric reveals important patterns:")
        ],
        spacing: { after: 240 }
      }),

      new Paragraph({
        numbering: { reference: "potomac-bullets", level: 0 },
        children: [
          new TextRun({
            text: "Mean reversion: ",
            bold: true
          }),
          new TextRun("When rolling returns reach extremes, they tend to revert to historical averages")
        ]
      }),

      new Paragraph({
        numbering: { reference: "potomac-bullets", level: 0 },
        children: [
          new TextRun({
            text: "Cyclicality: ",
            bold: true
          }),
          new TextRun("Periods of high returns are followed by periods of below-average returns")
        ]
      }),

      new Paragraph({
        numbering: { reference: "potomac-bullets", level: 0 },
        children: [
          new TextRun({
            text: "Current position: ",
            bold: true
          }),
          new TextRun("Today's 10-year rolling returns are in the top 5% historically")
        ],
        spacing: { after: 360 }
      }),

      // ===== PERFORMANCE TABLE =====
      
      new Paragraph({
        heading: HeadingLevel.HEADING_3,
        children: [new TextRun("TRADITIONAL DIVERSIFIERS PERFORMANCE")]
      }),

      new Paragraph({
        children: [
          new TextRun("The table below shows the stark underperformance of traditional diversification strategies:")
        ],
        spacing: { after: 120 }
      }),

      // Create table
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2800, 1400, 1400, 1400, 1400, 960],
        rows: [
          // Header row
          new TableRow({
            children: [
              new TableCell({
                width: { size: 2800, type: WidthType.DXA },
                shading: { fill: "FEC00F", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({
                  children: [new TextRun({ text: "Asset", bold: true, color: "212121" })]
                })]
              }),
              new TableCell({
                width: { size: 1400, type: WidthType.DXA },
                shading: { fill: "FEC00F", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({
                  children: [new TextRun({ text: "10-Year", bold: true, color: "212121" })]
                })]
              }),
              new TableCell({
                width: { size: 1400, type: WidthType.DXA },
                shading: { fill: "FEC00F", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({
                  children: [new TextRun({ text: "15-Year", bold: true, color: "212121" })]
                })]
              }),
              new TableCell({
                width: { size: 1400, type: WidthType.DXA },
                shading: { fill: "FEC00F", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({
                  children: [new TextRun({ text: "Max DD", bold: true, color: "212121" })]
                })]
              }),
              new TableCell({
                width: { size: 1400, type: WidthType.DXA },
                shading: { fill: "FEC00F", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({
                  children: [new TextRun({ text: "Correlation", bold: true, color: "212121" })]
                })]
              }),
              new TableCell({
                width: { size: 960, type: WidthType.DXA },
                shading: { fill: "FEC00F", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({
                  children: [new TextRun({ text: "Beta", bold: true, color: "212121" })]
                })]
              })
            ]
          }),
          // Data rows
          createDataRow("S&P 500", "11.10%", "11.76%", "-33.92%", "1.00", "1.00", false),
          createDataRow("Gold (GLD)", "-1.26%", "-0.42%", "-23.31%", "0.01", "0.00", true),
          createDataRow("Bonds (AGG)", "-1.14%", "2.63%", "-48.35%", "-0.29", "-0.26", false),
          createDataRow("20Y Treasury", "7.88%", "5.59%", "-45.56%", "0.00", "0.00", true),
          createDataRow("Commodities", "3.00%", "0.04%", "-65.71%", "0.33", "0.34", false),
          createDataRow("Managed Futures", "3.54%", "2.34%", "-23.23%", "-0.15", "-0.08", true)
        ]
      }),

      new Paragraph({
        children: [
          new TextRun({
            text: "Source: FastTrack.net as of 12/31/2024",
            size: 18,
            italics: true
          })
        ],
        spacing: { before: 120, after: 360 }
      }),

      // ===== CONCLUSION =====
      
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("CONCLUSION")]
      }),

      new Paragraph({
        children: [
          new TextRun("The 'bear market in diversification' has left many investors questioning the value of traditional diversification strategies. As Meb Faber noted, despite well-researched and thoughtful implementation, diversified portfolios 'got steamrolled by the S&P 500.'")
        ],
        spacing: { after: 240 }
      }),

      new Paragraph({
        children: [
          new TextRun("However, history suggests that this outperformance is cyclical. Previous periods of extreme rolling returns—the Roaring Twenties, Nifty Fifty, and Dot-com boom—were all followed by significant mean reversion. Tactical strategies that actively manage risk may provide a more effective diversification approach than traditional static allocations.")
        ],
        spacing: { after: 480 }
      }),

      // ===== DISCLOSURE SECTION =====
      
      // Yellow divider line
      new Paragraph({
        border: {
          top: {
            style: BorderStyle.SINGLE,
            size: 6,
            color: "FEC00F"
          }
        },
        spacing: { before: 240, after: 240 }
      }),

      new Paragraph({
        children: [
          new TextRun({
            text: "IMPORTANT DISCLOSURES",
            bold: true,
            size: 22,
            font: "Rajdhani",
            allCaps: true
          })
        ],
        spacing: { after: 180 }
      }),

      new Paragraph({
        children: [
          new TextRun({
            text: "This research paper is prepared by and is the property of Potomac. It is circulated for informational and educational purposes only. There is no consideration given to the specific investment needs, objectives, or tolerances of any of the recipients. Additionally, the actual investment positions of Potomac may, and often will, vary from the conclusions discussed herein based on various factors, such as client investment restrictions, portfolio rebalancing, and transaction costs, among others. Recipients should consult their own advisors, including tax advisors, before making any investment decisions.",
            size: 18
          })
        ],
        spacing: { after: 240 }
      }),

      new Paragraph({
        children: [
          new TextRun({
            text: "Past performance is not a guide to future performance; future returns are not guaranteed, and a complete loss of original capital may occur. For complete disclosures, please visit ",
            size: 18
          }),
          new TextRun({
            text: "potomac.com/disclosures",
            size: 18,
            bold: true
          })
        ]
      })
    ]
  }]
});

// Helper function to create table rows
function createDataRow(asset, tenYear, fifteenYear, maxDD, corr, beta, isAlternate) {
  const bgColor = isAlternate ? "F5F5F5" : "FFFFFF";
  const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
  const borders = { top: border, bottom: border, left: border, right: border };

  return new TableRow({
    children: [
      new TableCell({
        width: { size: 2800, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        borders: borders,
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: asset })]
        })]
      }),
      new TableCell({
        width: { size: 1400, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        borders: borders,
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: tenYear })]
        })]
      }),
      new TableCell({
        width: { size: 1400, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        borders: borders,
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: fifteenYear })]
        })]
      }),
      new TableCell({
        width: { size: 1400, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        borders: borders,
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: maxDD })]
        })]
      }),
      new TableCell({
        width: { size: 1400, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        borders: borders,
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: corr })]
        })]
      }),
      new TableCell({
        width: { size: 960, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        borders: borders,
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: beta })]
        })]
      })
    ]
  });
}

// Save document
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('/mnt/user-data/outputs/Potomac_Research_Report.docx', buffer);
  console.log('Document created successfully!');
});
