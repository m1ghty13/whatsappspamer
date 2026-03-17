"""
BroadcastService — non-Qt sequential WhatsApp broadcast with GPT variation support.
Runs in a background thread with interruptible delays.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BroadcastService:
    """
    Manages a sequential broadcast to a list of contacts.

    Callbacks (set before calling start):
        on_progress(done, total, phone)
        on_log(text)
        on_done(sent, errors, stopped)
    """

    def __init__(self, account_manager):
        self._am = account_manager
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Callbacks — set by the caller
        self.on_progress: Optional[Callable[[int, int, str], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_done: Optional[Callable[[int, int, bool], None]] = None

        # State
        self.status: str = "idle"   # idle | running | stopped
        self.done: int = 0
        self.total: int = 0
        self.errors: int = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(
        self,
        contacts: list[dict],
        text: str,
        url: str = "",
        button_text: str = "",
        button_url: str = "",
        gpt_cfg: Optional[dict] = None,
        gpt_proxies: Optional[dict] = None,
    ) -> None:
        """Start broadcast in a background thread. No-op if already running."""
        if self.status == "running":
            logger.warning("BroadcastService.start() called while already running.")
            return

        self._stop_event.clear()
        self.done = 0
        self.total = len(contacts)
        self.errors = 0
        self.status = "running"

        self._thread = threading.Thread(
            target=self._run,
            args=(contacts, text, url, button_text, button_url, gpt_cfg or {}, gpt_proxies),
            daemon=True,
            name="BroadcastThread",
        )
        self._thread.start()
        self._log(f"Broadcast started: {self.total} contacts.")

    def stop(self) -> None:
        """Request graceful stop. Returns immediately; thread finishes current send."""
        if self.status == "running":
            self._stop_event.set()
            self.status = "stopped"
            self._log("Stop requested.")

    def get_status(self) -> dict:
        return {
            "status": self.status,
            "done": self.done,
            "total": self.total,
            "errors": self.errors,
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        logger.info("[Broadcast] %s", text)
        if self.on_log:
            try:
                self.on_log(text)
            except Exception:
                pass

    def _run(
        self,
        contacts: list[dict],
        text: str,
        url: str,
        button_text: str,
        button_url: str,
        gpt_cfg: dict,
        gpt_proxies: Optional[dict],
    ) -> None:
        """Main broadcast loop running in background thread."""
        import sys
        sys.path.insert(0, "d:/python/new/whatsapp_sender")

        try:
            from gpt_text_variator import generate_variant
            import history_manager
        except ImportError as e:
            self._log(f"Import error: {e}")
            self.status = "idle"
            return

        sent = 0
        errors = 0
        remaining: list[dict] = list(contacts)

        for idx, contact in enumerate(contacts):
            if self._stop_event.is_set():
                remaining = contacts[idx:]
                break

            phone = contact.get("phone", "").strip()
            name = contact.get("name", "").strip()

            if not phone:
                errors += 1
                self.errors = errors
                self._log(f"[{idx+1}/{self.total}] Skipped empty phone.")
                continue

            # GPT variation
            message = text
            if gpt_cfg.get("enabled") and gpt_cfg.get("api_key"):
                try:
                    message = generate_variant(
                        base_text=text,
                        api_key=gpt_cfg.get("api_key", ""),
                        model=gpt_cfg.get("model", "gpt-4.1-mini"),
                        temperature=float(gpt_cfg.get("temperature", 0.3)),
                        proxies=None if gpt_cfg.get("skip_proxy") else gpt_proxies,
                    )
                except Exception as e:
                    self._log(f"GPT error (using original): {e}")

            # Find a connected account to send from
            workers = self._am.get_connected()
            if not workers:
                self._log("No connected accounts. Stopping broadcast.")
                errors += 1
                self.errors = errors
                remaining = contacts[idx:]
                break

            # Pick account with fewest sent (round-robin-ish)
            worker = min(workers, key=lambda t: t._info.sent_count)
            account_id = worker._info.account_id

            self._log(f"[{idx+1}/{self.total}] Sending to {phone} ({name}) via {account_id}…")

            ok = worker.send(
                phone=phone,
                text=message,
                url=url,
                button_text=button_text,
                button_url=button_url,
            )

            if ok:
                sent += 1
                history_manager.record_sent(phone, name, "success", message)
                self._log(f"  ✓ Sent to {phone}")
            else:
                errors += 1
                history_manager.record_sent(phone, name, "failed", message)
                self._log(f"  ✗ Failed to send to {phone}")

            self.done = idx + 1
            self.errors = errors

            if self.on_progress:
                try:
                    self.on_progress(self.done, self.total, phone)
                except Exception:
                    pass

            # Remove from remaining
            if idx + 1 < len(contacts):
                remaining = contacts[idx + 1:]
            else:
                remaining = []

            # Interruptible delay between sends (10-25 seconds)
            if idx + 1 < self.total and not self._stop_event.is_set():
                delay = random.uniform(10, 25)
                self._log(f"  Waiting {delay:.1f}s before next send…")
                elapsed = 0.0
                while elapsed < delay:
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.4)
                    elapsed += 0.4

        # Save remaining queue
        try:
            import history_manager
            history_manager.save_queue(remaining)
        except Exception as e:
            self._log(f"Failed to save queue: {e}")

        stopped = self._stop_event.is_set()
        self.status = "idle"

        self._log(
            f"Broadcast {'stopped' if stopped else 'done'}. "
            f"Sent: {sent}, Errors: {errors}, Remaining: {len(remaining)}"
        )

        if self.on_done:
            try:
                self.on_done(sent, errors, stopped)
            except Exception:
                pass
