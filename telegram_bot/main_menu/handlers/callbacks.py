from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from telegram_bot.main_menu.keyboards.config_keyboards import ConfigKeyboards as MainConfigKeyboards


router = Router()

@router.callback_query(F.data == "config_main")
async def config_main_callback(callback: CallbackQuery, state: FSMContext):
    print(f"User {callback.from_user.id} accessed main config menu.")
    await callback.message.edit_text("Выберете маркетплейс:", reply_markup=MainConfigKeyboards.get_config_keyboard())
    await state.clear()
    await callback.answer()