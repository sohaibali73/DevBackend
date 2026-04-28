"""
XLSX Analyzer
=============
Reads and profiles any uploaded .xlsx or .csv file.
Returns a JSON-serializable schema that the LLM can reason about
without needing to see raw data rows.

Usage
-----
    from core.sandbox.xlsx_analyzer import XlsxAnalyzer

    analyzer = XlsxAnalyzer()
    result   = analyzer.analyze(file_bytes, filename="report.xlsx")

    if result.success:
        print(result.profile)
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# XLSX / ZIP magic bytes — every valid .xlsx file starts with PK\x03\x04
# Using this is the only reliable way to distinguish xlsx from csv when the
# caller hasn't supplied a filename (or has supplied a misleading one).
# ---------------------------------------------------------------------------
_XLSX_MAGIC = b"PK\x03\x04"


# =============================================================================
# Result classes
# =============================================================================

@dataclass(frozen=True)
class SheetProfile:
    name: str
    row_count: int
    column_count: int
    columns: List[str]
    dtypes: Dict[str, str]
    null_counts: Dict[str, int]
    duplicate_count: int
    numeric_stats: Dict[str, Dict[str, float]]
    sample_rows: List[List[Any]]


@dataclass(frozen=True)
class AnalyzeResult:
    success: bool
    error: Optional[str] = None
    exec_time_ms: float = 0.0
    profile: Optional[Dict[str, Any]] = None


# =============================================================================
# XlsxAnalyzer
# =============================================================================

class XlsxAnalyzer:
    """
    Analyze any Excel or CSV file and return a structured profile.

    Thread-safe, stateless.  Works entirely in-memory.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
    ) -> AnalyzeResult:
        """
        Analyze file contents and return a profile.

        Parameters
        ----------
        file_bytes : bytes
            Raw bytes of an .xlsx or .csv file.
        filename : str, optional
            Original filename.  Used as a format hint but validated
            against magic bytes — a misnamed file is handled correctly.
        """
        start = time.time()

        try:
            buf = io.BytesIO(file_bytes)
            is_csv = self._detect_csv(file_bytes, filename)

            if is_csv:
                df_map: Dict[str, pd.DataFrame] = {
                    "Sheet1": pd.read_csv(buf, low_memory=False)
                }
            else:
                df_map = pd.read_excel(buf, sheet_name=None, engine="openpyxl")

            profile: Dict[str, Any] = {
                "format": "csv" if is_csv else "xlsx",
                "sheet_count": len(df_map),
                "sheets": list(df_map.keys()),
                "profile": {},
            }

            for sheet_name, df in df_map.items():
                sheet_profile = self._profile_dataframe(df, sheet_name)
                profile["profile"][sheet_name] = sheet_profile.__dict__

            elapsed = round((time.time() - start) * 1000, 2)
            logger.info(
                "XlsxAnalyzer ✓  %d sheet(s), %.0f ms", len(df_map), elapsed
            )

            return AnalyzeResult(success=True, profile=profile, exec_time_ms=elapsed)

        except Exception as exc:
            logger.error("XlsxAnalyzer error: %s", exc, exc_info=True)
            return AnalyzeResult(
                success=False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_csv(file_bytes: bytes, filename: Optional[str]) -> bool:
        """
        Reliably determine whether *file_bytes* is CSV or XLSX.

        Decision order
        --------------
        1. ZIP magic bytes (``PK\\x03\\x04``) → always xlsx, regardless of name.
        2. Explicit ``.xlsx`` / ``.xlsm`` / ``.xls`` extension → xlsx.
        3. Explicit ``.csv`` / ``.tsv`` extension → csv.
        4. Fallback byte-sniff for a comma in the first 1 KB → csv.

        This ordering means a file named ``data.csv`` that is actually a ZIP
        archive (i.e. an xlsx) is still read with openpyxl, avoiding the
        ``UnicodeDecodeError`` that the naive comma-sniff approach produces.
        """
        # 1. Magic bytes are authoritative — binary ZIP = xlsx, never csv
        if file_bytes[:4] == _XLSX_MAGIC:
            return False

        # 2-3. Trust the extension when no magic bytes match
        if filename:
            lower = filename.lower()
            if lower.endswith((".xlsx", ".xlsm", ".xls")):
                return False
            if lower.endswith((".csv", ".tsv")):
                return True

        # 4. Last resort: look for a comma in the first kilobyte of plaintext
        try:
            snippet = file_bytes[:1024].decode("utf-8", errors="strict")
            return "," in snippet
        except UnicodeDecodeError:
            # Non-UTF-8 binary that lacks the ZIP magic → not a valid xlsx
            # either, but let openpyxl handle the error with a clear message.
            return False

    # ------------------------------------------------------------------
    # Profiling helpers
    # ------------------------------------------------------------------

    def _profile_dataframe(
        self, df: pd.DataFrame, sheet_name: str
    ) -> SheetProfile:
        """Generate a profile for a single DataFrame."""

        row_count  = len(df)
        columns    = [str(c) for c in df.columns.tolist()]
        dtypes     = {str(k): str(v) for k, v in df.dtypes.items()}

        # Null counts
        null_counts = {
            str(k): int(v) for k, v in df.isnull().sum().items()
        }

        # Duplicate rows
        duplicate_count = int(df.duplicated().sum())

        # Numeric column statistics
        numeric_stats: Dict[str, Dict[str, float]] = {}
        for col in df.select_dtypes(include="number").columns:
            s = df[col].dropna()
            if len(s) > 0:
                numeric_stats[str(col)] = {
                    "min":    float(s.min()),
                    "max":    float(s.max()),
                    "mean":   float(s.mean()),
                    "median": float(s.median()),
                    "std":    float(s.std()) if len(s) > 1 else 0.0,
                }

        # Sample rows — max 5, strings truncated to 80 chars
        sample_rows: List[List[Any]] = []
        if row_count > 0:
            for _, row in df.head(min(5, row_count)).iterrows():
                row_values: List[Any] = []
                for val in row:
                    if isinstance(val, (int, float, bool)):
                        row_values.append(val)
                    elif pd.isna(val):
                        row_values.append(None)
                    else:
                        s = str(val).strip()
                        row_values.append(s[:80] + ("..." if len(s) > 80 else ""))
                sample_rows.append(row_values)

        return SheetProfile(
            name=sheet_name,
            row_count=row_count,
            column_count=len(columns),
            columns=columns,
            dtypes=dtypes,
            null_counts=null_counts,
            duplicate_count=duplicate_count,
            numeric_stats=numeric_stats,
            sample_rows=sample_rows,
        )