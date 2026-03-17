"""
FastAPI router for /api/license

Endpoints:
  GET  /api/license/status    — current activation status
  POST /api/license/activate  — activate with a code
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, "d:/python/new/backend")

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import license_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Dependency injected into all protected routers ────────────────────────────

async def require_license() -> None:
    """
    FastAPI dependency. Raises HTTP 403 if license is not active.
    Add to any router:  router = APIRouter(dependencies=[Depends(require_license)])
    """
    if not license_manager.is_activated():
        raise HTTPException(
            status_code=403,
            detail="license_not_active",
        )


# ── Request / response models ─────────────────────────────────────────────────

class ActivateRequest(BaseModel):
    code: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_license_status():
    """Return current in-memory license status."""
    return {
        "status": license_manager.get_status(),
        "reason": license_manager.get_reason(),
    }


@router.post("/activate")
async def activate_license(req: ActivateRequest):
    """
    Activate with a code.
    1. Generates HWID for this machine.
    2. Sends {code, hwid} to AMVERA license server.
    3. On success: persists license.json, sets in-memory status to 'active'.
    4. On failure: returns {status: 'error', message: <human-readable>}.
    """
    code = req.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="code_empty")

    hwid = license_manager.get_hwid()
    valid, reason = await license_manager.verify_with_server(code, hwid)

    if reason == "server_unavailable":
        return {
            "status": "error",
            "message": "Сервер лицензий недоступен. Проверьте интернет-соединение и попробуйте позже.",
        }

    if valid:
        now = datetime.now(timezone.utc).isoformat()
        license_manager.save_license(
            code=code,
            hwid=hwid,
            activated_at=now,
            last_check_at=now,
            status="active",
        )
        license_manager.set_status("active")
        logger.info("License activated successfully (code=%s…)", code[:4])
        return {"status": "active"}

    # Map server reason to user-friendly Russian message
    messages = {
        "code_not_found": "Код не найден. Проверьте правильность ввода.",
        "revoked":        "Этот код был отозван. Обратитесь к разработчику.",
        "hwid_mismatch":  "Код уже привязан к другому устройству.",
    }
    msg = messages.get(reason, f"Ошибка активации: {reason}")
    return {"status": "error", "message": msg}
