from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from telegram_bot.main_menu.keyboards.config_keyboards import ConfigKeyboards
from configs import BuildConfigs, OpenSeaConfig
from telegram_bot.utils import Utils

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.type == 'private' and message.from_user.id not in BuildConfigs.opensea:
        BuildConfigs.opensea[message.from_user.id] = OpenSeaConfig()
        await message.answer("Вам теперь будут приходить уведомления.")
    else:
        await message.answer("Вы уже подписаны на уведомления. Для смены настроек используйте /config.")
    
    Utils.is_send_notifications[message.from_user.id] = True

@router.message(Command("config"))
async def cmd_config(message: Message):
    if message.chat.type == 'private':
        if message.from_user.id in BuildConfigs.opensea:
            Utils.is_send_notifications[message.from_user.id] = False
            print(f"User {message.from_user.id} paused notifications.")
            await message.answer("Уведомления на паузе.\n\nВыберете маркетплейс:", reply_markup=ConfigKeyboards.get_config_keyboard())
        else:
            await cmd_start(message)
    else:
        await message.answer("Эта команда доступна только в личных сообщениях.")

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if message.chat.type == 'private':
        await state.clear()
        Utils.is_send_notifications[message.from_user.id] = True
        await message.answer("Действия отменены. Вы можете начать заново, используя /config.")