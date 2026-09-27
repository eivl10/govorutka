# ─── Часть 3: Логика перевода ─────────────────────────────────────────────────
#
# Пользователь отправляет текст → бот показывает кнопки с языками-назначениями.
# Если текст на языке, отличном от исходного — сразу переводит на исходный.
# Нажал кнопку → получил перевод через DeepL.
# Под переводом: кнопка "🔄 Обратно" (обратный перевод) и "🌐 Гугол" (Google Translate).
#
# Голосовые: скачиваем файл → отправляем в Groq Whisper API → получаем текст → переводим.
# Если выбран только один язык-назначение — переводим сразу, без кнопок выбора.

import asyncio
import html
import io
import hashlib
import deepl
import httpx
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext

# Импорт из Части 1
from bot_part1 import (
    LANGUAGES, get_label,
    get_user_settings, is_lang_configured,
    get_deepl_target,
    ADMIN_ID,
    is_allowed, is_pending, add_pending,
    approve_user, deny_user, revoke_user,
    get_request_mode,
    is_auto_approve_enabled, approve_user_auto,
)

router = Router()

# ─── Маппинг редких DeepL-кодов → поддерживаемым в LANGUAGES ───────────────
# DeepL для коротких фраз может вернуть нестандартные коды (HR, ST, LMO и т.д.)
DEEPL_ALIAS_MAP = {
    "PAM": "EN",   # Пампанган (возвращается для "bye") → EN
    "LMO": "IT",   # Lombard → Итальянский
    "NO": "NB",    # Норвежский → Норвежский (bokmål)
    "EN-US": "EN",
    "EN-GB": "EN",
    "PT-BR": "PT",
    "PT-PT": "PT",
    "ZH": "ZH",
    "ZH-HANS": "ZH",
    "ZH-HANT": "ZH",
    "PAG": "EN",   # Pangasinan → EN (для "hey how ya doin")
    "ILO": "EN",   # Ilokano → EN
    "CEB": "EN",   # Cebuano → EN  
    "HMN": "EN",   # Hmong → EN
}

# ─── Клиенты API ─────────────────────────────────────────────────────────────
# Задаются в main.py перед запуском

deepl_translator: deepl.Translator | None = None   # deepl.Translator(api_key)
GROQ_API_KEY: str | None = None                    # Groq API key

# Задаётся из main.py для подсчёта переводов и символов
increment_translation = None
increment_chars = None


# ─── TTS (Google Translate) ──────────────────────────────────────────────────

# Маппинг DeepL-кодов в Google TTS коды
GOOGLE_TTS_LANGS = {
    "AF": "af",
    "AR": "ar",
    "BG": "bg",
    "BN": "bn",
    "BS": "bs",
    "CA": "ca",
    "CS": "cs",
    "DA": "da",
    "DE": "de",
    "EL": "el",
    "EN": "en",
    "ES": "es",
    "ET": "et",
    "FI": "fi",
    "FR": "fr",
    "GU": "gu",
    "HE": "iw",
    "HI": "hi",
    "HR": "hr",
    "HU": "hu",
    "ID": "id",
    "IS": "is",
    "IT": "it",
    "JA": "ja",
    "KO": "ko",
    "LA": "la",
    "LV": "lv",
    "ML": "ml",
    "MR": "mr",
    "MS": "ms",
    "MY": "my",
    "NB": "no",
    "NE": "ne",
    "NL": "nl",
    "PL": "pl",
    "PT": "pt",
    "RO": "ro",
    "RU": "ru",
    "SK": "sk",
    "SQ": "sq",
    "SR": "sr",
    "SU": "su",
    "SV": "sv",
    "SW": "sw",
    "TA": "ta",
    "TE": "te",
    "TH": "th",
    "TL": "tl",
    "TR": "tr",
    "UK": "uk",
    "UR": "ur",
    "VI": "vi",
    "ZH": "zh-CN",
}



async def send_translation(bot_obj, chat_id, text, reply_markup, auto_speech=False, translated_text="", target_lang="en"):
    # text — готовый HTML: пользовательские части должны быть экранированы вызывающим
    await bot_obj.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")
    # Озвучивает если надо
    if auto_speech and translated_text:
        try:
            audio_data = await synthesize_speech(translated_text, target_lang)
            audio_file = BufferedInputFile(audio_data, filename="speech.mp3")
            await bot_obj.send_voice(chat_id=chat_id, voice=audio_file)
        except Exception:
            pass

