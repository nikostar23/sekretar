"""Telegram-бот AudioAssistant: аудио → транскрибация → краткие тезисы."""

from __future__ import annotations

import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from openai import BadRequestError as OpenAIBadRequest
from openai import RateLimitError
from telegram import BotCommand, Update
from telegram.error import BadRequest as TelegramBadRequest
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import MIN_FILE_BYTES, ROOT, Settings, load_settings
from formatting import (
    TELEGRAM_MESSAGE_LIMIT,
    format_success,
    format_theses_only,
    format_transcript_with_note,
    split_message,
)
from prompts import (
    AUTH_ERROR_TEXT,
    BAD_FORMAT_TEXT,
    BUSY_TEXT,
    CONNECTION_ERROR,
    GENERIC_ERROR,
    HELP_TEXT,
    KNOWLEDGE_MISSING,
    LOW_QUALITY_TEXT,
    RATE_LIMIT_TEXT,
    START_TEXT,
    STATUS_SUMMARY,
    STATUS_TRANSCRIBE,
    SUMMARY_FAILED_FILE_NOTE,
    SUMMARY_FAILED_NOTE,
    TEXT_HINT,
    TOO_BIG_TEXT,
    TOO_SMALL_TEXT,
    UNKNOWN_COMMAND,
    UNSUPPORTED_MESSAGE,
)
from summarizer import SummarizerError, summarize
from transcriber import LowQualityTranscription, transcribe

logger = logging.getLogger(__name__)

_EXTENSIONS = {".ogg": ".ogg", ".oga": ".ogg", ".mp3": ".mp3", ".wav": ".wav"}
_MIME_TO_EXT = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/vnd.wave": ".wav",
}


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def resolve_extension(file_name: str | None, mime_type: str | None) -> str | None:
    if file_name:
        suffix = Path(file_name).suffix.lower()
        if suffix in _EXTENSIONS:
            return _EXTENSIONS[suffix]
        if suffix:
            return None
    if mime_type:
        return _MIME_TO_EXT.get(mime_type.split(";", 1)[0].strip().lower())
    return None


def actor_id(message: Any) -> int:
    if message.from_user is not None:
        return message.from_user.id
    return message.chat_id


async def post_init(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    client_kwargs: dict[str, Any] = {
        "api_key": settings.openai_api_key,
        "timeout": 180.0,
    }
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    application.bot_data["openai"] = AsyncOpenAI(**client_kwargs)
    application.bot_data.setdefault("busy", set())
    try:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Начать работу"),
                BotCommand("help", "Как пользоваться ботом"),
                BotCommand("faq", "Форматы и качество записи"),
                BotCommand("examples", "Примеры результата"),
            ]
        )
    except TelegramError:
        logger.exception("could not register bot commands")


