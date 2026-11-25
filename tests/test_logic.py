import json
import unittest
from pathlib import Path

from formatting import format_success, split_message
from summarizer import parse_theses
from transcriber import is_usable_transcript


class ParseThesesTests(unittest.TestCase):
    def test_json_object(self) -> None:
        raw = '{"theses": ["Первый тезис.", "Второй тезис.", "Третий тезис."]}'
        self.assertEqual(len(parse_theses(raw)), 3)

    def test_markdown_fence(self) -> None:
        raw = '```json\n{"theses": ["Альфа.", "Бета.", "Гамма."]}\n```'
        self.assertEqual(parse_theses(raw), ["Альфа.", "Бета.", "Гамма."])

    def test_json_inside_prose(self) -> None:
        raw = 'Вот результат:\n{"theses": ["Альфа.", "Бета.", "Гамма."]}\nГотово'
        self.assertEqual(parse_theses(raw), ["Альфа.", "Бета.", "Гамма."])

    def test_numbered_fallback(self) -> None:
        raw = "1. Встреча завтра.\n2. Подготовить договор.\n3. Отправить до пятницы."
        self.assertEqual(
            parse_theses(raw),
            ["Встреча завтра.", "Подготовить договор.", "Отправить до пятницы."],
        )

    def test_caps_at_seven(self) -> None:
        raw = json.dumps({"theses": [f"Тезис {index}." for index in range(1, 11)]}, ensure_ascii=False)
        self.assertEqual(len(parse_theses(raw)), 7)

    def test_drops_duplicates_and_numbering_inside_items(self) -> None:
        raw = json.dumps(
            {"theses": ["1. Созвон завтра.", "Созвон завтра", "Отправить договор."]},
            ensure_ascii=False,
        )
        self.assertEqual(parse_theses(raw), ["Созвон завтра.", "Отправить договор."])

    def test_string_payload(self) -> None:
        raw = '{"theses": "Один тезис без списка."}'
        self.assertEqual(parse_theses(raw), ["Один тезис без списка."])


class TranscriptQualityTests(unittest.TestCase):
    def test_normal_sentence(self) -> None:
        self.assertTrue(is_usable_transcript("Завтра в десять встреча с клиентом."))

    def test_short_agreement(self) -> None:
        self.assertTrue(is_usable_transcript("Да, хорошо."))

    def test_empty(self) -> None:
        self.assertFalse(is_usable_transcript("   "))
        self.assertFalse(is_usable_transcript("..."))

    def test_one_word(self) -> None:
        self.assertFalse(is_usable_transcript("Привет"))

    def test_hallucination(self) -> None:
        self.assertFalse(is_usable_transcript("Субтитры создавал DimaTorzok"))
        self.assertFalse(is_usable_transcript("Спасибо за просмотр!"))

    def test_marker_inside_real_speech(self) -> None:
        text = (
            "На встрече сказали спасибо за просмотр материалов "
            "и завтра отправить договор поставщику до обеда."
        )
        self.assertTrue(is_usable_transcript(text))


class FormattingTests(unittest.TestCase):
    def test_success_contains_both_blocks(self) -> None:
        text = format_success("Полный текст записи.", ["Первый пункт.", "Второй пункт."])
        self.assertIn("Полный текст записи.", text)
        self.assertIn("1. Первый пункт.", text)
        self.assertIn("2. Второй пункт.", text)

    def test_split_keeps_short_text(self) -> None:
        self.assertEqual(split_message("коротко"), ["коротко"])

    def test_split_long_paragraph(self) -> None:
        parts = split_message("а" * 25, limit=10)
        self.assertEqual(parts, ["а" * 10, "а" * 10, "а" * 5])

    def test_split_prefers_lines(self) -> None:
        parts = split_message("один\nдва\nтри", limit=7)
        self.assertEqual("".join(parts).replace("\n", ""), "одиндватри")
        self.assertTrue(all(len(part) <= 7 for part in parts))

    def test_knowledge_messages_fit_telegram(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        for name in ("faq.md", "examples.md", "system_prompt.md", "response_template.md"):
            parts = split_message((root / name).read_text(encoding="utf-8"))
            self.assertTrue(parts, name)
            self.assertTrue(all(len(part) <= 4000 for part in parts), name)


if __name__ == "__main__":
    unittest.main()
