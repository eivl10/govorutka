# ─── Часть 5: AI-разбор слов и OCR-перевод фото ───────────────────────────────
#
# Фича 1: Кнопка [🤖 AI] после перевода → Groq llama-3.3-70b даёт лингво-разбор
# Фича 2: Фото с текстом → Groq llama-4-scout (Vision) → OCR + перевод
# Fallback для Vision: Google Gemini Flash Lite (если задан GOOGLE_API_KEY)
#
# Новые переменные .env:
#   GOOGLE_API_KEY   — опционально, для резервного Vision
#   AI_EXPLAIN_ENABLED — true/false (default: true)
#   AI_PHOTO_ENABLED   — true/false (default: true)

import io
import os
import json
import base64
import httpx

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext

from bot_part1 import (
    LANGUAGES,
    is_allowed, is_auto_approve_enabled, approve_user_auto,
    is_pending, add_pending,
    get_user_settings, is_lang_configured,
)
from bot_part3 import get_cached_text, cache_text, synthesize_speech

router = Router()

# ─── Глобальные переменные (устанавливаются из main.py) ──────────────────────
GROQ_API_KEY: str | None = None
GOOGLE_API_KEY: str | None = None

AI_MODEL_TEXT   = "llama-3.3-70b-versatile"
AI_MODEL_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"

GROQ_CHAT_URL  = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL     = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent"

AI_EXPLAIN_ENABLED = os.environ.get("AI_EXPLAIN_ENABLED", "true").lower() == "true"
AI_PHOTO_ENABLED   = os.environ.get("AI_PHOTO_ENABLED", "true").lower() == "true"


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def lang_name(code: str) -> str:
    """DeepL-код → название языка на русском."""
    entry = LANGUAGES.get(code.upper())
    return entry[2] if entry else code


async def ai_explain_word(
    text: str,
    source_lang: str,
    target_lang: str,
    deepl_translation: str,
) -> str:
    """
    Запрашивает у Groq llama-3.3-70b лингвистический разбор слова/фразы.
    Возвращает готовый текст для отправки пользователю.
    """
    src_name = lang_name(source_lang)
    tgt_name = lang_name(target_lang)

    system_prompt = (
        "Ты лингвистический помощник. Дай краткий разбор слова/фразы строго по шаблону. "
        "Используй HTML-теги <b> для жирного текста. "
        "Ответ всегда на РУССКОМ языке. "
        "Никаких эмодзи кроме 🌍 в первой строке. "
        "Никаких примеров, никаких похожих слов. Только: Язык, Перевод, Транскрипция, Нюанс."
    )

    user_prompt = f"""Разбери слово/фразу: "{text}"
Исходный язык: {src_name}
Язык перевода: {tgt_name}
Перевод DeepL: "{deepl_translation}"

Дай в таком формате (используй эти эмодзи):

🌍 <b>Язык:</b> <название языка оригинала>
<b>Перевод:</b> <точный перевод с нюансами>
<b>Транскрипция:</b> <транскрипция МФА или произношение, если применимо; иначе пропусти строку>
<b>Нюанс:</b> <культурный или лингвистический контекст, 1-2 предложения>

Больше ничего не добавляй. Никаких примеров, похожих слов, дополнительных секций."""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL_TEXT,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": 600,
        "temperature": 0.4,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
        resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def ai_translate_image_groq(image_bytes: bytes, target_lang_name: str) -> dict:
    """
    OCR + перевод через Groq Vision (llama-4-scout).
    Возвращает dict: {original, lang, translated} или бросает исключение.
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    user_prompt = f"""1. Извлеки весь видимый текст с этого изображения.
2. Определи язык текста.
3. Переведи на {target_lang_name}.

Формат ответа (строго, без лишних слов):
ORIGINAL: <извлечённый текст>
LANG: <язык оригинала>
TRANSLATED: <перевод>

Если текст не найден: ORIGINAL: [нет текста]"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL_VISION,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "max_tokens": 800,
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
        resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()
    return _parse_vision_response(content)


async def ai_translate_image_gemini(image_bytes: bytes, target_lang_name: str) -> dict:
    """
    Fallback: OCR + перевод через Google Gemini Flash Lite.
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = f"""Извлеки весь текст с изображения, определи язык и переведи на {target_lang_name}.

