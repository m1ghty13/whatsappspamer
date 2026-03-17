"""
FastAPI backend for Xivora WhatsApp Sender.
Serves on port 8765, WebSocket at /ws for real-time events.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
# Works both in dev (d:/python/new/backend/) and in packaged app (resources/backend/)
_BACKEND_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_WHATSAPP_DIR = os.path.join(_PROJECT_ROOT, "whatsapp_sender")

sys.path.insert(0, _WHATSAPP_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _BACKEND_DIR)

os.chdir(_PROJECT_ROOT)

# ── FastAPI imports ────────────────────────────────────────────────────────────
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── License ────────────────────────────────────────────────────────────────────
import license_manager

# ── Internal imports ──────────────────────────────────────────────────────────
from account_manager import AccountManager, AccountStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── WebSocket Connection Manager ───────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active.append(ws)
        logger.info("WS client connected. Total: %d", len(self.active))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.active = [c for c in self.active if c is not ws]
        logger.info("WS client disconnected. Total: %d", len(self.active))

    async def broadcast(self, payload: dict) -> None:
        msg = json.dumps(payload, ensure_ascii=False)
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self.active)
        for ws in targets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                self.active = [c for c in self.active if c not in dead]


ws_manager = ConnectionManager()

# ── Shared broadcast function used by routers ─────────────────────────────────

async def ws_broadcast(event_type: str, data: dict) -> None:
    payload = {"type": event_type, **data}
    await ws_manager.broadcast(payload)


# ── Global state shared across routers ────────────────────────────────────────

_loop: asyncio.AbstractEventLoop | None = None
_executor = ThreadPoolExecutor(max_workers=4)
account_manager: AccountManager | None = None

# QR cache: account_id -> base64 PNG string
_qr_cache: dict[str, str] = {}


def _schedule_broadcast(event_type: str, data: dict) -> None:
    """Thread-safe: schedule a coroutine on the event loop from a sync thread."""
    if _loop is not None and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(ws_broadcast(event_type, data), _loop)


def _on_qr_callback(account_id: str, qr_data: bytes) -> None:
    """Called from account thread when QR is generated."""
    try:
        import segno
        buf = io.BytesIO()
        segno.make_qr(qr_data).save(buf, kind="png", scale=10, border=2)
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        _qr_cache[account_id] = qr_b64
        _schedule_broadcast("account_qr", {"id": account_id, "qr_b64": qr_b64})
    except Exception as e:
        logger.error("QR callback error: %s", e)


def _on_status_callback(account_id: str, status: AccountStatus, phone: str) -> None:
    """Called from account thread when status changes."""
    _schedule_broadcast("account_status", {
        "id": account_id,
        "status": status.value,
        "phone": phone,
    })


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(title="Xivora WhatsApp Sender", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    global _loop, account_manager
    _loop = asyncio.get_running_loop()

    # ── License check ──────────────────────────────────────────────────────────
    await license_manager.check_on_startup()
    # Start background periodic re-check every 24 h
    asyncio.create_task(license_manager.periodic_check_loop(interval_hours=24))

    # Initialize AccountManager (restores sessions on startup)
    account_manager = AccountManager()
    account_manager.on_qr = _on_qr_callback
    account_manager.on_status = _on_status_callback

    logger.info("Backend started. AccountManager initialized.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    _executor.shutdown(wait=False)
    logger.info("Backend shutting down.")


# ── Health endpoint ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True, "status": "running"}


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        # Send initial account states
        if account_manager:
            for info in account_manager.get_all():
                await ws_broadcast("account_status", {
                    "id": info.account_id,
                    "status": info.status.value,
                    "phone": info.phone,
                })
        while True:
            # Keep connection alive; client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS error: %s", e)
    finally:
        await ws_manager.disconnect(websocket)


# ── QR endpoint ───────────────────────────────────────────────────────────────

@app.get("/api/accounts/{account_id}/qr")
async def get_account_qr(account_id: str):
    from fastapi import HTTPException
    if not license_manager.is_activated():
        raise HTTPException(status_code=403, detail="license_not_active")
    qr_b64 = _qr_cache.get(account_id)
    if qr_b64 is None:
        raise HTTPException(status_code=404, detail="QR not available")
    return {"account_id": account_id, "qr_b64": qr_b64}


# ── Include routers ────────────────────────────────────────────────────────────

from routers import accounts, contacts, broadcast, config_router, history, templates
from routers.license import router as license_router, require_license

# License routes — always accessible (needed to activate / check status)
app.include_router(license_router, prefix="/api/license", tags=["license"])

# All business routes require an active license
_lic = [Depends(require_license)]
app.include_router(accounts.router,     prefix="/api/accounts",  tags=["accounts"],  dependencies=_lic)
app.include_router(contacts.router,     prefix="/api/contacts",  tags=["contacts"],  dependencies=_lic)
app.include_router(broadcast.router,    prefix="/api/broadcast", tags=["broadcast"], dependencies=_lic)
app.include_router(config_router.router,prefix="/api/config",    tags=["config"],    dependencies=_lic)
app.include_router(history.router,      prefix="/api/history",   tags=["history"],   dependencies=_lic)
app.include_router(templates.router,    prefix="/api/templates", tags=["templates"], dependencies=_lic)


# ── Expose shared objects for routers ─────────────────────────────────────────

def get_account_manager() -> AccountManager:
    return account_manager


def get_executor() -> ThreadPoolExecutor:
    return _executor


def get_qr_cache() -> dict[str, str]:
    return _qr_cache


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Pass app object directly (not "main:app" string) so uvicorn works
    # regardless of cwd or sys.path order
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="info",
    )
