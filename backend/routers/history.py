"""
FastAPI router for /api/history
Reads history.csv and returns records with filtering/stats.
"""

from __future__ import annotations

import csv
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, "d:/python/new/whatsapp_sender")

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter()

HISTORY_FILE = Path("d:/python/new/history.csv")


def _read_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    records = []
    try:
        with open(HISTORY_FILE, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(dict(row))
    except Exception as e:
        logger.error("Failed to read history: %s", e)
    return records


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def get_history(
    limit: int = Query(100, ge=1, le=10000),
    status: str = Query("all"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    records = _read_history()

    # Filter by status
    if status != "all":
        records = [r for r in records if r.get("status", "") == status]

    # Filter by date range (timestamp field format: YYYY-MM-DD HH:MM:SS)
    if date_from:
        records = [r for r in records if r.get("timestamp", "") >= date_from]
    if date_to:
        date_to_end = date_to + " 23:59:59" if len(date_to) == 10 else date_to
        records = [r for r in records if r.get("timestamp", "") <= date_to_end]

    total = len(records)

    # Most recent first
    records_sorted = list(reversed(records))
    paginated = records_sorted[:limit]

    return {"records": paginated, "total": total}


@router.get("/stats")
async def get_stats():
    records = _read_history()

    total = len(records)
    success = sum(1 for r in records if r.get("status") == "success")
    failed = sum(1 for r in records if r.get("status") == "failed")

    by_date_map: dict[str, dict] = defaultdict(lambda: {"success": 0, "failed": 0})
    for r in records:
        ts = r.get("timestamp", "")
        date = ts[:10] if ts else "unknown"
        st = r.get("status", "")
        if st == "success":
            by_date_map[date]["success"] += 1
        elif st == "failed":
            by_date_map[date]["failed"] += 1

    by_date = [
        {"date": d, "success": v["success"], "failed": v["failed"]}
        for d, v in sorted(by_date_map.items())
    ]

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "by_date": by_date,
    }
