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


def _write_json(path: str, data) -> None:
    """Атомарная запись: пишем во временный файл и подменяем, чтобы падение
    посреди записи не оставило битый JSON."""
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def save_users(data: dict):
    _write_json(USERS_FILE, data)


def is_allowed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
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
    "AF":    ("af",    "🇿🇦", "Африкаанс"),
    "AN":    ("an",    "🇪🇸", "Арагонский"),
    "AR":    ("ar",    "🇸🇦", "Арабский"),
    "AS":    ("as",    "🇮🇳", "Ассамский"),
    "AY":    ("ay",    "🇧🇴", "Аймара"),
    "AZ":    ("az",    "🇦🇿", "Азербайджанский"),
    "BA":    ("ba",    "🇷🇺", "Башкирский"),
    "BE":    ("be",    "🇧🇾", "Белорусский"),
    "BG":    ("bg",    "🇧🇬", "Болгарский"),
    "BN":    ("bn",    "🇧🇩", "Бенгальский"),
    "BR":    ("br",    "🇫🇷", "Бретонский"),
    "BS":    ("bs",    "🇷🇸", "Сербский"),
    "CA":    ("ca",    "🇪🇸", "Каталанский"),
    "CS":    ("cs",    "🇨🇿", "Чешский"),
    "CY":    ("cy",    "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Валлийский"),
    "DA":    ("da",    "🇩🇰", "Датский"),
    "DE":    ("de",    "🇩🇪", "Немецкий"),
    "EL":    ("el",    "🇬🇷", "Греческий"),
    "EN":    ("en",    "🇬🇧", "Английский"),
    "EO":    ("eo",    "🌍", "Эсперанто"),
    "ES":    ("es",    "🇪🇸", "Испанский"),
    "ET":    ("et",    "🇪🇪", "Эстонский"),
    "EU":    ("eu",    "🇪🇸", "Баскский"),
    "FA":    ("fa",    "🇮🇷", "Персидский"),
    "FI":    ("fi",    "🇫🇮", "Финский"),
    "FR":    ("fr",    "🇫🇷", "Французский"),
    "GA":    ("ga",    "🇮🇪", "Ирландский"),
    "GL":    ("gl",    "🇪🇸", "Галисийский"),
    "GN":    ("gn",    "🇵🇾", "Гуарани"),
    "GU":    ("gu",    "🇮🇳", "Гуджарати"),
    "HA":    ("ha",    "🇳🇬", "Хауса"),
    "HE":    ("he",    "🇮🇱", "Иврит"),
    "HI":    ("hi",    "🇮🇳", "Хинди"),
    "HR":    ("hr",    "🇭🇷", "Хорватский"),
    "HT":    ("ht",    "🇭🇹", "Гаитянский креольский"),
    "HU":    ("hu",    "🇭🇺", "Венгерский"),
    "HY":    ("hy",    "🇦🇲", "Армянский"),
    "ID":    ("id",    "🇮🇩", "Индонезийский"),
    "IG":    ("ig",    "🇳🇬", "Игбо"),
    "IS":    ("is",    "🇮🇸", "Исландский"),
    "IT":    ("it",    "🇮🇹", "Итальянский"),
    "JA":    ("ja",    "🇯🇵", "Японский"),
    "JV":    ("jv",    "🇮🇩", "Яванский"),
    "KA":    ("ka",    "🇬🇪", "Грузинский"),
    "KK":    ("kk",    "🇰🇿", "Казахский"),
    "KO":    ("ko",    "🇰🇷", "Корейский"),
    "KY":    ("ky",    "🇰🇬", "Киргизский"),
    "LA":    ("la",    "🏛️", "Латынь"),
    "LB":    ("lb",    "🇱🇺", "Люксембургский"),
    "LN":    ("ln",    "🇨🇩", "Лингала"),
    "LT":    ("lt",    "🇱🇹", "Литовский"),
    "LV":    ("lv",    "🇱🇻", "Латышский"),
    "MG":    ("mg",    "🇲🇬", "Малагасийский"),
    "MI":    ("mi",    "🇳🇿", "Маори"),
    "MK":    ("mk",    "🇲🇰", "Македонский"),
    "ML":    ("ml",    "🇮🇳", "Малаялам"),
    "MN":    ("mn",    "🇲🇳", "Монгольский"),
    "MR":    ("mr",    "🇮🇳", "Маратхи"),
    "MS":    ("ms",    "🇲🇾", "Малайский"),
    "MT":    ("mt",    "🇲🇹", "Мальтийский"),
    "MY":    ("my",    "🇲🇲", "Бирманский"),
    "NB":    ("no",    "🇳🇴", "Норвежский"),
    "NE":    ("ne",    "🇳🇵", "Непальский"),
    "NL":    ("nl",    "🇳🇱", "Нидерландский"),
    "OC":    ("oc",    "🇫🇷", "Окситанский"),
    "OM":    ("om",    "🇪🇹", "Оромо"),
    "PA":    ("pa",    "🇮🇳", "Пенджабский"),
    "PL":    ("pl",    "🇵🇱", "Польский"),
    "PS":    ("ps",    "🇦🇫", "Пушту"),
    "PT":    ("pt",    "🇵🇹", "Португальский"),
    "QU":    ("qu",    "🇵🇪", "Кечуа"),
    "RO":    ("ro",    "🇷🇴", "Румынский"),
    "RU":    ("ru",    "🇷🇺", "Русский"),
    "SA":    ("sa",    "🇮🇳", "Санскрит"),
    "SK":    ("sk",    "🇸🇰", "Словацкий"),
    "SL":    ("sl",    "🇸🇮", "Словенский"),
    "SQ":    ("sq",    "🇦🇱", "Албанский"),
    "ST":    ("st",    "🇱🇸", "Сесото"),
    "SU":    ("su",    "🇮🇩", "Сунданский"),
    "SV":    ("sv",    "🇸🇪", "Шведский"),
    "SW":    ("sw",    "🇰🇪", "Суахили"),
    "TA":    ("ta",    "🇮🇳", "Тамильский"),
    "TE":    ("te",    "🇮🇳", "Телугу"),
    "TG":    ("tg",    "🇹🇯", "Таджикский"),
    "TH":    ("th",    "🇹🇭", "Тайский"),
    "TK":    ("tk",    "🇹🇲", "Туркменский"),
    "TL":    ("tl",    "🇵🇭", "Тагальский"),
    "TN":    ("tn",    "🇧🇼", "Тсвана"),
    "TR":    ("tr",    "🇹🇷", "Турецкий"),
    "TS":    ("ts",    "🇿🇦", "Тсонга"),
    "TT":    ("tt",    "🇷🇺", "Татарский"),
    "UK":    ("uk",    "🇺🇦", "Украинский"),
    "UR":    ("ur",    "🇵🇰", "Урду"),
    "UZ":    ("uz",    "🇺🇿", "Узбекский"),
    "VI":    ("vi",    "🇻🇳", "Вьетнамский"),
    "WO":    ("wo",    "🇸🇳", "Волоф"),
    "XH":    ("xh",    "🇿🇦", "Коса"),
    "YI":    ("yi",    "✡️", "Идиш"),
    "ZH":    ("zh-CN",    "🇨🇳", "Китайский"),
    "ZU":    ("zu",    "🇿🇦", "Зулу"),
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
    entry = LANGUAGES.get(deepl_code)
    if not entry:
        return f"❓ {deepl_code}"
    return f"{entry[1]} {entry[2]}"


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
    _write_json(LANGS_FILE, user_lang_settings)

# Загружаем при старте
user_lang_settings: dict = _load_langs()


def get_user_settings(user_id: int) -> dict:
    """Возвращает настройки пользователя, создаёт пустые если нет"""
    uid = str(user_id)
    if uid not in user_lang_settings:
        user_lang_settings[uid] = {"source": None, "targets": []}
    
    # Добавляем дефолтные значения новых настроек
    if "auto_speech" not in user_lang_settings[uid]:
        user_lang_settings[uid]["auto_speech"] = False
    if "ai_detail" not in user_lang_settings[uid]:
        user_lang_settings[uid]["ai_detail"] = "short"
        
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

def toggle_auto_speech(user_id: int):
    settings = get_user_settings(user_id)
    settings["auto_speech"] = not settings.get("auto_speech", False)
    _save_langs()

def toggle_ai_detail(user_id: int):
    settings = get_user_settings(user_id)
    current = settings.get("ai_detail", "short")
    settings["ai_detail"] = "full" if current == "short" else "short"
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
    _write_json(STATS_FILE, data)

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
