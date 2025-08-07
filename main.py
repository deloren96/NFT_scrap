import logging

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
import asyncio, aiohttp, os

from OpenSea.opensea import OpenSea_Scraper
from telegram_bot.bot import TelegramBot
from telegram_bot.message_manager import NotificationManagerFactory

from dotenv import load_dotenv; load_dotenv()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")



async def init():
    async with aiohttp.ClientSession() as session:
        tg = TelegramBot(token=TG_BOT_TOKEN)

        notification_managers = NotificationManagerFactory(
            send_message=tg.bot.send_message,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

        opensea = OpenSea_Scraper(
            session=session,
            notification_managers=notification_managers
        )

        asyncio.create_task(tg.start())
        log.info("Telegram bot started")
        await opensea.run()
        print("OpenSea scraper started")
        await asyncio.sleep(1)


if __name__ == "__main__":

        asyncio.run(init())
