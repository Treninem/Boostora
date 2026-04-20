from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Config
from app.db import Database
from app.handlers import router


def run() -> None:
    asyncio.run(main())


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    config = Config.load()
    if not config.bot_token:
        raise RuntimeError('BOT_TOKEN is not set in .env')

    db = Database(config.db_path)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp['config'] = config
    dp['db'] = db
    dp.include_router(router)
    logging.info('Starting %s', config.brand_name)
    await dp.start_polling(bot)
