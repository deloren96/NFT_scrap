
import logging
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)
import asyncio, aiohttp, aiofiles, json, uuid
from utils import get_usd_price, deep_dict_update



class OpenSea_WebSocket:
    def __init__(
            self,
            session: aiohttp.ClientSession,
            queue: asyncio.Queue,
            slugs_data: dict,
            notification_manager: callable
        ):
        self.session = session
        self.websocket: aiohttp.ClientWebSocketResponse = None
        
        self.queue: asyncio.Queue = queue
        self.slugs_data = slugs_data
        self.slugs_subscriptions = set(slugs_data.keys())

        self.check_for_notification = notification_manager



    async def init(self):
        async with aiofiles.open("./GraphQL/subscribe_query_clean.graphql", "r") as f:
            self.SUBSCRIBE_QUERY = await f.read()



    async def load_slugs(self):
        try:
            async with aiofiles.open("collections.json", "r") as f:
                self.slugs_subscriptions.update(json.loads(await f.read()))
        except Exception as e:
            logger.error(f"Error loading collections: {e}") 



    async def batch_subscribe(self, to_sub: list[str]):
        """Подписываемся на все коллекции частями"""

        batch_size = 200
        tasks = []
        
        for i in range(0, len(to_sub), batch_size):
            
            batch = to_sub[i:i+batch_size]
            
            if batch:
                
                tasks.append(self.websocket.send_json(
                    
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
                    
                ))

        await asyncio.gather(*tasks)



    async def save_collections(self, subs: list):
        try:
            async with aiofiles.open("collections.json", "w") as f:
                await f.write(json.dumps(
                    list(subs), 
                    separators=(',', ':')
                ))
        except:
            pass
    

    
    async def init_subscriptions_manager(self):
        
        collection_manager = asyncio.create_task(self.manage_subscriptions())

        while not self.queue._getters:
            await asyncio.sleep(0.1)

        await self.load_slugs()
        await self.queue.put(self.slugs_subscriptions)
        return collection_manager



    async def manage_subscriptions(self):
        
        active_slugs = self.slugs_subscriptions
        try:

            while not self.websocket.closed:

                new_slugs: set = await self.queue.get()
                
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

            # logger.debug(f"{id} \n\n Slug: {slug}\n Floor Price: {floorPrice} USD, Top Offer: {topOffer} USD\n{'-'*70}")

            asyncio.create_task(self.check_for_notification(old_collection))



    async def run_websocket(self):
        """Подключается к WebSocket OpenSea и отслеживает изменения в коллекциях"""

        await self.init()


        while True:
            
            if not self.session: continue
            
            try:

                async with self.session.ws_connect(f"wss://os2-wss.prod.privatesea.io/subscriptions", heartbeat=30) as websocket:
                    self.websocket = websocket

                    await websocket.send_json({"type": "connection_init"})


                    collection_manager = await self.init_subscriptions_manager()


                    async for message in websocket:
                        message_data = message.json()


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


            except Exception as e:
                logger.error(f"Error in WebSocket connection: {e}")
                await asyncio.sleep(1)