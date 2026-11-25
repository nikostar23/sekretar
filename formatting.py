"""Сборка ответа пользователю и нарезка длинных сообщений Telegram."""

from __future__ import annotations

TELEGRAM_MESSAGE_LIMIT = 4000


def format_success(transcript: str, theses: list[str]) -> str:
    thesis_block = "\n".join(f"{index}. {item}" for index, item in enumerate(theses, 1))
    return (
        "🎙 Транскрибация\n\n"
        f"{transcript.strip()}\n\n"
        "────────────────\n\n"
        "📌 Краткие тезисы\n\n"
        f"{thesis_block}"
    )


def format_theses_only(theses: list[str]) -> str:
    thesis_block = "\n".join(f"{index}. {item}" for index, item in enumerate(theses, 1))
    return (
        "📌 Краткие тезисы\n\n"
        f"{thesis_block}\n\n"
        "Полная транскрибация длиннее одного сообщения — отправил её файлом."
    )


def format_transcript_with_note(transcript: str, note: str) -> str:
    return f"{note}\n\n🎙 Транскрибация\n\n{transcript.strip()}"


def split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Делит текст на части не длиннее limit, по возможности по абзацам."""
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    if len(normalized) <= limit:
        return [normalized]

    parts: list[str] = []
    current = ""
    for paragraph in normalized.split("\n"):
        candidate = paragraph if not current else f"{current}\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        if len(paragraph) <= limit:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            parts.append(paragraph[start : start + limit])
            start += limit
    if current:
        parts.append(current)
    return [part for part in parts if part]
