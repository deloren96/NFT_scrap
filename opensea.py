import logging

logging.basicConfig(level=logging.WARNING, format="%(asctime)s:%(levelname)s: %(message)s")
logging.getLogger('aiogram').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

import asyncio, aiohttp, os, json, uuid, heapq
import telegram_bot as tg
import cloudscraper



from dotenv import load_dotenv; load_dotenv()

OPENSEA_API_KEY = os.getenv("OPENSEA_API_KEY")
TG_BOT_TOKEN    = os.getenv("TG_BOT_TOKEN")

slugs_data = {}

async def get_all_collections_helix():
    async with aiohttp.ClientSession() as session:
        all_collections = []

        url = "https://api.opensea.io/api/v2/collections?include_hidden=true&limit=100"
        headers = {"X-API-KEY": OPENSEA_API_KEY, "accept": "application/json"}
        
        collections = await (await session.get(url, headers=headers)).json()
        all_collections += [slug['collection'] for slug in collections.get("collections", [])]

        logger.debug(f"{len(all_collections)} {collections.get('next')}")

        while collections.get("next"):
            collections = await (await session.get(f"{url}&next={collections.get('next')}", headers=headers)).json()
            all_collections += [slug['collection'] for slug in collections.get("collections", [])]
            
            logger.debug(f"{len(all_collections)} {collections.get('next')}")

        logger.info(f"Total collections: {len(all_collections)}")

        with open("collections.json", "w") as f:
            json.dump(all_collections, f, indent=2)

async def get_collection_listings(slug):
    async with aiohttp.ClientSession() as session:
        all_offers = []
        
        url = f"https://api.opensea.io/api/v2/listings/collection/{slug}/all?limit=100"

        offers = await (await session.get(url, headers={"X-API-KEY": OPENSEA_API_KEY, "accept": "application/json"})).json()
        all_offers += offers.get("listings", [])
        
        if offers.get("next") and len(all_offers)>0: logger.debug(f"{len(all_offers)} {offers.get('next')}")
        
        while offers.get("next"):
            offers = await (await session.get(f"{url}&next={offers.get('next')}", headers={"X-API-KEY": OPENSEA_API_KEY, "accept": "application/json"})).json()
            all_offers += offers.get("listings", [])
            
            if offers.get("next") and len(all_offers)>0: logger.debug(f"{len(all_offers)} {offers.get('next')}")
        
        if len(all_offers)>0:
            logger.info(f"Total offers for {slug}: {len(all_offers)}")
            
            # with open(f"offers_{slug}.json", "w") as f:
            #     json.dump(offers, f, indent=2)

def custom_condition(collection, user_id):
    # Условие
    # Конфиги
    config = tg.config.get(user_id, {})
    filter_rules = config['filter_slugs_rules']
    alert_rules = config['alert_rules']
    if not config: return False
    ## Фильтры
    # Черный список
    if collection["slug"] in config.get("blacklist", []): return False
    # Топ N по 1d объему
    if filter_rules['top_N_by_1d_volume'] < float('inf'):
        colls = [coll for coll in slugs_data.values() if coll.get("stats") is not None]
        top_N_by_1d_volume = heapq.nlargest(
            filter_rules['top_N_by_1d_volume'],
            colls,
            key=lambda coll: coll["stats"]["volume"]["usd"]
        )
        if filter_rules['top_N_by_1d_volume'] \
            and not any(d['name'] == collection['slug'] for d in top_N_by_1d_volume):
                return False
    # Диапазон по 1d объему
    if not (filter_rules['min_USD_1d_volume'] <= collection["stats"]["volume"]["usd"] <= filter_rules['max_USD_1d_volume']):
        return False
    # Диапазон по цене топ оффера
    if not (filter_rules['min_USD_top_offer'] <= (get_usd_price(collection, "topOffer") or 0) <= filter_rules['max_USD_top_offer']):
        return False
    
    ## Alerts
    topOffer = get_usd_price(collection, "topOffer")
    floorPrice = get_usd_price(collection, "floorPrice")
    if not (topOffer and floorPrice): return False
    
    if all([
        # Разница между ценой топ оффера и ценой листинга
        (floorPrice - topOffer) / floorPrice * 100 > alert_rules['diff_percent_offer_to_floor']
        ]):
        return True

    return False

