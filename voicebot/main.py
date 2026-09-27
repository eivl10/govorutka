import asyncio
import os

import deepl
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

import services
import handlers


async def main():
    bot_token = os.environ["BOT_TOKEN"]
    deepl_key = os.environ["DEEPL_KEY"]
    groq_key = os.environ["GROQ_KEY"]

    services.deepl_translator = deepl.Translator(deepl_key)
    services.GROQ_API_KEY = groq_key

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()
    dp.include_router(handlers.router)

    print("Бот запущен", flush=True)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
