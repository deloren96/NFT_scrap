
import logging
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)
import asyncio, aiohttp, aiofiles, json, uuid, pathlib
from OpenSea.utils import get_usd_price, deep_dict_update
from aiohttp.client_exceptions import WSServerHandshakeError


class OpenSea_WebSocket:
    def __init__(
            self,
            scraper
        ):
        self.session = scraper.session
        self.websocket: aiohttp.ClientWebSocketResponse = None

        self.queue: asyncio.Queue = scraper.queue
        self.slugs_data = scraper.slugs_data

        self.notification_queue = scraper.notification_queue
        self.file_dir = pathlib.Path(__file__).parent



    async def init(self):
        graphql_file = self.file_dir / "GraphQL" / "subscribe_query.graphql"
        async with aiofiles.open(graphql_file, "r") as f:
            self.SUBSCRIBE_QUERY = await f.read()



    async def load_slugs(self):
        try:

            async with aiofiles.open(self.file_dir / "collections.json", "r") as f:
                return set(json.loads(await f.read()))
        except Exception as e:
            logger.error(f"Error loading collections: {e}") 
            return set()


    async def batch_subscribe(self, to_sub: set[str]):
        """Подписываемся на все коллекции частями"""
        to_sub: list[str] = list(to_sub)

        batch_size = 200

        for i in range(0, len(to_sub), batch_size):


            if batch := to_sub[i:i+batch_size]:

                asyncio.create_task(
                    self.websocket.send_json(

                        {
                            "id": str(uuid.uuid4()), 
                            "type": "subscribe", 
                            "payload": {
                                "query": self.SUBSCRIBE_QUERY,
                                "operationName": "useCollectionStatsSubscription",
                                "variables": {
                                    "slugs": batch
                                }
                            }
                        }

                    )
                )


    async def save_collections(self, subs: list):
        try:
            async with aiofiles.open("collections.json", "w") as f:
                await f.write(json.dumps(
                    list(subs), 
                    separators=(',', ':')
                ))
            logger.info(f"Saved {len(subs)} collections to file.")
        except:
            logger.error("Error saving collections to file.")
    

    
    async def init_subscriptions_manager(self):
        
        collection_manager = asyncio.create_task(self.manage_subscriptions())
        new_slugs = await self.load_slugs()

        while not self.queue._getters:
            await asyncio.sleep(0.1)

        
        await self.queue.put(new_slugs)
        return collection_manager



    async def manage_subscriptions(self):
        
        active_slugs = set()
        try:

            while not self.websocket.closed:
                
                new_slugs: set[str] = await self.queue.get()
                
                if not new_slugs:
                    logger.warning("No slugs found.")
                    continue
                
                new_subscriptions = new_slugs - active_slugs
                
                if not new_subscriptions:
                    logger.debug("No new slugs to subscribe.")
                    continue

                active_slugs.update(new_subscriptions)

                await self.save_collections(active_slugs)

                await self.batch_subscribe(new_subscriptions)

                logger.info(f"Subscribed to {len(new_subscriptions)} collections.")

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Connection manager cancelled.")



    async def manage_prices(self, payload: dict):
        
        slugs_data = self.slugs_data

        new_collection = payload["data"]["collectionsBySlugs"]

        if new_collection and (slug := new_collection.get("slug")):
            
            old_collection = slugs_data.get(slug)

            if not old_collection: 
                slugs_data[slug] = new_collection
            else:

                old_floorPrice = get_usd_price(old_collection, "floorPrice")
                new_floorPrice = get_usd_price(new_collection, "floorPrice")
                old_topOffer   = get_usd_price(old_collection, "topOffer")
                new_topOffer   = get_usd_price(new_collection, "topOffer")
                
                if old_floorPrice == new_floorPrice \
                    and old_topOffer == new_topOffer:
                        return

                deep_dict_update(old_collection, new_collection)

            # logger.debug(f"{id} \n\n Slug: {slug}\n Floor Price: {new_floorPrice} USD, Top Offer: {new_topOffer} USD\n{'-'*70}")

            await self.notification_queue.put(slugs_data[slug])



    async def run_websocket(self):
        """Подключается к WebSocket OpenSea и отслеживает изменения в коллекциях"""

        await self.init()

        reconnect_delay = 1

        while True:
            
            if not self.session: continue
            
            try:

                async with self.session.ws_connect(f"wss://os2-wss.prod.privatesea.io/subscriptions", heartbeat=30) as websocket:
                    self.websocket = websocket
                    
                    reconnect_delay = 1

                    await websocket.send_json({"type": "connection_init"})


                    collection_manager = await self.init_subscriptions_manager()


                    async for message in websocket:
                        message_data = message.json()
                        # logger.debug(f"Received WebSocket message: {message_data}")


                        if message_data.get("type") == "connection_ack":
                            logger.info("WebSocket connection established.")
                            continue


                        if payload := message_data.get("payload"):
                            await self.manage_prices(payload)
                        else:
                            logger.warning(f"Received unexpected message: {message.data}")


                    else:
                        collection_manager.cancel()
                        await collection_manager
                        logger.info(f"WebSocket connection closed. {message.type}")

            except WSServerHandshakeError as e:
                logger.error(f"WebSocket connection failed: {e}\nRetrying in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
            except Exception as e:
                logger.error(f"Error in WebSocket connection: {e}\nRetrying in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)