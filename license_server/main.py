"""
Xivora License Server — deploy on AMVERA VPS.

Public:  POST /license/verify
Admin:   POST /license/add | /license/revoke | /license/reset | GET /license/list
         (require header:  X-API-Key: <ADMIN_API_KEY>)

Env vars:
  ADMIN_API_KEY  — admin secret (default: "change-me")
  DB_PATH        — SQLite path   (default: /data/licenses.db)
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

ADMIN_API_KEY: str = os.environ.get("ADMIN_API_KEY", "change-me")
DB_PATH: str = os.environ.get("DB_PATH", "/data/licenses.db")

if ADMIN_API_KEY == "change-me":
    logger.warning("ADMIN_API_KEY is not set!")

# ── Database ───────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init_db() -> None:
    # Create parent directory if needed (/data on AMVERA, or any custom path)
    parent = Path(DB_PATH).parent
    parent.mkdir(parents=True, exist_ok=True)
    logger.info("DB directory: %s", parent)

    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                code       TEXT PRIMARY KEY,
                status     TEXT NOT NULL DEFAULT 'active',
                hwid       TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
    logger.info("Database ready: %s", DB_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_db()
    yield


app = FastAPI(title="Xivora License Server", lifespan=lifespan,
              docs_url=None, redoc_url=None)

# ── Admin auth ─────────────────────────────────────────────────────────────────

def check_admin(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


# ── Models ─────────────────────────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    code: str
    hwid: str

class CodeRequest(BaseModel):
    code: str


# ── Public: verify ─────────────────────────────────────────────────────────────

@app.post("/license/verify")
def verify_license(req: VerifyRequest):
    code = req.code.strip()
    hwid = req.hwid.strip()

    with _conn() as c:
        row = c.execute("SELECT * FROM licenses WHERE code = ?", (code,)).fetchone()

    if row is None:
        return {"valid": False, "reason": "code_not_found"}

    if row["status"] == "revoked":
        return {"valid": False, "reason": "revoked"}

    if not row["hwid"]:
        # First activation — bind to this device
        with _conn() as c:
            c.execute("UPDATE licenses SET hwid = ?, updated_at = ? WHERE code = ?",
                      (hwid, _now(), code))
        logger.info("Code %s… bound to hwid %s…", code[:4], hwid[:8])
        return {"valid": True, "reason": "ok"}

    if row["hwid"] == hwid:
        return {"valid": True, "reason": "ok"}

    logger.warning("HWID mismatch for code %s…", code[:4])
    return {"valid": False, "reason": "hwid_mismatch"}


# ── Admin: add ─────────────────────────────────────────────────────────────────

@app.post("/license/add", dependencies=[Depends(check_admin)])
def add_license(req: CodeRequest):
    code = req.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="code_empty")
    now = _now()
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO licenses (code, status, hwid, created_at, updated_at) VALUES (?, 'active', NULL, ?, ?)",
                (code, now, now),
            )
        logger.info("Added: %s", code)
        return {"ok": True, "code": code}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="code_exists")


# ── Admin: revoke ──────────────────────────────────────────────────────────────

@app.post("/license/revoke", dependencies=[Depends(check_admin)])
def revoke_license(req: CodeRequest):
    code = req.code.strip()
    with _conn() as c:
        r = c.execute("UPDATE licenses SET status = 'revoked', updated_at = ? WHERE code = ?",
                      (_now(), code))
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="code_not_found")
    logger.info("Revoked: %s", code)
    return {"ok": True}


# ── Admin: reset HWID ──────────────────────────────────────────────────────────

@app.post("/license/reset", dependencies=[Depends(check_admin)])
def reset_hwid(req: CodeRequest):
    code = req.code.strip()
    with _conn() as c:
        r = c.execute(
            "UPDATE licenses SET hwid = NULL, status = 'active', updated_at = ? WHERE code = ?",
            (_now(), code),
        )
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="code_not_found")
    logger.info("Reset HWID for: %s", code)
    return {"ok": True}


# ── Admin: list ────────────────────────────────────────────────────────────────

@app.get("/license/list", dependencies=[Depends(check_admin)])
def list_licenses():
    with _conn() as c:
        rows = c.execute(
            "SELECT code, status, hwid, created_at, updated_at FROM licenses ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "80")))
