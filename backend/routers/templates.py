"""
FastAPI router for /api/templates
CRUD for message templates stored in templates.json.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

TEMPLATES_FILE = Path("d:/python/new/templates.json")


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    if not TEMPLATES_FILE.exists():
        return []
    try:
        data = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Failed to load templates: %s", e)
        return []


def _save(templates: list[dict]) -> None:
    TEMPLATES_FILE.write_text(
        json.dumps(templates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Models ─────────────────────────────────────────────────────────────────────

class TemplateBody(BaseModel):
    name: str
    text: str
    url: str = ""
    button_text: str = ""
    button_url: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def list_templates():
    return _load()


@router.post("/")
async def create_template(body: TemplateBody):
    templates = _load()
    new_tmpl = {
        "id": str(uuid.uuid4()),
        **body.dict(),
    }
    templates.append(new_tmpl)
    _save(templates)
    return new_tmpl


@router.put("/{template_id}")
async def update_template(template_id: str, body: TemplateBody):
    templates = _load()
    for i, t in enumerate(templates):
        if t.get("id") == template_id:
            templates[i] = {"id": template_id, **body.dict()}
            _save(templates)
            return templates[i]
    raise HTTPException(status_code=404, detail="Template not found")


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    templates = _load()
    new_list = [t for t in templates if t.get("id") != template_id]
    if len(new_list) == len(templates):
        raise HTTPException(status_code=404, detail="Template not found")
    _save(new_list)
    return {"ok": True}
