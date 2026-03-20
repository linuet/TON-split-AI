import asyncio

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.api.main import create_app
from app.bot.handlers.receipt import router as receipt_router
from app.bot.handlers.start import router as start_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import Base, engine


async def run_bot() -> None:
    settings = get_settings()
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(receipt_router)
    await dp.start_polling(bot)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run_api() -> None:
    settings = get_settings()
    config = uvicorn.Config(
        app=create_app(),
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.debug)
    await init_db()
    await asyncio.gather(run_api(), run_bot())


if __name__ == "__main__":
    asyncio.run(main())
