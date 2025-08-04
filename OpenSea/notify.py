import logging
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s:%(levelname)s:%(funcName)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

import asyncio, heapq
from utils import get_usd_price, get_native_price

class NotifyCreator:
    def __init__(self, slugs_data, full_scanned, configs, notification_managers):
        self.slugs_data = slugs_data
        self.full_scanned = full_scanned
        
        self.configs = configs
        self.notification_managers = notification_managers
        
        self.last_notifications = {}
        self.last_diffs = {}



    def is_blacklisted(self, new_collection, blacklist):
        
        return new_collection["slug"] in blacklist



    def is_top_N_1dVolume(self, new_collection, top_volume):

        if not self.full_scanned[0] or 0 >= top_volume: 
            return False


        old_collections = [old_collection for old_collection in self.slugs_data.values() if old_collection.get("stats") is not None]
        
        top_N = heapq.nlargest(
            top_N,
            old_collections,
            key=lambda collection: collection["stats"]["oneDay"]["volume"]["usd"]
        )

        if top_N \
            and any(collection['slug'] == new_collection['slug'] for collection in top_N):
                return True

        return False



    def is_in_range_1dVolume(self, new_collection, min_volume, max_volume):
        
        return (min_volume <= new_collection["stats"]["volume"]["usd"] <= max_volume)



    def is_in_range_topOffer(self, new_collection, min_price, max_price):
        
        return min_price <= (get_usd_price(new_collection, "topOffer") or 0) <= max_price



    def custom_condition(self, new_collection, user_id):
        """Фильтрация коллекций по настройкам пользователей и проверка условий для отправки уведомлений"""
        # Условие
        
        # Конфиги
        config = self.configs[user_id]
        
        if not config:
            return False


        blacklist = config.blacklist or []

        top_volume = config.top_N_by_1d_volume or float('inf')
        min_volume = config.min_USD_1d_volume or 0
        max_volume = config.max_USD_1d_volume or float('inf')

        min_price = config.min_USD_top_offer or 0
        max_price = config.max_USD_top_offer or float('inf')

        diff = config.diff_percent_offer_to_floor or 0


        ## Фильтры

        if self.is_blacklisted(new_collection, blacklist):
            return False

        if top_volume < float('inf') and not self.is_top_N_1dVolume(new_collection, top_volume):
            return False

        if not self.is_in_range_1dVolume(new_collection, min_volume, max_volume):
            return False

        if not self.is_in_range_topOffer(new_collection, min_price, max_price):
            return False


        ## Alerts
        
        topOffer = get_usd_price(new_collection, "topOffer")
        floorPrice = get_usd_price(new_collection, "floorPrice")
        
        if not (topOffer and floorPrice): 
            return False
        
        
        conditions = {}


        diff_offer_to_floor = (floorPrice - topOffer) / floorPrice * 100
        
        if diff_offer_to_floor > diff:
            
            conditions['diff_percent_offer_to_floor'] = diff_offer_to_floor


        if any(conditions.values()): # all(required_conditions) or any(not_required_conditions)
            return conditions

        return False

    

    async def is_notification_cooldown_passed(self, collection, user_id, notification_cooldown):
        if not notification_cooldown:
            return True

        now = asyncio.get_running_loop().time()

        previous_notification = self.last_notifications.setdefault(collection['slug'], {}).setdefault(user_id, 0)

        if now - previous_notification < notification_cooldown: 
            return False

        return True



    def is_diff_step_range_passed(self, collection, diff, percent_step, user_id):
        if not percent_step:
            return True
                    
        previous_diff = self.last_diffs.setdefault(collection['slug'], {}).setdefault(user_id, 0.001)

        step_size = previous_diff * (percent_step / 100)

        if abs(diff - previous_diff) <= step_size:
            return True

        return False



    def build_notification(self, collection, diff):
        """Получаем цены и создаем уведомление"""
        
        usd_price = (get_usd_price(collection, 'topOffer') or get_usd_price(collection, 'floorPrice') or 0)
        topOffer   = get_native_price(collection, "topOffer")
        floorPrice = get_native_price(collection, "floorPrice")

        return (

            f"Collection - {collection['slug']}\n"
            f"Price - {usd_price:.2f}$\n"
            f"List - {topOffer['price']} {topOffer['currency']}\n"
            f"Floor - {floorPrice['price']} {floorPrice['currency']}\n"
            f"Diff - <b>{diff:.2f}%</b>\n"
            f"opensea.io/collection/{collection['slug']}"
        
        )



    async def send_notifications(self, collection):
        """Проверка условий и отправка уведомлений"""
        for user_id, config in self.configs.items():

            notification_cooldown = config.notification_cooldown or 0
            percent_step = config.percent_step or 0

            # Проверка кулдауна с последнего уведомления по notification_cooldown в config
            if not await self.is_notification_cooldown_passed(collection, user_id, notification_cooldown):
                continue



            conditions = self.custom_condition(collection, user_id)

            diff = conditions.get('diff_percent_offer_to_floor', 0)

            if conditions:
                
                # Проверка движения на шаг процентов с прошлого diff процента по percent_step в config
                if not self.is_diff_step_range_passed(

                    user_id,
                    collection, 
                    diff,
                    percent_step

                ):
                    continue


                notification = self.build_notification(collection, diff)

                try:

                    await self.notification_managers[user_id].add_message(
                        user_id, 
                        notification
                    )


                    if notification_cooldown:

                        now = asyncio.get_running_loop().time()
                        self.last_notifications[collection['slug']][user_id] = now


                    if percent_step: 
                        self.last_diffs.setdefault(collection['slug'], {})[user_id] = diff
                
                except Exception as e: logger.error(f"Error sending message to {user_id}: {e}")
