import logging

from aiogram import Bot, Dispatcher

from telegram_bot.main_menu.handlers import \
    commands as main_menu_commands, \
    callbacks as main_menu_callbacks
from telegram_bot.opensea.handlers import \
    text_handlers as opensea_text_handlers, \
    callbacks as opensea_callbacks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




class TelegramBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()

        self.dp.include_router(main_menu_commands.router)
        self.dp.include_router(main_menu_callbacks.router)
        self.dp.include_router(opensea_text_handlers.router)
        self.dp.include_router(opensea_callbacks.router)



    async def start(self):
        try:
            logging.info("Бот запускается...")
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logging.error(f"Ошибка при запуске бота: {e}")
        finally:
            await self.bot.session.close()
            logging.info("Бот остановлен.")