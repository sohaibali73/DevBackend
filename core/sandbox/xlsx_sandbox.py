"""
XLSX Sandbox
============
Generates Potomac-branded Excel workbooks (.xlsx) entirely in Python using
``openpyxl``.  No Node.js, no subprocess — runs directly in-process.

The sandbox implements the full Potomac brand palette and spreadsheet standards
from ``ClaudeSkills/potomac-xlsx/SKILL.md``:
  - Yellow (#FEC00F) column headers, title block, and accent fills
  - Dark-gray (#212121) body text, Calibri font
  - Zebra-striped data rows, thin borders, yellow footers
  - Optional DISCLOSURES sheet

Usage
-----
    from core.sandbox.xlsx_sandbox import XlsxSandbox
    from core.file_store import store_file

    sandbox = XlsxSandbox()
    result  = sandbox.generate(spec_dict)
    if result.success:
        entry = store_file(result.data, result.filename, "xlsx", "generate_xlsx")
        download_url = f"/files/{entry.file_id}/download"
"""

from __future__ import annotations

import io
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Potomac Brand Constants
# =============================================================================

_YELLOW        = "FEC00F"   # Primary yellow — headers, accent
_DARK_GRAY     = "212121"   # All body text
_YELLOW_LIGHT  = "FEE896"   # Subheader / subtitle fill
_ROW_ALT       = "F5F5F5"   # Alternating row background
_WHITE         = "FFFFFF"   # Primary row background
_PINK          = "EB2F5C"   # Risk / alert (use sparingly)
_TEAL          = "00DED1"   # Investment Strategies only (use sparingly)

# Tab color defaults by sheet position
_TAB_COLORS = {0: _YELLOW, 1: _DARK_GRAY, 2: _DARK_GRAY, 3: _PINK}


# =============================================================================
# Result dataclass
# =============================================================================

class XlsxResult:
    """Lightweight result container from XlsxSandbox.generate()."""
    __slots__ = ("success", "data", "filename", "error", "exec_time_ms")

    def __init__(
        self,
        success: bool,
        data: Optional[bytes] = None,
        filename: Optional[str] = None,
        error: Optional[str] = None,
        exec_time_ms: float = 0.0,
    ):
        self.success      = success
        self.data         = data
        self.filename     = filename
        self.error        = error
        self.exec_time_ms = exec_time_ms


# =============================================================================
# XlsxSandbox
# =============================================================================

