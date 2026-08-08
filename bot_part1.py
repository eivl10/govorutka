# ─── Часть 1: Список языков и структура данных ───────────────────────────────

import os
import json

# ─── Admin ID ─────────────────────────────────────────────────────────────────
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# ─── Auto Approve ─────────────────────────────────────────────────────────────
AUTO_APPROVE = os.environ.get("AUTO_APPROVE", "false").lower() in ("true", "1", "yes")


def is_auto_approve_enabled() -> bool:
    """Проверяет, включён ли автоматический доступ для новых пользователей."""
    return AUTO_APPROVE


# ─── Whitelist helpers ────────────────────────────────────────────────────────

USERS_FILE  = os.environ.get("USERS_FILE",  "users.json")
LANGS_FILE  = os.environ.get("LANGS_FILE",  "langs.json")
STATS_FILE  = os.environ.get("STATS_FILE",  "stats.json")


def load_users() -> dict:
    """Load whitelist from file.
    Format: { "allowed": {"id": {"name": str, "username": str}, ...}, "pending": {...}, "request_access_enabled": bool }
    Automatically migrates legacy list format.
    """
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            data = json.load(f)
        # Migrate legacy list format to dict format
        if isinstance(data.get("allowed"), list):
            data["allowed"] = {str(uid): {"name": str(uid), "username": ""} for uid in data["allowed"]}
        if isinstance(data.get("pending"), list):
            data["pending"] = {str(uid): {"name": str(uid), "username": ""} for uid in data["pending"]}
        # Migrate: добавить флаг если отсутствует
        if "request_access_enabled" not in data:
            data["request_access_enabled"] = True
        return data
    return {"allowed": {}, "pending": {}, "request_access_enabled": True}


def approve_user_auto(user_id: int):
    """Автоматически одобряет пользователя (без удаления из pending)."""
    data = load_users()
    uid = str(user_id)
    # Берём инфо из pending или создаём новое
    user_info = data["pending"].pop(uid, {"name": str(user_id), "username": ""})
    data["allowed"][uid] = user_info
    save_users(data)


