from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot_part1 import (
    LANGUAGES, get_label,
    get_user_settings, set_source_lang, toggle_target_lang
)

router = Router()

class LangSetup(StatesGroup):
    source  = State()
    targets = State()

PAGE_SIZE = 30

def get_sorted_codes():
    return sorted(LANGUAGES.keys(), key=lambda k: LANGUAGES[k][2])

def kb_source(current_source, page: int = 0) -> InlineKeyboardMarkup:
    codes = get_sorted_codes()
    total_pages = (len(codes) + PAGE_SIZE - 1) // PAGE_SIZE
    page_codes = codes[page*PAGE_SIZE : (page+1)*PAGE_SIZE]

    buttons = []
    row = []
    for code in page_codes:
        label = get_label(code)
        if code == current_source:
            label = "✅ " + label
        row.append(InlineKeyboardButton(text=label, callback_data=f"src:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"src_page:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"src_page:{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="src:save")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_targets(current_targets: list, page: int = 0) -> InlineKeyboardMarkup:
    codes = get_sorted_codes()
    total_pages = (len(codes) + PAGE_SIZE - 1) // PAGE_SIZE
    page_codes = codes[page*PAGE_SIZE : (page+1)*PAGE_SIZE]

    buttons = []
    row = []
    for code in page_codes:
        label = get_label(code)
        if code in current_targets:
            label = "✅ " + label
        row.append(InlineKeyboardButton(text=label, callback_data=f"tgt:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"tgt_page:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"tgt_page:{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="tgt:save")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("lang"))
async def cmd_lang(message: Message, state: FSMContext):
    uid = message.from_user.id
    settings = get_user_settings(uid)
    current_source = settings.get("source")
    await state.set_state(LangSetup.source)
    await state.update_data(src_page=0)
    await message.answer(
        "Шаг 1 из 2 — выбери <b>исходный язык</b> (с какого переводить):",
        reply_markup=kb_source(current_source, 0),
        parse_mode="HTML"
    )

@router.callback_query(LangSetup.source, F.data.startswith("src_page:"))
async def cb_src_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(":")[1])
    uid = call.from_user.id
    settings = get_user_settings(uid)
    await state.update_data(src_page=page)
    await call.message.edit_reply_markup(reply_markup=kb_source(settings.get("source"), page))
    await call.answer()

@router.callback_query(LangSetup.source, F.data.startswith("src:"))
async def cb_source_action(call: CallbackQuery, state: FSMContext):
    action = call.data.split(":")[1]
    uid = call.from_user.id
    settings = get_user_settings(uid)
    data = await state.get_data()
    page = data.get("src_page", 0)

    if action == "save":
        if not settings.get("source"):
            await call.answer("Выбери исходный язык!", show_alert=True)
            return
        await state.set_state(LangSetup.targets)
        await state.update_data(tgt_page=0)
        src_label = get_label(settings.get("source"))
        await call.message.edit_text(
            f"Исходный: {src_label}\n\n"
            "Шаг 2 из 2 — выбери <b>языки для перевода</b> (можно несколько):",
            reply_markup=kb_targets(settings.get("targets", []), 0),
            parse_mode="HTML"
        )
        await call.answer()
    else:
        set_source_lang(uid, action)
        await call.message.edit_reply_markup(reply_markup=kb_source(action, page))
        await call.answer()

@router.callback_query(LangSetup.targets, F.data.startswith("tgt_page:"))
async def cb_tgt_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(":")[1])
    uid = call.from_user.id
    settings = get_user_settings(uid)
    await state.update_data(tgt_page=page)
    await call.message.edit_reply_markup(reply_markup=kb_targets(settings.get("targets", []), page))
    await call.answer()

@router.callback_query(LangSetup.targets, F.data.startswith("tgt:"))
async def cb_target_action(call: CallbackQuery, state: FSMContext):
    action = call.data.split(":")[1]
    uid = call.from_user.id
    settings = get_user_settings(uid)
    data = await state.get_data()
    page = data.get("tgt_page", 0)

    if action == "save":
        targets = settings.get("targets", [])
        source = settings.get("source")
        if not targets:
            await call.answer("Выбери хотя бы один язык!", show_alert=True)
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
        toggle_target_lang(uid, action)
        updated_targets = get_user_settings(uid).get("targets", [])
        await call.message.edit_reply_markup(reply_markup=kb_targets(updated_targets, page))
    await call.answer()
