"""
Управление конфигурацией приложения (config.json).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.json")

_DEFAULTS: dict = {
    "proxy": {
        "enabled": False,
        "type": "HTTP",
        "host": "",
        "port": "",
        "login": "",
        "password": "",
    },
    "message": "",
    "event_url": "",
    "gpt": {
        "enabled": False,
        "api_key": "",
        "model": "gpt-4.1-mini",
        "temperature": 0.3,
        "proxy_mode": "none",    # none | system | custom
        "custom_proxy": "",      # socks5://... или http://...
    },
}


def load() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            # Merge with defaults so new keys are always present
            merged = _DEFAULTS.copy()
            merged.update(data)
            return merged
        except Exception as e:
            logger.warning("Не удалось прочитать config.json: %s", e)
    return _DEFAULTS.copy()


def save(data: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_proxy_settings(cfg: dict) -> dict | None:
    """
    Возвращает словарь прокси в формате для requests/httpx,
    или None если прокси отключён.

    Пример возвращаемого значения:
        {"http": "http://user:pass@host:port",
         "https": "http://user:pass@host:port"}
    """
    p = cfg.get("proxy", {})
    if not p.get("enabled") or not p.get("host"):
        return None

    auth = ""
    if p.get("login"):
        auth = f"{p['login']}:{p['password']}@"

    scheme = "socks5" if p.get("type") == "SOCKS5" else "http"
    url = f"{scheme}://{auth}{p['host']}:{p['port']}"
    return {"http": url, "https": url}
