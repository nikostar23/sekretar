# AudioAssistant

Telegram-бот для учебного проекта «Бот-обработчик аудио: транскрибация + генерация тезисов».

Пользователь отправляет голосовое сообщение или файл OGG, MP3, WAV. Бот возвращает полную транскрибацию и краткие тезисы (обычно 3–7). Неразборчивую речь бот не восстанавливает, эмоции не оценивает и ничего не додумывает.

## Что понадобится

- Токен бота от [@BotFather](https://t.me/BotFather).
- Ключ [OpenAI API](https://platform.openai.com/api-keys).
- Для сервера: Docker и плагин Docker Compose.
- Для запуска без Docker: Python 3.11 или новее.

## Настройка

Скопируйте образец настроек:

```bash
copy .env.example .env
```

На Linux и macOS: `cp .env.example .env`.

Откройте `.env` и впишите два обязательных значения без кавычек:

```
TELEGRAM_BOT_TOKEN=123456:ABC...
OPENAI_API_KEY=sk-...
```

Как получить токен в BotFather:

1. Откройте @BotFather и отправьте `/newbot`.
2. Задайте имя и username бота.
3. Скопируйте выданный токен в `.env`.

В личном чате бот видит голосовые сразу. Если добавите его в группу, в BotFather выполните `/setprivacy` и выберите Disable, иначе голосовые из группы до бота не доходят.

Если сервер не открывает `api.openai.com`, укажите совместимый адрес в `OPENAI_BASE_URL`. Модель тезисов меняется переменной `GPT_MODEL` (`gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo`). Язык записи — `WHISPER_LANGUAGE` (`ru` или `auto`).

## Запуск на сервере

Скопируйте папку проекта на сервер, заполните `.env` и в этой папке выполните:

```bash
docker compose up -d --build
docker compose logs -f audio-bot
```

Остановка и обновление:

```bash
docker compose down
docker compose up -d --build
```

Ключи в образ не попадают: контейнер читает их из `.env` при старте. В логах пишутся идентификатор пользователя, размер файла и длина текста, сам ключ не печатается.

## Локальный запуск

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

Проверка логики без ключей и без Telegram:

```bash
python -m unittest discover -s tests
```

## Как пользоваться ботом

Отправьте боту голосовое сообщение или файл `.ogg`, `.mp3`, `.wav` до 20 МБ.

Команды:

- `/start` — приветствие
- `/help` — как отправить запись
- `/faq` — форматы и качество записи
- `/examples` — примеры «аудио → текст → тезисы»

Ответ выглядит так: блок «Транскрибация», затем «Краткие тезисы». Если текст длинный, тезисы приходят сообщением, а полная расшифровка — файлом `transcription.txt`.

## Документ для Google Docs

Текст ассистента с оглавлением и разделами лежит в [docs/assistant.md](docs/assistant.md). Его нужно перенести в Google Docs: заголовки станут разделами, оглавление добавляется через «Вставка → Оглавление».

База знаний в репозитории:

- `knowledge/system_prompt.md` — роль, сценарий, ограничения
- `knowledge/faq.md` — форматы и качество записи
- `knowledge/examples.md` — примеры
- `knowledge/response_template.md` — шаблон ответа

## Состав проекта

```
bot.py              диалог в Telegram
config.py           настройки из .env
transcriber.py      Whisper
summarizer.py       тезисы через GPT
prompts.py          промпт и тексты бота
formatting.py       сборка ответа
knowledge/          база знаний
docs/assistant.md   документ для Google Docs
Dockerfile
docker-compose.yml
```
