import logging

logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger('aiogram').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

import asyncio, aiohttp, aiofiles, os, json, uuid, heapq
import telegram_bot.bot as tg
import cloudscraper

from dotenv import load_dotenv; load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
queue = asyncio.Queue()

slugs_data = {}

last_notifications = {}
last_diffs = {}
full_scanned = False

def custom_condition(collection, user_id):
    """Фильтрация коллекций по настройкам пользователей и проверка условий для отправки уведомлений"""
    # Условие
    
    # Конфиги
    cfg = tg.configs[user_id]
    if not cfg: return False

    ## Фильтры
    
    # Черный список
    if collection["slug"] in cfg.blacklist: return False
    # Топ N по 1d объему
    if cfg.top_N_by_1d_volume < float('inf'):
        if not full_scanned or 0 >= cfg.top_N_by_1d_volume: return False

        colls = [coll for coll in slugs_data.values() if coll.get("stats") is not None]
        top_N_by_1d_volume = heapq.nlargest(
            cfg.top_N_by_1d_volume,
            colls,
            key=lambda coll: coll["stats"]["oneDay"]["volume"]["usd"]
        )
        if cfg.top_N_by_1d_volume \
            and not any(coll['slug'] == collection['slug'] for coll in top_N_by_1d_volume):
                return False
    # Диапазон по 1d объему
    if not (cfg.min_USD_1d_volume <= collection["stats"]["volume"]["usd"] <= cfg.max_USD_1d_volume):
        return False
    # Диапазон по цене топ оффера
    if not (cfg.min_USD_top_offer <= (get_usd_price(collection, "topOffer") or 0) <= cfg.max_USD_top_offer):
        return False
    
    ## Alerts
    
    topOffer = get_usd_price(collection, "topOffer")
    floorPrice = get_usd_price(collection, "floorPrice")
    if not (topOffer and floorPrice): return False
    conditions = {}
    
    # Разница между ценой топ оффера и ценой листинга
    diff_percent_offer_to_floor = (floorPrice - topOffer) / floorPrice * 100
    if diff_percent_offer_to_floor > cfg.diff_percent_offer_to_floor:
        
        conditions['diff_percent_offer_to_floor'] = diff_percent_offer_to_floor
        
    if any(conditions.values()): # all(required_conditions) or any(not_required_conditions)
        return conditions

    return False

async def send_notifications(collection):
    """Проверка условий и отправка уведомлений"""
    for user_id, cfg in tg.configs.items():
        # Проверка кулдауна с последнего уведомления по notification_cooldown в config
        if cfg.notification_cooldown:
            now = asyncio.get_event_loop().time()
            prev_notification = last_notifications.setdefault(collection['slug'], {}).setdefault(user_id, 0)
            if now - prev_notification < cfg.notification_cooldown: continue

        conditions = custom_condition(collection, user_id)
        if conditions:
            
            # Проверка движения на шаг процентов с прошлого diff процента по percent_step в config
            if cfg.percent_step:
                diff_prev = last_diffs.setdefault(collection['slug'], {}).setdefault(user_id, 0.001)
                step_size = diff_prev * (cfg.percent_step / 100)
                if abs(conditions['diff_percent_offer_to_floor'] - diff_prev) <= step_size:
                    continue
            
            # Получаем цены и создаем уведомление
            usd_price = (get_usd_price(collection, 'topOffer') or get_usd_price(collection, 'floorPrice') or 0)
            topOffer   = get_native_price(collection, "topOffer")
            floorPrice = get_native_price(collection, "floorPrice")

            try: 
                await tg.message_manager[user_id].add_message(

                    f"Collection - {collection['slug']}\n"
                    f"Price - {usd_price:.2f}$\n"
                    f"List - {topOffer['price']} {topOffer['currency']}\n"
                    f"Floor - {floorPrice['price']} {floorPrice['currency']}\n"
                    f"Diff - <b>{conditions['diff_percent_offer_to_floor']:.2f}%</b>\n"
                    f"opensea.io/collection/{collection['slug']}"
                
                )

                if cfg.notification_cooldown: 
                    last_notifications[collection['slug']][user_id] = now
                
                if cfg.percent_step: 
                    last_diffs.setdefault(collection['slug'], {})[user_id] = conditions['diff_percent_offer_to_floor']
            
            except Exception as e: logger.error(f"Error sending message to {user_id}: {e}")

