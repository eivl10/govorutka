# ─── Хэндлеры бота ────────────────────────────────────────────────────────────
#
# Текст → сразу озвучивается (TTS) + кнопка 🌐 (перевести).
# Голосовое → транскрибируется + кнопки 🔊 (озвучить оригинал) и 🌐 (перевести).
# 🌐 открывает выбор языка(ов): по умолчанию выбор одного (тап = сразу перевод),
# переключатель 🔘/☑️ включает мульти-выбор (тапы копят галочки, ✅ подтверждает).
# Перевод на каждый выбранный язык приходит отдельным сообщением со своей 🔊.

import hashlib
import secrets

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)

from langs import sorted_codes, get_flag
from services import translate_text, detect_source_lang, transcribe_voice, synthesize_speech

router = Router()

PAGE_SIZE = 30       # 6 в ряд × 5 рядов
PER_ROW = 6

# ─── Кеш текстов: hash → (text, lang) ─────────────────────────────────────────

_text_cache: dict[str, tuple[str, str]] = {}
_CACHE_MAX = 1000


def cache_text(text: str, lang: str) -> str:
    h = hashlib.md5(text.encode()).hexdigest()[:12]
    _text_cache[h] = (text, lang)
    if len(_text_cache) > _CACHE_MAX:
        _text_cache.pop(next(iter(_text_cache)), None)
    return h


def get_cached(h: str) -> tuple[str, str] | None:
    return _text_cache.get(h)


# ─── Состояние открытых пикеров языка: pid → {...} ────────────────────────────

_pickers: dict[str, dict] = {}
_PICKERS_MAX = 300


def new_picker(text_hash: str, origin_markup: InlineKeyboardMarkup | None) -> str:
    pid = secrets.token_hex(4)
    _pickers[pid] = {
        "text_hash": text_hash,
        "multi": False,
        "selected": set(),
        "page": 0,
        "origin_markup": origin_markup,
    }
    if len(_pickers) > _PICKERS_MAX:
        _pickers.pop(next(iter(_pickers)), None)
    return pid


# ─── Клавиатуры ───────────────────────────────────────────────────────────────

def kb_text_result(h: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐", callback_data=f"tr|{h}"),
    ]])


def kb_voice_result(h: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔊", callback_data=f"sp|{h}"),
        InlineKeyboardButton(text="🌐", callback_data=f"tr|{h}"),
    ]])


def kb_speak_only(h: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔊", callback_data=f"sp|{h}"),
    ]])


