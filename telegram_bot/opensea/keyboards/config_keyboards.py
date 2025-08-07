from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from configs import BuildConfigs

class ConfigKeyboards:

    @staticmethod
    def back_to_config():
        return [InlineKeyboardButton(text="Назад к настройкам", callback_data="opensea_config")]

    @staticmethod
    def opensea_config_keyboard() -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Черный список",                   callback_data="opensea_blacklist")],
            [InlineKeyboardButton(text="Задержка уведомлений",            callback_data="opensea_notification_cooldown")],
            [InlineKeyboardButton(text="Топ N по 1d объему",              callback_data="opensea_top_N_by_1d_volume")],
            [InlineKeyboardButton(text="Мин USD 1d объем",                callback_data="opensea_min_USD_1d_volume"),
             InlineKeyboardButton(text="Макс USD 1d объем",               callback_data="opensea_max_USD_1d_volume")],
            [InlineKeyboardButton(text="Мин USD цена",                    callback_data="opensea_min_USD_top_offer"),
             InlineKeyboardButton(text="Макс USD цена",                   callback_data="opensea_max_USD_top_offer")],
            [InlineKeyboardButton(text="Разница % topOffer/floorPrice",   callback_data="opensea_topOffer_floorPrice_diff_percent")],
            [InlineKeyboardButton(text="Шаг в % разницы для уведомления", callback_data="opensea_percent_step")],
            [InlineKeyboardButton(text="Назад к выбору маркетплейсов",    callback_data="config_main")]
        ])
        return keyboard
    
    @staticmethod
    def opensea_blacklist_keyboard() -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить в черный список", callback_data="opensea_blacklist_add")],
            [InlineKeyboardButton(text="Удалить из черного списка", callback_data="opensea_blacklist_remove")],
            ConfigKeyboards.back_to_config()
        ])
        return keyboard
    
    @staticmethod
    def opensea_blacklist_empty_keyboard() -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить в черный список", callback_data="opensea_blacklist_add")],
            ConfigKeyboards.back_to_config()
        ])
        return keyboard

    @staticmethod
    def opensea_blacklist_remove_all_keyboard() -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Очистить черный список", callback_data="opensea_blacklist_remove_all")],
            ConfigKeyboards.back_to_config()
        ])
        return keyboard

    @staticmethod
    def opensea_config_back_keyboard() -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[ConfigKeyboards.back_to_config()])
        return keyboard