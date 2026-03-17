"""
Чтение контактов из CSV/TXT и валидация номеров ОАЭ.

Формат номера ОАЭ:
  +971 5X XXXXXXX  (мобильные префиксы: 50, 52, 54, 55, 56, 58)
  Итого: 12 цифр без '+', первые три — 971.
"""

import re
import csv
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Допустимые мобильные префиксы ОАЭ (после 971)
UAE_MOBILE_PREFIXES = {"50", "52", "54", "55", "56", "58"}


@dataclass
class Contact:
    raw: str          # исходная строка из файла
    phone: str        # нормализованный номер (без '+', e164)
    name: str = ""    # опциональное поле из CSV


def normalize_uae(raw: str) -> str | None:
    """
    Принимает строку в любом формате, возвращает E.164 без '+' (971XXXXXXXXX)
    или None если номер невалиден.

    Примеры входных форматов:
      +971 50 123 4567  →  971501234567
      00971501234567    →  971501234567
      0501234567        →  971501234567
      501234567         →  971501234567
    """
    digits = re.sub(r"[^\d]", "", raw)

    if digits.startswith("00971"):
        digits = digits[2:]          # 00971... → 971...
    elif digits.startswith("971"):
        pass                         # уже в правильном формате
    elif digits.startswith("0") and len(digits) == 10:
        digits = "971" + digits[1:]  # 0501234567 → 971501234567
    elif len(digits) == 9:
        digits = "971" + digits      # 501234567  → 971501234567

    if not re.fullmatch(r"971\d{9}", digits):
        return None

    prefix = digits[3:5]
    if prefix not in UAE_MOBILE_PREFIXES:
        logger.debug("Пропущен номер с неизвестным префиксом ОАЭ: %s", digits)
        return None

    return digits


def load_contacts(filepath: str) -> list[Contact]:
    """
    Загружает контакты из CSV или TXT файла.

    CSV: должен содержать колонку 'phone' (обязательно) и опционально 'name'.
    TXT: каждая строка — один номер телефона.

    Возвращает список валидных Contact объектов.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл контактов не найден: {filepath}")

    contacts: list[Contact] = []
    skipped = 0

    if path.suffix.lower() == ".csv":
        contacts, skipped = _load_csv(path)
    else:
        contacts, skipped = _load_txt(path)

    logger.info(
        "Загружено %d валидных контактов, пропущено %d невалидных.",
        len(contacts),
        skipped,
    )
    return contacts


def _load_csv(path: Path) -> tuple[list[Contact], int]:
    contacts: list[Contact] = []
    skipped = 0

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if "phone" not in (reader.fieldnames or []):
            raise ValueError(
                f"CSV файл '{path}' должен содержать колонку 'phone'. "
                f"Найденные колонки: {reader.fieldnames}"
            )

        for row in reader:
            raw = row.get("phone", "").strip()
            normalized = normalize_uae(raw)
            if normalized:
                contacts.append(
                    Contact(
                        raw=raw,
                        phone=normalized,
                        name=row.get("name", "").strip(),
                    )
                )
            else:
                logger.warning("Невалидный номер пропущен: '%s'", raw)
                skipped += 1

    return contacts, skipped


def _load_txt(path: Path) -> tuple[list[Contact], int]:
    contacts: list[Contact] = []
    skipped = 0

    with open(path, encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            normalized = normalize_uae(raw)
            if normalized:
                contacts.append(Contact(raw=raw, phone=normalized))
            else:
                logger.warning("Невалидный номер пропущен: '%s'", raw)
                skipped += 1

    return contacts, skipped
