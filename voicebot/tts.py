# TTS: сначала edge-tts (Microsoft, не режется по IP хостинга), при сбое — gTTS.
# gTTS ходит на translate.google.com, который блокирует IP многих серверов.
import asyncio
import io
import logging

log = logging.getLogger(__name__)

# DeepL-код → голос Edge. Языков нет в таблице — сразу gTTS.
EDGE_VOICES = {
    "AF": "af-ZA-WillemNeural", "AR": "ar-SA-HamedNeural", "BG": "bg-BG-BorislavNeural",
    "BN": "bn-IN-BashkarNeural", "CA": "ca-ES-EnricNeural", "CS": "cs-CZ-AntoninNeural",
    "DA": "da-DK-JeppeNeural", "DE": "de-DE-ConradNeural", "EL": "el-GR-NestorasNeural",
    "EN": "en-US-GuyNeural", "ES": "es-ES-AlvaroNeural", "ET": "et-EE-KertNeural",
    "FI": "fi-FI-HarriNeural", "FR": "fr-FR-HenriNeural", "GU": "gu-IN-NiranjanNeural",
    "HE": "he-IL-AvriNeural", "HI": "hi-IN-MadhurNeural", "HR": "hr-HR-SreckoNeural",
    "HU": "hu-HU-TamasNeural", "ID": "id-ID-ArdiNeural", "IS": "is-IS-GunnarNeural",
    "IT": "it-IT-DiegoNeural", "JA": "ja-JP-KeitaNeural", "KO": "ko-KR-InJoonNeural",
    "LT": "lt-LT-LeonasNeural", "LV": "lv-LV-NilsNeural", "ML": "ml-IN-MidhunNeural",
    "MR": "mr-IN-ManoharNeural", "MS": "ms-MY-OsmanNeural", "MY": "my-MM-ThihaNeural",
    "NB": "nb-NO-FinnNeural", "NE": "ne-NP-SagarNeural", "NL": "nl-NL-MaartenNeural",
    "PL": "pl-PL-MarekNeural", "PT": "pt-PT-DuarteNeural", "RO": "ro-RO-EmilNeural",
    "RU": "ru-RU-DmitryNeural", "SK": "sk-SK-LukasNeural", "SL": "sl-SI-RokNeural",
    "SQ": "sq-AL-IlirNeural", "SR": "sr-RS-NicholasNeural", "SU": "su-ID-JajangNeural",
    "SV": "sv-SE-MattiasNeural", "SW": "sw-KE-RafikiNeural", "TA": "ta-IN-ValluvarNeural",
    "TE": "te-IN-MohanNeural", "TH": "th-TH-NiwatNeural", "TR": "tr-TR-AhmetNeural",
    "UK": "uk-UA-OstapNeural", "UR": "ur-PK-AsadNeural", "VI": "vi-VN-NamMinhNeural",
    "ZH": "zh-CN-YunxiNeural", "BS": "sr-RS-NicholasNeural",
}


async def _edge(text: str, voice: str) -> bytes:
    import edge_tts
    chunks = []
    async for part in edge_tts.Communicate(text, voice).stream():
        if part["type"] == "audio":
            chunks.append(part["data"])
    data = b"".join(chunks)
    if not data:
        raise RuntimeError("edge-tts вернул пустое аудио")
    return data


async def _gtts(text: str, tts_lang: str) -> bytes:
    from gtts import gTTS

    def _synth() -> bytes:
        buf = io.BytesIO()
        gTTS(text=text, lang=tts_lang).write_to_fp(buf)
        return buf.getvalue()

    return await asyncio.to_thread(_synth)


async def synthesize(text: str, lang_code: str, gtts_lang: str) -> bytes:
    """MP3 в bytes. gtts_lang — код для фолбэка."""
    voice = EDGE_VOICES.get(lang_code)
    if voice:
        try:
            return await asyncio.wait_for(_edge(text, voice), timeout=30)
        except Exception as e:
            log.warning("edge-tts не сработал (%s), пробую gTTS", e)
    return await _gtts(text, gtts_lang)