async def synthesize_speech(text: str, lang_code: str) -> bytes:
    """
    Синтез речи через gTTS (Google Text-to-Speech).
    Возвращает MP3-данные в bytes.
    """
    from gtts import gTTS

    tts_lang = GOOGLE_TTS_LANGS.get(lang_code, "en")

    def _synth():
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=tts_lang)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()

    # Запускаем блокирующий gTTS в отдельном потоке
    return await asyncio.to_thread(_synth)


# ─── Проверка доступа ────────────────────────────────────────────────────────

async def ensure_access(message: Message) -> bool:
    """True, если пользователь может пользоваться ботом.
    Иначе отвечает ему сам (заявка на рассмотрении / кнопка запроса) и возвращает False."""
    uid = message.from_user.id
    if is_allowed(uid):
        return True
    if is_auto_approve_enabled():
        approve_user_auto(uid)
        return True
    if is_pending(uid):
        await message.answer("✅ Заявку кря. Погоди немного.")
        return False
    keyboard = [[InlineKeyboardButton(text="📨 Кря", callback_data=f"request_access|{uid}")]]
    await message.answer(
        "🔒 Тебя прикрякнули.\n\nОтправь кря администратору:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    return False


async def check_callback_access(callback: CallbackQuery) -> bool:
    """Кнопки под старыми сообщениями не должны работать после отзыва доступа."""
    if is_allowed(callback.from_user.id):
        return True
    await callback.answer("🔒 Нет доступа.", show_alert=True)
    return False


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def kb_admin_approve(user_id: int) -> InlineKeyboardMarkup:
    """Кнопки одобрения/отклонения заявки для админа."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Кря", callback_data=f"admin_approve|{user_id}"),
        InlineKeyboardButton(text="❌ Кря", callback_data=f"admin_deny|{user_id}"),
    ]])


def kb_translate_targets(targets: list, text_hash: str) -> InlineKeyboardMarkup:
    """Кнопки с языками-назначениями для перевода конкретного текста."""
    buttons = []
    row = []
    for lang in targets:
        label = get_label(lang)
        row.append(InlineKeyboardButton(text=label, callback_data=f"translate|{lang}|{text_hash}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_after_translation(source_lang: str, target_lang: str, text_hash: str, translated_text_hash: str) -> InlineKeyboardMarkup:
    """Кнопки после перевода: обратный перевод, Google Translate, TTS, AI-разбор."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Google", callback_data=f"google|{source_lang}|{target_lang}|{text_hash}"),
            InlineKeyboardButton(text="🤖 Groq", callback_data=f"ai_explain|{text_hash}|{translated_text_hash}|{source_lang}|{target_lang}"),
        ],
        [
            InlineKeyboardButton(text="▶️", callback_data=f"speak|{translated_text_hash}|{target_lang}"),
            InlineKeyboardButton(text="🔄 Обратно", callback_data=f"back|{source_lang}|{target_lang}|{text_hash}"),
        ],
    ])


# Кеш текстов: { hash: text }. Ограничен по размеру — самые старые вытесняются.
_text_cache: dict[str, str] = {}
_CACHE_MAX = 5000

def cache_text(text: str) -> str:
    """Кешируем текст и возвращаем его хеш."""
    h = hashlib.md5(text.encode()).hexdigest()[:12]
    _text_cache.pop(h, None)  # повторный текст переезжает в конец очереди
    _text_cache[h] = text
    while len(_text_cache) > _CACHE_MAX:
        _text_cache.pop(next(iter(_text_cache)))
    return h

def get_cached_text(h: str) -> str | None:
    return _text_cache.get(h)


def count_usage(uid: int, text: str):
    """Учитывает перевод в статистике пользователя."""
    if increment_translation:
        increment_translation(uid)
    if increment_chars:
        increment_chars(uid, len(text))


async def translate_deepl(text: str, source: str, target: str) -> str:
    """Переводим через DeepL (в отдельном потоке — клиент синхронный)."""
    target_code = get_deepl_target(target)
    result = await asyncio.to_thread(
        deepl_translator.translate_text, text, source_lang=source, target_lang=target_code
    )
    return result.text


