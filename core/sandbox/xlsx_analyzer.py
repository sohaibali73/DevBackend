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
    result = analyzer.analyze(file_bytes)

    if result.success:
        print(result.profile)
"""

from __future__ import annotations

import io
import json
import logging
import time
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Result Classes
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


class XlsxAnalyzer:
    """
    Analyze any Excel or CSV file and return a structured profile.
    
    Thread-safe, stateless. Works entirely in-memory.
    """
    
    def analyze(self, file_bytes: bytes, filename: Optional[str] = None) -> AnalyzeResult:
        """
        Analyze file contents and return a profile.
        
        Parameters
        ----------
        file_bytes : bytes
            Raw bytes of .xlsx or .csv file
        filename : str, optional
            Original filename for format detection
        """
        start = time.time()
        
        try:
            buf = io.BytesIO(file_bytes)
            
            # Detect format
            is_csv = filename and filename.lower().endswith('.csv') or \
                    len(file_bytes) < 1024 * 1024 and b',' in file_bytes[:1024]
            
            if is_csv:
                df_map = {'Sheet1': pd.read_csv(buf, low_memory=False)}
            else:
                df_map = pd.read_excel(buf, sheet_name=None, engine='openpyxl')
            
            profile: Dict[str, Any] = {
                "format": "csv" if is_csv else "xlsx",
                "sheet_count": len(df_map),
                "sheets": list(df_map.keys()),
                "profile": {}
            }
            
            for sheet_name, df in df_map.items():
                sheet_profile = self._profile_dataframe(df, sheet_name)
                profile["profile"][sheet_name] = sheet_profile.__dict__
            
            elapsed = round((time.time() - start) * 1000, 2)
            logger.info("XlsxAnalyzer ✓  %d sheets, %.0f ms", len(df_map), elapsed)
            
            return AnalyzeResult(
                success=True,
                profile=profile,
                exec_time_ms=elapsed
            )
            
        except Exception as exc:
            logger.error("XlsxAnalyzer error: %s", exc, exc_info=True)
            return AnalyzeResult(
                success=False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2)
            )
    
    def _profile_dataframe(self, df: pd.DataFrame, sheet_name: str) -> SheetProfile:
        """Generate profile for a single DataFrame"""
        
        # Basic metrics
        row_count = len(df)
        columns = [str(c) for c in df.columns.tolist()]
        dtypes = {str(k): str(v) for k, v in df.dtypes.items()}
        
        # Null counts
        null_counts = df.isnull().sum().to_dict()
        null_counts = {str(k): int(v) for k, v in null_counts.items()}
        
        # Duplicates
        duplicate_count = int(df.duplicated().sum())
        
        # Numeric stats
        numeric_cols = df.select_dtypes(include='number').columns.tolist()
        numeric_stats: Dict[str, Dict[str, float]] = {}
        
        for col in numeric_cols:
            s = df[col].dropna()
            if len(s) > 0:
                numeric_stats[str(col)] = {
                    "min": float(s.min()),
                    "max": float(s.max()),
                    "mean": float(s.mean()),
                    "median": float(s.median()),
                    "std": float(s.std()) if len(s) > 1 else 0.0
                }
        
        # Sample rows (max 5, hide PII)
        sample_rows = []
        if row_count > 0:
            sample_df = df.head(min(5, row_count))
            for _, row in sample_df.iterrows():
                row_values = []
                for val in row:
                    if isinstance(val, (int, float, bool)):
                        row_values.append(val)
                    elif pd.isna(val):
                        row_values.append(None)
                    else:
                        s = str(val).strip()
                        # Truncate long strings for sample
                        row_values.append(s[:80] + ('...' if len(s) > 80 else ''))
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
            sample_rows=sample_rows
        )