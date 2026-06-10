"""PostgREST-compatible client backed by Azure Postgres (psycopg, synchronous).

WHY THIS EXISTS
---------------
The codebase historically used ``supabase-py`` and called PostgREST through a
fluent builder::

    db.table("user_profiles").select("*").eq("id", uid).single().execute()

Migrating off Supabase, we keep that exact interface but execute against Azure
Database for PostgreSQL directly via a synchronous ``psycopg`` connection pool.
This means the ~900 ``db.table(...)`` / ``db.rpc(...)`` call sites across the
app keep working with **no changes** — only this one module was swapped.

Hot-path async code should still prefer ``db.async_db`` (asyncpg). This shim
covers the convenience/REST-style call sites and is intentionally synchronous,
matching the original ``supabase-py`` behaviour.

SUPPORTED SURFACE
-----------------
    .table(name) -> .select/.insert/.update/.upsert/.delete
    filters: .eq .neq .gt .gte .lt .lte .like .ilike .in_ .is_ .contains
             .match .or_ .filter  (+ .not_ modifier)
    modifiers: .order(col, desc=) .limit(n) .range(a, b) .offset(n)
               .single() .maybe_single()
    .execute() -> APIResponse(data=..., count=...)
    .rpc(fn, params) -> calls a Postgres function: SELECT * FROM fn(k => %s, ...)

Anything not covered raises a clear error so it can be added deliberately.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import logging
import re
import threading
import uuid as _uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from config import get_settings

logger = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from psycopg_pool import ConnectionPool
    _PSYCOPG_AVAILABLE = True
except Exception as _exc:  # pragma: no cover
    psycopg = None  # type: ignore
    ConnectionPool = None  # type: ignore
    dict_row = None  # type: ignore
    Jsonb = None  # type: ignore
    _PSYCOPG_AVAILABLE = False
    logger.warning("psycopg not available — PostgREST shim disabled (%s)", _exc)


def _adapt(v: Any) -> Any:
    """Coerce Python values to what psycopg can bind. supabase-py/PostgREST
    JSON-encoded dicts/lists automatically; psycopg needs dicts (and nested
    lists) wrapped as Jsonb, while flat scalar lists stay as SQL arrays."""
    if isinstance(v, dict):
        return Jsonb(v)
    if isinstance(v, (list, tuple)):
        seq = list(v)
        if any(isinstance(e, (dict, list, tuple)) for e in seq):
            return Jsonb(seq)
        return seq
    return v


# ── Connection pool (synchronous, process-local) ───────────────────────────────

_pool = None  # type: ignore
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    if not _PSYCOPG_AVAILABLE:
        raise RuntimeError("psycopg is not installed — cannot run DB queries")
    dsn = get_settings().effective_db_url
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set — cannot connect to Postgres")
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=10,
                kwargs={"row_factory": dict_row, "autocommit": True},
                open=True,
            )
            logger.info("psycopg PostgREST-shim pool ready")
    return _pool


def close_sync_pool() -> None:
    """Close the synchronous pool on shutdown."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None


# ── Result object (mirrors supabase-py's APIResponse) ──────────────────────────

@dataclass
class APIResponse:
    data: Any = None
    count: Optional[int] = None


def _json_safe(v: Any) -> Any:
    """Coerce psycopg-native types to the JSON-native types PostgREST returned,
    so callers that assume strings (uuid/timestamp) keep working unchanged."""
    if isinstance(v, _uuid.UUID):
        return str(v)
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, _decimal.Decimal):
        return float(v)
    if isinstance(v, _dt.timedelta):
        return v.total_seconds()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).decode("utf-8", "ignore")
    return v


def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _json_safe(v) for k, v in row.items()}


# ── Identifier / SQL helpers ───────────────────────────────────────────────────

def _quote_ident(name: str) -> str:
    """Quote a single column/table identifier. Trusted (code-supplied) names."""
    name = name.strip()
    if "(" in name or "*" in name:  # function call or star — pass through
        return name
    return '"' + name.replace('"', '""') + '"'


_OP_SQL = {
    "eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "like": "LIKE", "ilike": "ILIKE",
}