async def translate_google(text: str, source: str, target: str) -> str:
    """Переводим через Google Translate (httpx)."""
    google_source = LANGUAGES[source][0]
    google_target = LANGUAGES[target][0]
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": google_source,
        "tl": google_target,
        "dt": "t",
        "q": text,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    translated = "".join(part[0] for part in data[0] if part[0])
    return translated


async def detect_language_google(text: str) -> str | None:
    """Определяем язык текста через неофициальный Google Translate API. Возвращает google-код."""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "en",
            "dt": ["t", "ld"],
            "q": text,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        # data[2] — определённый язык, data[0][0][3] — тоже вариант
        lang = None
        try:
            lang = data[2]
        except (IndexError, TypeError):
            pass
        if not lang:
            try:
                lang = data[0][0][3]
            except (IndexError, TypeError):
                pass
        return lang
    except Exception:
        return None


def google_to_deepl_code(google_code: str) -> str | None:
    """Конвертируем google-код в DeepL-код."""
    if google_code is None:
        return None
    google_code = google_code.lower().split("-")[0]
    for deepl_code, (g_code, _, _) in LANGUAGES.items():
        if g_code.lower().split("-")[0] == google_code:
            return deepl_code
    return None


def normalize_deepl_code(code: str | None) -> str | None:
    """Приводит код, который вернул DeepL при детекте, к ключу LANGUAGES (или None)."""
    if not code:
        return None
    code = code.upper()
    if code in LANGUAGES:
        return code
    if code in DEEPL_ALIAS_MAP and DEEPL_ALIAS_MAP[code] in LANGUAGES:
        return DEEPL_ALIAS_MAP[code]
    prefix = code.split("-")[0]
    if prefix in LANGUAGES:
        return prefix
    if prefix in DEEPL_ALIAS_MAP and DEEPL_ALIAS_MAP[prefix] in LANGUAGES:
        return DEEPL_ALIAS_MAP[prefix]
    return None


# ISO 639-1 код langdetect → DeepL код
_LANGDETECT_TO_DEEPL = {
    "en": "EN", "ru": "RU", "de": "DE", "fr": "FR", "es": "ES",
    "it": "IT", "nl": "NL", "pl": "PL", "pt": "PT", "ja": "JA",
    "zh-cn": "ZH", "zh-tw": "ZH", "ko": "KO", "ar": "AR", "tr": "TR",
    "sv": "SV", "da": "DA", "fi": "FI", "nb": "DA", "cs": "CS",
    "ro": "RO", "hu": "HU", "sk": "SK", "bg": "BG", "uk": "UK",
    "hr": "BS", "bs": "BS", "sl": "SL", "et": "ET", "lv": "LV",
    "lt": "LT", "id": "ID", "ms": "MS", "vi": "VI",
}

# langdetect доверяем без DeepL только на достаточно длинном тексте и с высокой уверенностью
LANGDETECT_MIN_LEN = 20
LANGDETECT_MIN_PROB = 0.95
# Для детекта через DeepL хватает начала текста — остальное зря съедает лимит символов
DETECT_SAMPLE_LEN = 200

def detect_language_langdetect(text: str, min_prob: float = 0.0) -> str | None:
    """Офлайн детект через langdetect. Возвращает DeepL-код или None."""
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0  # детерминированный результат
        best = detect_langs(text)[0]
        if best.prob < min_prob:
            return None
        return _LANGDETECT_TO_DEEPL.get(best.lang)
    except Exception:
        return None


async def detect_lang(text: str) -> str | None:
    """Определяет язык текста, возвращает DeepL-код или None.
    Порядок: уверенный langdetect (бесплатно) → DeepL по началу текста →
    langdetect без порога → Google."""
    if len(text) >= LANGDETECT_MIN_LEN:
        code = detect_language_langdetect(text, min_prob=LANGDETECT_MIN_PROB)
        if code:
            return code

    if deepl_translator is not None:
        try:
            result = await asyncio.to_thread(
                deepl_translator.translate_text, text[:DETECT_SAMPLE_LEN], target_lang="EN-US"
            )
            code = normalize_deepl_code(result.detected_source_lang)
            if code:
                return code
        except Exception:
            pass

    code = detect_language_langdetect(text)
    if code:
        return code

    return google_to_deepl_code(await detect_language_google(text))


