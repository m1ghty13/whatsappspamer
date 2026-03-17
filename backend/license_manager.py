"""
License manager for Xivora WhatsApp Sender.

Handles:
  - Local license storage in license.json (project root)
  - HWID generation (SHA256 of hostname + MAC + username)
  - Remote verification against AMVERA license server
  - In-memory status: "not_activated" | "active" | "blocked"
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

# Change this URL to your actual AMVERA domain after deployment
BASE_LICENSE_URL = "https://licenseserver111-xivora.waw0.amvera.tech"

# license.json sits in the project root (one level above backend/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_FILE = os.path.join(_PROJECT_ROOT, "license.json")

REQUEST_TIMEOUT = 10  # seconds

# ── In-memory state ────────────────────────────────────────────────────────────

_status: str = "not_activated"  # "not_activated" | "active" | "blocked"
_reason: str = ""


def get_status() -> str:
    return _status


def get_reason() -> str:
    return _reason


def set_status(status: str, reason: str = "") -> None:
    global _status, _reason
    _status = status
    _reason = reason


# ── HWID ──────────────────────────────────────────────────────────────────────

def get_hwid() -> str:
    """
    Generate a stable hardware ID unique to this device.
    Combines: hostname + MAC address + OS username + machine type.
    Result: first 32 chars of SHA256 hex digest.
    """
    username = (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "unknown"
    )
    parts = [
        platform.node(),          # hostname
        str(uuid.getnode()),       # MAC as integer (most stable cross-platform)
        platform.machine(),        # e.g. AMD64
        username,
    ]
    raw = ":".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ── Local license file I/O ─────────────────────────────────────────────────────

def load_license() -> Optional[dict]:
    """Load license.json. Returns dict with keys (code, hwid, ...) or None."""
    if not os.path.exists(LICENSE_FILE):
        return None
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "code" in data and "hwid" in data:
            return data
        logger.warning("license.json has unexpected structure, ignoring.")
    except Exception as e:
        logger.warning("Failed to read license.json: %s", e)
    return None


def save_license(
    code: str,
    hwid: str,
    activated_at: str,
    last_check_at: str,
    status: str,
) -> None:
    """Write license data to license.json."""
    data = {
        "code": code,
        "hwid": hwid,
        "activated_at": activated_at,
        "last_check_at": last_check_at,
        "status": status,
    }
    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("License saved (code=%s…, status=%s)", code[:4], status)
    except Exception as e:
        logger.error("Failed to write license.json: %s", e)


def clear_license() -> None:
    """Delete local license file."""
    if os.path.exists(LICENSE_FILE):
        try:
            os.remove(LICENSE_FILE)
            logger.info("license.json deleted.")
        except Exception as e:
            logger.error("Failed to delete license.json: %s", e)


def is_activated() -> bool:
    """Quick check: is current in-memory status 'active'?"""
    return _status == "active"


def get_current_license() -> Optional[dict]:
    """Return the persisted license dict (or None)."""
    return load_license()


def _update_last_check(lic: dict) -> None:
    """Update last_check_at in license.json without changing other fields."""
    now = datetime.now(timezone.utc).isoformat()
    save_license(
        code=lic["code"],
        hwid=lic["hwid"],
        activated_at=lic.get("activated_at", now),
        last_check_at=now,
        status=lic.get("status", "active"),
    )


# ── Remote verification ────────────────────────────────────────────────────────

async def verify_with_server(code: str, hwid: str) -> tuple[bool, str]:
    """
    POST {BASE_LICENSE_URL}/license/verify  →  {valid: bool, reason: str}

    Returns:
      (True, "ok")               — license valid
      (False, "revoked")         — explicitly revoked
      (False, "code_not_found")  — unknown code
      (False, "hwid_mismatch")   — bound to another device
      (True,  "server_unavailable") — server unreachable → grace period
    """
    url = f"{BASE_LICENSE_URL}/license/verify"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(url, json={"code": code, "hwid": hwid})
        if resp.status_code == 200:
            body = resp.json()
            return bool(body.get("valid", False)), body.get("reason", "unknown")
        else:
            logger.warning("License server HTTP %s", resp.status_code)
            return False, f"server_http_{resp.status_code}"
    except httpx.ConnectError:
        logger.warning("License server unreachable — granting grace period.")
        return True, "server_unavailable"
    except httpx.TimeoutException:
        logger.warning("License server timed out — granting grace period.")
        return True, "server_unavailable"
    except Exception as e:
        logger.error("Unexpected license check error: %s", e)
        return True, "server_unavailable"


# ── Startup check ──────────────────────────────────────────────────────────────

async def check_on_startup() -> None:
    """
    Called once when the FastAPI backend starts.
    Loads local license.json and verifies it against the remote server.
    Sets the in-memory _status accordingly.
    """
    lic = load_license()
    if lic is None:
        set_status("not_activated")
        logger.info("License: not activated.")
        return

    code = lic["code"]
    hwid = lic["hwid"]
    current_hwid = get_hwid()

    # Sanity: if the license was saved for a different machine, block immediately
    if hwid != current_hwid:
        logger.warning("License HWID mismatch (local file tampered?). Blocking.")
        clear_license()
        set_status("blocked", "hwid_mismatch")
        return

    valid, reason = await verify_with_server(code, hwid)

    if valid:
        _update_last_check(lic)
        set_status("active", reason)
        logger.info("License: active (reason=%s).", reason)
    else:
        logger.warning("License check failed: %s. Blocking.", reason)
        clear_license()
        set_status("blocked", reason)


# ── Periodic recheck (background task) ────────────────────────────────────────

async def periodic_check_loop(interval_hours: int = 24) -> None:
    """
    Background asyncio task: re-verify license every `interval_hours`.
    If server says revoked → set blocked, clear local file.
    If server unreachable → keep current status (grace period).
    """
    import asyncio
    while True:
        await asyncio.sleep(interval_hours * 3600)
        lic = load_license()
        if lic is None or _status != "active":
            continue
        valid, reason = await verify_with_server(lic["code"], lic["hwid"])
        if not valid and reason != "server_unavailable":
            logger.warning("Periodic check: license revoked (%s). Blocking app.", reason)
            clear_license()
            set_status("blocked", reason)
        elif valid:
            _update_last_check(lic)
            logger.debug("Periodic license check passed.")
