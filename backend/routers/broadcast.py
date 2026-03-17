"""
FastAPI router for /api/broadcast
Manages the BroadcastService singleton.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Optional

sys.path.insert(0, "d:/python/new/whatsapp_sender")
sys.path.insert(0, "d:/python/new/backend")

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Lazy singleton ─────────────────────────────────────────────────────────────

_broadcast_service = None


def _get_service():
    global _broadcast_service
    if _broadcast_service is None:
        # Import lazily to avoid circular import at module load time
        import sys
        import importlib
        backend_main = sys.modules.get("__main__") or sys.modules.get("main") or importlib.import_module("main")
        from broadcast_service import BroadcastService

        am = backend_main.get_account_manager()
        if am is None:
            return None

        svc = BroadcastService(am)

        def _on_progress(done: int, total: int, phone: str):
            backend_main._schedule_broadcast("broadcast_progress", {
                "done": done,
                "total": total,
                "phone": phone,
            })

        def _on_log(text: str):
            backend_main._schedule_broadcast("broadcast_log", {"text": text})

        def _on_done(sent: int, errors: int, stopped: bool):
            backend_main._schedule_broadcast("broadcast_done", {
                "sent": sent,
                "errors": errors,
                "stopped": stopped,
            })

        svc.on_progress = _on_progress
        svc.on_log = _on_log
        svc.on_done = _on_done

        _broadcast_service = svc
    return _broadcast_service


# ── Models ─────────────────────────────────────────────────────────────────────

class StartBroadcastBody(BaseModel):
    contacts: list[dict]
    text: str
    url: str = ""
    button_text: str = ""
    button_url: str = ""
    gpt_enabled: bool = False
    gpt_proxies: Optional[dict] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start")
async def start_broadcast(body: StartBroadcastBody):
    svc = _get_service()
    if svc is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    if svc.status == "running":
        raise HTTPException(status_code=409, detail="Broadcast already running")

    if not body.contacts:
        raise HTTPException(status_code=400, detail="No contacts provided")

    # Build GPT config from stored settings
    import config_manager
    cfg = config_manager.load()
    gpt_cfg = cfg.get("gpt", {}).copy()
    gpt_cfg["enabled"] = body.gpt_enabled

    # Resolve proxy for GPT if not skipping
    gpt_proxies = body.gpt_proxies
    if gpt_proxies is None and not gpt_cfg.get("skip_proxy"):
        gpt_proxies = config_manager.get_proxy_settings(cfg)

    loop = asyncio.get_running_loop()
    executor_fn = lambda: svc.start(
        contacts=body.contacts,
        text=body.text,
        url=body.url,
        button_text=body.button_text,
        button_url=body.button_url,
        gpt_cfg=gpt_cfg,
        gpt_proxies=gpt_proxies,
    )

    import sys, importlib
    bm = sys.modules.get("__main__") or sys.modules.get("main") or importlib.import_module("main")
    await loop.run_in_executor(bm.get_executor(), executor_fn)

    return {"ok": True, "total": len(body.contacts)}


@router.post("/stop")
async def stop_broadcast():
    svc = _get_service()
    if svc is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    svc.stop()
    return {"ok": True}


@router.get("/status")
async def get_broadcast_status():
    svc = _get_service()
    if svc is None:
        return {"status": "idle", "done": 0, "total": 0, "errors": 0}
    return svc.get_status()
