import asyncio
import os

import deepl
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

import bot_part2
import bot_part3
import bot_part4
import bot_part5
from bot_part1 import increment_translation, increment_chars

# ─── Подключаем счётчики переводов и символов в bot_part3 ─────────────────────
bot_part3.increment_translation = increment_translation
bot_part3.increment_chars = increment_chars


async def main():
    # ─── Ключи из переменных окружения ───────────────────────────────────────
    bot_token = os.environ["BOT_TOKEN"]
    deepl_key = os.environ["DEEPL_KEY"]
    groq_key  = os.environ["GROQ_KEY"]
    # ADMIN_ID читается напрямую в bot_part1.py через os.environ.get("ADMIN_ID")

    # ─── Инициализация клиентов API ───────────────────────────────────────────
    bot_part3.deepl_translator = deepl.Translator(deepl_key)
    bot_part3.GROQ_API_KEY     = groq_key

    # ─── AI (bot_part5) ───────────────────────────────────────────────────────
    bot_part5.GROQ_API_KEY   = groq_key
    bot_part5.GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

    # ─── Бот и диспетчер ─────────────────────────────────────────────────────
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=None)
    )
    dp = Dispatcher(storage=MemoryStorage())

    @dp.update.outer_middleware()
    async def log_updates(handler, event, data):
        print(f"[TELEGRAM UPDATE] {event}", flush=True)
        return await handler(event, data)


    # Порядок важен: сначала /lang и команды, потом текст/голос
    dp.include_router(bot_part2.router)   # /lang (FSM)
    dp.include_router(bot_part4.router)   # /start, /stats, /rest, /users
    dp.include_router(bot_part5.router)   # AI-разбор + фото (до bot_part3!)
    dp.include_router(bot_part3.router)   # текст, голосовые, access-колбэки (последний!)

    print("Кря! Бот запущен 🦆")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