async def send_notifications(collection):
    for user_id in tg.config:
        if custom_condition(collection, user_id):
            try: await tg.bot.send_message(user_id, f"Notification")
            except Exception as e: logger.error(f"Error sending message to {user_id}: {e}")

def filter_collections():
    
    with open("collections_3.json", "r") as f:
        collections = json.load(f)
    
    filtered = [c for c in collections if "0x" not in c]
    
    logger.debug(f"Filtered collections: {len(filtered)}")
    return filtered

async def get_all_collections() -> dict:
    """Собирает данные всех коллекций с OpenSea"""
    global slugs_data
    slugs_data = {}
    next_page = None
    variables = {
            "filter":{
                "floorPriceRange"   : {"min": 0.001}, 
                "hasMerchandising"  : False, 
                "topOfferPriceRange": {"min": 0.001}
                },
            "limit":100,
            "sort":{
                "by":"ONE_DAY_VOLUME",
                "direction":"DESC"
                }
            }
    with cloudscraper.create_scraper() as scraper:
        while True:
            await asyncio.sleep(0.1)
            # Делаем запрос пока не дойдем до конца страниц
            if next_page: variables["cursor"] = next_page

            response = scraper.post('https://gql.opensea.io/graphql', json={"operationName":"TopStatsTableQuery","query":"query TopStatsTableQuery($cursor: String, $sort: TopCollectionsSort!, $filter: TopCollectionsFilter, $category: CategoryIdentifier, $limit: Int!) {\n  topCollections(\n    cursor: $cursor\n    sort: $sort\n    filter: $filter\n    category: $category\n    limit: $limit\n  ) {\n    items {\n      id\n      slug\n      __typename\n      ...StatsVolume\n      ...StatsTableRow\n      ...CollectionStatsSubscription\n      ...CollectionNativeCurrencyIdentifier\n    }\n    nextPageCursor\n    __typename\n  }\n}\nfragment StatsVolume on Collection {\n  stats {\n    volume {\n      native {\n        unit\n        __typename\n      }\n      ...Volume\n      __typename\n    }\n    oneMinute {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fifteenMinute {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fiveMinute {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneDay {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneHour {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    sevenDays {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    thirtyDays {\n      volume {\n        native {\n          unit\n          __typename\n        }\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment Volume on Volume {\n  usd\n  native {\n    symbol\n    unit\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRow on Collection {\n  id\n  slug\n  ...StatsTableRowFloorPrice\n  ...StatsTableRowTopOffer\n  ...StatsTableRowFloorChange\n  ...StatsTableRowOwners\n  ...StatsTableRowSales\n  ...StatsTableRowSupply\n  ...StatsTableRowVolume\n  ...StatsTableRowCollection\n  ...isRecentlyMinted\n  ...CollectionLink\n  ...CollectionPreviewTooltip\n  ...CollectionWatchListButton\n  ...StatsTableRowSparkLineChart\n  ...StatsTableRowFloorPriceMobile\n  __typename\n}\nfragment isRecentlyMinted on Collection {\n  createdAt\n  __typename\n}\nfragment CollectionLink on CollectionIdentifier {\n  slug\n  ... on Collection {\n    ...getDropStatus\n    __typename\n  }\n  __typename\n}\nfragment getDropStatus on Collection {\n  drop {\n    __typename\n    ... on Erc721SeaDropV1 {\n      maxSupply\n      totalSupply\n      __typename\n    }\n    ... on Erc1155SeaDropV2 {\n      tokenSupply {\n        totalSupply\n        maxSupply\n        __typename\n      }\n      __typename\n    }\n    stages {\n      startTime\n      endTime\n      __typename\n    }\n  }\n  __typename\n}\nfragment StatsTableRowFloorPrice on Collection {\n  floorPrice {\n    pricePerItem {\n      token {\n        unit\n        __typename\n      }\n      ...TokenPrice\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment TokenPrice on Price {\n  usd\n  token {\n    unit\n    symbol\n    contractAddress\n    chain {\n      identifier\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowTopOffer on Collection {\n  topOffer {\n    pricePerItem {\n      token {\n        unit\n        __typename\n      }\n      ...TokenPrice\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowFloorChange on Collection {\n  stats {\n    oneMinute {\n      floorPriceChange\n      __typename\n    }\n    fiveMinute {\n      floorPriceChange\n      __typename\n    }\n    fifteenMinute {\n      floorPriceChange\n      __typename\n    }\n    oneDay {\n      floorPriceChange\n      __typename\n    }\n    oneHour {\n      floorPriceChange\n      __typename\n    }\n    sevenDays {\n      floorPriceChange\n      __typename\n    }\n    thirtyDays {\n      floorPriceChange\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowOwners on Collection {\n  stats {\n    ownerCount\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowSales on Collection {\n  stats {\n    sales\n    oneMinute {\n      sales\n      __typename\n    }\n    fiveMinute {\n      sales\n      __typename\n    }\n    fifteenMinute {\n      sales\n      __typename\n    }\n    oneDay {\n      sales\n      __typename\n    }\n    oneHour {\n      sales\n      __typename\n    }\n    sevenDays {\n      sales\n      __typename\n    }\n    thirtyDays {\n      sales\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowSupply on Collection {\n  stats {\n    totalSupply\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowVolume on Collection {\n  ...StatsVolume\n  __typename\n}\nfragment StatsTableRowCollection on Collection {\n  name\n  isVerified\n  ...CollectionImage\n  ...NewCollectionChip\n  ...CollectionPreviewTooltip\n  ...isRecentlyMinted\n  __typename\n}\nfragment CollectionPreviewTooltip on CollectionIdentifier {\n  ...CollectionPreviewTooltipContent\n  __typename\n}\nfragment CollectionPreviewTooltipContent on CollectionIdentifier {\n  slug\n  __typename\n}\nfragment CollectionImage on Collection {\n  name\n  imageUrl\n  chain {\n    ...ChainBadge\n    __typename\n  }\n  __typename\n}\nfragment ChainBadge on Chain {\n  identifier\n  name\n  __typename\n}\nfragment NewCollectionChip on Collection {\n  createdAt\n  ...isRecentlyMinted\n  __typename\n}\nfragment CollectionWatchListButton on Collection {\n  slug\n  name\n  __typename\n}\nfragment StatsTableRowSparkLineChart on Collection {\n  ...FloorPriceSparkLineChart\n  __typename\n}\nfragment FloorPriceSparkLineChart on Collection {\n  analytics {\n    sparkLineSevenDay {\n      price {\n        token {\n          unit\n          symbol\n          __typename\n        }\n        __typename\n      }\n      time\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\nfragment StatsTableRowFloorPriceMobile on Collection {\n  ...StatsTableRowFloorPrice\n  ...StatsTableRowFloorChange\n  __typename\n}\nfragment CollectionStatsSubscription on Collection {\n  id\n  slug\n  __typename\n  floorPrice {\n    pricePerItem {\n      usd\n      ...TokenPrice\n      ...NativePrice\n      __typename\n    }\n    __typename\n  }\n  topOffer {\n    pricePerItem {\n      usd\n      ...TokenPrice\n      ...NativePrice\n      __typename\n    }\n    __typename\n  }\n  stats {\n    ownerCount\n    totalSupply\n    uniqueItemCount\n    listedItemCount\n    volume {\n      usd\n      ...Volume\n      __typename\n    }\n    sales\n    oneMinute {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fiveMinute {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    fifteenMinute {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneHour {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    oneDay {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    sevenDays {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    thirtyDays {\n      floorPriceChange\n      sales\n      volume {\n        usd\n        ...Volume\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\nfragment NativePrice on Price {\n  ...UsdPrice\n  token {\n    unit\n    contractAddress\n    ...currencyIdentifier\n    __typename\n  }\n  native {\n    symbol\n    unit\n    contractAddress\n    ...currencyIdentifier\n    __typename\n  }\n  __typename\n}\nfragment UsdPrice on Price {\n  usd\n  token {\n    contractAddress\n    unit\n    ...currencyIdentifier\n    __typename\n  }\n  __typename\n}\nfragment currencyIdentifier on ContractIdentifier {\n  contractAddress\n  chain {\n    identifier\n    __typename\n  }\n  __typename\n}\nfragment CollectionNativeCurrencyIdentifier on Collection {\n  chain {\n    identifier\n    nativeCurrency {\n      address\n      __typename\n    }\n    __typename\n  }\n  __typename\n}","variables": variables}).json()

            # Формируем данные коллекций
            for item in response["data"]["topCollections"]["items"]:
                slugs_data[item['slug']] = item

            next_page = response["data"]["topCollections"]["nextPageCursor"]

            logger.debug(f"{next_page} {len(slugs_data)}")
            if not next_page: break
    for collection in slugs_data.values():
        await send_notifications(collection)


