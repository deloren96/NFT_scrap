import asyncio

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from telegram_bot.opensea.keyboards.config_keyboards import ConfigKeyboards
from telegram_bot.opensea.states.config_states import ConfigStates
from configs import BuildConfigs
from telegram_bot.opensea.utils import build_blacklist_string, edit_message_text

router = Router()

@router.message(ConfigStates.waiting_blacklist_add)
async def process_blacklist_add(message: Message, state: FSMContext, bot):
    """Обработка добавления в черный список"""
    item = message.text.strip()
    user_id = message.from_user.id
    
    data = await state.get_data()
    message_id = data.get('message_id')
    try:
        if not item:
            await bot.edit_message_text(

            chat_id=message.from_user.id,
            message_id=message_id,
            text=f"❌ Не удалось добавить <code>{item}</code> в черный список."+build_blacklist_string(BuildConfigs.opensea[user_id].blacklist),
            parse_mode='HTML',
            reply_markup=ConfigKeyboards.opensea_config_back_keyboard()
            )
        
        else:

            BuildConfigs.opensea[user_id].blacklist.add(item)
            
            await bot.edit_message_text(

                chat_id=message.from_user.id,
                message_id=message_id,
                text=f"✅ Черный список обновлен. <code>{item}</code>"+build_blacklist_string(BuildConfigs.opensea[user_id].blacklist),
                parse_mode='HTML',
                reply_markup=ConfigKeyboards.opensea_config_back_keyboard()
            )
            asyncio.create_task(BuildConfigs.save_configs())
    except:
        pass
    await message.delete()
    

@router.message(ConfigStates.waiting_blacklist_remove)
async def process_blacklist_remove(message: Message, state: FSMContext, bot):
    """Обработка удаления из черного списка"""
    item = message.text.strip()
    user_id = message.from_user.id
    
    data = await state.get_data()
    message_id = data.get('message_id')

    try:
        if not item:
            await bot.edit_message_text(

            chat_id=message.from_user.id,
            message_id=message_id,
            text=f"❌ Не удалось удалить <code>{item}</code> из черного списка."+build_blacklist_string(BuildConfigs.opensea[user_id].blacklist),
            parse_mode='HTML',
            reply_markup=ConfigKeyboards.opensea_blacklist_remove_all_keyboard() if BuildConfigs.opensea[user_id].blacklist else ConfigKeyboards.opensea_blacklist_empty_keyboard()
            )
        elif item in BuildConfigs.opensea[user_id].blacklist:
            
            BuildConfigs.opensea[user_id].blacklist.remove(item)

            await bot.edit_message_text(

                chat_id=message.from_user.id,
                message_id=message_id,
                text=f"✅ Черный список обновлен. <code>{item}</code>"+build_blacklist_string(BuildConfigs.opensea[user_id].blacklist),
                parse_mode='HTML',
                reply_markup=ConfigKeyboards.opensea_blacklist_remove_all_keyboard() if BuildConfigs.opensea[user_id].blacklist else ConfigKeyboards.opensea_blacklist_empty_keyboard()
            )
            asyncio.create_task(BuildConfigs.save_configs())
    except:
        pass

    await message.delete()
    

@router.message(ConfigStates.waiting_notification_cooldown)
async def process_notification_cooldown(message: Message, state: FSMContext, bot):
    """Обработка установки задержки уведомлений"""
    cooldown = message.text.strip()
    try:
        if float(cooldown) >= 0:
            BuildConfigs.opensea[message.from_user.id].notification_cooldown = float(cooldown)
            await edit_message_text(
                f"✅ Задержка уведомлений установлена на <b>{cooldown} сек</b>.",
                message, state, bot
            )
            await state.clear()
            asyncio.create_task(BuildConfigs.save_configs())
        else:
            raise ValueError("Задержка не может быть отрицательной")
    except ValueError:
            await edit_message_text(
                "❌ Пожалуйста, введите корректное значение задержки (число >= 0).",
                message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
            )
    await message.delete()
    

@router.message(ConfigStates.waiting_top_N_daily_volume)
async def process_top_n_daily_volume(message: Message, state: FSMContext, bot):
    """Обработка установки топ N по 1d объему"""
    top_n = message.text.strip()

    if not top_n.isdigit() or int(top_n) <= 0:
        await edit_message_text(
            "❌ Пожалуйста, введите корректное значение (положительное целое число).",
            message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
        )
        await state.clear()
        asyncio.create_task(BuildConfigs.save_configs())
    else:

        BuildConfigs.opensea[message.from_user.id].top_N_by_1d_volume = int(top_n)
        await edit_message_text(
            f"✅ Топ N по 1d объему установлен: <b>{top_n}</b>.",
            message, state, bot
        )

    await message.delete()
    

