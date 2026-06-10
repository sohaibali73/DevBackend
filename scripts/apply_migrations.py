#!/usr/bin/env python3
"""Apply all SQL migrations in order against DATABASE_URL (Azure Postgres).

Usage:
    python scripts/apply_migrations.py            # apply pending migrations
    DATABASE_URL=postgresql://... python scripts/apply_migrations.py

Migrations in db/migrations/*.sql are applied in filename order (000_, 001_,
...). Applied files are recorded in a `schema_migrations` ledger so re-runs only
apply new files. The 000_azure_bootstrap.sql shim runs first and creates the
Supabase-compatibility objects the historical migrations expect.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(".env.local")
except Exception:
    pass

import psycopg

MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not dsn:
        print("ERROR: set DATABASE_URL")
        sys.exit(1)
    return dsn


def _ordered_files() -> list[Path]:
    """Use _apply_order.txt manifest if present (curated order); else sorted glob."""
    manifest = MIGRATIONS_DIR / "_apply_order.txt"
    if manifest.exists():
        names = []
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
        missing = [n for n in names if not (MIGRATIONS_DIR / n).exists()]
        if missing:
            print(f"WARNING: manifest lists missing files: {missing}")
        listed = set(names)
        extras = sorted(
            p.name for p in MIGRATIONS_DIR.glob("*.sql") if p.name not in listed
        )
        if extras:
            print(f"• not in manifest (skipped): {extras}")
        return [MIGRATIONS_DIR / n for n in names if (MIGRATIONS_DIR / n).exists()]
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)


def main() -> None:
    dsn = _dsn()
    files = _ordered_files()
    if not files:
        print("No migration files found.")
        return

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  filename text PRIMARY KEY,"
                "  applied_at timestamptz NOT NULL DEFAULT now())"
            )
            cur.execute("SELECT filename FROM schema_migrations")
            applied = {r[0] for r in cur.fetchall()}

        # Historical migrations contain order paradoxes (legacy `users` vs modern
        # `user_profiles`) that only surface on a clean replay. --continue-on-error
        # applies every file in its own transaction and reports failures, so the
        # final schema is the union of everything that applied cleanly. The later
        # migrations create the correct final tables regardless of early-patch
        # failures.
        cont = "--continue-on-error" in sys.argv
        failures: list[tuple[str, str]] = []
        for f in files:
            if f.name in applied:
                print(f"• skip   {f.name} (already applied)")
                continue
            sql = f.read_text(encoding="utf-8")
            print(f"▶ apply  {f.name} ({len(sql)} bytes)")
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(sql)
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO schema_migrations(filename) VALUES (%s) "
                        "ON CONFLICT DO NOTHING",
                        (f.name,),
                    )
            except Exception as exc:
                msg = str(exc).splitlines()[0]
                if cont:
                    print(f"  ⚠ skipped (error): {msg}")
                    failures.append((f.name, msg))
                    continue
                print(f"✗ FAILED {f.name}: {msg}")
                sys.exit(1)
    if failures:
        print(f"\n⚠ {len(failures)} migration(s) did not apply (continue-on-error):")
        for name, msg in failures:
            print(f"   - {name}: {msg}")
    print("✅ Migrations complete.")


if __name__ == "__main__":
    main()
