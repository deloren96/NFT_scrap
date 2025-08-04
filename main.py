import logging

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S",
    filename="main.log"
)
import asyncio, os

from opensea.opensea import OpenSea_Scraper
from telegram_bot import bot

from dotenv import load_dotenv; load_dotenv()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")

async def init():
    opensea = OpenSea_Scraper()
    asyncio.create_task(opensea.run())
    await bot.start_bot(token=TG_BOT_TOKEN, services={
        "opensea": opensea
    })

async def finish():
    log.info("Finishing...")
    await bot.dp.storage.close()
    await bot.dp.storage.wait_closed()
    log.info("Finished.")

if __name__ == "__main__":
    try:
        asyncio.run(init())

    except KeyboardInterrupt:
        log.info("Stopped.")
        
    except Exception as e:
        log.error(f"Error: {e}")