def kb_picker(pid: str) -> InlineKeyboardMarkup:
    state = _pickers[pid]
    codes = sorted_codes()
    total_pages = (len(codes) + PAGE_SIZE - 1) // PAGE_SIZE
    page = state["page"]
    page_codes = codes[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]

    buttons = []
    row = []
    for code in page_codes:
        label = get_flag(code)
        if state["multi"] and code in state["selected"]:
            label = "✅" + label
        row.append(InlineKeyboardButton(text=label, callback_data=f"p|{pid}|lg|{code}"))
        if len(row) == PER_ROW:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"p|{pid}|pg|{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="🔙", callback_data=f"p|{pid}|bk"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"p|{pid}|pg|{page + 1}"))
    buttons.append(nav_row)

    toggle_row = [InlineKeyboardButton(
        text="☑️" if state["multi"] else "🔘",
        callback_data=f"p|{pid}|mm",
    )]
    if state["multi"]:
        toggle_row.append(InlineKeyboardButton(text="✅", callback_data=f"p|{pid}|ok"))
    buttons.append(toggle_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Вспомогательное: перевести и отправить одним сообщением ─────────────────

async def _translate_and_send(bot: Bot, chat_id: int, text: str, source: str, target: str):
    try:
        translated = await translate_text(text, source, target)
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка перевода: {e}")
        return
    th = cache_text(translated, target)
    await bot.send_message(
        chat_id,
        f"{get_flag(target)} {translated}",
        reply_markup=kb_speak_only(th),
    )


# ─── Текст → сразу озвучка ─────────────────────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot):
    text = message.text
    await bot.send_chat_action(message.chat.id, "record_voice")

    detected = await detect_source_lang(text)
    h = cache_text(text, detected)

    try:
        audio = await synthesize_speech(text, detected)
    except Exception as e:
        await message.answer(f"❌ Ошибка TTS: {e}")
        return

    audio_file = BufferedInputFile(audio, filename="speech.mp3")
    await message.answer_voice(voice=audio_file, reply_markup=kb_text_result(h))


# ─── Голосовое → транскрибация ─────────────────────────────────────────────────

@router.message(F.voice)
async def on_voice(message: Message, bot: Bot):
    await bot.send_chat_action(message.chat.id, "typing")

    try:
        file = await bot.get_file(message.voice.file_id)
        file_bytes_io = await bot.download_file(file.file_path)
        file_bytes = file_bytes_io.read()
    except Exception as e:
        await message.answer(f"❌ Не смог скачать аудио: {e}")
        return

    try:
        text = await transcribe_voice(file_bytes)
    except Exception as e:
        await message.answer(f"❌ Ошибка транскрибации: {e}")
        return

    if not text.strip():
        await message.answer("❌ Не удалось распознать речь.")
        return

    detected = await detect_source_lang(text)
    h = cache_text(text, detected)
    await message.answer(text, reply_markup=kb_voice_result(h))


# ─── Callback: озвучить (оригинал или перевод) ────────────────────────────────

@router.callback_query(F.data.startswith("sp|"))
async def cb_speak(callback: CallbackQuery, bot: Bot):
    _, h = callback.data.split("|", 1)
    entry = get_cached(h)
    if not entry:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    text, lang = entry
    await callback.answer("🔊 Говорю...")

    try:
        audio = await synthesize_speech(text, lang)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка TTS: {e}")
        return

    audio_file = BufferedInputFile(audio, filename="speech.mp3")
    await bot.send_voice(chat_id=callback.message.chat.id, voice=audio_file)


# ─── Callback: открыть выбор языка перевода ───────────────────────────────────

@router.callback_query(F.data.startswith("tr|"))
async def cb_translate_open(callback: CallbackQuery):
    _, h = callback.data.split("|", 1)
    if not get_cached(h):
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    pid = new_picker(h, callback.message.reply_markup)
    await callback.message.edit_reply_markup(reply_markup=kb_picker(pid))
    await callback.answer()


# ─── Callback: пикер языка (пагинация / мульти-режим / назад / выбор / ок) ───

@router.callback_query(F.data.startswith("p|"))
async def cb_picker(callback: CallbackQuery, bot: Bot):
    _, pid, action, *rest = callback.data.split("|")
    state = _pickers.get(pid)
    if not state:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        return

    if action == "pg":
        state["page"] = int(rest[0])
        await callback.message.edit_reply_markup(reply_markup=kb_picker(pid))
        await callback.answer()
        return

    if action == "mm":
        state["multi"] = not state["multi"]
        if not state["multi"]:
            state["selected"].clear()
        await callback.message.edit_reply_markup(reply_markup=kb_picker(pid))
        await callback.answer()
        return

    if action == "bk":
        await callback.message.edit_reply_markup(reply_markup=state["origin_markup"])
        _pickers.pop(pid, None)
        await callback.answer()
        return

    entry = get_cached(state["text_hash"])
    if not entry:
        await callback.answer("Текст устарел. Отправь заново.", show_alert=True)
        _pickers.pop(pid, None)
        return
    text, source = entry

    if action == "lg":
        code = rest[0]
        if state["multi"]:
            if code in state["selected"]:
                state["selected"].discard(code)
            else:
                state["selected"].add(code)
            await callback.message.edit_reply_markup(reply_markup=kb_picker(pid))
            await callback.answer()
            return

        await callback.answer()
        await _translate_and_send(bot, callback.message.chat.id, text, source, code)
        await callback.message.edit_reply_markup(reply_markup=state["origin_markup"])
        _pickers.pop(pid, None)
        return

    if action == "ok":
        if not state["selected"]:
            await callback.answer("Выбери хотя бы один язык!", show_alert=True)
            return
        await callback.answer()
        for code in list(state["selected"]):
            await _translate_and_send(bot, callback.message.chat.id, text, source, code)
        await callback.message.edit_reply_markup(reply_markup=state["origin_markup"])
        _pickers.pop(pid, None)
        return


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "<b>Кря! Кря на любом языке 🦆</b>\n\n"
        "Крякни мне текст — сразу озвучу.\n"
        "Крякни голосовое — расшифрую.\n\n"
        "🌐 — перевести (🔘 один язык, ☑️ — сразу несколько)\n"
        "🔊 — озвучить\n\n"
        "Кря! 🦆",
        parse_mode="HTML",
    )
