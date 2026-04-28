"""
XLSX Transformer
================
Pandas-powered data-transformation pipeline engine.
Runs 15+ common analyst operations in a single tool call.

Input  : file bytes + operations array
Output : branded Potomac .xlsx download

Operations
----------
filter_rows       → {"column": "RETURN", "op": ">", "value": 0}
sort              → {"by": ["DATE", "ALPHA"], "ascending": [true, false]}
rename_columns    → {"mapper": {"Rtn %": "RETURN %"}}
drop_columns      → {"columns": ["NOTES", "INTERNAL_ID"]}
add_column        → {"name": "P&L %", "formula": "(EXIT - ENTRY) / ENTRY"}
fill_nulls        → {"column": "STATUS", "value": "PENDING"}
drop_duplicates   → {"subset": ["TICKER", "DATE"]}
change_dtype      → {"column": "DATE", "to": "date"}
normalize_text    → {"column": "TICKER", "transform": "upper"}
group_aggregate   → {"by": ["SECTOR"], "agg": {"VALUE": "sum", "RETURN": "mean"}}
pivot             → {"index": "SECTOR", "columns": "QUARTER", "values": "RETURN", "aggfunc": "mean"}
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.sandbox.xlsx_analyzer import XlsxAnalyzer   # reuses _detect_csv
from core.sandbox.xlsx_sandbox import XlsxSandbox

logger = logging.getLogger(__name__)


# =============================================================================
# Result class
# =============================================================================

@dataclass(frozen=True)
class TransformResult:
    success: bool
    error: Optional[str] = None
    exec_time_ms: float = 0.0
    data: Optional[bytes] = None
    filename: Optional[str] = None
    row_count: int = 0
    operations_applied: int = 0


# =============================================================================
# XlsxTransformer
# =============================================================================

class XlsxTransformer:
    """
    Apply a pipeline of data-transformation operations to an uploaded file.

    Thread-safe, stateless.  All operations are pure functions applied to
    a pandas DataFrame in sequence.
    """

    VALID_OPERATIONS = frozenset({
        "filter_rows", "sort", "rename_columns", "drop_columns",
        "add_column", "fill_nulls", "drop_duplicates", "change_dtype",
        "normalize_text", "group_aggregate", "pivot",
    })

    AGG_FUNCTIONS = frozenset({
        "sum", "mean", "median", "min", "max", "count",
        "std", "var", "first", "last", "nunique",
    })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transform(
        self,
        file_bytes: bytes,
        operations: List[Dict[str, Any]],
        filename: Optional[str] = None,
        output_title: Optional[str] = None,
    ) -> TransformResult:
        """
        Apply *operations* to *file_bytes* and return a branded xlsx file.

        Parameters
        ----------
        file_bytes : bytes
            Raw bytes of the source .xlsx or .csv file.
        operations : list[dict]
            Ordered list of transformation operations.  Each dict must
            contain a ``"type"`` key matching one of VALID_OPERATIONS.
        filename : str, optional
            Original filename — used for format detection via magic bytes.
        output_title : str, optional
            Title written into the generated workbook's title block.
        """
        start = time.time()

        try:
            buf = io.BytesIO(file_bytes)

            # ── Format detection (magic-byte safe, shared with analyzer) ──
            is_csv = XlsxAnalyzer._detect_csv(file_bytes, filename)

            if is_csv:
                sheet_map: Dict[str, pd.DataFrame] = {
                    "Sheet1": pd.read_csv(buf, low_memory=False)
                }
            else:
                sheet_map = pd.read_excel(buf, sheet_name=None, engine="openpyxl")

            # Process first sheet only
            sheet_name = next(iter(sheet_map))
            df = sheet_map[sheet_name]
            initial_rows = len(df)
            operations_applied = 0

            # ── Apply pipeline ────────────────────────────────────────────
            for op in operations:
                op_type = op.get("type")
                if op_type not in self.VALID_OPERATIONS:
                    logger.warning("Skipping unknown operation: %r", op_type)
                    continue
                df = self._apply_operation(df, op_type, op)
                operations_applied += 1

            # ── Serialise to branded xlsx ─────────────────────────────────
            xlsx_spec = self._df_to_xlsx_spec(
                df, output_title or filename or "Transformed Data"
            )
            sandbox = XlsxSandbox()
            result  = sandbox.generate(xlsx_spec)

            if not result.success:
                return TransformResult(
                    success=False,
                    error=result.error,
                    exec_time_ms=round((time.time() - start) * 1000, 2),
                )

            elapsed = round((time.time() - start) * 1000, 2)
            logger.info(
                "XlsxTransformer ✓  %d → %d rows, %d ops, %.0f ms",
                initial_rows, len(df), operations_applied, elapsed,
            )

            return TransformResult(
                success=True,
                data=result.data,
                filename=result.filename,
                row_count=len(df),
                operations_applied=operations_applied,
                exec_time_ms=elapsed,
            )

        except Exception as exc:
            logger.error("XlsxTransformer error: %s", exc, exc_info=True)
            return TransformResult(
                success=False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )

    # ------------------------------------------------------------------
    # Operation dispatcher
    # ------------------------------------------------------------------

    def _apply_operation(
        self,
        df: pd.DataFrame,
        op_type: str,
        op: Dict[str, Any],
    ) -> pd.DataFrame:
        """Dispatch a single transformation and return the modified DataFrame."""

        # ── filter_rows ────────────────────────────────────────────────
        if op_type == "filter_rows":
            column   = op["column"]
            operator = op["op"]
            value    = op["value"]

            ops_map = {
                "==":          lambda c: df[df[c] == value],
                "!=":          lambda c: df[df[c] != value],
                ">":           lambda c: df[df[c] > value],
                ">=":          lambda c: df[df[c] >= value],
                "<":           lambda c: df[df[c] < value],
                "<=":          lambda c: df[df[c] <= value],
                "contains":    lambda c: df[df[c].astype(str).str.contains(str(value), case=False, na=False)],
                "not_contains":lambda c: df[~df[c].astype(str).str.contains(str(value), case=False, na=False)],
                "is_null":     lambda c: df[df[c].isnull()],
                "not_null":    lambda c: df[df[c].notnull()],
            }
            fn = ops_map.get(operator)
            return fn(column) if fn else df

        # ── sort ───────────────────────────────────────────────────────
        elif op_type == "sort":
            by        = op["by"]
            ascending = op.get("ascending", True)
            return df.sort_values(by=by, ascending=ascending)

        # ── rename_columns ─────────────────────────────────────────────
        elif op_type == "rename_columns":
            mapper = op.get("mapper", {})
            return df.rename(columns=mapper)

        # ── drop_columns ───────────────────────────────────────────────
        elif op_type == "drop_columns":
            columns  = op.get("columns", [])
            existing = [c for c in columns if c in df.columns]
            return df.drop(columns=existing)

        # ── add_column ─────────────────────────────────────────────────
        elif op_type == "add_column":
            name    = op["name"]
            formula = op["formula"]
            # df.eval() keeps the expression safe and pandas-native
            df[name] = df.eval(formula)
            return df

        # ── fill_nulls ─────────────────────────────────────────────────
        elif op_type == "fill_nulls":
            column = op["column"]
            value  = op["value"]
            df[column] = df[column].fillna(value)
            return df

        # ── drop_duplicates ────────────────────────────────────────────
        elif op_type == "drop_duplicates":
            subset = op.get("subset")
            keep   = op.get("keep", "first")
            return df.drop_duplicates(subset=subset, keep=keep)

        # ── change_dtype ───────────────────────────────────────────────
        elif op_type == "change_dtype":
            column  = op["column"]
            to_type = op["to"]

            if to_type == "date":
                df[column] = pd.to_datetime(df[column], errors="coerce")
            elif to_type == "int":
                df[column] = (
                    pd.to_numeric(df[column], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )
            elif to_type == "float":
                df[column] = pd.to_numeric(df[column], errors="coerce")
            elif to_type == "string":
                df[column] = df[column].astype(str)

            return df

        # ── normalize_text ─────────────────────────────────────────────
        elif op_type == "normalize_text":
            column    = op["column"]
            transform = op["transform"]

            transforms = {
                "upper": lambda s: s.str.upper().str.strip(),
                "lower": lambda s: s.str.lower().str.strip(),
                "title": lambda s: s.str.title().str.strip(),
                "strip": lambda s: s.str.strip(),
            }
            fn = transforms.get(transform)
            if fn:
                df[column] = fn(df[column].astype(str))
            return df

        # ── group_aggregate ────────────────────────────────────────────
        elif op_type == "group_aggregate":
            by  = op["by"]
            agg = op["agg"]
            return df.groupby(by, dropna=False).agg(agg).reset_index()

        # ── pivot ──────────────────────────────────────────────────────
        elif op_type == "pivot":
            index   = op["index"]
            columns = op["columns"]
            values  = op["values"]
            aggfunc = op.get("aggfunc", "mean")
            return df.pivot_table(
                index=index, columns=columns, values=values, aggfunc=aggfunc
            ).reset_index()

        # Unknown — should not reach here after the guard in transform()
        return df

    # ------------------------------------------------------------------
    # Spec builder
    # ------------------------------------------------------------------

    @staticmethod
    def _df_to_xlsx_spec(df: pd.DataFrame, title: str) -> Dict[str, Any]:
        """Convert a DataFrame to the standard xlsx-generation spec."""

        columns = [str(c).strip() for c in df.columns.tolist()]

        rows: List[List[Any]] = []
        for _, row in df.iterrows():
            row_values: List[Any] = []
            for val in row:
                if pd.isna(val):
                    row_values.append(None)
                elif isinstance(val, (np.int64, np.int32)):
                    row_values.append(int(val))
                elif isinstance(val, (np.float64, np.float32)):
                    row_values.append(float(round(val, 6)))
                else:
                    row_values.append(val)
            rows.append(row_values)

        return {
            "title": title,
            "sheets": [
                {
                    "name":    "DATA",
                    "columns": columns,
                    "rows":    rows,
                }
            ],
        }