async def get_price(currency, session):
    currencies = {"WETH": '2369',
                  "ETH": '1027'}
    return (await (await session.get(f"https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail/lite?id={currencies[currency]}")).json())["data"]["statistics"]["price"]

def get_usd_price(data, key):
    value = data.get(key)
    if value:
        return value["pricePerItem"]["usd"]
    return None

def dict_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            dict_update(d[k], v)
        else:
            d[k] = v
    return d

async def check_all_collection_stats(session, slugs=None):
    if slugs is None:
        slugs = filter_collections()

    async def get_offers(slug):
        res = {"errors": ["Rate limit exceeded"]}
        delay = 0.1
        while "errors" in res and res["errors"][0] == "Rate limit exceeded":
            res = await(await session.get(f"https://api.opensea.io/api/v2/offers/collection/{slug}", headers={"X-API-KEY": OPENSEA_API_KEY, "accept": "application/json"})).json()
            if "errors" in res: 
                logger.debug(f"{slug} {res['errors']}") 
                await asyncio.sleep(delay) 
                delay *= 2

        for offers in res.get("offers", []):
            if isinstance(offers, dict) and offers:
                topOffer = int(offers["price"]["value"]) / 1000000000000000000
                logger.debug(f"Top offer: {topOffer} {offers['price']['currency']}")
                return {"slug": slug, "topOffer": topOffer}
        else:
            logger.debug(f"No offers found for {slug}")
    
    offers = []
    for slug in slugs:
        res = await get_offers(slug)
        if res:
            offers.append(res)
    logger.info(f"Total offers: {len(offers)}")

