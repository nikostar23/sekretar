"""Настройки бота из переменных окружения и файла .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
MIN_FILE_BYTES = 512
# Bot API отдаёт файл только до 20 МБ.
TELEGRAM_DOWNLOAD_LIMIT_BYTES = 20 * 1024 * 1024

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    openai_api_key: str
    openai_base_url: str | None
    whisper_model: str
    gpt_model: str
    whisper_language: str | None
    max_file_bytes: int
    log_level: str


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not token:
        raise RuntimeError(
            "Задайте TELEGRAM_BOT_TOKEN в файле .env или в переменных окружения."
        )
    if not api_key:
        raise RuntimeError(
            "Задайте OPENAI_API_KEY в файле .env или в переменных окружения."
        )

    language = os.getenv("WHISPER_LANGUAGE", "ru").strip()
    if language.lower() in {"", "auto"}:
        whisper_language = None
    else:
        whisper_language = language

    try:
        max_mb = int(os.getenv("MAX_FILE_MB", "20"))
    except ValueError:
        max_mb = 20
    max_mb = max(1, min(max_mb, 20))

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        log_level = "INFO"

    return Settings(
        telegram_token=token,
        openai_api_key=api_key,
        openai_base_url=_optional("OPENAI_BASE_URL"),
        whisper_model=os.getenv("WHISPER_MODEL", "whisper-1").strip() or "whisper-1",
        gpt_model=os.getenv("GPT_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        whisper_language=whisper_language,
        max_file_bytes=max_mb * 1024 * 1024,
        log_level=log_level,
    )