# ── PostgREST resource embedding (e.g. select("a, related(*)")) ────────────────

_embed_cache: Dict[Tuple[str, str], Tuple[str, str, str]] = {}


def _parse_select(columns: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Split a select string into plain columns and embedded resources.

    'file_id, file_uploads(id, name)'  ->  (['file_id'], [('file_uploads','id, name')])
    """
    columns = (columns or "*").strip()
    if columns == "*":
        return ["*"], []
    plain: List[str] = []
    embeds: List[Tuple[str, str]] = []
    for part in _split_top_level(columns):
        m = re.match(r"^([A-Za-z_][\w]*)\s*\((.*)\)$", part.strip(), re.DOTALL)
        if m:
            embeds.append((m.group(1), m.group(2).strip()))
        else:
            plain.append(part.strip())
    return plain, embeds


def _resolve_embed(base: str, emb: str) -> Tuple[str, str, str]:
    """Resolve the FK between base and embedded table.

    Returns (base_col, emb_col, direction) where the correlation is
    emb.emb_col = base.base_col. direction is 'one' (base has FK to emb) or
    'many' (emb has FK to base).
    """
    key = (base, emb)
    if key in _embed_cache:
        return _embed_cache[key]
    sql = """
        SELECT a.attname AS local_col, af.attname AS remote_col
        FROM pg_constraint c
        JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum  = c.conkey[1]
        JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
        WHERE c.contype = 'f' AND c.conrelid = %s::regclass AND c.confrelid = %s::regclass
        LIMIT 1
    """
    pool = _get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        # to-one: FK on base referencing emb
        cur.execute(sql, [base, emb])
        row = cur.fetchone()
        if row:
            res = (row["local_col"], row["remote_col"], "one")
        else:
            # to-many: FK on emb referencing base
            cur.execute(sql, [emb, base])
            row = cur.fetchone()
            if not row:
                raise PostgrestError(
                    f"cannot embed '{emb}' in '{base}': no FK relationship found"
                )
            res = (row["remote_col"], row["local_col"], "many")
    _embed_cache[key] = res
    return res


# ── Query builder ───────────────────────────────────────────────────────────────

class _Query:
    def __init__(self, table: str):
        self._table = table
        self._op = "select"
        self._columns = "*"
        self._count_mode: Optional[str] = None
        self._filters: List[Tuple[str, List[Any]]] = []
        self._order: List[str] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._payload: Any = None
        self._on_conflict: Optional[str] = None
        self._single = False
        self._maybe_single = False
        self._negate_next = False

    # -- operation selectors ----------------------------------------------------
    def select(self, columns: str = "*", *, count: Optional[str] = None) -> "_Query":
        self._op = "select"
        self._columns = columns or "*"
        self._count_mode = count
        return self

    def insert(self, values: Any, *, returning: bool = True) -> "_Query":
        self._op = "insert"
        self._payload = values
        return self

    def update(self, values: Dict[str, Any]) -> "_Query":
        self._op = "update"
        self._payload = values
        return self

    def upsert(self, values: Any, *, on_conflict: str = "id") -> "_Query":
        self._op = "upsert"
        self._payload = values
        self._on_conflict = on_conflict
        return self

    def delete(self) -> "_Query":
        self._op = "delete"
        return self

    # -- filters ----------------------------------------------------------------
    def _add(self, frag: str, params: List[Any]) -> "_Query":
        if self._negate_next:
            frag = f"NOT ({frag})"
            self._negate_next = False
        self._filters.append((frag, params))
        return self

    @property
    def not_(self) -> "_Query":
        self._negate_next = True
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        if val is None:
            return self._add(f"{_quote_ident(col)} IS NULL", [])
        return self._add(f"{_quote_ident(col)} = %s", [val])

    def neq(self, col: str, val: Any) -> "_Query":
        return self._add(f"{_quote_ident(col)} <> %s", [val])

    def gt(self, col: str, val: Any) -> "_Query":
        return self._add(f"{_quote_ident(col)} > %s", [val])

    def gte(self, col: str, val: Any) -> "_Query":
        return self._add(f"{_quote_ident(col)} >= %s", [val])

    def lt(self, col: str, val: Any) -> "_Query":
        return self._add(f"{_quote_ident(col)} < %s", [val])

    def lte(self, col: str, val: Any) -> "_Query":
        return self._add(f"{_quote_ident(col)} <= %s", [val])

    def like(self, col: str, pattern: str) -> "_Query":
        return self._add(f"{_quote_ident(col)} LIKE %s", [pattern])

    def ilike(self, col: str, pattern: str) -> "_Query":
        return self._add(f"{_quote_ident(col)} ILIKE %s", [pattern])

    def in_(self, col: str, values: List[Any]) -> "_Query":
        return self._add(f"{_quote_ident(col)} = ANY(%s)", [list(values)])

    def is_(self, col: str, val: Any) -> "_Query":
        token = val
        if isinstance(val, str):
            token = {"null": None, "true": True, "false": False}.get(val.lower(), val)
        if token is None:
            return self._add(f"{_quote_ident(col)} IS NULL", [])
        if token is True:
            return self._add(f"{_quote_ident(col)} IS TRUE", [])
        if token is False:
            return self._add(f"{_quote_ident(col)} IS FALSE", [])
        return self._add(f"{_quote_ident(col)} IS %s", [token])

    def contains(self, col: str, val: Any) -> "_Query":
        return self._add(f"{_quote_ident(col)} @> %s", [_adapt(val)])

    def match(self, criteria: Dict[str, Any]) -> "_Query":
        for k, v in criteria.items():
            self.eq(k, v)
        return self

    def filter(self, col: str, op: str, val: Any) -> "_Query":
        op = op.lower()
        if op in _OP_SQL:
            return self._add(f"{_quote_ident(col)} {_OP_SQL[op]} %s", [val])
        if op == "in":
            vals = _parse_pg_list(val) if isinstance(val, str) else list(val)
            return self._add(f"{_quote_ident(col)} = ANY(%s)", [vals])
        if op == "is":
            return self.is_(col, val)
        if op in ("cs", "contains"):
            return self._add(f"{_quote_ident(col)} @> %s", [val])
        if op in ("cd",):
            return self._add(f"{_quote_ident(col)} <@ %s", [val])
        raise NotImplementedError(f"filter op '{op}' not supported by the shim")

    def or_(self, expr: str, *_, **__) -> "_Query":
        """Parse a PostgREST OR expression: 'col.op.val,col2.op2.val2'."""
        frag, params = _parse_or(expr)
        return self._add(frag, params)

    # -- modifiers --------------------------------------------------------------
    def order(self, col: str, *, desc: bool = False, **__) -> "_Query":
        self._order.append(f"{_quote_ident(col)} {'DESC' if desc else 'ASC'}")
        return self

    def limit(self, n: int, **__) -> "_Query":
        self._limit = n
        return self

    def offset(self, n: int) -> "_Query":
        self._offset = n
        return self

    def range(self, start: int, end: int) -> "_Query":
        # PostgREST range is inclusive on both ends.
        self._offset = start
        self._limit = (end - start) + 1
        return self

    def single(self) -> "_Query":
        self._single = True
        return self

    def maybe_single(self) -> "_Query":
        self._maybe_single = True
        return self

    # -- execution --------------------------------------------------------------
    def _where(self) -> Tuple[str, List[Any]]:
        if not self._filters:
            return "", []
        clauses, params = [], []
        for frag, p in self._filters:
            clauses.append(frag)
            params.extend(p)
        return " WHERE " + " AND ".join(clauses), params

    def _build(self) -> Tuple[str, List[Any], bool]:
        """Return (sql, params, returns_rows)."""
        tbl = _quote_ident(self._table)
        if self._op == "select":
            where, wp = self._where()
            plain, embeds = _parse_select(self._columns)
            if not embeds:
                sql = f"SELECT {self._columns} FROM {tbl}{where}"
            else:
                a = "_b"  # base alias for FK correlation
                items: List[str] = []
                for c in plain:
                    items.append(f"{a}.*" if c == "*" else f"{a}.{_quote_ident(c)}")
                for name, inner in embeds:
                    base_col, emb_col, direction = _resolve_embed(self._table, name)
                    qn = _quote_ident(name)
                    inner_sql = inner or "*"
                    corr = f"_e.{_quote_ident(emb_col)} = {a}.{_quote_ident(base_col)}"
                    sub = f"(SELECT {inner_sql} FROM {qn} _e WHERE {corr}) _x"
                    if direction == "many":
                        items.append(
                            f"(SELECT COALESCE(jsonb_agg(to_jsonb(_x)), '[]'::jsonb) "
                            f"FROM {sub}) AS {qn}"
                        )
                    else:
                        items.append(f"(SELECT to_jsonb(_x) FROM {sub}) AS {qn}")
                sql = f"SELECT {', '.join(items)} FROM {tbl} {a}{where}"
            if self._order:
                sql += " ORDER BY " + ", ".join(self._order)
            if self._limit is not None:
                sql += f" LIMIT {int(self._limit)}"
            if self._offset is not None:
                sql += f" OFFSET {int(self._offset)}"
            return sql, wp, True

        if self._op == "insert":
            cols, rows_params = _rows_to_params(self._payload)
            placeholders = ", ".join(
                "(" + ", ".join(["%s"] * len(cols)) + ")" for _ in rows_params
            )
            flat = [_adapt(v) for row in rows_params for v in row]
            collist = ", ".join(_quote_ident(c) for c in cols)
            sql = f"INSERT INTO {tbl} ({collist}) VALUES {placeholders} RETURNING *"
            return sql, flat, True

        if self._op == "upsert":
            cols, rows_params = _rows_to_params(self._payload)
            placeholders = ", ".join(
                "(" + ", ".join(["%s"] * len(cols)) + ")" for _ in rows_params
            )
            flat = [_adapt(v) for row in rows_params for v in row]
            collist = ", ".join(_quote_ident(c) for c in cols)
            conflict_cols = ", ".join(
                _quote_ident(c.strip()) for c in (self._on_conflict or "id").split(",")
            )
            updates = ", ".join(
                f"{_quote_ident(c)} = EXCLUDED.{_quote_ident(c)}" for c in cols
            )
            sql = (
                f"INSERT INTO {tbl} ({collist}) VALUES {placeholders} "
                f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {updates} RETURNING *"
            )
            return sql, flat, True

        if self._op == "update":
            set_cols = list(self._payload.keys())
            set_frag = ", ".join(f"{_quote_ident(c)} = %s" for c in set_cols)
            set_params = [_adapt(self._payload[c]) for c in set_cols]
            where, wp = self._where()
            sql = f"UPDATE {tbl} SET {set_frag}{where} RETURNING *"
            return sql, set_params + wp, True

        if self._op == "delete":
            where, wp = self._where()
            sql = f"DELETE FROM {tbl}{where} RETURNING *"
            return sql, wp, True

        raise NotImplementedError(f"operation '{self._op}' not supported")

    def execute(self) -> APIResponse:
        sql, params, returns_rows = self._build()
        pool = _get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = [_normalize(r) for r in cur.fetchall()] if returns_rows else []

        count = None
        if self._count_mode:  # exact count requested
            where, wp = self._where()
            csql = f"SELECT count(*) AS c FROM {_quote_ident(self._table)}{where}"
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(csql, wp)
                    count = cur.fetchone()["c"]

        if self._single:
            if len(rows) != 1:
                raise PostgrestError(
                    f"single() expected exactly 1 row, got {len(rows)}"
                )
            return APIResponse(data=rows[0], count=count)
        if self._maybe_single:
            return APIResponse(data=(rows[0] if rows else None), count=count)
        return APIResponse(data=rows, count=count)


class PostgrestError(Exception):
    pass


# ── OR-expression + list parsing (PostgREST syntax) ─────────────────────────────

def _split_top_level(expr: str) -> List[str]:
    """Split on commas that are not inside parentheses."""
    parts, depth, cur = [], 0, ""
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _parse_pg_list(val: str) -> List[str]:
    return [v.strip() for v in val.strip().lstrip("(").rstrip(")").split(",") if v.strip()]


def _parse_or(expr: str) -> Tuple[str, List[Any]]:
    """Translate 'a.eq.1,b.ilike.%x%' -> ('("a" = %s OR "b" ILIKE %s)', [1, '%x%'])."""
    conds, params = [], []
    for cond in _split_top_level(expr):
        # split into col, op, value (value may itself contain dots)
        try:
            col, op, val = cond.split(".", 2)
        except ValueError:
            raise NotImplementedError(f"cannot parse or_ condition: {cond!r}")
        op = op.lower()
        if op in _OP_SQL:
            sql_op = _OP_SQL[op]
            if op in ("like", "ilike"):
                val = val.replace("*", "%")
            conds.append(f"{_quote_ident(col)} {sql_op} %s")
            params.append(val)
        elif op == "in":
            vals = _parse_pg_list(val)
            conds.append(f"{_quote_ident(col)} = ANY(%s)")
            params.append(vals)
        elif op == "is":
            token = {"null": None, "true": True, "false": False}.get(val.lower(), val)
            if token is None:
                conds.append(f"{_quote_ident(col)} IS NULL")
            elif token is True:
                conds.append(f"{_quote_ident(col)} IS TRUE")
            elif token is False:
                conds.append(f"{_quote_ident(col)} IS FALSE")
            else:
                conds.append(f"{_quote_ident(col)} IS %s")
                params.append(token)
        else:
            raise NotImplementedError(f"or_ op '{op}' not supported")
    return "(" + " OR ".join(conds) + ")", params


def _rows_to_params(payload: Any) -> Tuple[List[str], List[List[Any]]]:
    """Normalize insert/upsert payload into (columns, [row_values, ...])."""
    rows = payload if isinstance(payload, list) else [payload]
    if not rows:
        raise PostgrestError("insert/upsert called with empty payload")
    # union of keys, stable order from first row then any extras
    cols: List[str] = list(rows[0].keys())
    for r in rows[1:]:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    out = [[r.get(c) for c in cols] for r in rows]
    return cols, out


# ── RPC (Postgres function calls) ──────────────────────────────────────────────

class _RPC:
    def __init__(self, fn: str, params: Optional[Dict[str, Any]]):
        self._fn = fn
        self._params = params or {}
        self._single = False
        self._maybe_single = False

    def single(self) -> "_RPC":
        self._single = True
        return self

    def maybe_single(self) -> "_RPC":
        self._maybe_single = True
        return self

    def execute(self) -> APIResponse:
        keys = list(self._params.keys())
        arglist = ", ".join(f"{k} => %s" for k in keys)
        sql = f"SELECT * FROM {self._fn}({arglist})"
        values = [self._params[k] for k in keys]
        pool = _get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
                rows = [_normalize(r) for r in cur.fetchall()]
        if self._single:
            return APIResponse(data=(rows[0] if rows else None))
        if self._maybe_single:
            return APIResponse(data=(rows[0] if rows else None))
        return APIResponse(data=rows)


# ── Client facade ───────────────────────────────────────────────────────────────

class _StorageUnsupported:
    def from_(self, *_a, **_k):
        raise NotImplementedError(
            "Supabase Storage was removed. Use core.storage (Azure Blob) instead "
            "of get_supabase().storage."
        )


class PostgrestClient:
    """Drop-in replacement for the parts of the supabase-py Client we use."""

    storage = _StorageUnsupported()

    def table(self, name: str) -> _Query:
        return _Query(name)

    # supabase-py exposes both .table() and .from_()
    def from_(self, name: str) -> _Query:
        return _Query(name)

    def rpc(self, fn: str, params: Optional[Dict[str, Any]] = None) -> _RPC:
        return _RPC(fn, params)


@lru_cache(maxsize=1)
def get_supabase() -> PostgrestClient:
    """Return the PostgREST-compatible client (cached singleton)."""
    return PostgrestClient()


def get_supabase_with_token(token: str) -> PostgrestClient:
    """Token is ignored — the backend connects with a privileged DB role and
    enforces authorization in application code (RLS is no longer used)."""
    return get_supabase()


def get_auth_client() -> PostgrestClient:
    """DEPRECATED. Supabase Auth is gone; auth is self-hosted (see api/routes/auth.py).
    Kept only so legacy imports resolve."""
    return get_supabase()