async def transcribe_voice(file_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Транскрибируем голосовое через Groq Whisper API."""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    files = {"file": (filename, file_bytes, "audio/ogg")}
    data = {"model": "whisper-large-v3"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, files=files, data=data)
        resp.raise_for_status()
    return resp.json().get("text", "")


# ─── Хэндлеры ────────────────────────────────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, state: FSMContext):
    """Пользователь прислал текст.
    - Если язык текста ≠ исходный → переводим на исходный без вопросов.
    - Если язык текста == исходный и один язык-назначение → сразу переводим.
    - Если язык текста == исходный и несколько языков → показываем кнопки.
    """
    uid = message.from_user.id

    if not await ensure_access(message):
        return

    # ── Обработка режима рассылки от админа ──────────────────────────────────
    if uid == ADMIN_ID:
        fsm_data = await state.get_data()
        target_id = fsm_data.get("admin_msg_target")
        if target_id:
            await state.update_data(admin_msg_target=None)
            try:
                await message.bot.send_message(
                    chat_id=target_id,
                    text=f"📩 Тебе сообщение от администкрятора:\n\n{message.text}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(
                            text="💬 Крякнуть в ответ",
                            callback_data=f"user_reply|{uid}"
                        )
                    ]])
                )
                await message.answer(f"✅ Крякнуто {target_id}.")
            except Exception as e:
                await message.answer(f"❌ Не смох крякнуть. Ошибка: {e}")
            return

    # ── Обработка режима ответа пользователя администратору ──────────────────
    fsm_data = await state.get_data()
    reply_to_admin = fsm_data.get("user_reply_to_admin")
    if reply_to_admin:
        await state.update_data(user_reply_to_admin=None)
        user = message.from_user
        name = user.full_name
        username = f"@{user.username}" if user.username else f"ID {uid}"
        try:
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"💬 Ответ от {name} ({username}):\n\n{message.text}"
            )
            await message.answer("✅ Кря отправлено.")
        except Exception as e:
            await message.answer(f"❌ Не смог кря. Ошибка: {e}")
        return

    # ── Проверка настройки языков ─────────────────────────────────────────────
    settings = get_user_settings(uid)
    if not is_lang_configured(uid):
        await message.answer("⚙️ Сначала настрой языки командой /lang")
        return

    source = settings["source"]
    targets = settings["targets"]
    text = message.text
    auto_speech = settings.get("auto_speech", False)

    detected = await detect_lang(text)

    # Если детект не сработал или совпал с source — переводим как обычно
    if detected and detected != source:
        # Текст на другом языке → переводим на исходный
        try:
            translated = await translate_deepl(text, detected, source)
            count_usage(uid, text)
            kb = kb_after_translation(detected, source, cache_text(text), cache_text(translated))
            await send_translation(message.bot, uid, html.escape(translated), kb, auto_speech, translated, source)
        except Exception as e:
            await message.answer(f"❌ Ошибка перевода: {e}")
        return

    # Текст на исходном языке
    text_hash = cache_text(text)

    if len(targets) == 1:
        # Один язык — переводим сразу
        target = targets[0]
        try:
            translated = await translate_deepl(text, source, target)
            count_usage(uid, text)
            kb = kb_after_translation(source, target, text_hash, cache_text(translated))
            await send_translation(message.bot, uid, html.escape(translated), kb, auto_speech, translated, target)
        except Exception as e:
            await message.answer(f"❌ Ошибка перевода: {e}")
    else:
        # Несколько языков — показываем кнопки выбора
        kb = kb_translate_targets(targets, text_hash)
        await message.answer("На какой язык кря?", reply_markup=kb)


@router.message(F.voice)
async def on_voice(message: Message, state: FSMContext):
    """Голосовое сообщение → транскрибируем → переводим."""
    uid = message.from_user.id

    if not await ensure_access(message):
        return

    if not is_lang_configured(uid):
        await message.answer("⚙️ Сначала настрой языки командой /lang")
        return

    if not GROQ_API_KEY:
        await message.answer("❌ Голосовые не поддерживаются: нет API-ключа Groq.")
        return

    settings = get_user_settings(uid)
    source = settings["source"]
    targets = settings["targets"]
    auto_speech = settings.get("auto_speech", False)

    status_msg = await message.answer("Кря 🦆")

    try:
        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_bytes_io = await message.bot.download_file(file.file_path)
        file_bytes = file_bytes_io.read()
    except Exception as e:
        await status_msg.edit_text(f"❌ Не смог скачать аудио: {e}")
        return

    try:
        text = await transcribe_voice(file_bytes)
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка транскрибации: {e}")
        return

    if not text.strip():
        await status_msg.edit_text("❌ Не удалось распознать речь.")
        return

    await status_msg.delete()

    # Дальше — как обычный текст
    text_hash = cache_text(text)
    quoted = f"<i>{html.escape(text)}</i>"

    detected = await detect_lang(text)

    if detected and detected != source:
        try:
            translated = await translate_deepl(text, detected, source)
            count_usage(uid, text)
            kb = kb_after_translation(detected, source, text_hash, cache_text(translated))
            await send_translation(message.bot, uid, f"{quoted}\n{html.escape(translated)}", kb, auto_speech, translated, source)
        except Exception as e:
            await message.answer(f"❌ Ошибка перевода: {e}")
        return

    if len(targets) == 1:
        target = targets[0]
        try:
            translated = await translate_deepl(text, source, target)
            count_usage(uid, text)
            kb = kb_after_translation(source, target, text_hash, cache_text(translated))
            await send_translation(message.bot, uid, f"{quoted}\n{html.escape(translated)}", kb, auto_speech, translated, target)
        except Exception as e:
            await message.answer(f"❌ Ошибка перевода: {e}")
    else:
        kb = kb_translate_targets(targets, text_hash)
        await message.answer(f"На какой язык кря?\n\n{quoted}", parse_mode="HTML", reply_markup=kb)


# ─── Callback: выбор языка перевода ──────────────────────────────────────────

@router.callback_query(F.data.startswith("translate|"))
async def cb_translate(callback: CallbackQuery):
    """Пользователь выбрал язык перевода."""
    if not await check_callback_access(callback):
        return
    _, target, text_hash = callback.data.split("|")
    uid = callback.from_user.id

    text = get_cached_text(text_hash)
    if not text:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    settings = get_user_settings(uid)
    source = settings["source"]

    await callback.answer()
    try:
        translated = await translate_deepl(text, source, target)
        count_usage(uid, text)
        kb = kb_after_translation(source, target, text_hash, cache_text(translated))
        await send_translation(callback.bot, uid, html.escape(translated), kb, settings.get("auto_speech", False), translated, target)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка перевода: {e}")


# ─── Callback: обратный перевод ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("back|"))
async def cb_back(callback: CallbackQuery):
    """Обратный перевод."""
    if not await check_callback_access(callback):
        return
    _, source_lang, target_lang, text_hash = callback.data.split("|")

    text = get_cached_text(text_hash)
    if not text:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    await callback.answer()
    try:
        translated = await translate_deepl(text, target_lang, source_lang)
        count_usage(callback.from_user.id, text)
        kb = kb_after_translation(target_lang, source_lang, text_hash, cache_text(translated))
        await callback.message.answer(translated, reply_markup=kb)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка перевода: {e}")


# ─── Callback: Google Translate ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("google|"))
async def cb_google(callback: CallbackQuery):
    """Перевод через Google Translate."""
    if not await check_callback_access(callback):
        return
    _, source_lang, target_lang, text_hash = callback.data.split("|")

    text = get_cached_text(text_hash)
    if not text:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    await callback.answer()
    try:
        translated = await translate_google(text, source_lang, target_lang)
        await callback.message.answer(f"🌐 {translated}")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка Google перевода: {e}")


# ─── Callback: TTS (озвучка текста) ───────────────────────────────────────────

@router.callback_query(F.data.startswith("speak|"))
async def cb_speak(callback: CallbackQuery, bot: Bot):
    """Озвучка текста через Google TTS."""
    if not await check_callback_access(callback):
        return
    _, text_hash, lang_code = callback.data.split("|")

    text = get_cached_text(text_hash)
    if not text:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    await callback.answer("🔊 Говорю...")

    try:
        audio_data = await synthesize_speech(text, lang_code)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка TTS: {e}")
        return

    # Отправляем как голосовое сообщение (aiogram 3.x требует BufferedInputFile)
    audio_file = BufferedInputFile(audio_data, filename="speech.mp3")
    await bot.send_voice(chat_id=callback.from_user.id, voice=audio_file)


# ─── Callback: ответ пользователя администратору ──────────────────────────────

@router.callback_query(F.data.startswith("user_reply|"))
async def cb_user_reply(callback: CallbackQuery, state: FSMContext):
    """Пользователь хочет ответить администратору."""
    await state.update_data(user_reply_to_admin=True)
    await callback.answer()
    await callback.message.answer("✏️ Напиши своё сообщение:")


# ─── Callback-хэндлеры системы доступа ───────────────────────────────────────

@router.callback_query(F.data.startswith("request_access|"))
async def on_request_access(callback: CallbackQuery):
    """Пользователь нажал кнопку 'Кря' для запроса доступа."""
    # ID берём у нажавшего, а не из callback_data — кнопку мог нажать кто-то другой
    user = callback.from_user
    requester_id = user.id

    if is_pending(requester_id):
        await callback.answer()
        await callback.message.edit_text("✅ Заявку кря. Погоди немного.")
        return

    if is_allowed(requester_id):
        await callback.answer()
        await callback.message.edit_text("✅ У тебя уже есть доступ. Кря!")
        return

    name = user.full_name
    username = user.username or ""

    # ── Шаг 4: проверяем режим доступа ───────────────────────────────────────
    if not get_request_mode():
        # Режим выключен → доступ выдаётся автоматически
        approve_user(requester_id)
        await callback.answer()
        await callback.message.edit_text("✅ Доступ открыт. Кря!")
        return

    # Режим включён → добавляем в pending и уведомляем админа
    add_pending(requester_id, name=name, username=username)

    username_display = f"@{username}" if username else "нет username"

    try:
        await callback.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📨 Новая заявка на доступ:\n\n"
                 f"Имя: {name}\n"
                 f"Username: {username_display}\n"
                 f"ID: {requester_id}",
            reply_markup=kb_admin_approve(requester_id)
        )
    except Exception:
        pass

    await callback.answer()
    await callback.message.edit_text("✅ Заявку кря. Погоди немного.")


@router.callback_query(F.data.startswith("admin_approve|"))
async def on_admin_approve(callback: CallbackQuery):
    """Админ одобрил пользователя."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет прав.", show_alert=True)
        return
    target_id = int(callback.data.split("|")[1])
    approve_user(target_id)
    await callback.message.edit_text(f"✅ Пользователь {target_id} одобрен.")
    try:
        await callback.bot.send_message(
            chat_id=target_id,
            text="✅ Тебе открякали доступ. Вэлкам кря!"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("admin_deny|"))
