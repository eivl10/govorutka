# ─── Часть 4: /start, /stats, /rest, /users, /adduser ───────────────────────
#
# /start    — приветствие (с проверкой доступа)
# /stats    — сколько переводов сделал пользователь
# /rest     — остаток символов DeepL
# /users    — список одобренных пользователей (только для админа)
# /adduser  — добавить пользователя по айди (только для админа)

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import asyncio
import os
import httpx

import bot_part3  # для доступа к deepl_translator

from bot_part1 import (
    ADMIN_ID,
    is_allowed, is_pending, add_pending,
    load_users, add_user, update_user_info,
    get_translation_count, get_char_count,
    get_request_mode, set_request_mode,
    is_auto_approve_enabled, approve_user_auto,
    get_user_settings, toggle_auto_speech, toggle_ai_detail
)

router = Router()


# ─── Хэндлеры ────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    print(f"[DEBUG] /start received from {message.from_user.id} (@{message.from_user.username})", flush=True)
    user = message.from_user

    if not is_allowed(user.id):
        if is_auto_approve_enabled():
            approve_user_auto(user.id)
        elif is_pending(user.id):
            await message.answer("⏳ Твоя заявка всё ещё на рассмотрении. Ожидайте.")
            return
        else:
            add_pending(user.id, user.full_name, user.username or "")
            await message.answer("📝 Заявка отправлена администратору. Ожидайте подтверждения.")
            admin_msg = f"🆕 Новая заявка:\nID: {user.id}\nИмя: {user.full_name}\nЮзернейм: @{user.username}"
            try:
                await message.bot.send_message(ADMIN_ID, admin_msg, reply_markup=bot_part3.kb_admin_approve(user.id))
            except Exception as e:
                print(f"Failed to notify admin: {e}")
            return

    # Подтягиваем имя/юзернейм для добавленных через /adduser
    update_user_info(user.id, user.full_name, user.username or "")

    await message.answer(
        "<b>Кря! Кря кря кря на любой язык 🦆</b>\n\n"
        "Я кря с глубоким кря кря по умолчанию через DeepL. Но могу и Google кря и ИИ кря.\n"
        "Просто кря мне текст, войс или крятинку — я кря кря кря изи!\n\n"
        "<i>Ну и если крякнешь на любом языке, который не исходный, то переведу на исходный. Попробуй.</i>\n\n"
        "<b>Кряманды:</b>\n"
        "/lang — кря языка\n"
        "/settings — настройки озвучки и ИИ\n"
        "/stats — статистика переводов кря\n"
        "/rest — остаток кря DeepL кря\n\n"
        "Ну всё. Начни с кря языка по команде /lang. Кря! 🦆",
        parse_mode="HTML"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    uid = message.from_user.id

    if not is_allowed(uid):
        await message.answer("🔒 Нет доступа.")
        return

    count = get_translation_count(uid)

    if count == 0:
        text = "<b>Кря!</b> Ты ещё не кря ни одного перевода 🦆"
    elif count % 10 == 1 and count % 100 != 11:
        text = f"<b>Кря!</b> Ты накрякал {count} перевод 🦆"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        text = f"<b>Кря!</b> Ты накрякал {count} перевода 🦆"
    else:
        text = f"<b>Кря!</b> Ты накрякал {count} переводов 🦆"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("rest"))