class XlsxSandbox:
    """
    Builds Potomac-branded Excel workbooks from a structured spec dict.

    The spec describes one or more sheets; no code generation by the LLM is
    required.  All brand styling is applied automatically.

    Thread safety
    -------------
    ``generate()`` creates its own Workbook instance per call — no shared
    mutable state.  Multiple concurrent calls are safe.
    """

    def generate(self, spec: Dict[str, Any]) -> XlsxResult:
        """
        Generate a ``.xlsx`` workbook from *spec*.

        Parameters
        ----------
        spec : dict
            Workbook specification.  Required keys: ``title``, ``sheets``.
            See the ``generate_xlsx`` tool schema for the full definition.

        Returns
        -------
        XlsxResult
        """
        start = time.time()
        try:
            from openpyxl import Workbook
            from openpyxl.styles import (
                Alignment, Border, Font, PatternFill, Side,
            )
            from openpyxl.utils import get_column_letter

            wb = Workbook()
            # Remove the default blank sheet added by openpyxl
            if wb.active and wb.active.title == "Sheet":
                del wb[wb.active.title]

            doc_title    = str(spec.get("title", "POTOMAC REPORT"))
            doc_subtitle = str(spec.get("subtitle", ""))
            sheets_spec  = spec.get("sheets", [])

            if not sheets_spec:
                # Flat spec — wrap in single sheet
                sheets_spec = [{
                    "name":    "SHEET1",
                    "columns": spec.get("columns", []),
                    "rows":    spec.get("rows", []),
                }]

            for idx, sheet_spec in enumerate(sheets_spec):
                name = str(sheet_spec.get("name", f"SHEET{idx + 1}")).upper()[:31]
                ws   = wb.create_sheet(name)

                # ── Tab color ──────────────────────────────────────────────
                tab_color = sheet_spec.get("tab_color") or _TAB_COLORS.get(idx, _DARK_GRAY)
                ws.sheet_properties.tabColor = tab_color

                columns    = [str(c) for c in sheet_spec.get("columns", [])]
                col_count  = len(columns) or 1
                rows_data  = sheet_spec.get("rows", [])

                # ── Title block (rows 1-2) ─────────────────────────────────
                self._write_title_block(ws, doc_title, doc_subtitle, col_count)

                # ── Column headers (row 4; row 3 is a spacer) ─────────────
                header_row = 4
                for ci, header in enumerate(columns, start=1):
                    cell       = ws.cell(row=header_row, column=ci)
                    cell.value = header.upper()
                    self._style_header_cell(cell)
                ws.row_dimensions[header_row].height = 20

                # ── Data rows ─────────────────────────────────────────────
                num_formats = sheet_spec.get("number_formats", {})
                data_start  = 5
                for ri, row_vals in enumerate(rows_data):
                    row_num = data_start + ri
                    is_alt  = ri % 2 == 1
                    for ci, val in enumerate(row_vals, start=1):
                        cell       = ws.cell(row=row_num, column=ci)
                        cell.value = val
                        self._style_data_cell(cell, is_alt)
                        fmt_key = str(ci)
                        if fmt_key in num_formats:
                            cell.number_format = num_formats[fmt_key]

                # ── Formula overrides ──────────────────────────────────────
                for formula_spec in sheet_spec.get("formulas", []):
                    addr    = formula_spec.get("cell", "")
                    formula = formula_spec.get("formula", "")
                    if addr and formula:
                        ws[addr] = formula
                        self._style_data_cell(ws[addr], alt=False)

                # ── Footer row ─────────────────────────────────────────────
                if sheet_spec.get("include_footer", True):
                    footer_row  = data_start + len(rows_data) + 1
                    footer_text = sheet_spec.get("footer_text") or (
                        "Potomac  |  Built to Conquer Risk\u00ae  |  For Advisor Use Only"
                    )
                    self._write_footer(ws, footer_row, col_count, footer_text)

                # ── Column widths ──────────────────────────────────────────
                col_widths = sheet_spec.get("col_widths", [])
                for ci, width in enumerate(col_widths, start=1):
                    ws.column_dimensions[get_column_letter(ci)].width = width
                # Auto-width for columns not covered by col_widths
                for ci in range(len(col_widths) + 1, col_count + 1):
                    ws.column_dimensions[get_column_letter(ci)].width = 16

                # ── Merge title / subtitle across all used columns ─────────
                if col_count > 1:
                    ws.merge_cells(
                        start_row=1, start_column=1,
                        end_row=1,   end_column=col_count,
                    )
                    if doc_subtitle:
                        ws.merge_cells(
                            start_row=2, start_column=1,
                            end_row=2,   end_column=col_count,
                        )

                # ── Freeze panes ───────────────────────────────────────────
                freeze = sheet_spec.get("freeze_panes", "")
                if freeze:
                    ws.freeze_panes = freeze
                elif columns:
                    ws.freeze_panes = f"A{header_row + 1}"

                # ── Charts ─────────────────────────────────────────────────
                from openpyxl.chart import (
                    BarChart, LineChart, PieChart, AreaChart, ScatterChart,
                    Reference,
                )

                for chart_spec in sheet_spec.get("charts", []):
                    chart_type = chart_spec.get("type", "bar_chart")
                    title = chart_spec.get("title", "")
                    x_col = chart_spec.get("x_col", 1)
                    y_cols = chart_spec.get("y_cols", [])
                    series_labels = chart_spec.get("series_labels", [])
                    anchor = chart_spec.get("anchor", "G5")
                    width = chart_spec.get("width", 15)
                    height = chart_spec.get("height", 10)

                    chart = None
                    if chart_type == "bar_chart":
                        chart = BarChart()
                    elif chart_type == "line_chart":
                        chart = LineChart()
                    elif chart_type == "pie_chart":
                        chart = PieChart()
                    elif chart_type == "area_chart":
                        chart = AreaChart()
                    elif chart_type == "scatter_chart":
                        chart = ScatterChart()

                    if chart:
                        chart.title = title
                        chart.style = 10
                        chart.y_axis.title = series_labels[0] if series_labels else ""
                        chart.x_axis.title = columns[x_col - 1] if x_col <= len(columns) else ""

                        data_end = data_start + len(rows_data) - 1

                        # X axis labels
                        if x_col >= 1:
                            chart.set_categories(
                                Reference(ws, min_col=x_col, min_row=data_start, max_row=data_end)
                            )

                        # Y series
                        for series_idx, y_col in enumerate(y_cols):
                            series = Reference(ws, min_col=y_col, min_row=header_row, max_row=data_end)
                            chart.append(series)
                            if series_idx < len(series_labels):
                                chart.series[series_idx].title = series_labels[series_idx]

                        ws.add_chart(chart, anchor)
                        chart.width = width
                        chart.height = height

                # ── Conditional Formatting ─────────────────────────────────
                from openpyxl.formatting.rule import (
                    ColorScaleRule, DataBarRule, CellIsRule
                )
                from openpyxl.styles import Font, PatternFill

                for cf_spec in sheet_spec.get("conditional_formats", []):
                    cf_type = cf_spec.get("type")
                    range_str = cf_spec.get("range", "")

                    if cf_type == "color_scale" and range_str:
                        colors = cf_spec.get("colors", ["EB2F5C", "FFEB84", "63BE7B"])
                        ws.conditional_formatting.add(range_str,
                            ColorScaleRule(
                                start_type="min", start_color=colors[0],
                                mid_type="num", mid_value=0, mid_color=colors[1],
                                end_type="max", end_color=colors[2]
                            )
                        )

                    elif cf_type == "data_bars" and range_str:
                        color = cf_spec.get("color", "FEC00F")
                        ws.conditional_formatting.add(range_str,
                            DataBarRule(start_type="min", end_type="max", color=color)
                        )

                    elif cf_type == "highlight_negatives" and range_str:
                        ws.conditional_formatting.add(range_str,
                            CellIsRule(
                                operator="lessThan", formula=["0"],
                                font=Font(color="EB2F5C")
                            )
                        )

                    elif cf_type == "highlight_positives" and range_str:
                        ws.conditional_formatting.add(range_str,
                            CellIsRule(
                                operator="greaterThan", formula=["0"],
                                font=Font(color="276221")
                            )
                        )

                # ── Excel Table ────────────────────────────────────────────
                if sheet_spec.get("as_table", False):
                    from openpyxl.worksheet.table import Table, TableStyleInfo

                    table_name = sheet_spec.get("table_name", "DataTable")
                    table = Table(displayName=table_name, ref=f"A{header_row}:{get_column_letter(col_count)}{data_start + len(rows_data) - 1}")

                    style = TableStyleInfo(
                        name="TableStyleMedium9",
                        showFirstColumn=False,
                        showLastColumn=False,
                        showRowStripes=True,
                        showColumnStripes=False
                    )
                    table.tableStyleInfo = style

                    # Totals row
                    totals = sheet_spec.get("totals_row", {})
                    if totals:
                        table.showTotals = True
                        for col_idx, func in totals.items():
                            col_letter = get_column_letter(int(col_idx))
                            for tc in table.tableColumns:
                                if tc.name == columns[int(col_idx) - 1]:
                                    tc.totalsRowFunction = func

                    ws.add_table(table)

                # ── Page setup for printing ────────────────────────────────
                ws.page_setup.orientation = "landscape"
                ws.page_setup.fitToWidth  = 1
                ws.page_setup.fitToHeight = 0
                ws.print_title_rows        = f"1:{header_row}"

            # ── Disclosures sheet ──────────────────────────────────────────
            if spec.get("include_disclosures", True):
                disc_text = spec.get("disclosure_text") or (
                    "IMPORTANT DISCLOSURES: Past performance is not indicative of future results. "
                    "This material is for informational purposes only and does not constitute "
                    "investment advice. Potomac | potomac.com | Built to Conquer Risk\u00ae"
                )
                self._add_disclosures_sheet(wb, disc_text)

            # ── Serialize to bytes ─────────────────────────────────────────
            buf = io.BytesIO()
            wb.save(buf)
            data    = buf.getvalue()
            elapsed = round((time.time() - start) * 1000, 2)
            filename = spec.get("filename") or f"{doc_title.replace(' ', '_')}.xlsx"
            logger.info(
                "XlsxSandbox ✓  %s  (%.1f KB, %.0f ms)",
                filename, len(data) / 1024, elapsed,
            )
            return XlsxResult(True, data=data, filename=filename, exec_time_ms=elapsed)

        except Exception as exc:
            logger.error("XlsxSandbox error: %s", exc, exc_info=True)
            return XlsxResult(
                False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )

    # =========================================================================
    # Styling helpers
    # =========================================================================

    @staticmethod
    def _yellow_fill() -> "PatternFill":
        from openpyxl.styles import PatternFill
        return PatternFill("solid", fgColor=_YELLOW)

    @staticmethod
    def _light_yellow_fill() -> "PatternFill":
        from openpyxl.styles import PatternFill
        return PatternFill("solid", fgColor=_YELLOW_LIGHT)

    @staticmethod
    def _alt_fill() -> "PatternFill":
        from openpyxl.styles import PatternFill
        return PatternFill("solid", fgColor=_ROW_ALT)

    @staticmethod
    def _white_fill() -> "PatternFill":
        from openpyxl.styles import PatternFill
        return PatternFill("solid", fgColor=_WHITE)

    @staticmethod
    def _thin_border() -> "Border":
        from openpyxl.styles import Border, Side
        thin = Side(style="thin", color=_DARK_GRAY)
        return Border(left=thin, right=thin, top=thin, bottom=thin)

    @staticmethod
    def _header_font(size: int = 11) -> "Font":
        from openpyxl.styles import Font
        return Font(name="Calibri", bold=True, color=_DARK_GRAY, size=size)

    @staticmethod
    def _body_font(size: int = 10) -> "Font":
        from openpyxl.styles import Font
        return Font(name="Calibri", color=_DARK_GRAY, size=size)

    def _write_title_block(
        self,
        ws: Any,
        title: str,
        subtitle: str,
        col_count: int,
    ) -> None:
        """Write the Potomac title block in rows 1-2 (row 3 is spacer)."""
        from openpyxl.styles import Alignment, Font, PatternFill

        ws.row_dimensions[1].height = 30
        ws.row_dimensions[2].height = 18
        ws.row_dimensions[3].height = 6   # spacer

        # Row 1: main title
        cell       = ws.cell(row=1, column=1)
        cell.value = title.upper()
        cell.font  = Font(name="Calibri", bold=True, size=16, color=_DARK_GRAY)
        cell.fill  = self._yellow_fill()
        cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        # Row 2: subtitle (if any)
        if subtitle:
            cell2       = ws.cell(row=2, column=1)
            cell2.value = subtitle
            cell2.font  = Font(name="Calibri", size=10, color=_DARK_GRAY)
            cell2.fill  = self._light_yellow_fill()
            cell2.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    def _style_header_cell(self, cell: Any) -> None:
        from openpyxl.styles import Alignment
        cell.font      = self._header_font()
        cell.fill      = self._yellow_fill()
        cell.border    = self._thin_border()
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )

    def _style_data_cell(self, cell: Any, alt: bool = False) -> None:
        from openpyxl.styles import Alignment
        cell.font      = self._body_font()
        cell.fill      = self._alt_fill() if alt else self._white_fill()
        cell.border    = self._thin_border()
        cell.alignment = Alignment(vertical="center")

    def _write_footer(
        self,
        ws: Any,
        footer_row: int,
        col_count: int,
        text: str,
    ) -> None:
        from openpyxl.styles import Alignment, Font
        ws.merge_cells(
            start_row=footer_row, start_column=1,
            end_row=footer_row,   end_column=max(col_count, 1),
        )
        cell       = ws.cell(row=footer_row, column=1)
        cell.value = text
        cell.font  = Font(name="Calibri", size=8, italic=True, color=_DARK_GRAY)
        cell.fill  = self._light_yellow_fill()
        cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[footer_row].height = 14

    @staticmethod
    def _add_disclosures_sheet(wb: Any, text: str) -> None:
        from openpyxl.styles import Alignment, Font, PatternFill
        ws = wb.create_sheet("DISCLOSURES")
        ws.sheet_properties.tabColor = _DARK_GRAY

        ws.row_dimensions[1].height = 24
        ws.row_dimensions[2].height = 60
        ws.column_dimensions["A"].width = 120

        title_cell       = ws.cell(row=1, column=1)
        title_cell.value = "DISCLOSURES"
        title_cell.font  = Font(name="Calibri", bold=True, size=14, color=_DARK_GRAY)
        title_cell.fill  = PatternFill("solid", fgColor=_YELLOW)
        title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        body_cell       = ws.cell(row=2, column=1)
        body_cell.value = text
        body_cell.font  = Font(name="Calibri", size=9, color=_DARK_GRAY)
        body_cell.alignment = Alignment(wrap_text=True, vertical="top")
