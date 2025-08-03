import logging
import asyncio, aiofiles, os, json

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import CommandStart

from telegram_bot.message_manager import MessageManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from dotenv import load_dotenv; load_dotenv()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")

router = Router()
bot = Bot(token=TG_BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

message_manager: dict[int, MessageManager] = {}

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

configs  : dict[int, Config] = {}

def init_message_manager():
    for chat_id in configs.keys():
        if chat_id not in message_manager:
            message_manager[chat_id] = MessageManager(chat_id, bot.send_message, parse_mode='HTML', disable_web_page_preview=True)

async def load_configs():
    global configs
    try:
        async with aiofiles.open("configs.json", "r") as f:
            configs = { int(user_id) : Config(cfg) for user_id, cfg in json.loads((await f.read())).items() }
        init_message_manager()
        logger.debug(f"Loaded configs: {configs.keys()}")

    except Exception as e:
        configs = {}
        logger.warning(f"No configs found, starting with an empty dictionary. Error: {e}")

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.type == 'private' and message.from_user.id not in configs:
        configs[message.from_user.id] = Config()
        
        async with aiofiles.open("configs.json", "w") as f:
            await f.write(json.dumps({user_id: cfg.save_config() for user_id, cfg in configs.items()}, indent=2))

        await message.answer("Вам теперь будут приходить уведомления.")
    else:
        await message.answer("Вы уже подписаны на уведомления. Хотите сбросить настройки?")



async def start_bot():

    await load_configs()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_bot())