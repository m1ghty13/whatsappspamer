"""
FastAPI router for /api/config
Manages proxy and GPT settings.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

sys.path.insert(0, "d:/python/new/whatsapp_sender")

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Models ─────────────────────────────────────────────────────────────────────

class ProxySettings(BaseModel):
    enabled: bool = False
    type: str = "HTTP"
    host: str = ""
    port: str = ""
    login: str = ""
    password: str = ""


class GptSettings(BaseModel):
    enabled: bool = False
    api_key: str = ""
    model: str = "gpt-4.1-mini"
    temperature: float = 0.3
    skip_proxy: bool = False


# ── Proxy endpoints ────────────────────────────────────────────────────────────

@router.get("/proxy")
async def get_proxy():
    import config_manager
    cfg = config_manager.load()
    return cfg.get("proxy", {})


@router.post("/proxy")
async def save_proxy(body: ProxySettings):
    import config_manager
    cfg = config_manager.load()
    cfg["proxy"] = body.dict()
    config_manager.save(cfg)
    return {"ok": True}


@router.post("/proxy/test")
async def test_proxy(body: ProxySettings):
    import config_manager

    proxy_dict = None
    if body.host:
        auth = ""
        if body.login:
            auth = f"{body.login}:{body.password}@"
        scheme = "socks5" if body.type == "SOCKS5" else "http"
        url = f"{scheme}://{auth}{body.host}:{body.port}"
        proxy_dict = {"http": url, "https": url}

    def _test():
        try:
            import httpx
            proxy_url = proxy_dict.get("https") if proxy_dict else None
            client_kwargs = {"timeout": 10}
            if proxy_url:
                client_kwargs["proxy"] = proxy_url
            with httpx.Client(**client_kwargs) as client:
                resp = client.get("https://api.ipify.org?format=json")
                resp.raise_for_status()
                ip = resp.json().get("ip", "unknown")
                return {"ok": True, "ip": ip, "error": None}
        except Exception as e:
            return {"ok": False, "ip": None, "error": str(e)}

    loop = asyncio.get_running_loop()
    import sys, importlib
    bm = sys.modules.get("__main__") or sys.modules.get("main") or importlib.import_module("main")
    result = await loop.run_in_executor(bm.get_executor(), _test)
    return result


# ── GPT endpoints ──────────────────────────────────────────────────────────────

@router.get("/gpt")
async def get_gpt():
    import config_manager
    cfg = config_manager.load()
    gpt = cfg.get("gpt", {}).copy()
    # Mask API key
    if gpt.get("api_key"):
        key = gpt["api_key"]
        gpt["api_key"] = key[:4] + "*" * (len(key) - 8) + key[-4:] if len(key) > 8 else "****"
        gpt["has_key"] = True
    else:
        gpt["has_key"] = False
    return gpt


@router.post("/gpt")
async def save_gpt(body: GptSettings):
    import config_manager
    cfg = config_manager.load()

    existing_gpt = cfg.get("gpt", {})

    # If api_key is masked (contains ***), preserve the original
    if "****" in body.api_key or (len(body.api_key) > 8 and "*" * 4 in body.api_key):
        body_dict = body.dict()
        body_dict["api_key"] = existing_gpt.get("api_key", "")
    else:
        body_dict = body.dict()

    cfg["gpt"] = body_dict
    config_manager.save(cfg)
    return {"ok": True}


@router.post("/gpt/test")
async def test_gpt(body: GptSettings):
    import config_manager

    # Resolve real API key
    api_key = body.api_key
    if "****" in api_key or (len(api_key) > 8 and "*" * 4 in api_key):
        cfg = config_manager.load()
        api_key = cfg.get("gpt", {}).get("api_key", "")

    if not api_key:
        return {"ok": False, "error": "No API key configured"}

    def _test():
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": body.model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Say: OK"}],
            }
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                return {"ok": True, "error": None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    loop = asyncio.get_running_loop()
    import sys, importlib
    bm = sys.modules.get("__main__") or sys.modules.get("main") or importlib.import_module("main")
    result = await loop.run_in_executor(bm.get_executor(), _test)
    return result