def filter_collections():
    
    with open("collections.json", "r") as f:
        collections = json.load(f)
    
    filtered = [c for c in collections if "0x" not in c]
    
    logger.debug(f"Filtered collections: {len(filtered)}")
    return filtered

async def wrapper_get_all_collections():
    """Обертка для асинхронного вызова get_all_collections"""
    global full_scanned
    loop = asyncio.get_event_loop()
    while True:
        temp_slugs_data = await asyncio.wait_for(
            loop.run_in_executor(None, get_all_collections), 
            timeout=60  # секунд
        )
        if not temp_slugs_data: continue
        slugs_data.update(temp_slugs_data)

        await queue.put(list(temp_slugs_data.keys()))
        
        if not full_scanned: full_scanned = True
        
        for collection in temp_slugs_data.values():
            asyncio.create_task(send_notifications(collection))
        
        await asyncio.sleep(60)
        

def get_all_collections() -> dict:
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
    # spended = time.time()
    with cloudscraper.create_scraper() as scraper:
        while True:
            try:
                # Делаем запрос пока не дойдем до конца страниц
                if next_page: variables["cursor"] = next_page

                response = scraper.post('https://gql.opensea.io/graphql', json={"operationName":"TopStatsTableQuery","query":"query TopStatsTableQuery($cursor: String, $sort: TopCollectionsSort!, $filter: TopCollectionsFilter, $category: CategoryIdentifier, $limit: Int!) {\n  topCollections(\n    cursor: $cursor\n    sort: $sort\n    filter: $filter\n    category: $category\n    limit: $limit\n  ) {\n    items {\n      id\n      slug\n      __typename\n      ...StatsVolume\n      ...StatsTableRow\n      ...CollectionStatsSubscription\n      ...CollectionNativeCurrencyIdentifier\n    }\n    nextPageCursor\n    __typename\n  }\n}\nfragment StatsVolume on Collection {\n  stats {\n    volume {\n      native {\n        unit\n        __typename\n      }\n      ...Volume\n      __typename\n    }\n    oneMinute {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fifteenMinute {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fiveMinute {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneDay {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneHour {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    sevenDays {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    thirtyDays {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment Volume on Volume {\n  usd\n  native {\n    symbol\n    unit\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRow on Collection {\n  id\n  slug\n  ...StatsTableRowFloorPrice\n  ...StatsTableRowTopOffer\n  ...StatsTableRowFloorChange\n  ...StatsTableRowOwners\n  ...StatsTableRowSales\n  ...StatsTableRowSupply\n  ...StatsTableRowVolume\n  ...StatsTableRowCollection\n  ...isRecentlyMinted\n  ...CollectionLink\n  ...CollectionPreviewTooltip\n  ...CollectionWatchListButton\n  ...StatsTableRowSparkLineChart\n  ...StatsTableRowFloorPriceMobile\n  __typename\n}\nfragment isRecentlyMinted on Collection {\n  createdAt\n  __typename\n}\nfragment CollectionLink on CollectionIdentifier {\n  slug\n  ... on Collection {\n    ...getDropStatus\n    __typename\n  }\n  __typename\n}\nfragment getDropStatus on Collection {\n  drop {\n    __typename\n    ... on Erc721SeaDropV1 {\n      maxSupply\n      totalSupply\n      __typename\n    }\n    ... on Erc1155SeaDropV2 {\n      tokenSupply {\n        totalSupply\n        maxSupply\n        __typename\n      }\n      __typename\n    }\n    stages {\n      startTime\n      endTime\n      __typename\n    }\n  }\n  __typename\n}\nfragment StatsTableRowFloorPrice on Collection {\n  floorPrice {\n    pricePerItem {\n      token {\n        unit\n        __typename\n      }\n      ...TokenPrice\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment TokenPrice on Price {\n  usd\n  token {\n    unit\n    symbol\n    contractAddress\n    chain {\n      identifier\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowTopOffer on Collection {\n  topOffer {\n    pricePerItem {\n      token {\n        unit\n        __typename\n      }\n      ...TokenPrice\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowFloorChange on Collection {\n  stats {\n    oneMinute {\n      floorPriceChange\n      __typename\n    }\n    fiveMinute {\n      floorPriceChange\n      __typename\n    }\n    fifteenMinute {\n      floorPriceChange\n      __typename\n    }\n    oneDay {\n      floorPriceChange\n      __typename\n    }\n    oneHour {\n      floorPriceChange\n      __typename\n    }\n    sevenDays {\n      floorPriceChange\n      __typename\n    }\n    thirtyDays {\n      floorPriceChange\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowOwners on Collection {\n  stats {\n    ownerCount\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowSales on Collection {\n  stats {\n    sales\n    oneMinute {\n      sales\n      __typename\n    }\n    fiveMinute {\n      sales\n      __typename\n    }\n    fifteenMinute {\n      sales\n      __typename\n    }\n    oneDay {\n      sales\n      __typename\n    }\n    oneHour {\n      sales\n      __typename\n    }\n    sevenDays {\n      sales\n      __typename\n    }\n    thirtyDays {\n      sales\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowSupply on Collection {\n  stats {\n    totalSupply\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowVolume on Collection {\n  ...StatsVolume\n  __typename\n}\nfragment StatsTableRowCollection on Collection {\n  name\n  isVerified\n  ...CollectionImage\n  ...NewCollectionChip\n  ...CollectionPreviewTooltip\n  ...isRecentlyMinted\n  __typename\n}\nfragment CollectionPreviewTooltip on CollectionIdentifier {\n  ...CollectionPreviewTooltipContent\n  __typename\n}\nfragment CollectionPreviewTooltipContent on CollectionIdentifier {\n  slug\n  __typename\n}\nfragment CollectionImage on Collection {\n  name\n  imageUrl\n  chain {\n    ...ChainBadge\n    __typename\n  }\n  __typename\n}\nfragment ChainBadge on Chain {\n  identifier\n  name\n  __typename\n}\nfragment NewCollectionChip on Collection {\n  createdAt\n  ...isRecentlyMinted\n  __typename\n}\nfragment CollectionWatchListButton on Collection {\n  slug\n  name\n  __typename\n}\nfragment StatsTableRowSparkLineChart on Collection {\n  ...FloorPriceSparkLineChart\n  __typename\n}\nfragment FloorPriceSparkLineChart on Collection {\n  analytics {\n    sparkLineSevenDay {\n      price {\n        token {\n          unit\n          symbol\n          __typename\n        }\n        __typename\n      }\n      time\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowFloorPriceMobile on Collection {\n  ...StatsTableRowFloorPrice\n  ...StatsTableRowFloorChange\n  __typename\n}\nfragment CollectionStatsSubscription on Collection {\n  id\n  slug\n  __typename\n  floorPrice {\n    pricePerItem {\n      usd\n      ...TokenPrice\n      ...NativePrice\n      __typename\n    }\n    __typename\n  }\n  topOffer {\n    pricePerItem {\n      usd\n      ...TokenPrice\n      ...NativePrice\n      __typename\n    }\n    __typename\n  }\n  stats {\n    ownerCount\n    totalSupply\n    uniqueItemCount\n    listedItemCount\n    volume {\n      usd\n      ...Volume\n      __typename\n    }\n    sales\n    oneMinute {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fiveMinute {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fifteenMinute {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneHour {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneDay {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    sevenDays {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    thirtyDays {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\nfragment NativePrice on Price {\n  ...UsdPrice\n  token {\n    unit\n    contractAddress\n    ...currencyIdentifier\n    __typename\n  }\n  native {\n    symbol\n    unit\n    contractAddress\n    ...currencyIdentifier\n    __typename\n  }\n  __typename\n}\nfragment UsdPrice on Price {\n  usd\n  token {\n    contractAddress\n    unit\n    ...currencyIdentifier\n    __typename\n  }\n  __typename\n}\nfragment currencyIdentifier on ContractIdentifier {\n  contractAddress\n  chain {\n    identifier\n    __typename\n  }\n  __typename\n}\nfragment CollectionNativeCurrencyIdentifier on Collection {\n  chain {\n    identifier\n    nativeCurrency {\n      address\n      __typename\n    }\n    __typename\n  }\n  __typename\n}","variables": variables}).json()

                # Формируем данные коллекций
                for item in response["data"]["topCollections"]["items"]:
                    temp_slugs_data[item['slug']] = item

                next_page = response["data"]["topCollections"]["nextPageCursor"]

                # logger.debug(f"{next_page} {len(temp_slugs_data)} {(time.time() - spended)*1000:.2f} ms")
                # spended = time.time()
                if not next_page: return temp_slugs_data
            except Exception as e:
                logger.error(f"Error fetching collections: {e}")
                next_page = None
    
        

