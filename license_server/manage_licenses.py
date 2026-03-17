#!/usr/bin/env python3
"""
CLI tool for managing Xivora licenses directly in licenses.db.

Usage:
  python manage_licenses.py add    CODE123          — add new active code
  python manage_licenses.py revoke CODE123          — revoke a code
  python manage_licenses.py reset  CODE123          — clear HWID (re-bind on new device)
  python manage_licenses.py list                    — show all codes
  python manage_licenses.py delete CODE123          — permanently delete a code

Run this on the AMVERA VPS in the license_server/ directory.
"""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "licenses.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def _ensure_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                code        TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'active',
                hwid        TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)


def cmd_add(code: str):
    now = _now()
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO licenses (code, status, hwid, created_at, updated_at) VALUES (?, 'active', NULL, ?, ?)",
                (code, now, now),
            )
        print(f"[OK]  Added: {code}")
    except sqlite3.IntegrityError:
        print(f"[!!]  Already exists: {code}")


def cmd_revoke(code: str):
    with _conn() as c:
        r = c.execute(
            "UPDATE licenses SET status = 'revoked', updated_at = ? WHERE code = ?",
            (_now(), code),
        )
    if r.rowcount:
        print(f"[OK]  Revoked: {code}")
    else:
        print(f"[!!]  Not found: {code}")


def cmd_reset(code: str):
    with _conn() as c:
        r = c.execute(
            "UPDATE licenses SET hwid = NULL, status = 'active', updated_at = ? WHERE code = ?",
            (_now(), code),
        )
    if r.rowcount:
        print(f"[OK]  HWID cleared, status reset to active: {code}")
    else:
        print(f"[!!]  Not found: {code}")


def cmd_delete(code: str):
    with _conn() as c:
        r = c.execute("DELETE FROM licenses WHERE code = ?", (code,))
    if r.rowcount:
        print(f"[OK]  Deleted: {code}")
    else:
        print(f"[!!]  Not found: {code}")


def cmd_list():
    with _conn() as c:
        rows = c.execute(
            "SELECT code, status, hwid, created_at, updated_at FROM licenses ORDER BY created_at DESC"
        ).fetchall()
    if not rows:
        print("No licenses in database.")
        return
    print(f"{'CODE':<24} {'STATUS':<10} {'HWID':<35} CREATED")
    print("─" * 90)
    for r in rows:
        hwid = r["hwid"][:16] + "…" if r["hwid"] else "(unbound)"
        print(f"{r['code']:<24} {r['status']:<10} {hwid:<35} {r['created_at'][:19]}")


CMDS = {
    "add":    (cmd_add,    1),
    "revoke": (cmd_revoke, 1),
    "reset":  (cmd_reset,  1),
    "delete": (cmd_delete, 1),
    "list":   (cmd_list,   0),
}

if __name__ == "__main__":
    _ensure_db()
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    fn, nargs = CMDS[cmd]
    if nargs and len(sys.argv) < 3:
        print(f"Usage: python manage_licenses.py {cmd} <code>")
        sys.exit(1)

    args = sys.argv[2:2 + nargs]
    fn(*args)
