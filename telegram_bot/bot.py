import logging
import asyncio, aiofiles, os, json

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import CommandStart

from telegram_bot.message_manager import MessageManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


router = Router()
bot = Bot(token=TG_BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

message_managers: dict[int, MessageManager] = {}

def init_message_manager():
    for chat_id in configs.keys():
        if chat_id not in message_managers:
            message_managers[chat_id] = MessageManager(chat_id, bot.send_message, parse_mode='HTML', disable_web_page_preview=True)


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

    await dp.start_polling(bot)

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
    asyncio.run(start_bot())