async def post_shutdown(application: Application) -> None:
    client = application.bot_data.get("openai")
    if client is not None:
        await client.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(START_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(HELP_TEXT)


async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_knowledge(update, "faq.md")


async def examples_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_knowledge(update, "examples.md")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(UNKNOWN_COMMAND)


async def send_knowledge(update: Update, filename: str) -> None:
    message = update.effective_message
    if message is None:
        return
    path = ROOT / "knowledge" / filename
    if not path.is_file():
        logger.error("missing knowledge file: %s", path)
        await message.reply_text(KNOWLEDGE_MISSING)
        return
    for part in split_message(path.read_text(encoding="utf-8")):
        await message.reply_text(part)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.voice is None:
        return
    voice = message.voice
    await process_audio(message, context, voice.file_id, voice.file_size, ".ogg")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.audio is None:
        return
    audio = message.audio
    extension = resolve_extension(audio.file_name, audio.mime_type)
    await process_audio(message, context, audio.file_id, audio.file_size, extension)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.document is None:
        return
    document = message.document
    extension = resolve_extension(document.file_name, document.mime_type)
    await process_audio(message, context, document.file_id, document.file_size, extension)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(TEXT_HINT)


async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(UNSUPPORTED_MESSAGE)


async def replace_status(message: Any, status: Any, text: str) -> None:
    parts = split_message(text)
    if not parts:
        return
    start_index = 0
    if status is not None:
        try:
            await status.edit_text(parts[0])
            start_index = 1
        except TelegramError:
            logger.warning("could not edit status message")
            try:
                await status.delete()
            except TelegramError:
                pass
    for part in parts[start_index:]:
        await message.reply_text(part)


async def send_transcript_file(message: Any, transcript: str) -> None:
    buffer = BytesIO(transcript.encode("utf-8"))
    buffer.name = "transcription.txt"
    await message.reply_document(
        document=buffer,
        filename="transcription.txt",
        caption="Полная транскрибация",
    )


async def deliver_result(message: Any, status: Any, transcript: str, theses: list[str]) -> None:
    full = format_success(transcript, theses)
    if len(full) <= TELEGRAM_MESSAGE_LIMIT:
        await replace_status(message, status, full)
        return
    await replace_status(message, status, format_theses_only(theses))
    await send_transcript_file(message, transcript)


async def deliver_transcript_only(message: Any, status: Any, transcript: str) -> None:
    full = format_transcript_with_note(transcript, SUMMARY_FAILED_NOTE)
    if len(full) <= TELEGRAM_MESSAGE_LIMIT:
        await replace_status(message, status, full)
        return
    await replace_status(message, status, SUMMARY_FAILED_FILE_NOTE)
    await send_transcript_file(message, transcript)


async def process_audio(
    message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    file_size: int | None,
    extension: str | None,
) -> None:
    settings: Settings = context.application.bot_data["settings"]
    user_id = actor_id(message)
    busy: set[int] = context.application.bot_data["busy"]

    if extension is None:
        await message.reply_text(BAD_FORMAT_TEXT)
        return
    if file_size is not None and file_size > settings.max_file_bytes:
        await message.reply_text(TOO_BIG_TEXT)
        return
    if file_size is not None and file_size < MIN_FILE_BYTES:
        await message.reply_text(TOO_SMALL_TEXT)
        return
    if user_id in busy:
        await message.reply_text(BUSY_TEXT)
        return

    busy.add(user_id)
    status = None
    path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(suffix=extension)
        os.close(descriptor)
        path = Path(raw_path)
        logger.info("start user=%s bytes=%s ext=%s", user_id, file_size, extension)
        status = await message.reply_text(STATUS_TRANSCRIBE)
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=str(path))

        client = context.application.bot_data["openai"]
        try:
            transcript = await transcribe(
                client,
                path,
                model=settings.whisper_model,
                language=settings.whisper_language,
            )
        except LowQualityTranscription as exc:
            logger.warning("low quality user=%s sample=%r", user_id, exc.text[:300])
            await replace_status(message, status, LOW_QUALITY_TEXT)
            return

        try:
            await status.edit_text(STATUS_SUMMARY)
        except TelegramError:
            logger.warning("could not update status user=%s", user_id)
        try:
            theses = await summarize(client, transcript, model=settings.gpt_model)
        except SummarizerError:
            logger.exception("summary failed user=%s", user_id)
            await deliver_transcript_only(message, status, transcript)
            return

        logger.info(
            "done user=%s transcript_chars=%s theses=%s",
            user_id,
            len(transcript),
            len(theses),
        )
        await deliver_result(message, status, transcript, theses)
    except RateLimitError:
        logger.warning("rate limit user=%s", user_id)
        await replace_status(message, status, RATE_LIMIT_TEXT)
    except OpenAIBadRequest:
        logger.exception("openai rejected audio user=%s", user_id)
        await replace_status(message, status, BAD_FORMAT_TEXT)
    except APIConnectionError:
        logger.exception("openai connection error user=%s", user_id)
        await replace_status(message, status, CONNECTION_ERROR)
    except APIStatusError as exc:
        logger.error("openai status user=%s code=%s", user_id, exc.status_code)
        text = AUTH_ERROR_TEXT if exc.status_code == 401 else GENERIC_ERROR
        await replace_status(message, status, text)
    except TelegramBadRequest as exc:
        logger.warning("telegram bad request user=%s: %s", user_id, exc)
        text = TOO_BIG_TEXT if "too big" in str(exc).lower() else GENERIC_ERROR
        await replace_status(message, status, text)
    except TelegramError:
        logger.exception("telegram error user=%s", user_id)
    except Exception:
        logger.exception("processing failed user=%s", user_id)
        try:
            await replace_status(message, status, GENERIC_ERROR)
        except TelegramError:
            logger.exception("failed to report error user=%s", user_id)
    finally:
        busy.discard(user_id)
        if path is not None:
            path.unlink(missing_ok=True)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    application = (
        Application.builder()
        .token(settings.telegram_token)
        .connect_timeout(30)
        .read_timeout(120)
        .write_timeout(120)
        .pool_timeout(30)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["busy"] = set()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("examples", examples_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(
        MessageHandler(
            filters.ALL
            & ~filters.COMMAND
            & ~filters.VOICE
            & ~filters.AUDIO
            & ~filters.Document.ALL
            & ~filters.TEXT,
            handle_other,
        )
    )

    logger.info("AudioAssistant is starting")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