async def cmd_rest(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("🔒 Нет доступа.")
        return

    if bot_part3.deepl_translator is None:
        await message.answer("<b>Кря!</b> DeepL не подключён 🦆", parse_mode="HTML")
        return

    try:
        usage = await asyncio.to_thread(bot_part3.deepl_translator.get_usage)
        used = usage.character.count
        limit = usage.character.limit
        left = limit - used
        percent_used = round(used / limit * 100, 1)

        groq_limit_text = ""
        groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY")
        if groq_key:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
                    )
                    hdrs = {k.lower(): v for k, v in resp.headers.items()}
                    tok_rem = hdrs.get("x-ratelimit-remaining-tokens-today", hdrs.get("x-ratelimit-remaining-tokens"))
                    req_rem = hdrs.get("x-ratelimit-remaining-requests-today", hdrs.get("x-ratelimit-remaining-requests"))
                    if tok_rem and req_rem:
                        groq_limit_text = f"\n\n🤖 <b>Лимиты Groq (AI):</b>\nОстаток токенов: {tok_rem}\nОстаток запросов: {req_rem}"
            except Exception:
                pass

        await message.answer(
            f"<b>Кря!</b> Остаток DeepL 🦆\n\n"
            f"Использовано: {used:,} / {limit:,} символов ({percent_used}%)\n"
            f"Осталось: <b>{left:,}</b> символов{groq_limit_text}",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"<b>Кря!</b> Не смог проверить остаток: {e}", parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message):
    """Только для админа: список одобренных пользователей с кнопками управления."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав.")
        return

    data = load_users()
    allowed = data.get("allowed", {})

    # Считаем пользователей без самого админа
    users_list = [(uid, info) for uid, info in allowed.items() if int(uid) != ADMIN_ID]

    # Пробуем получить лимит DeepL для расчёта процентов
    deepl_limit = None
    if bot_part3.deepl_translator is not None:
        try:
            usage = await asyncio.to_thread(bot_part3.deepl_translator.get_usage)
            deepl_limit = usage.character.limit
        except Exception:
            pass

    if users_list:
        text = f"👥 Одобренные пользователи ({len(users_list)}):\n\n"
        keyboard = []

        for uid, info in users_list:
            name = info.get("name", "") if isinstance(info, dict) else ""
            username = info.get("username", "") if isinstance(info, dict) else ""

            # Чистим username от случайного @ в начале
            username = username.lstrip("@") if username else ""

            if name and username:
                display = f"{name} (@{username})"
                btn_label = f"@{username}"
            elif username:
                display = f"@{username}"
                btn_label = f"@{username}"
            elif name and name != uid:
                display = name
                btn_label = name
            else:
                # Нет никаких данных — показываем айди
                display = f"ID {uid}"
                btn_label = f"ID {uid}"

            chars = get_char_count(int(uid))
            if chars > 0:
                if deepl_limit:
                    percent = round(chars / deepl_limit * 100, 1)
                    display += f" · {chars:,} симв. ({percent}%)"
                else:
                    display += f" · {chars:,} симв."

            text += f"• {display}\n"
            keyboard.append([
                InlineKeyboardButton(text=f"✉️ {btn_label}", callback_data=f"admin_msg|{uid}"),
                InlineKeyboardButton(text="🚫 Отозвать", callback_data=f"admin_revoke|{uid}"),
            ])
    else:
        text = "Нет одобренных пользователей.\n"
        keyboard = []

    # Кнопка переключения режима доступа по запросу
    request_mode = get_request_mode()
    if request_mode:
        mode_btn = InlineKeyboardButton(
            text="🔓 Доступ по запросу: вкл",
            callback_data="admin_toggle_request_mode"
        )
    else:
        mode_btn = InlineKeyboardButton(
            text="🔒 Доступ по запросу: выкл",
            callback_data="admin_toggle_request_mode"
        )
    keyboard.append([mode_btn])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.message(Command("adduser"))
async def cmd_adduser(message: Message):
    """Только для админа: добавить пользователя по айди напрямую."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав.")
        return

    parts = message.text.split(maxsplit=2)
    # /adduser <user_id> [username]
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Использование:\n"
            "/adduser <user_id> — добавить по айди\n"
            "/adduser <user_id> @username — добавить с юзернеймом\n\n"
            "Пример: /adduser 123456789 @ivan"
        )
        return

    user_id = int(parts[1])
    username = parts[2].lstrip("@") if len(parts) > 2 else ""

    add_user(user_id, name=username or str(user_id), username=username)

    if username:
        await message.answer(f"✅ Пользователь @{username} (ID {user_id}) добавлен.")
    else:
        await message.answer(
            f"✅ Пользователь ID {user_id} добавлен.\n"
            f"Юзернейм неизвестен — появится автоматически когда напишет /start."
        )


@router.callback_query(F.data == "admin_toggle_request_mode")
async def cb_toggle_request_mode(callback: CallbackQuery):
    """Переключает режим доступа по запросу."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет прав.", show_alert=True)
        return

    current = get_request_mode()
    new_mode = not current
    set_request_mode(new_mode)

    # Обновляем текст кнопки
    if new_mode:
        new_btn = InlineKeyboardButton(
            text="🔓 Доступ по запросу: вкл",
            callback_data="admin_toggle_request_mode"
        )
        status_text = "включён"
    else:
        new_btn = InlineKeyboardButton(
            text="🔒 Доступ по запросу: выкл",
            callback_data="admin_toggle_request_mode"
        )
        status_text = "выключен"

    # Берём текущую клавиатуру и обновляем последнюю строку
    old_keyboard = callback.message.reply_markup.inline_keyboard if callback.message.reply_markup else []
    new_keyboard = old_keyboard[:-1] + [[new_btn]]  # заменяем последнюю строку

    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=new_keyboard))
    await callback.answer(f"Режим доступа по запросу {status_text}.")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        await message.answer("🔒 Нет доступа.")
        return

    settings = get_user_settings(uid)
    auto_speech = settings.get("auto_speech", False)
    ai_detail = settings.get("ai_detail", "short")

    btn_speech = InlineKeyboardButton(
        text="🔊 Автоозвучка: " + ("ВКЛ" if auto_speech else "ВЫКЛ"),
        callback_data="settings:toggle_speech"
    )
    btn_ai = InlineKeyboardButton(
        text="🤖 AI детали: " + ("Кратко" if ai_detail == "short" else "Подробно"),
        callback_data="settings:toggle_ai"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_speech], [btn_ai]])
    await message.answer("⚙️ <b>Настройки:</b>", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("settings:"))
async def cb_settings(callback: CallbackQuery):
    uid = callback.from_user.id
    if not is_allowed(uid):
        await callback.answer("🔒 Нет доступа.", show_alert=True)
        return
    action = callback.data.split(":")[1]

    if action == "toggle_speech":
        toggle_auto_speech(uid)
    elif action == "toggle_ai":
        toggle_ai_detail(uid)

    settings = get_user_settings(uid)
    auto_speech = settings.get("auto_speech", False)
    ai_detail = settings.get("ai_detail", "short")

    btn_speech = InlineKeyboardButton(
        text="🔊 Автоозвучка: " + ("ВКЛ" if auto_speech else "ВЫКЛ"),
        callback_data="settings:toggle_speech"
    )
    btn_ai = InlineKeyboardButton(
        text="🤖 AI детали: " + ("Кратко" if ai_detail == "short" else "Подробно"),
        callback_data="settings:toggle_ai"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_speech], [btn_ai]])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()
