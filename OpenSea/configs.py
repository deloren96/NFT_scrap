import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import aiofiles, json


class Config():
    def __init__(self, import_config=None):
        self.blacklist: list = []
        self.notification_cooldown: int = 30  # seconds
        self.percent_step: float = 0.0 # разница в процентах с прошлого diff процента: diff = 3; diff * (percent_step / 100)
        
       # filter_slugs_rules
        self.top_N_by_1d_volume: float = float('inf')
        self.max_USD_1d_volume: float = float('inf')
        self.min_USD_1d_volume: float = 0.0
        self.max_USD_top_offer: float = float('inf')
        self.min_USD_top_offer: float = 0.0

        # alert_rules
        self.diff_percent_offer_to_floor: float = float('inf')

        if import_config and isinstance(import_config, dict):
            self.__dict__.update(import_config)
    
    def save_config(self):
           return self.__dict__
    
async def load_configs() -> dict[int, Config]:
    configs  : dict[int, Config] = {}

    try:
        async with aiofiles.open("configs.json", "r") as f:
            configs = { int(user_id) : Config(cfg) for user_id, cfg in json.loads((await f.read())).items() }

        logger.debug(f"Loaded configs: {configs.keys()}")

    except Exception as e:
        logger.warning(f"No configs found, starting with an empty dictionary. Error: {e}")

    return configs