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

from notify import NotifyCreator
from opensea_websocket import OpenSea_WebSocket
from opensea_toplist_scanner import OpenSea_TopListScanner
from configs import load_configs

class OpenSea_Scraper:
    def __init__(
            self,
            session: aiohttp.ClientSession,
            notification_managers: callable
        ):
        self.session = session
        self.queue = asyncio.Queue()
        self.notification_managers = notification_managers

        self.slugs_data = {}

        self.last_notifications = {}
        self.last_diffs = {}
        self.full_scanned = [False]

        self.configs = {}



    async def run(self):
        """Запуск основного цикла работы с OpenSea"""

        self.configs = await load_configs()

        notify_creator = NotifyCreator(
            self.slugs_data, 
            self.full_scanned, 
            self.configs, 
            self.notification_managers
        )

        top_list_scanner = OpenSea_TopListScanner(
            self.queue, 
            self.slugs_data, 
            notify_creator.send_notifications
        )

        opensea_websocket = OpenSea_WebSocket(
            self.session, 
            self.queue, 
            self.slugs_data, 
            notify_creator.send_notifications
        )

        asyncio.create_task(top_list_scanner.start())
        asyncio.create_task(opensea_websocket.run_websocket())


def filter_collections():
    
    with open("collections.json", "r") as f:
        collections = json.load(f)
    
    filtered = [c for c in collections if "0x" not in c]
    
    logger.debug(f"Filtered collections: {len(filtered)}")
    return filtered



async def main():
    pass