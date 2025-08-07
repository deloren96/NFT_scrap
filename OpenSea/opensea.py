import logging

logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger('aiogram').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

import asyncio, aiohttp, json
from collections import defaultdict

from OpenSea.notify import NotifyCreator
from OpenSea.opensea_websocket import OpenSea_WebSocket
from OpenSea.opensea_toplist_scanner import OpenSea_TopListScanner

from configs import BuildConfigs



class BaseNotificationManager:
    
    @staticmethod
    async def add_message(self, user_id, message):
        print(user_id, message)


class OpenSea_Scraper:
    def __init__(
            self,
            session: aiohttp.ClientSession,
            notification_managers
        ):
        self.session = session
        self.queue = asyncio.Queue()
        self.notification_queue = asyncio.Queue()
        self.notification_managers = notification_managers

        self.slugs_data = {}

        self.last_notifications = {}
        self.last_diffs = {}
        self.full_scanned = False

        self.configs = BuildConfigs.opensea



    async def run(self):
        """Запуск основного цикла работы с OpenSea"""

        scraper = self

        notify_creator = NotifyCreator(scraper)
        top_list_scanner = OpenSea_TopListScanner(scraper)
        opensea_websocket = OpenSea_WebSocket(scraper)

        asyncio.create_task(notify_creator.wraper_check_for_notifications())
        asyncio.create_task(top_list_scanner.start())
        await opensea_websocket.run_websocket()


def filter_collections():
    
    with open("collections.json", "r") as f:
        collections = json.load(f)
    
    filtered = [c for c in collections if "0x" not in c]
    
    logger.debug(f"Filtered collections: {len(filtered)}")
    return filtered



async def main():
    async with aiohttp.ClientSession() as session:
        scraper = OpenSea_Scraper(
            session=session,
            notification_managers=defaultdict(BaseNotificationManager)
        )
        await scraper.run()
        


if __name__ == "__main__":
    asyncio.run(main())