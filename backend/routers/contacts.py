"""
FastAPI router for /api/contacts
Handles CSV/TXT upload, queue management.
"""

from __future__ import annotations

import csv
import io
import logging
import sys
from pathlib import Path

sys.path.insert(0, "d:/python/new/whatsapp_sender")

from fastapi import APIRouter, HTTPException, UploadFile, File

logger = logging.getLogger(__name__)

router = APIRouter()

QUEUE_FILE = Path("d:/python/new/queue.csv")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_contacts(file: UploadFile = File(...)):
    """Upload CSV or TXT file, validate UAE numbers, return parsed contacts."""
    from contact_manager import normalize_uae

    content = await file.read()
    filename = (file.filename or "").lower()

    contacts: list[dict] = []
    invalid_count = 0

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    if filename.endswith(".csv"):
        try:
            reader = csv.DictReader(io.StringIO(text))
            fields = reader.fieldnames or []
            if "phone" not in fields:
                raise HTTPException(
                    status_code=400,
                    detail=f"CSV must have a 'phone' column. Found: {fields}",
                )
            for row in reader:
                raw = (row.get("phone") or "").strip()
                normalized = normalize_uae(raw)
                if normalized:
                    contacts.append({
                        "phone": normalized,
                        "name": (row.get("name") or "").strip(),
                    })
                else:
                    invalid_count += 1
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    elif filename.endswith(".txt"):
        for line in text.splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            normalized = normalize_uae(raw)
            if normalized:
                contacts.append({"phone": normalized, "name": ""})
            else:
                invalid_count += 1
    else:
        raise HTTPException(status_code=400, detail="Only .csv or .txt files are supported.")

    return {
        "contacts": contacts,
        "total": len(contacts),
        "invalid": invalid_count,
    }


@router.get("/queue")
async def get_queue():
    """Return contacts currently in queue.csv."""
    if not QUEUE_FILE.exists():
        return {"contacts": [], "total": 0}

    contacts = []
    try:
        with open(QUEUE_FILE, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                phone = (row.get("phone") or "").strip()
                if phone:
                    contacts.append({
                        "phone": phone,
                        "name": (row.get("name") or "").strip(),
                    })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read queue: {e}")

    return {"contacts": contacts, "total": len(contacts)}


@router.delete("/queue")
async def clear_queue():
    """Clear queue.csv."""
    if QUEUE_FILE.exists():
        try:
            QUEUE_FILE.unlink()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to clear queue: {e}")
    return {"ok": True}
