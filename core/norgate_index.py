"""Norgate ticker universe index.

The Norgate data feed ships 75,000+ securities across 9 databases (US Equities,
US Equities Delisted, US Indices, World Indices, Cash Commodities, Continuous
Futures, Futures, Economic, Forex Spot). The AFL generator must reference REAL
tickers when emitting Foreign(), SetForeign(), AddToComposite() etc. — otherwise
the AmiBroker formula errors at runtime.

This module parses the on-disk ticker dump once (~50 ms) into in-memory indices,
then offers O(1) exact-symbol lookup and ranked substring/word search across
symbols and human names. The full 12 MB text never enters LLM context — only
matching rows do, served through the lookup_norgate_ticker tool.

Source file (override with NORGATE_TICKER_FILE env var):
    C:\\Users\\SohaibAli\\Videos\\Development\\DevBackend\\ALL NORGATE TICKERS.txt

Record format (3-line blocks separated by a `------` ruler):
    Symbol:   SPY
    Name:     SPDR S&P 500 ETF
    AssetID:  123456

Sections opened by:
    ================================================================================
    DATABASE: <Database Name>
    ================================================================================
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Path resolution ──────────────────────────────────────────────────────────
# The Norgate dump is committed to the repo at the project root as
# `ALL NORGATE TICKERS.txt` (12 MB). To make the same code work on Windows
# dev AND Linux/Railway prod without forking, we resolve the path at module
# load time by walking these candidates in order:
#
#   1. $NORGATE_TICKER_FILE env var (explicit override; wins always)
#   2. <repo_root>/ALL NORGATE TICKERS.txt        — the committed location
#   3. <repo_root>/data/norgate_tickers.txt       — alt slug if someone renames
#   4. <repo_root>/ALL_NORGATE_TICKERS.txt        — underscored alt
#   5. /data/norgate_tickers.txt                  — Railway volume convention
#
# The previously-hardcoded Windows path is kept only as a last-resort fallback
# so existing local-dev workflows don't break.

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LEGACY_WIN_PATH = r"C:\Users\SohaibAli\Videos\Development\DevBackend\ALL NORGATE TICKERS.txt"


def _resolve_default_path() -> str:
    env_path = os.environ.get("NORGATE_TICKER_FILE", "").strip()
    if env_path:
        return env_path

    candidates = [
        _REPO_ROOT / "ALL NORGATE TICKERS.txt",
        _REPO_ROOT / "data" / "norgate_tickers.txt",
        _REPO_ROOT / "ALL_NORGATE_TICKERS.txt",
        Path("/data/norgate_tickers.txt"),
        Path(_LEGACY_WIN_PATH),
    ]
    for p in candidates:
        try:
            if p.exists() and p.is_file():
                return str(p)
        except OSError:
            continue

    # Nothing found — return the repo-root candidate so the resulting error
    # message at load time tells the operator where to drop the file.
    return str(_REPO_ROOT / "ALL NORGATE TICKERS.txt")


DEFAULT_PATH = _resolve_default_path()

# Symbols use these prefixes by convention; surfaced in tool output so the
# model can compose composite formulas (Foreign("&ES", "C") etc.) without
# guessing.
NORGATE_PREFIX_HINTS: Dict[str, str] = {
    "#":  "indices / cash commodities (e.g. #GSR Gold/Silver Ratio)",
    "$":  "indices (e.g. $SPX, $DJI)",
    "%":  "economic series (e.g. %TYX)",
    "&":  "continuous futures (e.g. &ES, &CL)",
    "@":  "cash / spot commodities (e.g. @ZN)",
    "":   "US equities, ETFs, forex pairs, etc. (plain symbols)",
}


class _Record:
    __slots__ = ("symbol", "name", "asset_id", "database")

    def __init__(self, symbol: str, name: str, asset_id: str, database: str):
        self.symbol = symbol
        self.name = name
        self.asset_id = asset_id
        self.database = database

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_id": self.asset_id,
            "database": self.database,
        }


class NorgateIndex:
    """Lazy-loaded, thread-safe in-memory Norgate ticker index."""

    _instance: Optional["NorgateIndex"] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get(cls, path: Optional[str] = None) -> "NorgateIndex":
        """Return the process-wide singleton, building it on first call.

        Path resolution order:
          1. ``path`` argument (caller override)
          2. ``$NORGATE_TICKER_FILE`` env var
          3. ``DEFAULT_PATH`` from _resolve_default_path() — walks committed
             repo locations + Railway volume conventions
        """
        if cls._instance is not None:
            return cls._instance
        with cls._instance_lock:
            if cls._instance is None:
                resolved = path or os.environ.get("NORGATE_TICKER_FILE") or DEFAULT_PATH
                logger.info("NorgateIndex resolving ticker file at %s", resolved)
                cls._instance = cls(resolved)
                if cls._instance.error:
                    logger.warning(
                        "NorgateIndex unavailable (%s). Tried: $NORGATE_TICKER_FILE, "
                        "<repo>/ALL NORGATE TICKERS.txt, <repo>/data/norgate_tickers.txt, "
                        "/data/norgate_tickers.txt",
                        cls._instance.error,
                    )
        return cls._instance

    def __init__(self, path: str):
        self.path = path
        self.loaded: bool = False
        self.error: Optional[str] = None
        # symbol (upper) -> Record
        self._by_symbol: Dict[str, _Record] = {}
        # database -> list[Record] (records also stored in self.records)
        self._by_database: Dict[str, List[_Record]] = {}
        self.records: List[_Record] = []
        # word token (lowercase) -> set of record indices, for word-level search
        self._word_index: Dict[str, List[int]] = {}
        self._load()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        if not os.path.exists(self.path):
            self.error = f"Norgate ticker file not found at {self.path}"
            logger.warning(self.error)
            return
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            self.error = f"Failed to read Norgate file: {e}"
            logger.warning(self.error)
            return

        current_db = ""
        db_header_re = re.compile(r"^DATABASE:\s*(.+?)\s*$")
        symbol_re = re.compile(r"^Symbol:\s*(\S+)\s*$")
        name_re = re.compile(r"^Name:\s*(.+?)\s*$")
        asset_re = re.compile(r"^AssetID:\s*(\S+)\s*$")

        cur_sym = cur_name = cur_aid = None
        for line in text.splitlines():
            m = db_header_re.match(line)
            if m:
                current_db = m.group(1).strip()
                continue
            m = symbol_re.match(line)
            if m:
                cur_sym = m.group(1)
                continue
            m = name_re.match(line)
            if m:
                cur_name = m.group(1)
                continue
            m = asset_re.match(line)
            if m:
                cur_aid = m.group(1)
                if cur_sym is not None:
                    rec = _Record(
                        symbol=cur_sym,
                        name=cur_name or "",
                        asset_id=cur_aid or "",
                        database=current_db,
                    )
                    idx = len(self.records)
                    self.records.append(rec)
                    self._by_symbol[cur_sym.upper()] = rec
                    self._by_database.setdefault(current_db, []).append(rec)
                    # word index for name search
                    for tok in _tokenize(rec.name):
                        bucket = self._word_index.get(tok)
                        if bucket is None:
                            self._word_index[tok] = [idx]
                        else:
                            bucket.append(idx)
                cur_sym = cur_name = cur_aid = None

        self.loaded = True
        logger.info(
            "NorgateIndex loaded: %d records, %d databases, %d unique name tokens",
            len(self.records), len(self._by_database), len(self._word_index),
        )

    # --------------------------------------------------------------- lookups
    def get_symbol(self, symbol: str) -> Optional[_Record]:
        return self._by_symbol.get(symbol.upper())

    def list_databases(self) -> List[Dict[str, Any]]:
        return [
            {"database": db, "count": len(recs)}
            for db, recs in sorted(self._by_database.items())
        ]

    def search(
        self,
        query: str,
        database: Optional[str] = None,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Rank-ordered search: exact symbol > symbol prefix > word-set name match.

        Pass database to filter to one section (e.g. "US Equities", "Continuous
        Futures"). Matching is case-insensitive and tolerates common prefix
        markers ($, #, &, @, %).
        """
        if not query or not query.strip():
            return []

        q = query.strip()
        q_upper = q.upper()
        q_lower = q.lower()
        q_stripped = q_upper.lstrip("#$&@%")
        db_filter = _norm_db(database) if database else None

        seen: set = set()
        scored: List[Tuple[float, _Record]] = []

        def _accept(rec: _Record) -> bool:
            if db_filter and _norm_db(rec.database) != db_filter:
                return False
            key = (rec.symbol, rec.database)
            if key in seen:
                return False
            seen.add(key)
            return True

        # 1) exact symbol hit (with and without leading punctuation)
        for candidate in (q_upper, q_stripped):
            rec = self._by_symbol.get(candidate)
            if rec and _accept(rec):
                scored.append((100.0, rec))

        # 2) symbol prefix / substring
        if len(q_stripped) >= 1:
            for rec in self.records:
                if db_filter and _norm_db(rec.database) != db_filter:
                    continue
                sym_up = rec.symbol.upper()
                sym_stripped = sym_up.lstrip("#$&@%")
                if sym_up.startswith(q_upper) or sym_stripped.startswith(q_stripped):
                    if _accept(rec):
                        # exact length match scores higher (already handled above)
                        score = 80.0 if len(sym_stripped) == len(q_stripped) else 60.0
                        scored.append((score, rec))
                        if len(scored) > limit * 4:
                            break

        # 3) name word search — every query token must appear as a name token
        q_tokens = [t for t in _tokenize(q_lower) if t]
        if q_tokens:
            # candidate index set = intersection of bucket hits per token
            candidate_idx: Optional[set] = None
            for tok in q_tokens:
                bucket = self._word_index.get(tok)
                if bucket is None:
                    # also try partial-match: any token that STARTS WITH tok
                    partial = []
                    for word, idxs in self._word_index.items():
                        if word.startswith(tok):
                            partial.extend(idxs)
                            if len(partial) > 2000:
                                break
                    if not partial:
                        candidate_idx = set()
                        break
                    bucket = partial
                if candidate_idx is None:
                    candidate_idx = set(bucket)
                else:
                    candidate_idx &= set(bucket)
                if not candidate_idx:
                    break
            if candidate_idx:
                for idx in candidate_idx:
                    rec = self.records[idx]
                    if not _accept(rec):
                        continue
                    name_lower = rec.name.lower()
                    # boost: query appears as a contiguous substring of the name
                    if q_lower in name_lower:
                        score = 50.0 + min(20.0, 200.0 / max(len(name_lower), 1))
                    else:
                        score = 30.0
                    # prefer US Equities for ambiguous queries (most common case)
                    if rec.database == "US Equities":
                        score += 5.0
                    scored.append((score, rec))

        # Order: score desc, then by database (Equities first), then symbol
        db_priority = {
            "US Equities": 0,
            "US Indices": 1,
            "Continuous Futures": 2,
            "Forex Spot": 3,
            "World Indices": 4,
            "Cash Commodities": 5,
            "Futures": 6,
            "Economic": 7,
            "US Equities Delisted": 8,
        }
        scored.sort(key=lambda t: (-t[0], db_priority.get(t[1].database, 99), t[1].symbol))
        return [r.to_dict() for _, r in scored[:limit]]


# ────────────────────────────────────────────────────────────────── helpers
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(s: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(s or "")]


def _norm_db(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())
