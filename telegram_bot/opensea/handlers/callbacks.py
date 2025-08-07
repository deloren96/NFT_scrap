from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from telegram_bot.opensea.keyboards.config_keyboards import ConfigKeyboards
from telegram_bot.opensea.states.config_states import ConfigStates
from configs import BuildConfigs
from telegram_bot.opensea.utils import build_blacklist_string

router = Router()




@router.callback_query(F.data == "opensea_config")
async def show_opensea_config(callback: CallbackQuery, state: FSMContext):
    print(f"User {callback.from_user.id} accessed OpenSea config menu.")
    cfg = BuildConfigs.opensea[callback.from_user.id]
    configs_string = (
        f"Настройки OpenSea:\n\n"
        f"Черный список <b>{len(cfg.blacklist)}</b> элементов\n"
        f"Задержка уведомлений <b>{cfg.notification_cooldown} сек</b>\n"
        f"Топ <b>{cfg.top_N_by_1d_volume}</b> по 1d объему\n"
        f"1d объем <b>{cfg.min_USD_1d_volume}-{cfg.max_USD_1d_volume}$</b> \n"
        f"Лимиты цен <b>{cfg.min_USD_top_offer}-{cfg.max_USD_top_offer}$</b>\n"
        f"Разница до <b>{cfg.diff_percent_offer_to_floor}%</b> topOffer/floorPrice\n"
        f"Шаг в <b>{cfg.percent_step}%</b> разницы для уведомления\n"
    )
    await callback.message.edit_text(configs_string, reply_markup=ConfigKeyboards.opensea_config_keyboard(), parse_mode='HTML')
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "opensea_blacklist")
async def show_opensea_blacklist(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    blacklist = BuildConfigs.opensea[user_id].blacklist
    if not blacklist:
        await callback.message.edit_text("Черный список пуст.", reply_markup=ConfigKeyboards.opensea_blacklist_empty_keyboard())
    else:
        blacklist_string = build_blacklist_string(blacklist)
        await callback.message.edit_text(
            f"Черный список {len(BuildConfigs.opensea[callback.from_user.id].blacklist)} элементов:{blacklist_string}\n\nВыберите действие:",
            reply_markup=ConfigKeyboards.opensea_blacklist_keyboard(), parse_mode='HTML'
        )
    await callback.answer()


@router.callback_query(F.data == "opensea_blacklist_add")
async def add_to_blacklist(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    blacklist = BuildConfigs.opensea[user_id].blacklist

    blacklist_string = build_blacklist_string(blacklist)
    await callback.message.edit_text(
        "Введите название коллекции для добавления в черный список" + (f"\n\nТекущий черный список:{blacklist_string}" ),
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(), parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_blacklist_add)
    await callback.answer()


@router.callback_query(F.data == "opensea_blacklist_remove")
async def remove_from_blacklist(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    blacklist = BuildConfigs.opensea[user_id].blacklist

    if not blacklist:
        await callback.answer("Черный список пуст!", show_alert=True)
        return

    blacklist_string = build_blacklist_string(blacklist)
    await callback.message.edit_text(
        f"Введите название коллекции для удаления из черного списка:{blacklist_string}",
        reply_markup=ConfigKeyboards.opensea_blacklist_remove_all_keyboard(), parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_blacklist_remove)
    await callback.answer()
    

@router.callback_query(F.data == "opensea_blacklist_remove_all")
async def remove_all_from_blacklist(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    BuildConfigs.opensea[user_id].blacklist.clear()
    
    await callback.message.edit_text(
        "Черный список очищен.",
        reply_markup=ConfigKeyboards.opensea_blacklist_empty_keyboard(), parse_mode='HTML'
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "opensea_notification_cooldown")
async def set_notification_cooldown(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите задержку уведомлений в секундах. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].notification_cooldown} сек</b>.",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(), parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_notification_cooldown)
    await callback.answer()


@router.callback_query(F.data == "opensea_percent_step")
async def set_notification_step(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите шаг в % разницы для уведомления. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].percent_step}</b>%:",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(),
        parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_notification_percent_step)
    await callback.answer()


@router.callback_query(F.data == "opensea_top_N_by_1d_volume")
async def set_top_n_by_1d_volume(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите количество топ N по 1d объему. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].top_N_by_1d_volume}</b>:",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(),
        parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_top_N_daily_volume)
    await callback.answer()


@router.callback_query(F.data == "opensea_max_USD_1d_volume")
async def set_max_usd_1d_volume(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите максимальный 1d объем в USD. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].max_USD_1d_volume}$</b>:",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(),
        parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_max_1d_volume)
    await callback.answer()


@router.callback_query(F.data == "opensea_min_USD_1d_volume")
async def set_min_usd_1d_volume(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите минимальный 1d объем в USD. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].min_USD_1d_volume}$</b>:",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(),
        parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_min_1d_volume)
    await callback.answer()


@router.callback_query(F.data == "opensea_max_USD_top_offer")
async def set_max_usd_top_offer(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите максимальный топ-офер в USD. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].max_USD_top_offer}$</b>:",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(),
        parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_max_USD_top_offer)
    await callback.answer()


@router.callback_query(F.data == "opensea_min_USD_top_offer")
async def set_min_usd_top_offer(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите минимальный топ-офер в USD. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].min_USD_top_offer}$</b>:",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(),
        parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_min_USD_top_offer)
    await callback.answer()


@router.callback_query(F.data == "opensea_topOffer_floorPrice_diff_percent")
async def set_top_offer_floor_price_diff(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"Введите разницу % между topOffer и floorPrice. Сейчас <b>{BuildConfigs.opensea[callback.from_user.id].diff_percent_offer_to_floor}%</b>:",
        reply_markup=ConfigKeyboards.opensea_config_back_keyboard(),
        parse_mode='HTML'
    )
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(ConfigStates.waiting_topOffer_floorPrice_diff)
    await callback.answer()

