import logging

import asyncio
from collections import deque, defaultdict

from aiogram.exceptions import TelegramRetryAfter
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)



class MessageManager:
    """Менеджер, который распределяет отправку сообщений согласно лимитам Telegram Bot API."""

    def __init__(s, chat_id: int,send_message: callable, *args, **kwargs):
        """
        Инициализация менеджера сообщений.

        :param send_message: coroutine для отправки сообщений, принимающая chat_id и текст сообщения.
        :param args: дополнительные аргументы для send_message.
        :param kwargs: дополнительные ключевые аргументы для send_message.
        """
        s._send_message = send_message
        s.args = args
        s.kwargs = kwargs

        s.chat_id = chat_id

        s.messages = []

        s.cooldown = 10

        s.TIME_WINDOW = 5 # seconds
        s.MESSAGES_LIMIT = s.TIME_WINDOW * 2
        s.BASE_DELAY = 0.3 # seconds
        s.MAX_DELAY = 1.0 # seconds
        s.current_delay = s.BASE_DELAY

        s.message_timestamps = deque()
        s.recent_messages_timestamps: deque[float] = deque()

        s.flood_control: float = 0.0

        s.queue = asyncio.Queue()
        s.chat_task = asyncio.create_task(s.process_chat_queue())



    async def send_message(s, message):
        try:

            await s._send_message(s.chat_id, message, *s.args, **s.kwargs)
            now = asyncio.get_running_loop().time()
            s.recent_messages_timestamps.append(now)

        except TelegramRetryAfter as exception:

            await s.queue.put(message)

            now = asyncio.get_running_loop().time()
            s.flood_control = now + exception.retry_after

            log.warning(f"Flood control: {s.chat_id} попробуйте снова через {exception.retry_after} секунд")

        except Exception as exception:

            log.error(f"Error sending message to {s.chat_id}: {exception}")



    def gather_messages(s):
        while not s.queue.empty():
            try:
                s.messages.append(s.queue.get_nowait())
            except asyncio.QueueEmpty:
                break



    async def add_message(s, message):
        log.debug(f"Adding message to {s.chat_id}")
        await s.queue.put(message)



    async def clean_timestamps(s):

        now = asyncio.get_running_loop().time()
        timestamps = s.recent_messages_timestamps

        while timestamps and (now - timestamps[0]) > s.TIME_WINDOW:
            timestamps.popleft()



    async def wait_delay(s, end_timestamp: float):
        """Останавливает весь цикл, и все сообщения накапливаются в очередь."""

        now = asyncio.get_running_loop().time()

        if now < end_timestamp:
            await asyncio.sleep(end_timestamp - now)



    async def combine_messages(s) -> str:
        combined_message = ""
        i = 0
        while i < len(s.messages):

            message = s.messages[i]
            if len(combined_message) + len(message) > 4096:
                s.messages = s.messages[i:]
                break
            else:
                if combined_message:
                    combined_message += "\n\n" + message
                else:
                    combined_message = message
            i += 1

        return combined_message



    async def control_messages_speed(s):
        timestamps = s.recent_messages_timestamps

        await s.clean_timestamps()
        s.current_delay = s.MAX_DELAY if len(timestamps) >= s.MESSAGES_LIMIT else s.BASE_DELAY

        last_timestamp = timestamps[-1] if timestamps else 0
        end_timestamp = max([
            0,
            last_timestamp + s.current_delay,
            s.flood_control
        ])

        return end_timestamp



    async def process_chat_queue(s):
        while True:

            
            if len(s.messages) > 0 and s.queue.empty():
                log.debug(f"{s.chat_id if s.chat_id==857039354 else ''} No queued messages, only cached. {len(s.messages)}")
            else:
                log.debug(f"{s.chat_id} Processing queue. {s.queue.qsize()} messages in queue, {len(s.messages)} cached messages")
                s.messages.append(await s.queue.get())
            
            if s.flood_control:
                log.debug(f"{s.chat_id} Flood control active, waiting until {s.flood_control}")
                await s.wait_delay(s.flood_control)
                s.gather_messages()
                s.messages.clear()
                s.flood_control = 0.0
                continue
            

            end_timestamp = await s.control_messages_speed()

            await s.wait_delay(end_timestamp)
            s.gather_messages()
            combined_message = await s.combine_messages()
            if combined_message:
                await s.send_message(combined_message)





if __name__ == "__main__":
    import os

    from aiogram import Bot, Dispatcher, Router

    from dotenv import load_dotenv; load_dotenv()
    TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")

    router = Router()
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    message_manager = MessageManager(bot.send_message, parse_mode='HTML', disable_web_page_preview=True)

    async def start_bot():

        await dp.start_polling(bot)

    asyncio.run(start_bot())