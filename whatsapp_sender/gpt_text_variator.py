"""
Генератор лёгких вариаций текста через OpenAI ChatGPT API.

Использует httpx (лучший TLS-стек на Windows, нет SSLEOFError).

Основная функция:
    generate_variant(base_text, api_key, model, temperature, ...) -> str

При любой ошибке возвращает исходный текст — рассылка не прерывается.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = """\
Ты помогаешь слегка переформулировать WhatsApp-сообщение для массовой рассылки.

Строгие правила:
1. Сохраняй ВСЕ URL без изменений — не трогай домен, путь, параметры, регистр.
2. Не меняй смысл: не добавляй обещаний, деталей и фактов которых нет в оригинале.
3. Не трогай числа: даты, время, суммы, проценты, номера телефонов.
4. Пиши на том же языке что и оригинал.
5. Допускается вернуть текст почти без изменений — это нормально и предпочтительно.
6. Не добавляй эмодзи если их не было в оригинале.
7. Верни ТОЛЬКО текст сообщения, без кавычек, без объяснений, без предисловий.
8. Не используй канцелярит, списки, «конечно!», «рад помочь» и другой ИИ-стиль.\
"""


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://\S+", text)


def _restore_urls(base_text: str, variant: str, urls: list[str]) -> str:
    for url in urls:
        if url not in variant:
            logger.warning("GPT изменил/удалил ссылку, вставляем оригинальную: %s", url)
            variant += f"\n{url}"
    return variant


def _build_proxy_url(proxies: dict | None) -> str | None:
    """Конвертирует dict-прокси requests-формата в одну строку для httpx."""
    if not proxies:
        return None
    url = proxies.get("https") or proxies.get("http") or ""
    if url and "://" not in url:
        url = "http://" + url   # забыли схему — добавляем
    return url or None


def generate_variant(
    base_text: str,
    api_key: str = "",
    model: str = "gpt-4.1-mini",
    temperature: float = 0.3,
    context: str | None = None,
    proxies: dict | None = None,
    timeout: int = 20,
) -> str:
    """
    Возвращает лёгкую вариацию base_text через ChatGPT.
    При любой ошибке возвращает исходный текст.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key or not base_text.strip():
        return base_text

    try:
        import httpx
    except ImportError:
        logger.error("httpx не установлен. Выполни: pip install httpx")
        return base_text

    urls     = _extract_urls(base_text)
    url_note = ""
    if urls:
        url_note = "\n\nСсылки — оставить ДОСЛОВНО без изменений:\n" + "\n".join(urls)

    ctx_note  = f"\nКонтекст: {context}" if context else ""
    user_msg  = (
        f"Переформулируй это сообщение{ctx_note}:\n\n"
        f"{base_text}{url_note}"
    )

    payload = {
        "model":       model,
        "temperature": temperature,
        "max_tokens":  1500,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }

    proxy_url = _build_proxy_url(proxies)

    def _do_request(verify: bool) -> str | None:
        """Один HTTP-запрос. Возвращает текст вариации или None при ошибке."""
        import time
        client_kwargs: dict = {"timeout": timeout, "verify": verify}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        # До 2 повторов при 429 (с экспоненциальным ожиданием)
        for attempt in range(2):
            try:
                with httpx.Client(**client_kwargs) as client:
                    resp = client.post(_OPENAI_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data    = resp.json()
                variant = data["choices"][0]["message"]["content"].strip()
                if not variant:
                    logger.warning("GPT: пустой ответ, используем оригинал.")
                    return None
                return variant

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429 and attempt == 0:
                    # Берём Retry-After из заголовка, минимум 60 сек (free tier лимит — 3 RPM)
                    retry_after = int(exc.response.headers.get("retry-after", 60))
                    retry_after = max(retry_after, 60)
                    logger.warning("GPT: rate limit (429), жду %ds…", retry_after)
                    time.sleep(retry_after)
                    continue
                logger.warning("GPT: HTTP %s, используем оригинальный текст.", status)
                return None

            except (httpx.TimeoutException, httpx.ConnectError):
                raise   # передаём выше для обработки по SSL-стратегии

            except Exception as exc:
                logger.warning("GPT: ошибка (%s), используем оригинальный текст.", exc)
                return None

        return None

    # Стратегия: сначала с проверкой сертификата, при SSL-ошибке — без
    for verify in (True, False):
        try:
            variant = _do_request(verify)
            if variant is None:
                return base_text
            variant = _restore_urls(base_text, variant, urls)
            logger.debug("GPT: вариация готова (%d → %d симв.)", len(base_text), len(variant))
            return variant

        except httpx.ConnectError as exc:
            if verify:
                logger.warning("GPT: SSL/connect ошибка, повторяю без проверки сертификата…")
                continue
            logger.warning("GPT: connect ошибка (%s), используем оригинальный текст.", exc)

        except httpx.TimeoutException:
            logger.warning("GPT: таймаут (%ds), используем оригинальный текст.", timeout)
            break

    return base_text