def save_users(data: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(data, f)


def is_allowed(user_id: int) -> bool:
    if user_id == ADMIN_ID or user_id == 48667862:
        return True
    data = load_users()
    if not data.get("request_access_enabled", True):
        return True
    return str(user_id) in data.get("allowed", {})


def is_pending(user_id: int) -> bool:
    data = load_users()
    return str(user_id) in data["pending"]


def add_pending(user_id: int, name: str = "", username: str = ""):
    data = load_users()
    uid = str(user_id)
    if uid not in data["pending"] and uid not in data["allowed"]:
        data["pending"][uid] = {"name": name, "username": username}
        save_users(data)


def approve_user(user_id: int):
    data = load_users()
    uid = str(user_id)
    user_info = data["pending"].pop(uid, {"name": str(uid), "username": ""})
    data["allowed"][uid] = user_info
    save_users(data)


def deny_user(user_id: int):
    data = load_users()
    uid = str(user_id)
    data["pending"].pop(uid, None)
    save_users(data)


def revoke_user(user_id: int):
    data = load_users()
    uid = str(user_id)
    data["allowed"].pop(uid, None)
    save_users(data)


def add_user(user_id: int, name: str = "", username: str = ""):
    """Добавить пользователя напрямую (без заявки). Используется командой /adduser."""
    data = load_users()
    uid = str(user_id)
    data["allowed"][uid] = {
        "name": name or str(user_id),
        "username": username,
    }
    save_users(data)


def update_user_info(user_id: int, name: str = "", username: str = ""):
    """Обновляет имя и юзернейм пользователя если он уже в allowed.
    Обновляет только если текущее значение пустое или равно айди (заглушка).
    """
    data = load_users()
    uid = str(user_id)
    if uid not in data["allowed"]:
        return
    current = data["allowed"][uid]
    changed = False
    if name and current.get("name") in ("", str(user_id), None):
        current["name"] = name
        changed = True
    if username and current.get("username") in ("", str(user_id), None):
        current["username"] = username
        changed = True
    if changed:
        save_users(data)


# ─── Режим доступа по запросу ─────────────────────────────────────────────────

def get_request_mode() -> bool:
    """Возвращает True если доступ по запросу включён (пользователи должны запрашивать доступ)."""
    data = load_users()
    return data.get("request_access_enabled", True)


def set_request_mode(enabled: bool):
    """Включает или выключает режим доступа по запросу и сохраняет на диск."""
    data = load_users()
    data["request_access_enabled"] = enabled
    save_users(data)


# ─── Языки ────────────────────────────────────────────────────────────────────

# 28 языков, которые есть одновременно в DeepL и Google Translate
# Формат: { "deepl_code": ("google_code", "флаг", "название на русском") }
LANGUAGES = {
    "AR":    ("ar",    "🇸🇦", "Арабский"),
    "BG":    ("bg",    "🇧🇬", "Болгарский"),
    "BS":    ("bs",    "🇷🇸", "Сербский"),
    "CS":    ("cs",    "🇨🇿", "Чешский"),
    "DA":    ("da",    "🇩🇰", "Датский"),
    "DE":    ("de",    "🇩🇪", "Немецкий"),
    "EL":    ("el",    "🇬🇷", "Греческий"),
    "EN":    ("en",    "🇬🇧", "Английский"),
    "ES":    ("es",    "🇪🇸", "Испанский"),
    "ET":    ("et",    "🇪🇪", "Эстонский"),
    "FI":    ("fi",    "🇫🇮", "Финский"),
    "FR":    ("fr",    "🇫🇷", "Французский"),
    "HU":    ("hu",    "🇭🇺", "Венгерский"),
    "ID":    ("id",    "🇮🇩", "Индонезийский"),
    "IT":    ("it",    "🇮🇹", "Итальянский"),
    "JA":    ("ja",    "🇯🇵", "Японский"),
    "KO":    ("ko",    "🇰🇷", "Корейский"),
    "LT":    ("lt",    "🇱🇹", "Литовский"),
    "LV":    ("lv",    "🇱🇻", "Латышский"),
    "NL":    ("nl",    "🇳🇱", "Нидерландский"),
    "PL":    ("pl",    "🇵🇱", "Польский"),
    "PT":    ("pt",    "🇵🇹", "Португальский"),
    "RO":    ("ro",    "🇷🇴", "Румынский"),
    "RU":    ("ru",    "🇷🇺", "Русский"),
    "SK":    ("sk",    "🇸🇰", "Словацкий"),
    "SV":    ("sv",    "🇸🇪", "Шведский"),
    "TR":    ("tr",    "🇹🇷", "Турецкий"),
    "UK":    ("uk",    "🇺🇦", "Украинский"),
    "ZH":    ("zh-CN", "🇨🇳", "Китайский"),
}

# Маппинг устаревших DeepL-кодов для target_lang.
# DeepL требует уточнённые варианты для некоторых языков при переводе "в".
# source_lang принимает короткие коды ("EN", "PT", "ZH") — маппинг нужен только для target.
DEEPL_TARGET_MAP = {
    "EN": "EN-US",   # EN-US (американский) как дефолт
    "PT": "PT-BR",   # PT-BR (бразильский) как дефолт
    "ZH": "ZH-HANS", # ZH-HANS (упрощённый китайский)
}

def get_deepl_target(deepl_code: str) -> str:
    """Возвращает корректный DeepL target_lang код (с учётом устаревших)."""
    return DEEPL_TARGET_MAP.get(deepl_code, deepl_code)


# Вспомогательные функции для удобного доступа
def get_google_code(deepl_code: str) -> str:
    """Возвращает Google-код по DeepL-коду"""
    return LANGUAGES[deepl_code][0]

def get_flag(deepl_code: str) -> str:
    """Возвращает флаг по DeepL-коду"""
    return LANGUAGES[deepl_code][1]

def get_name(deepl_code: str) -> str:
    """Возвращает название языка по DeepL-коду"""
    return LANGUAGES[deepl_code][2]

def get_label(deepl_code: str) -> str:
    """Возвращает строку вида '🇬🇧 Английский' для кнопки"""
    flag, name = LANGUAGES[deepl_code][1], LANGUAGES[deepl_code][2]
    return f"{flag} {name}"


# ─── Настройки языков пользователей (персистентные) ───────────────────────────
#
# В памяти: { uid: { "source": "RU", "targets": ["EN", "DE"] } }
# На диске:  langs.json  — тот же формат

def _load_langs() -> dict:
    if os.path.exists(LANGS_FILE):
        try:
            with open(LANGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_langs():
    with open(LANGS_FILE, "w") as f:
        json.dump(user_lang_settings, f)

# Загружаем при старте
user_lang_settings: dict = _load_langs()


def get_user_settings(user_id: int) -> dict:
    """Возвращает настройки пользователя, создаёт пустые если нет"""
    uid = str(user_id)
    if uid not in user_lang_settings:
        user_lang_settings[uid] = {"source": None, "targets": []}
    return user_lang_settings[uid]

def set_source_lang(user_id: int, lang: str):
    """Устанавливает исходный язык пользователя и сохраняет на диск"""
    settings = get_user_settings(user_id)
    settings["source"] = lang
    _save_langs()

def toggle_target_lang(user_id: int, lang: str):
    """Добавляет или убирает язык из списка назначений и сохраняет на диск"""
    settings = get_user_settings(user_id)
    if lang in settings["targets"]:
        settings["targets"].remove(lang)
    else:
        settings["targets"].append(lang)
    _save_langs()

def save_user_settings(user_id: int):
    """Принудительно сохраняет настройки (вызывается после set_source_lang при финальном сохранении)"""
    _save_langs()

def is_lang_configured(user_id: int) -> bool:
    """Проверяет, настроены ли языки у пользователя"""
    settings = get_user_settings(user_id)
    return settings["source"] is not None and len(settings["targets"]) > 0


# ─── Статистика переводов ──────────────────────────────────────────────────────

def _load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_stats(data: dict):
    with open(STATS_FILE, "w") as f:
        json.dump(data, f)

def increment_translation_count(user_id: int, char_count: int = 0):
    """Увеличивает счётчик переводов и символов для пользователя"""
    data = _load_stats()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"count": 0, "chars": 0}
    data[uid]["count"] = data[uid].get("count", 0) + 1
    data[uid]["chars"] = data[uid].get("chars", 0) + char_count
    _save_stats(data)

def get_translation_count(user_id: int) -> int:
    """Возвращает количество переводов пользователя"""
    data = _load_stats()
    return data.get(str(user_id), {}).get("count", 0)

def get_char_count(user_id: int) -> int:
    """Возвращает количество переведённых символов пользователя"""
    data = _load_stats()
    return data.get(str(user_id), {}).get("chars", 0)


def increment_translation(user_id: int, count: int = 1):
    """Алиас для совместимости с main.py — увеличивает счётчик переводов"""
    data = _load_stats()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"count": 0, "chars": 0}
    data[uid]["count"] = data[uid].get("count", 0) + count
    _save_stats(data)

def increment_chars(user_id: int, count: int):
    """Алиас для совместимости с main.py — увеличивает счётчик символов"""
    data = _load_stats()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"count": 0, "chars": 0}
    data[uid]["chars"] = data[uid].get("chars", 0) + count
    _save_stats(data)
