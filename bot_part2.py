# ─── Часть 2: Команда /lang ───────────────────────────────────────────────────
#
# Шаг 1: пользователь выбирает исходный язык (с какого переводить)
# Шаг 2: пользователь выбирает языки-назначения (на какой, можно несколько)
# Кнопки с галочками ✅ / без. Кнопка "Сохранить" завершает настройку.
#
# Состояния FSM:
#   LangSetup.source  — ждём выбора исходного языка
#   LangSetup.targets — ждём выбора языков-назначений

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорт из Части 1
from bot_part1 import (
    LANGUAGES, get_label,
    get_user_settings, set_source_lang, toggle_target_lang
)

router = Router()


# ─── FSM-состояния ────────────────────────────────────────────────────────────

class LangSetup(StatesGroup):
    source  = State()   # выбор исходного языка
    targets = State()   # выбор языков-назначений


# ─── Клавиатуры ───────────────────────────────────────────────────────────────

def kb_source(current_source: str | None) -> InlineKeyboardMarkup:
    """Клавиатура выбора исходного языка. Галочка на текущем."""
    buttons = []
    row = []
    for code in LANGUAGES:
        label = get_label(code)
        if code == current_source:
            label = "✅ " + label
        row.append(InlineKeyboardButton(text=label, callback_data=f"src:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_targets(current_targets: list) -> InlineKeyboardMarkup:
    """Клавиатура выбора языков-назначений. Галочки на выбранных."""
    buttons = []
    row = []
    for code in LANGUAGES:
        label = get_label(code)
        if code in current_targets:
            label = "✅ " + label
        row.append(InlineKeyboardButton(text=label, callback_data=f"tgt:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    # Кнопка "Сохранить"
    buttons.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="tgt:save")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Хэндлеры ─────────────────────────────────────────────────────────────────

@router.message(Command("lang"))
async def cmd_lang(message: Message, state: FSMContext):
    """Запускает настройку языков — Шаг 1: выбор исходного"""
    uid = message.from_user.id
    settings = get_user_settings(uid)
    current_source = settings.get("source")

    await state.set_state(LangSetup.source)
    await message.answer(
        "Шаг 1 из 2 — выбери <b>исходный язык</b> (с какого переводить):",
        reply_markup=kb_source(current_source),
        parse_mode="HTML"
    )


@router.callback_query(LangSetup.source, F.data.startswith("src:"))
async def cb_source_selected(call: CallbackQuery, state: FSMContext):
    """Пользователь выбрал исходный язык — переходим к шагу 2"""
    code = call.data.split(":", 1)[1]
    uid = call.from_user.id

    set_source_lang(uid, code)
    await state.update_data(source=code)

    settings = get_user_settings(uid)
    current_targets = settings.get("targets", [])

    await state.set_state(LangSetup.targets)
    await call.message.edit_text(
        f"Исходный: {get_label(code)}\n\n"
        "Шаг 2 из 2 — выбери <b>языки для перевода</b> (можно несколько):",
        reply_markup=kb_targets(current_targets),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(LangSetup.targets, F.data.startswith("tgt:"))
async def cb_target_toggled(call: CallbackQuery, state: FSMContext):
    """Пользователь тыкает по языкам-назначениям"""
    action = call.data.split(":", 1)[1]
    uid = call.from_user.id
    settings = get_user_settings(uid)

    if action == "save":
        targets = settings.get("targets", [])
        source = settings.get("source")

        if not targets:
            await call.answer("Кря! Выбери хотя бы один язык 🦆", show_alert=True)
            return

        src_label = get_label(source)
        tgt_labels = " · ".join(get_label(c) for c in targets)
        await call.message.edit_text(
            f"✅ <b>Кря!</b> Сохранено:\n\n"
            f"С: {src_label}\n"
            f"На: {tgt_labels}\n\n"
            f"Ок, теперь крякни, а я крякну",
            parse_mode="HTML"
        )
        await state.clear()

    else:
        # Переключаем галочку
        toggle_target_lang(uid, action)
        current_targets = settings.get("targets", [])
        data = await state.get_data()
        source = data.get("source") or settings.get("source")

        await call.message.edit_text(
            f"Исходный: {get_label(source)}\n\n"
            "Шаг 2 из 2 — выбери <b>языки для перевода</b> (можно несколько):",
            reply_markup=kb_targets(current_targets),
            parse_mode="HTML"
        )

    await call.answer()