async def run_ws():
    id = 1 #int(id / 200)
    while True:
        # Получаем данные всех коллекций
        await get_all_collections()
        async with aiohttp.ClientSession() as session:
            # try:
                # Подключаемся к WebSocket                
                async with session.ws_connect(f"wss://os2-wss.prod.privatesea.io/subscriptions", heartbeat=29) as ws:
                    await ws.send_json({"type": "connection_init"})
                    
                    # Подписываемся на все коллекции частями
                    slugs = [slug for slug in slugs_data.keys()]
                    if not slugs:
                        logger.warning("No slugs found.")
                        continue

                    batch_size = 200
                    for i in range(0, len(slugs), batch_size):

                        batch = slugs[i:i+batch_size]
                        if not batch:
                            continue

                        await ws.send_json({"id": str(uuid.uuid4()), "type": "subscribe", "payload": {"query": "subscription useCollectionStatsSubscription($slugs: [String!]!) {\n collectionsBySlugs(slugs: $slugs) {\n __typename\n ... on DelistedCollection {\n id\n __typename\n }\n ... on BlacklistedCollection {\n id\n __typename\n }\n ... on Collection {\n id\n slug\n ...CollectionStatsSubscription\n __typename\n }\n }\n}\nfragment CollectionStatsSubscription on Collection {\n id\n slug\n __typename\n floorPrice {\n pricePerItem {\n usd\n ...TokenPrice\n ...NativePrice\n __typename\n }\n __typename\n }\n topOffer {\n pricePerItem {\n usd\n ...TokenPrice\n ...NativePrice\n __typename\n }\n __typename\n }\n stats {\n ownerCount\n totalSupply\n uniqueItemCount\n listedItemCount\n volume {\n usd\n ...Volume\n __typename\n }\n sales\n oneMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n fiveMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n fifteenMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n oneHour {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n oneDay {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n sevenDays {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n thirtyDays {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n __typename\n }\n}\nfragment Volume on Volume {\n usd\n native {\n symbol\n unit\n __typename\n }\n __typename\n}\nfragment NativePrice on Price {\n ...UsdPrice\n token {\n unit\n contractAddress\n ...currencyIdentifier\n __typename\n }\n native {\n symbol\n unit\n contractAddress\n ...currencyIdentifier\n __typename\n }\n __typename\n}\nfragment UsdPrice on Price {\n usd\n token {\n contractAddress\n unit\n ...currencyIdentifier\n __typename\n }\n __typename\n}\nfragment currencyIdentifier on ContractIdentifier {\n contractAddress\n chain {\n identifier\n __typename\n }\n __typename\n}\nfragment TokenPrice on Price {\n usd\n token {\n unit\n symbol\n contractAddress\n chain {\n identifier\n __typename\n }\n __typename\n }\n __typename\n}","operationName": "useCollectionStatsSubscription", "variables": {"slugs": batch}}})
                        await asyncio.sleep(1)
                    
                    # Слушаем сообщения
                    async for msg in ws:
                        data = msg.json()

                        if data.get("payload"):
                            
                            collection = data["payload"]["data"]["collectionsBySlugs"]
                            if collection and (slug := collection.get("slug")):

                                # Получаем цены
                                floorPrice     = get_usd_price(collection, "floorPrice")
                                topOffer       = get_usd_price(collection, "topOffer")
                                old_floorPrice = get_usd_price(slugs_data[slug], "floorPrice")
                                old_topOffer   = get_usd_price(slugs_data[slug], "topOffer")
                                # Запись в кэш
                                if slug in slugs_data:
                                    if  old_floorPrice == floorPrice \
                                    and old_topOffer == topOffer:
                                        continue
                                dict_update(slugs_data[slug], collection)

                                logger.info(f"{id} \n\n Slug: {slug}\n Floor Price: {floorPrice} USD, Top Offer: {topOffer} USD\n{'-'*70}")

                                # Проверка условий для уведомления
                                await send_notifications(slugs_data[slug])
                        else:
                            logger.warning(f"{id} Received message: {msg.data}")
                        
            # except Exception as e:
            #     logger.error(f"Error in WebSocket connection: {e}")
            #     await asyncio.sleep(1)