Формат:
ORIGINAL: <текст>
LANG: <язык>
TRANSLATED: <перевод>"""

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ]
        }]
    }

    url = f"{GEMINI_URL}?key={GOOGLE_API_KEY}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    return _parse_vision_response(content)


def _parse_vision_response(text: str) -> dict:
    """Парсит ORIGINAL/LANG/TRANSLATED из ответа LLM."""
    result = {"original": "", "lang": "", "translated": ""}
    for line in text.splitlines():
        if line.startswith("ORIGINAL:"):
            result["original"] = line[len("ORIGINAL:"):].strip()
        elif line.startswith("LANG:"):
            result["lang"] = line[len("LANG:"):].strip()
        elif line.startswith("TRANSLATED:"):
            result["translated"] = line[len("TRANSLATED:"):].strip()
    return result


# ─── Хэндлер: кнопка 🤖 AI (разбор слова) ───────────────────────────────────

@router.callback_query(F.data.startswith("ai_explain|"))
async def cb_ai_explain(callback: CallbackQuery):
    """Нажали кнопку 🤖 AI — запрашиваем у Groq разбор слова."""
    if not AI_EXPLAIN_ENABLED:
        await callback.answer("AI временно отключён.", show_alert=True)
        return

    _, text_hash, translated_hash, source, target = callback.data.split("|")

    original_text   = get_cached_text(text_hash)
    deepl_translated = get_cached_text(translated_hash)

    if not original_text:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    await callback.answer("🤖 Думаю...")

    try:
        explanation = await ai_explain_word(
            text=original_text,
            source_lang=source,
            target_lang=target,
            deepl_translation=deepl_translated or "",
        )
        header = f"🤖 <b>Groq AI:</b> <i>{original_text}</i>\n\n"
        await callback.message.answer(header + explanation, parse_mode="HTML")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            await callback.message.answer("⚠️ Лимит Groq исчерпан. Попробуй через минуту.")
        else:
            await callback.message.answer(f"❌ Ошибка AI: {e.response.status_code}")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка AI: {e}")


# ─── Хэндлер: фото → OCR → перевод ──────────────────────────────────────────

@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext):
    """Пользователь прислал фото — извлекаем текст и переводим."""
    uid = message.from_user.id

    if not is_allowed(uid):
        if is_auto_approve_enabled():
            approve_user_auto(uid)
        elif is_pending(uid):
            await message.answer("✅ Заявку кря. Погоди немного.")
            return
        else:
            add_pending(uid)
            await message.answer("🦆 Запрос на доступ отправлен.")
            return

    if not AI_PHOTO_ENABLED:
        await message.answer("📸 Перевод фото временно отключён.")
        return

    settings = get_user_settings(uid)
    if not is_lang_configured(uid):
        await message.answer("⚙️ Сначала настрой языки командой /lang")
        return

    # Определяем язык назначения для отображения в ответе
    source = settings["source"]
    tgt_name = lang_name(source)  # переводим на source-язык пользователя

    status_msg = await message.answer("🔍 Анализирую фото...")

    # Скачиваем фото (берём наибольшее разрешение)
    photo = message.photo[-1]
    try:
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        image_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)
    except Exception as e:
        await status_msg.delete()
        await message.answer(f"❌ Не удалось загрузить фото: {e}")
        return

    # Vision: Groq → Gemini fallback
    parsed = None
    used_model = "Groq"

    try:
        parsed = await ai_translate_image_groq(image_bytes, tgt_name)
    except Exception as e_groq:
        if GOOGLE_API_KEY:
            try:
                parsed = await ai_translate_image_gemini(image_bytes, tgt_name)
                used_model = "Gemini"
            except Exception as e_gemini:
                await status_msg.delete()
                await message.answer(
                    f"❌ Groq Vision: {e_groq}\n❌ Gemini fallback: {e_gemini}"
                )
                return
        else:
            await status_msg.delete()
            await message.answer(f"❌ Ошибка Vision AI: {e_groq}")
            return

    await status_msg.delete()

    if not parsed or not parsed.get("original") or parsed["original"] == "[нет текста]":
        await message.answer("🦆 Текст на фото не найден.")
        return

    # Формируем ответ
    lang_label = parsed.get("lang", "Неизвестно")
    original   = parsed.get("original", "")
    translated = parsed.get("translated", "")

    # Кнопка «Озвучить перевод»
    trans_hash = cache_text(translated)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="▶ Озвучить",
            callback_data=f"speak|{trans_hash}|{source}",
        )
    ]])

    reply = (
        f"📸 <b>Текст на фото:</b>\n"
        f"<code>{original}</code>\n\n"
        f"🌍 <b>Язык:</b> {lang_label}\n\n"
        f"🇷🇺 <b>Перевод на {tgt_name}:</b>\n"
        f"{translated}\n\n"
        f"<i>via {used_model}</i>"
    )

    await message.answer(reply, parse_mode="HTML", reply_markup=kb)
