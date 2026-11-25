"""Выделение 1–7 тезисов из готовой транскрибации."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from prompts import SUMMARIZER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_ITEM_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

MAX_THESES = 7


class SummarizerError(Exception):
    """Модель не вернула ни одного пригодного тезиса."""


def _loads_embedded(raw: str) -> Any | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            continue
    return None


def _clean_item(value: Any) -> str:
    text = " ".join(str(value).split())
    text = _ITEM_PREFIX_RE.sub("", text).strip()
    return text


def _items_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        items = payload.get("theses", payload.get("тезисы"))
        if isinstance(items, str):
            return [items]
        if isinstance(items, list):
            return items
        return []
    if isinstance(payload, list):
        return payload
    return []


def _fallback_lines(raw: str) -> list[str]:
    items: list[str] = []
    for line in raw.splitlines():
        match = _LINE_RE.match(line)
        if match:
            items.append(match.group(1).strip())
    return items


def parse_theses(raw: str) -> list[str]:
    """Достаёт тезисы из JSON или нумерованного списка и оставляет не больше семи."""
    text = _FENCE_RE.sub("", raw.strip()).strip()
    payload = _loads_embedded(text)
    source = _items_from_payload(payload) if payload is not None else _fallback_lines(text)

    theses: list[str] = []
    seen: set[str] = set()
    for item in source:
        cleaned = _clean_item(item)
        if not cleaned:
            continue
        key = cleaned.casefold().rstrip(".")
        if key in seen:
            continue
        seen.add(key)
        theses.append(cleaned)
        if len(theses) == MAX_THESES:
            break
    return theses


async def _complete(client: Any, model: str, messages: list[dict[str, str]]) -> str:
    from openai import BadRequestError

    try:
        completion = await client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=messages,
        )
    except BadRequestError as exc:
        if "temperature" not in str(exc).lower():
            raise
        logger.info("model rejected temperature, retrying without it")
        completion = await client.chat.completions.create(model=model, messages=messages)

    return (completion.choices[0].message.content or "").strip()


async def summarize(client: Any, transcript: str, *, model: str) -> list[str]:
    """Просит модель выделить тезисы. Один повтор, если ответ не разобрался."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Транскрибация:\n\n{transcript}"},
    ]

    last_raw = ""
    for attempt in range(2):
        last_raw = await _complete(client, model, messages)
        theses = parse_theses(last_raw)
        if theses:
            return theses
        logger.warning("summarizer response was not parsed, attempt=%s", attempt + 1)
        messages = [
            messages[0],
            messages[1],
            {"role": "assistant", "content": last_raw},
            {
                "role": "user",
                "content": (
                    'Ответ не удалось разобрать. Верни только JSON '
                    '{"theses": ["тезис 1", "тезис 2"]} без пояснений.'
                ),
            },
        ]

    logger.warning("summarizer gave no theses, sample=%r", last_raw[:500])
    raise SummarizerError("empty theses")
