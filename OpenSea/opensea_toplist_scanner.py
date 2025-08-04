
import logging
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

import asyncio, aiofiles
import cloudscraper


class OpenSea_TopListScanner:
    def __init__(
            self,
            queue: asyncio.Queue,
            slugs_data: dict,
            notification_manager: callable
    ):
        self.queue = queue
        self.slugs_data = slugs_data
        self.check_for_notification = notification_manager

        self.full_scanned = False


    async def init(self):
        async with aiofiles.open("./GraphQL/get_top_list.graphql", "r") as f:
            self.GET_TOP_LIST_QUERY = await f.read()
    


    async def start(self):
        """Запуск основного цикла работы с OpenSea"""
        await self.init()

        await self.wrapper_get_all_collections()


    async def wrapper_get_all_collections(self):
        """Обертка для асинхронного вызова get_all_collections"""
        
        await self.init()

        while True:
            
            temp_slugs_data = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.get_all_collections), 
                timeout=60  # секунд
            )

            if not temp_slugs_data:
                continue

            self.slugs_data.update(temp_slugs_data)

            await self.queue.put(set(temp_slugs_data.keys()))

            if not self.full_scanned[0]:
                self.full_scanned[0] = True

            for collection in temp_slugs_data.values():
                asyncio.create_task(self.check_for_notification(collection))
            
            await asyncio.sleep(60)
        

    def get_all_collections(self) -> dict:
        """Собирает данные всех коллекций с OpenSea"""

        temp_slugs_data = {}
        next_page = None


        variables = {
            "filter":{
                # "floorPriceRange"   : {"min": 0.001}, 
                # "hasMerchandising"  : False, 
                # "topOfferPriceRange": {"min": 0.001}
            },
            "limit":100,
            "sort":{
                "by":"ONE_DAY_VOLUME",
                "direction":"DESC"
            }
        }

        with cloudscraper.create_scraper() as scraper:

            while True:

                try:

                    if next_page:
                        variables["cursor"] = next_page

                    response = scraper.post('https://gql.opensea.io/graphql', json={

                        "operationName":"TopStatsTableQuery",
                        "query": self.GET_TOP_LIST_QUERY,
                        "variables": variables
                    
                    }).json()

                    top_collections = response["data"]["topCollections"]
                    
                    if top_collections:


                        for item in top_collections["items"]:
                            temp_slugs_data[item['slug']] = item

                        next_page = top_collections["nextPageCursor"]


                    if not next_page:
                        return temp_slugs_data
                
                except Exception as e:
                    logger.error(f"Error fetching collections: {e}")
                    next_page = None
        
            