@router.message(ConfigStates.waiting_min_1d_volume)
async def process_min_1d_volume(message: Message, state: FSMContext, bot):
    """Обработка установки минимального 1d объема"""
    min_volume = message.text.strip()
    try:
        if float(min_volume) >= 0:
            BuildConfigs.opensea[message.from_user.id].min_USD_1d_volume = float(min_volume)
            await edit_message_text(
                f"✅ Минимальный 1d объем установлен: <b>{min_volume}$</b>.",
                message, state, bot
            )
            await state.clear()
            asyncio.create_task(BuildConfigs.save_configs())
        else:
            raise ValueError("Минимальный объем не может быть отрицательным")
    except ValueError:
            await edit_message_text(
                "❌ Пожалуйста, введите корректное значение (число >= 0).",
                message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
            )

    await message.delete()
    

@router.message(ConfigStates.waiting_max_1d_volume)
async def process_max_1d_volume(message: Message, state: FSMContext, bot):
    """Обработка установки максимального 1d объема"""
    max_volume = message.text.strip()
    try:
        if float(max_volume) >= 0:
            BuildConfigs.opensea[message.from_user.id].max_USD_1d_volume = float(max_volume)
            await edit_message_text(
                f"✅ Максимальный 1d объем установлен: <b>{max_volume}$</b>.",
                message, state, bot
            )
            await state.clear()
            asyncio.create_task(BuildConfigs.save_configs())
        else:
            raise ValueError("Максимальный объем не может быть отрицательным")
    except ValueError:
            await edit_message_text(
                "❌ Пожалуйста, введите корректное значение (число >= 0).",
                message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
            )
        

    await message.delete()
    

@router.message(ConfigStates.waiting_max_USD_top_offer)
async def process_max_usd_top_offer(message: Message, state: FSMContext, bot):
    """Обработка установки максимальной USD цены топ оффера"""
    max_offer = message.text.strip()
    try:
        if float(max_offer) >= 0:
            BuildConfigs.opensea[message.from_user.id].max_USD_top_offer = float(max_offer)
            await edit_message_text(
                f"✅ Максимальная USD цена топ оффера установлена: <b>{max_offer}$</b>.",
                message, state, bot
            )
            await state.clear()
            asyncio.create_task(BuildConfigs.save_configs())
            
        else:
            raise ValueError("Максимальная цена не может быть отрицательной")
    except ValueError:
            await edit_message_text(
                "❌ Пожалуйста, введите корректное значение (число >= 0).",
                message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
            )

    await message.delete()
    

@router.message(ConfigStates.waiting_min_USD_top_offer)
async def process_min_usd_top_offer(message: Message, state: FSMContext, bot):
    """Обработка установки минимальной USD цены топ оффера"""
    min_offer = message.text.strip()

    try:
        if float(min_offer) >= 0:
            BuildConfigs.opensea[message.from_user.id].min_USD_top_offer = float(min_offer)
            await edit_message_text(
                f"✅ Минимальная USD цена топ оффера установлена: <b>{min_offer}$</b>.",
                message, state, bot
            )
            await state.clear()
            asyncio.create_task(BuildConfigs.save_configs())
        else:
            raise ValueError("Минимальная цена не может быть отрицательной")
    except ValueError:
        await edit_message_text(
                    "❌ Пожалуйста, введите корректное значение (число >= 0).",
                    message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
                )
    await message.delete()


@router.message(ConfigStates.waiting_notification_percent_step)
async def set_notification_percent_step(message: Message, state: FSMContext, bot):
    """Обработка установки шага в % разницы для уведомления"""
    percent_step = message.text.strip()

    try:
        BuildConfigs.opensea[message.from_user.id].percent_step = float(percent_step)
        await edit_message_text(
            f"✅ Шаг в % разницы для уведомления установлен: <b>{percent_step}%</b>.",
            message, state, bot
        )
        await state.clear()
        asyncio.create_task(BuildConfigs.save_configs())
    except ValueError:
        await edit_message_text(
            "❌ Пожалуйста, введите корректное значение.",
            message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
        )

       

    await message.delete()
    

@router.message(ConfigStates.waiting_topOffer_floorPrice_diff)
async def set_top_offer_floor_price_diff(message: Message, state: FSMContext, bot):
    """Обработка установки разницы % topOffer/floorPrice"""
    diff_percent = message.text.strip()

    try:
        BuildConfigs.opensea[message.from_user.id].diff_percent_offer_to_floor = float(diff_percent)
        await edit_message_text(
            f"✅ Разница % topOffer/floorPrice установлена: <b>{diff_percent}%</b>.",
            message, state, bot
        )
        await state.clear()
        asyncio.create_task(BuildConfigs.save_configs())
    except ValueError:
        await edit_message_text(
            "❌ Пожалуйста, введите корректное значение.",
            message, state, bot, custom_keyboard=ConfigKeyboards.opensea_config_back_keyboard()
        )

    await message.delete()
    
    