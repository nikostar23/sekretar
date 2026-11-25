"""Транскрибация аудио через Whisper и проверка, что текст можно использовать."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")

# Типовые галлюцинации Whisper на тишине и шуме.
_HALLUCINATION_MARKERS = (
    "субтитры сделал",
    "субтитры создавал",
    "субтитры подогнал",
    "редактор субтитров",
    "продолжение следует",
    "спасибо за просмотр",
    "подписывайтесь на канал",
    "thanks for watching",
)


class LowQualityTranscription(Exception):
    """Речь не разобрана: текст пустой или похож на галлюцинацию модели."""

    def __init__(self, text: str) -> None:
        super().__init__("low quality transcript")
        self.text = text


def is_usable_transcript(text: str) -> bool:
    """Отсекает пустой результат и типичный мусор, не трогая нормальную короткую речь."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return False

    letters = sum(character.isalpha() for character in cleaned)
    if letters < 8:
        return False

    words = _WORD_RE.findall(cleaned)
    if len(words) < 2:
        return False
    if len({word.casefold() for word in words}) < 2:
        return False

    lowered = cleaned.casefold()
    for marker in _HALLUCINATION_MARKERS:
        if marker not in lowered:
            continue
        remainder = lowered.replace(marker, " ")
        if sum(character.isalpha() for character in remainder) < 20:
            return False
    return True


async def transcribe(
    client: Any,
    path: Path,
    *,
    model: str,
    language: str | None,
) -> str:
    """Отправляет файл в Whisper и возвращает текст либо сигнал о плохом качестве."""
    kwargs: dict[str, Any] = {"model": model, "file": None}
    if language:
        kwargs["language"] = language

    with path.open("rb") as audio_file:
        kwargs["file"] = audio_file
        result = await client.audio.transcriptions.create(**kwargs)

    text = getattr(result, "text", "") or ""
    text = text.strip()
    if not is_usable_transcript(text):
        logger.warning("whisper returned unusable transcript, chars=%s", len(text))
        raise LowQualityTranscription(text)
    return text
