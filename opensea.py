import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s:%(levelname)s: %(message)s")
logging.getLogger('aiogram').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

import asyncio, aiohttp, os, json, uuid, heapq, time
import telegram_bot as tg
import cloudscraper

from dotenv import load_dotenv; load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")

slugs_data = {}

last_notifications = {}
last_diffs = {}

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
        colls = [coll for coll in slugs_data.values() if coll.get("stats") is not None]
        top_N_by_1d_volume = heapq.nlargest(
            cfg.top_N_by_1d_volume,
            colls,
            key=lambda coll: coll["stats"]["volume"]["usd"]
        )
        if cfg.top_N_by_1d_volume \
            and not any(d['name'] == collection['slug'] for d in top_N_by_1d_volume):
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
            now = int(time.time())
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
                await tg.bot.send_message(user_id, \
                    
                    f"Collection - {collection['slug']}\n"
                    f"Price - {usd_price:.2f}$\n"
                    f"List - {topOffer['price']} {topOffer['currency']}\n"
                    f"Floor - {floorPrice['price']} {floorPrice['currency']}\n"
                    f"Diff - <b>{conditions['diff_percent_offer_to_floor']:.2f}%</b>\n"
                    f"opensea.io/collection/{collection['slug']}"

                , parse_mode='HTML', disable_web_page_preview=True)
                
                if cfg.notification_cooldown: 
                    last_notifications[collection['slug']][user_id] = now
                
                if cfg.percent_step: 
                    last_diffs.setdefault(collection['slug'], {})[user_id] = conditions['diff_percent_offer_to_floor']
            
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
        asyncio.create_task(send_notifications(collection))

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

async def run_ws():
    """Подключается к WebSocket OpenSea и отслеживает изменения в коллекциях"""
    # Получаем данные всех коллекций # TODO: распараллелить
    await get_all_collections()
    while True:
        # Queqe get
        slugs = list(slugs_data.keys())
        if not slugs:
            logger.warning("No slugs found.")
            continue

        async with aiohttp.ClientSession() as session:
            # try:
                # Подключаемся к WebSocket
                async with session.ws_connect(f"wss://os2-wss.prod.privatesea.io/subscriptions", heartbeat=29) as ws:
                    await ws.send_json({"type": "connection_init"})
                    
                    # Подписываемся на все коллекции частями
                    batch_size = 200
                    for i in range(0, len(slugs), batch_size):

                        batch = slugs[i:i+batch_size]
                        if not batch:
                            continue

                        await ws.send_json({"id": str(uuid.uuid4()), "type": "subscribe", "payload": {"query": "subscription useCollectionStatsSubscription($slugs: [String!]!) {\n collectionsBySlugs(slugs: $slugs) {\n __typename\n ... on DelistedCollection {\n id\n __typename\n }\n ... on BlacklistedCollection {\n id\n __typename\n }\n ... on Collection {\n id\n slug\n ...CollectionStatsSubscription\n __typename\n }\n }\n}\nfragment CollectionStatsSubscription on Collection {\n id\n slug\n __typename\n floorPrice {\n pricePerItem {\n usd\n ...TokenPrice\n ...NativePrice\n __typename\n }\n __typename\n }\n topOffer {\n pricePerItem {\n usd\n ...TokenPrice\n ...NativePrice\n __typename\n }\n __typename\n }\n stats {\n ownerCount\n totalSupply\n uniqueItemCount\n listedItemCount\n volume {\n usd\n ...Volume\n __typename\n }\n sales\n oneMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n fiveMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n fifteenMinute {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n oneHour {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n oneDay {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n sevenDays {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n thirtyDays {\n floorPriceChange\n sales\n volume {\n usd\n ...Volume\n __typename\n }\n __typename\n }\n __typename\n }\n}\nfragment Volume on Volume {\n usd\n native {\n symbol\n unit\n __typename\n }\n __typename\n}\nfragment NativePrice on Price {\n ...UsdPrice\n token {\n unit\n contractAddress\n ...currencyIdentifier\n __typename\n }\n native {\n symbol\n unit\n contractAddress\n ...currencyIdentifier\n __typename\n }\n __typename\n}\nfragment UsdPrice on Price {\n usd\n token {\n contractAddress\n unit\n ...currencyIdentifier\n __typename\n }\n __typename\n}\nfragment currencyIdentifier on ContractIdentifier {\n contractAddress\n chain {\n identifier\n __typename\n }\n __typename\n}\nfragment TokenPrice on Price {\n usd\n token {\n unit\n symbol\n contractAddress\n chain {\n identifier\n __typename\n }\n __typename\n }\n __typename\n}","operationName": "useCollectionStatsSubscription", "variables": {"slugs": batch}}})
                        await asyncio.sleep(1)
                    
                    # Слушаем сообщения
                    async for msg in ws:
                        msg_data = msg.json()
                        
                        if msg_data.get("type") == "connection_ack": logger.info("WebSocket connection established."); continue
                        
                        if msg_data.get("payload"):
                            
                            collection = msg_data["payload"]["data"]["collectionsBySlugs"]
                            if collection and (slug := collection.get("slug")):

                                # Получаем цены
                                floorPrice     = get_usd_price(collection, "floorPrice")
                                topOffer       = get_usd_price(collection, "topOffer")
                                old_floorPrice = get_usd_price(slugs_data[slug], "floorPrice")
                                old_topOffer   = get_usd_price(slugs_data[slug], "topOffer")
                                # Запись в кэш
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
        await asyncio.gather(tg.start_bot(TG_BOT_TOKEN), run_ws())

try:
    asyncio.run(main())
except KeyboardInterrupt:
        logger.warning("Stopped.")
# asyncio.run(check_all_collection_stats())