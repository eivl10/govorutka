# ─── Перевод, детект языка, синтез и распознавание речи ──────────────────────
#
# Логика перенесена из utka (bot_part3.py): DeepL для перевода, детект языка
# в три шага (DeepL → langdetect → Google), Groq Whisper для STT, gTTS для TTS.

import asyncio
import io

import deepl
import httpx
from langdetect import DetectorFactory, detect_langs

from langs import (
    LANGUAGES, GOOGLE_TTS_LANGS, LANGDETECT_TO_DEEPL,
    DEFAULT_LANG, get_deepl_target, normalize_deepl_code,
)

# Устанавливаются из main.py при старте
deepl_translator: "deepl.Translator | None" = None
GROQ_API_KEY: str | None = None

DetectorFactory.seed = 0  # детерминированный langdetect

# langdetect доверяем без DeepL только на достаточно длинном тексте и с высокой уверенностью
LANGDETECT_MIN_LEN = 20
LANGDETECT_MIN_PROB = 0.95
# Для детекта через DeepL хватает начала текста — остальное зря съедает лимит символов
DETECT_SAMPLE_LEN = 200


def _langdetect(text: str, min_prob: float = 0.0) -> str | None:
    try:
        best = detect_langs(text)[0]
        if best.prob < min_prob:
            return None
        return LANGDETECT_TO_DEEPL.get(best.lang)
    except Exception:
        return None


async def translate_text(text: str, source: str, target: str) -> str:
    """Перевод через DeepL."""
    target_code = get_deepl_target(target)
    result = await asyncio.to_thread(
        deepl_translator.translate_text, text, source_lang=source, target_lang=target_code
    )
    return result.text


async def detect_source_lang(text: str) -> str:
    """Определяет язык текста, возвращает DeepL-код (по умолчанию EN)."""
    # 1. Уверенный langdetect — бесплатно и офлайн
    if len(text) >= LANGDETECT_MIN_LEN:
        mapped = _langdetect(text, min_prob=LANGDETECT_MIN_PROB)
        if mapped:
            return mapped

    # 2. DeepL умеет вернуть detected_source_lang при любом переводе — шлём только начало
    if deepl_translator is not None:
        try:
            result = await asyncio.to_thread(
                deepl_translator.translate_text, text[:DETECT_SAMPLE_LEN], target_lang="EN-US"
            )
            detected = normalize_deepl_code(result.detected_source_lang)
            if detected:
                return detected
        except Exception:
            pass

    # 3. langdetect без порога уверенности
    mapped = _langdetect(text)
    if mapped:
        return mapped

    # 4. Последний резерв — неофициальный Google Translate API
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": ["t", "ld"], "q": text}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        google_code = data[2] if len(data) > 2 else None
        if google_code:
            google_code = google_code.lower().split("-")[0]
            for deepl_code, (g_code, _, _) in LANGUAGES.items():
                if g_code.lower().split("-")[0] == google_code:
                    return deepl_code
    except Exception:
        pass

    return DEFAULT_LANG


async def transcribe_voice(file_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Транскрибирует голосовое сообщение через Groq Whisper API."""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    files = {"file": (filename, file_bytes, "audio/ogg")}
    data = {"model": "whisper-large-v3"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, files=files, data=data)
        resp.raise_for_status()
    return resp.json().get("text", "").strip()


async def synthesize_speech(text: str, lang_code: str) -> bytes:
    """Синтез речи через gTTS. Возвращает MP3 в bytes."""
    from gtts import gTTS

    tts_lang = GOOGLE_TTS_LANGS.get(lang_code, "en")

    def _synth() -> bytes:
        buf = io.BytesIO()
        gTTS(text=text, lang=tts_lang).write_to_fp(buf)
        buf.seek(0)
        return buf.read()

    return await asyncio.to_thread(_synth)
