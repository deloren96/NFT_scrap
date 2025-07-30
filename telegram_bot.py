import logging
import asyncio, os, json

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()
bot = None

try:
    with open("config.json", "r") as f:
        config = {int(k): v for k, v in json.load(f).items()}
        if type(config) is not dict: config = {}
        logger.debug(f"Loaded configs: {config}")
except Exception as e:
    config = {}
    logger.warning(f"No configs found, starting with an empty dictionary. Error: {e}")

@dp.message(CommandStart())
async def cmd_start(message):
    if message.chat.type == 'private' and message.from_user.id not in config:
        config[message.from_user.id] = {
            "filter_slugs_rules": {
                "top_N_by_1d_volume": float('inf'),
                "max_USD_1d_volume": float('inf'),
                "min_USD_1d_volume": 0.0,
                "max_USD_top_offer": float('inf'),
                "min_USD_top_offer": 0.0
            },
            "alert_rules": {
                "diff_percent_offer_to_floor": float('inf'),
            },
            "blacklist": [],
            }
        with open("config.json", "w") as f:
            json.dump(config, f, indent=2)
        
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