def get_usd_price(data, key):
    """Получает цену в USD проверяя на ошибки"""
    return value["pricePerItem"]["usd"] if (value := data.get(key)) else None

def get_native_price(data, key):
    """Получает цену в нативной валюте проверяя на ошибки"""
    return {'price': native['unit'], 'currency': native['symbol']} if (value := data.get(key)) and (native := value["pricePerItem"]["native"]) and native.get("unit") and native.get("symbol") else None

def dict_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict): dict_update(d[k], v)
        else: d[k] = v
    return d

async def manage_connections(ws: aiohttp.ClientWebSocketResponse):
    # Подписываемся на все коллекции частями
    try:
        subs = set()
        while not ws.closed:
            
            slugs = await queue.get()
            if not slugs:
                logger.warning("No slugs found.")
                continue

            to_sub = [slug for slug in slugs if slug not in subs]
            
            if not to_sub: logger.debug("No new slugs to subscribe."); continue
            
            subs.update(to_sub)
            batch_size = 200
            try:
                async with aiofiles.open("collections.json", "w") as f:
                    await f.write(json.dumps(list(subs), separators=(',', ':')))
            except Exception:
                pass
            await asyncio.gather(*[ws.send_json({"id": str(uuid.uuid4()), "type": "subscribe", "payload": {"query": "subscription useCollectionStatsSubscription($slugs: [String!]!) {\n collectionsBySlugs(slugs: $slugs) {\n __typename\n ... on DelistedCollection {\n id\n __typename\n }\n ... on BlacklistedCollection {\n id\n __typename\n }\n ... on Collection {\n id\n slug\n ...CollectionStatsSubscription\n __typename\n }\n }\n}\nfragment CollectionStatsSubscription on Collection {\n id\n slug\n __typename\n floorPrice {\n pricePerItem {\n usd\n ...TokenPrice\n ...NativePrice\n __typename\n }\n __typename\n }\n topOffer {\n pricePerItem {\n usd\n ...TokenPrice\n ...NativePrice\n __typename\n }\n __typename\n }\n stats {\n ownerCount\n totalSupply\n uniqueItemCount\n listedItemCount\n volume {\n usd\n ...Volume\n __typename\n }\n sales\n oneMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n fiveMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n fifteenMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n oneHour {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n oneDay {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n sevenDays {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n thirtyDays {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n __typename\n }\n}\nfragment Volume on Volume {\n usd\n native {\n symbol\n unit\n __typename\n }\n __typename\n}\nfragment NativePrice on Price {\n ...UsdPrice\n token {\n unit\n contractAddress\n ...currencyIdentifier\n __typename\n }\n native {\n symbol\n unit\n contractAddress\n ...currencyIdentifier\n __typename\n }\n __typename\n}\nfragment UsdPrice on Price {\n usd\n token {\n contractAddress\n unit\n ...currencyIdentifier\n __typename\n }\n __typename\n}\nfragment currencyIdentifier on ContractIdentifier {\n contractAddress\n chain {\n identifier\n __typename\n }\n __typename\n}\nfragment TokenPrice on Price {\n usd\n token {\n unit\n symbol\n contractAddress\n chain {\n identifier\n __typename\n }\n __typename\n }\n __typename\n}","operationName": "useCollectionStatsSubscription", "variables": {"slugs": to_sub[i:i+batch_size]}}}) for i in range(0, len(to_sub), batch_size) if to_sub[i:i+batch_size]])
            logger.info(f"Subscribed to {len(to_sub)} collections.")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Connection manager cancelled.")

