from aiogram.fsm.state import State, StatesGroup

class ConfigStates(StatesGroup):
    """Состояния для настройки конфигурации"""
    
    # Состояния для настройки параметров OpenSea
    waiting_notification_cooldown = State()
    waiting_top_N_daily_volume = State()
    waiting_min_1d_volume = State()
    waiting_max_1d_volume = State()
    waiting_max_USD_top_offer = State()
    waiting_min_USD_top_offer = State()
    waiting_topOffer_floorPrice_diff = State()
    waiting_notification_percent_step = State()
    
    # Состояния для работы с черным списком
    waiting_blacklist_add = State()
    waiting_blacklist_remove = State()