async def main():
    try:
        
        """
        slugs = ["3d-tiny-dinos-v2","abstractio","acclimatedmooncats","all-that-remains-4","alterego-k3p6r7q2","angels-r-shohei-ohtani-inception-base-black-45-leg","anticyclone-by-william-mapan","archetype-by-kjetil-golid","async-blueprints","avastar","axie-consumable-item","axie-land","axie-material","axie-ronin","azragames-thehopeful","azuki","azuki-mizuki-anime-shorts","azukielementals","bad-bunnz","bankr-club","based-egg","based-koalas-1","bastard-gan-punks-v2","beanzofficial","bearish-abstract","beeple-spring-collection","blhz-medel","bobocouncil","bored-ape-kennel-club","boredapeyachtclub","by-snowfro","cambriafounders","capsule-shop","chainfaces","chimpersnft","chonks","chromie-squiggle-by-snowfro","chronoforge","chronoforge-support-airships","chronoforge-totem-abstract","clonex","contortions-bytristan","cool-cats-nft","crafted-avatars","creatures","cryptid-art","cryptoadz-by-gremplin","cryptoarte","cryptodickbutts-s3","cryptoninjapartners-v2","cryptopunks","cryptoskulls","curiocardswrapper","damage-control-xcopy","dataland-biomelumina","deadfellaz","degods-eth","di-animals","doodles-official","dream-tickets-1","dreamiliomaker-abstract","dropzone-mcade","dungeonhero-1","dxterminal","ecumenopolis-by-joshua-bagley","edifice-by-ben-kovach","ens","fableborne-primordials-20","factura-by-mathias-isaksen","farworld-creatures","fauvtoshi","finalbosu","finiliar","fontana-by-harvey-rayner-patterndotco","freek-by-0xsh","friendship-bracelets-by-alexis-andre","fugzfamily","gamblerzgg","gemesis","genesis-by-claire-silver","genesis-creepz","genesishero-abstract","gigaverse-roms-abstract","glhfers","glitch-skulls-1","good-vibes-club","grifters-by-xcopy","grill-by-1-crush-264348104","grills-by-num1crush","gumbo-by-mathias-isaksen","habbo-avatars","hashmasks","hv-mtl","hypio","icxn-by-xcopy","infinex-patrons","io-imaginary-ones","jirasan","jrnyers","kaito-genesis","l3e7-guardians","l3e7-worlds","lamborghini-fast-forworld-revuelto","larvva-lads","lasercat-nft","layer3-cube-polygon","life-in-west-america-by-roope-rainisto","lilpudgys","max-pain-and-frens-by-xcopy","meebits","memelandcaptainz","memelandpotatoz","memories-of-qilin-by-emily-xie","merge-vv","meridian-by-matt-deslauriers","metawinners-1","mfers","mibera333","milady","mind-the-gap-by-mountvitruvius","mocaverse","moki-collection","monster-capsules","moonbirds","moonbirds-mythics","moonbirds-oddities","moriusa-stpr","murakami-flowers-2022-official","mutant-ape-yacht-club","mypethooligan","nakamigos","neotokyo-citizens","ninja-squad-official","och-gacha-weapon","och-genesis-ring","off-the-grid","official-gamegpt-nft","official-v1-punks","okcomputers","omnia-pets-genesis","on-chain-all-stars","on-chain-miniz","one-gravity-7","opepen-edition","osf-rld","otherdeed","otherdeed-expanded","otherside-koda","paladins-alpha","parallel-avatars","pebbles-by-zeblocks","pengztracted-abstract","piratenation","pixelmongen1","pnuks-1","primera-by-mitchell-and-yun","project-aeon","proscenium-by-remnynt","pudgypenguins","pudgyrods","qql-mint-pass","rare-pepe-curated","rektguy","remilio-babies","rolg-nft","sappy-seals","seven-gods","singularity-by-hideki-tsukamoto","space-doodles-official","sproto-gremlins","sugartown-cores","sugartown-oras","superrare","supremon","tcg-world-dragons","terraforms","thecatmoon","thecurrency","thememes6529","thesadtimesbirthcertificate","trademark-by-jack-butcher","trailheads","treehouse-squirrel-council","treeverse-plots","trichro-matic-by-mountvitruvius","trump-digital-trading-cards-america-first-edition","unioverse-game-content","unioverse-heroes-2","urban-punk-official","valhalla","veefriends","veefriends-series-2","vv-checks","vv-checks-originals","winds-of-yawanawa","wonky-stonks","world-of-women-nft","wrapped-cryptopunks","xcopy-editions","yumemono"]

        batch_size = 200
        for i in range(0, len(slugs), batch_size):
            
            batch = slugs[i:i+batch_size]
            asyncio.create_task(run_ws(i+batch_size, batch))
            await asyncio.sleep(3)
        """
        await asyncio.gather(tg.start_bot(TG_BOT_TOKEN), run_ws())
    except KeyboardInterrupt:
        logger.warning("Stopped.")

asyncio.run(main())
# asyncio.run(check_all_collection_stats())