async def run_ws():
    """Подключается к WebSocket OpenSea и отслеживает изменения в коллекциях"""
    # Получаем данные всех коллекций # TODO: распараллелить
    asyncio.create_task(wrapper_get_all_collections())
    while True:
        
        async with aiohttp.ClientSession() as session:
            # try:
                # Подключаемся к WebSocket
                async with session.ws_connect(f"wss://os2-wss.prod.privatesea.io/subscriptions", heartbeat=29) as ws:
                    await ws.send_json({"type": "connection_init"})

                    # Подписываемся на коллекции
                    collection_manager = asyncio.create_task(manage_connections(ws))
                    while not queue._getters:
                        await asyncio.sleep(0.1)
                    try:
                        async with aiofiles.open("collections.json", "r") as f:
                            await queue.put(json.loads(await f.read()))
                    except:
                        await queue.put(list(slugs_data.keys()))

                    # Слушаем сообщения
                    async for msg in ws:
                        msg_data = msg.json()
                        
                        if msg_data.get("type") == "connection_ack": logger.info("WebSocket connection established."); continue
                        
                        if msg_data.get("payload"):
                            
                            collection = msg_data["payload"]["data"]["collectionsBySlugs"]
                            if collection and (slug := collection.get("slug")):
                                if slug not in slugs_data: slugs_data[slug] = collection
                                # Получаем цены
                                floorPrice     = get_usd_price(collection, "floorPrice")
                                topOffer       = get_usd_price(collection, "topOffer")
                                old_floorPrice = get_usd_price(slugs_data[slug], "floorPrice")
                                old_topOffer   = get_usd_price(slugs_data[slug], "topOffer")
                                # Запись в кэш если отличаются от старых значений
                                if slug in slugs_data \
                                    and old_floorPrice == floorPrice \
                                    and old_topOffer == topOffer:
                                        continue
                                dict_update(slugs_data[slug], collection)

                                # logger.debug(f"{id} \n\n Slug: {slug}\n Floor Price: {floorPrice} USD, Top Offer: {topOffer} USD\n{'-'*70}")

                                # Проверка условий для уведомления
                                asyncio.create_task(send_notifications(slugs_data[slug]))
                        
                        else:
                            logger.warning(f"Received unexpected message: {msg.data}")
                    else:
                        collection_manager.cancel()
                        await collection_manager
                        logger.info(f"WebSocket connection closed. {msg.type}")

            # except Exception as e:
            #     logger.error(f"Error in WebSocket connection: {e}")
            #     await asyncio.sleep(1)

