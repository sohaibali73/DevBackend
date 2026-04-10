"""
XLSX Transformer
================
Pandas-powered data transformation pipeline engine.
Runs 15+ common analyst operations in a single tool call.
Input: file_id + operations array
Output: branded Potomac xlsx download

Operations
----------
filter_rows       → {"column": "RETURN", "op": ">", "value": 0}
sort              → {"by": ["DATE", "ALPHA"], "ascending": [true, false]}
rename_columns    → {"old": "Rtn %", "new": "RETURN %"}
drop_columns      → ["NOTES", "INTERNAL_ID"]
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
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

import pandas as pd
import numpy as np

from core.sandbox.xlsx_sandbox import XlsxSandbox

logger = logging.getLogger(__name__)


# =============================================================================
# Result Classes
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


class XlsxTransformer:
    """
    Apply a pipeline of data transformation operations to an uploaded file.
    
    Thread-safe, stateless. All operations are pure functions.
    """
    
    VALID_OPERATIONS = {
        "filter_rows", "sort", "rename_columns", "drop_columns",
        "add_column", "fill_nulls", "drop_duplicates", "change_dtype",
        "normalize_text", "group_aggregate", "pivot"
    }
    
    AGG_FUNCTIONS = {
        "sum", "mean", "median", "min", "max", "count", "std", "var",
        "first", "last", "nunique"
    }
    
    def transform(self, file_bytes: bytes, operations: List[Dict[str, Any]],
                  filename: Optional[str] = None, output_title: Optional[str] = None) -> TransformResult:
        """
        Apply transformation pipeline and return branded xlsx bytes.
        """
        start = time.time()
        
        try:
            buf = io.BytesIO(file_bytes)
            
            # Read input
            is_csv = filename and filename.lower().endswith('.csv')
            if is_csv:
                df = pd.read_csv(buf, low_memory=False)
                sheet_map = {"Sheet1": df}
            else:
                sheet_map = pd.read_excel(buf, sheet_name=None, engine='openpyxl')
            
            # Process first sheet only for now
            sheet_name = list(sheet_map.keys())[0]
            df = sheet_map[sheet_name]
            
            initial_rows = len(df)
            operations_applied = 0
            
            # Apply each operation in order
            for op in operations:
                op_type = op.get("type")
                if op_type not in self.VALID_OPERATIONS:
                    logger.warning("Skipping unknown operation: %s", op_type)
                    continue
                
                df = self._apply_operation(df, op_type, op)
                operations_applied += 1
            
            # Convert to standard xlsx spec
            xlsx_spec = self._df_to_xlsx_spec(df, output_title or filename or "Transformed Data")
            
            # Generate branded output
            sandbox = XlsxSandbox()
            result = sandbox.generate(xlsx_spec)
            
            if not result.success:
                return TransformResult(
                    success=False,
                    error=result.error,
                    exec_time_ms=round((time.time() - start) * 1000, 2)
                )
            
            elapsed = round((time.time() - start) * 1000, 2)
            logger.info("XlsxTransformer ✓  %d → %d rows, %d ops, %.0f ms",
                        initial_rows, len(df), operations_applied, elapsed)
            
            return TransformResult(
                success=True,
                data=result.data,
                filename=result.filename,
                row_count=len(df),
                operations_applied=operations_applied,
                exec_time_ms=elapsed
            )
            
        except Exception as exc:
            logger.error("XlsxTransformer error: %s", exc, exc_info=True)
            return TransformResult(
                success=False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2)
            )
    
    def _apply_operation(self, df: pd.DataFrame, op_type: str, op: Dict[str, Any]) -> pd.DataFrame:
        """Apply a single transformation operation"""
        
        if op_type == "filter_rows":
            column = op["column"]
            operator = op["op"]
            value = op["value"]
            
            if operator == "==":
                return df[df[column] == value]
            elif operator == "!=":
                return df[df[column] != value]
            elif operator == ">":
                return df[df[column] > value]
            elif operator == ">=":
                return df[df[column] >= value]
            elif operator == "<":
                return df[df[column] < value]
            elif operator == "<=":
                return df[df[column] <= value]
            elif operator == "contains":
                return df[df[column].astype(str).str.contains(str(value), case=False)]
            elif operator == "not_contains":
                return df[~df[column].astype(str).str.contains(str(value), case=False)]
            elif operator == "is_null":
                return df[df[column].isnull()]
            elif operator == "not_null":
                return df[df[column].notnull()]
            
            return df
        
        elif op_type == "sort":
            by = op["by"]
            ascending = op.get("ascending", True)
            return df.sort_values(by=by, ascending=ascending)
        
        elif op_type == "rename_columns":
            mapper = op.get("mapper", {})
            return df.rename(columns=mapper)
        
        elif op_type == "drop_columns":
            columns = op.get("columns", [])
            existing = [c for c in columns if c in df.columns]
            return df.drop(columns=existing)
        
        elif op_type == "add_column":
            name = op["name"]
            formula = op["formula"]
            # Evaluate formula in safe pandas context
            df[name] = df.eval(formula)
            return df
        
        elif op_type == "fill_nulls":
            column = op["column"]
            value = op["value"]
            df[column] = df[column].fillna(value)
            return df
        
        elif op_type == "drop_duplicates":
            subset = op.get("subset")
            keep = op.get("keep", "first")
            return df.drop_duplicates(subset=subset, keep=keep)
        
        elif op_type == "change_dtype":
            column = op["column"]
            to_type = op["to"]
            
            if to_type == "date":
                df[column] = pd.to_datetime(df[column], errors="coerce")
            elif to_type == "int":
                df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)
            elif to_type == "float":
                df[column] = pd.to_numeric(df[column], errors="coerce")
            elif to_type == "string":
                df[column] = df[column].astype(str)
            
            return df
        
        elif op_type == "normalize_text":
            column = op["column"]
            transform = op["transform"]
            
            if transform == "upper":
                df[column] = df[column].astype(str).str.upper().str.strip()
            elif transform == "lower":
                df[column] = df[column].astype(str).str.lower().str.strip()
            elif transform == "title":
                df[column] = df[column].astype(str).str.title().str.strip()
            elif transform == "strip":
                df[column] = df[column].astype(str).str.strip()
            
            return df
        
        elif op_type == "group_aggregate":
            by = op["by"]
            agg = op["agg"]
            return df.groupby(by, dropna=False).agg(agg).reset_index()
        
        elif op_type == "pivot":
            index = op["index"]
            columns = op["columns"]
            values = op["values"]
            aggfunc = op.get("aggfunc", "mean")
            return df.pivot_table(index=index, columns=columns, values=values, aggfunc=aggfunc).reset_index()
        
        return df
    
    def _df_to_xlsx_spec(self, df: pd.DataFrame, title: str) -> Dict[str, Any]:
        """Convert DataFrame to standard xlsx generation spec"""
        
        # Clean column names
        columns = [str(c).strip() for c in df.columns.tolist()]
        
        # Convert rows to native Python types
        rows = []
        for _, row in df.iterrows():
            row_values = []
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
                    "name": "DATA",
                    "columns": columns,
                    "rows": rows
                }
            ]
        }