async def on_admin_deny(callback: CallbackQuery):
    """Админ отклонил пользователя."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет прав.", show_alert=True)
        return
    target_id = int(callback.data.split("|")[1])
    deny_user(target_id)
    await callback.message.edit_text(f"❌ Пользователь {target_id} отклонён.")
    try:
        await callback.bot.send_message(
            chat_id=target_id,
            text="❌ Тебе прикрыли кря. Больше не сможешь крякать. Можешь попробовать снова крякнуть /start"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("admin_revoke|"))
async def on_admin_revoke(callback: CallbackQuery):
    """Админ отозвал доступ пользователя."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет прав.", show_alert=True)
        return
    target_id = int(callback.data.split("|")[1])
    revoke_user(target_id)
    await callback.message.edit_text(f"🚫 Доступ пользователя {target_id} отозван.")
    try:
        await callback.bot.send_message(
            chat_id=target_id,
            text="❌ Тебе прикрыли кря. Больше не сможешь крякать. Можешь попробовать снова крякнуть /start"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("admin_msg|"))
async def cb_admin_msg(callback: CallbackQuery, state: FSMContext):
    """Админ хочет написать пользователю."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет прав.", show_alert=True)
        return
    target_id = int(callback.data.split("|")[1])
    await state.update_data(admin_msg_target=target_id)
    await callback.answer()
    await callback.message.answer(f"✏️ Напиши сообщение для пользователя {target_id}:")
