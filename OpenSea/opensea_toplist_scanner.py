
import logging
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

import asyncio, aiofiles
import cloudscraper
import pathlib

from requests.exceptions import JSONDecodeError


class OpenSea_TopListScanner:
    def __init__(
            self,
            scraper
    ):
        self.scraper = scraper
        self.queue = scraper.queue
        self.slugs_data = scraper.slugs_data

        self.notification_queue = scraper.notification_queue

        self.file_dir = pathlib.Path(__file__).parent


    async def init(self):
        graphql_file = self.file_dir / "GraphQL" / "get_top_list.graphql"
        async with aiofiles.open(graphql_file, "r") as f:
            self.GET_TOP_LIST_QUERY = await f.read()
    


    async def start(self):
        """Запуск основного цикла работы с OpenSea"""
        await self.init()

        await self.wrapper_get_all_collections()


    async def wrapper_get_all_collections(self):
        """Обертка для асинхронного вызова get_all_collections"""
        
        await self.init()

        retry_delay = 1

        while True:
            temp_slugs_data = {}
            try:
                temp_slugs_data = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, self.get_all_collections), 
                    timeout=60  # секунд
                )
                logger.debug(f"Получено {len(temp_slugs_data)} коллекций")
                
                retry_delay = 1

            except Exception as e:
                logger.error(f"Ошибка при получении коллекций: {e}")
                await asyncio.sleep(retry_delay)

                retry_delay = min(retry_delay * 2, 60)


            if not temp_slugs_data:
                continue


            self.slugs_data.update(temp_slugs_data)

            await self.queue.put(set(temp_slugs_data.keys()))

            if not self.scraper.full_scanned:
                self.scraper.full_scanned = True

            for collection in temp_slugs_data.values():
                await self.notification_queue.put(collection)

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
                    logger.error(f"Error fetching collections: {e} {response}")
                    raise e
        
            

