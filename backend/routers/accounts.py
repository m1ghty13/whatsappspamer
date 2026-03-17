"""
FastAPI router for /api/accounts
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

sys.path.insert(0, "d:/python/new/whatsapp_sender")
sys.path.insert(0, "d:/python/new/backend")

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_main():
    import sys
    import importlib
    return sys.modules.get("__main__") or sys.modules.get("main") or importlib.import_module("main")


def _get_am():
    return _get_main().get_account_manager()


def _get_executor():
    return _get_main().get_executor()


def _get_qr_cache():
    return _get_main().get_qr_cache()


# ── Models ─────────────────────────────────────────────────────────────────────

class AutoProfileBody(BaseModel):
    name: str = ""
    photo_path: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def list_accounts():
    am = _get_am()
    if am is None:
        return []
    result = []
    for info in am.get_all():
        result.append({
            "id": info.account_id,
            "status": info.status.value,
            "phone": info.phone,
            "sent_count": info.sent_count,
            "error_count": info.error_count,
        })
    return result


@router.post("/")
async def add_account():
    am = _get_am()
    if am is None:
        raise HTTPException(status_code=503, detail="AccountManager not ready")

    loop = asyncio.get_running_loop()
    executor = _get_executor()

    def _add():
        return am.add_account()

    account_id = await loop.run_in_executor(executor, _add)
    return {"account_id": account_id}


@router.delete("/{account_id}")
async def delete_account(account_id: str):
    am = _get_am()
    if am is None:
        raise HTTPException(status_code=503, detail="AccountManager not ready")

    loop = asyncio.get_running_loop()
    executor = _get_executor()

    def _remove():
        am.remove_account(account_id)

    await loop.run_in_executor(executor, _remove)

    # Clear QR cache
    _get_qr_cache().pop(account_id, None)

    return {"ok": True}


@router.get("/auto_profile")
async def get_auto_profile():
    import config_manager
    cfg = config_manager.load()
    profile = cfg.get("auto_profile", {"name": "", "photo_path": ""})
    return profile


@router.post("/auto_profile")
async def set_auto_profile(body: AutoProfileBody):
    import config_manager
    cfg = config_manager.load()
    cfg["auto_profile"] = {
        "name": body.name,
        "photo_path": body.photo_path,
    }
    config_manager.save(cfg)

    # Update AccountManager's auto_profile
    am = _get_am()
    if am is not None:
        am.auto_profile = cfg["auto_profile"]

    return {"ok": True}