async def main():

        """
        slugs = ["3d-tiny-dinos-v2","abstractio","acclimatedmooncats","all-that-remains-4","alterego-k3p6r7q2","angels-r-shohei-ohtani-inception-base-black-45-leg","anticyclone-by-william-mapan","archetype-by-kjetil-golid","async-blueprints","avastar","axie-consumable-item","axie-land","axie-material","axie-ronin","azragames-thehopeful","azuki","azuki-mizuki-anime-shorts","azukielementals","bad-bunnz","bankr-club","based-egg","based-koalas-1","bastard-gan-punks-v2","beanzofficial","bearish-abstract","beeple-spring-collection","blhz-medel","bobocouncil","bored-ape-kennel-club","boredapeyachtclub","by-snowfro","cambriafounders","capsule-shop","chainfaces","chimpersnft","chonks","chromie-squiggle-by-snowfro","chronoforge","chronoforge-support-airships","chronoforge-totem-abstract","clonex","contortions-bytristan","cool-cats-nft","crafted-avatars","creatures","cryptid-art","cryptoadz-by-gremplin","cryptoarte","cryptodickbutts-s3","cryptoninjapartners-v2","cryptopunks","cryptoskulls","curiocardswrapper","damage-control-xcopy","dataland-biomelumina","deadfellaz","degods-eth","di-animals","doodles-official","dream-tickets-1","dreamiliomaker-abstract","dropzone-mcade","dungeonhero-1","dxterminal","ecumenopolis-by-joshua-bagley","edifice-by-ben-kovach","ens","fableborne-primordials-20","factura-by-mathias-isaksen","farworld-creatures","fauvtoshi","finalbosu","finiliar","fontana-by-harvey-rayner-patterndotco","freek-by-0xsh","friendship-bracelets-by-alexis-andre","fugzfamily","gamblerzgg","gemesis","genesis-by-claire-silver","genesis-creepz","genesishero-abstract","gigaverse-roms-abstract","glhfers","glitch-skulls-1","good-vibes-club","grifters-by-xcopy","grill-by-1-crush-264348104","grills-by-num1crush","gumbo-by-mathias-isaksen","habbo-avatars","hashmasks","hv-mtl","hypio","icxn-by-xcopy","infinex-patrons","io-imaginary-ones","jirasan","jrnyers","kaito-genesis","l3e7-guardians","l3e7-worlds","lamborghini-fast-forworld-revuelto","larvva-lads","lasercat-nft","layer3-cube-polygon","life-in-west-america-by-roope-rainisto","lilpudgys","max-pain-and-frens-by-xcopy","meebits","memelandcaptainz","memelandpotatoz","memories-of-qilin-by-emily-xie","merge-vv","meridian-by-matt-deslauriers","metawinners-1","mfers","mibera333","milady","mind-the-gap-by-mountvitruvius","mocaverse","moki-collection","monster-capsules","moonbirds","moonbirds-mythics","moonbirds-oddities","moriusa-stpr","murakami-flowers-2022-official","mutant-ape-yacht-club","mypethooligan","nakamigos","neotokyo-citizens","ninja-squad-official","och-gacha-weapon","och-genesis-ring","off-the-grid","official-gamegpt-nft","official-v1-punks","okcomputers","omnia-pets-genesis","on-chain-all-stars","on-chain-miniz","one-gravity-7","opepen-edition","osf-rld","otherdeed","otherdeed-expanded","otherside-koda","paladins-alpha","parallel-avatars","pebbles-by-zeblocks","pengztracted-abstract","piratenation","pixelmongen1","pnuks-1","primera-by-mitchell-and-yun","project-aeon","proscenium-by-remnynt","pudgypenguins","pudgyrods","qql-mint-pass","rare-pepe-curated","rektguy","remilio-babies","rolg-nft","sappy-seals","seven-gods","singularity-by-hideki-tsukamoto","space-doodles-official","sproto-gremlins","sugartown-cores","sugartown-oras","superrare","supremon","tcg-world-dragons","terraforms","thecatmoon","thecurrency","thememes6529","thesadtimesbirthcertificate","trademark-by-jack-butcher","trailheads","treehouse-squirrel-council","treeverse-plots","trichro-matic-by-mountvitruvius","trump-digital-trading-cards-america-first-edition","unioverse-game-content","unioverse-heroes-2","urban-punk-official","valhalla","veefriends","veefriends-series-2","vv-checks","vv-checks-originals","winds-of-yawanawa","wonky-stonks","world-of-women-nft","wrapped-cryptopunks","xcopy-editions","yumemono"]

        batch_size = 200
        for i in range(0, len(slugs), batch_size):
            
            batch = slugs[i:i+batch_size]
            asyncio.create_task(run_ws(i+batch_size, batch))
            await asyncio.sleep(3)
        """
        asyncio.create_task(tg.start_bot())
        await run_ws()

try:
    asyncio.run(main())
except KeyboardInterrupt:
        logger.warning("Stopped.")
# asyncio.run(check_all_collection_stats())