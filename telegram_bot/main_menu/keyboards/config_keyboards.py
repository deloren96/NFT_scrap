from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class ConfigKeyboards:

    @staticmethod
    def get_config_keyboard() -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="OpenSea", callback_data=f"opensea_config")],
            # Другие кнопки для других маркетплейсов
        ])
        return keyboard

