import logging
import asyncio, os, json

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()
bot = None

class Config():
    def __init__(self, import_config=None):
        self.blacklist: list = []
        self.notification_cooldown: int = 30  # seconds
        self.percent_step: float = 0.0 # разница в процентах с прошлого diff процента: diff = 3; diff * (percent_step / 100)
        
       # filter_slugs_rules
        self.top_N_by_1d_volume: float = float('inf')
        self.max_USD_1d_volume: float = float('inf')
        self.min_USD_1d_volume: float = 0.0
        self.max_USD_top_offer: float = float('inf')
        self.min_USD_top_offer: float = 0.0

        # alert_rules
        self.diff_percent_offer_to_floor: float = float('inf')

        if import_config and isinstance(import_config, dict):
            self.__dict__.update(import_config)
    
    def save_config(self):
           return self.__dict__

try:
    with open("configs.json", "r") as f:
        configs : dict[int, Config] = { int(user_id) : Config(cfg) for user_id, cfg in json.load(f).items() }

        logger.debug(f"Loaded configs: {configs.keys()}")

except Exception as e:
    configs = {}
    logger.warning(f"No configs found, starting with an empty dictionary. Error: {e}")

@dp.message(CommandStart())
async def cmd_start(message):
    if message.chat.type == 'private' and message.from_user.id not in configs:
        configs[message.from_user.id] = Config()
        
        with open("configs.json", "w") as f:
            json.dump({user_id: cfg.save_config() for user_id, cfg in configs.items()}, f, indent=2)

        await message.answer("Вам теперь будут приходить уведомления.")
    else:
        await message.answer("Вы уже подписаны на уведомления. Хотите сбросить настройки?")


async def start_bot(token: str=None):
    global bot
    if token:
        bot = Bot(token=token)
        await dp.start_polling(bot)
    else:
        raise ValueError("Bot token is required to start the bot.")

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    asyncio.run(start_bot(os.getenv("TG_BOT_TOKEN")))