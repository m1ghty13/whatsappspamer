"""
Логирование результатов отправки.

Сохраняет результаты в JSON (полная история) и CSV (удобно открыть в Excel).
Файлы создаются в директории results/ с timestamp в имени.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from whatsapp_client import SendResult, SendStatus

logger = logging.getLogger(__name__)


class ResultLogger:
    """
    Записывает результаты отправки в JSON и CSV файлы.

    Использование:
        with ResultLogger("results") as log:
            log.record(send_result)
    """

    def __init__(self, results_dir: str = "results") -> None:
        self._dir = Path(results_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._json_path = self._dir / f"results_{timestamp}.json"
        self._csv_path = self._dir / f"results_{timestamp}.csv"

        self._records: list[dict] = []
        self._csv_file = None
        self._csv_writer = None

        self._stats = {
            SendStatus.SUCCESS: 0,
            SendStatus.FAILED: 0,
            SendStatus.INVALID_PHONE: 0,
        }

    def __enter__(self) -> "ResultLogger":
        self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8-sig")
        self._csv_writer = csv.DictWriter(
            self._csv_file,
            fieldnames=["timestamp", "phone", "status", "message_id", "message_text", "error"],
        )
        self._csv_writer.writeheader()
        logger.info("Логи сохраняются в: %s", self._dir.resolve())
        return self

    def __exit__(self, *_) -> None:
        self._flush_json()
        if self._csv_file:
            self._csv_file.close()
        self._print_summary()

    def record(self, result: SendResult) -> None:
        """Записывает один результат отправки."""
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "phone": result.phone,
            "status": result.status.value,
            "message_id": result.message_id,
            "message_text": result.message_text,
            "error": result.error,
        }
        self._records.append(entry)
        self._stats[result.status] += 1

        if self._csv_writer:
            self._csv_writer.writerow(entry)
            self._csv_file.flush()

    def _flush_json(self) -> None:
        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(self._records, f, ensure_ascii=False, indent=2)

    def _print_summary(self) -> None:
        total = sum(self._stats.values())
        success = self._stats[SendStatus.SUCCESS]
        print("\n" + "─" * 45)
        print(f"  Итого обработано : {total}")
        print(f"  ✓ Успешно        : {success}")
        print(f"  ✗ Не в WhatsApp  : {self._stats[SendStatus.INVALID_PHONE]}")
        print(f"  ✗ Прочие ошибки  : {self._stats[SendStatus.FAILED]}")
        print(f"  CSV : {self._csv_path}")
        print(f"  JSON: {self._json_path}")
        print("─" * 45 + "\n")
