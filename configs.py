import asyncio, aiofiles, json
from collections import defaultdict

class OpenSeaConfig():
    def __init__(self, import_config=None):
        self.blacklist: set = set()
        self.notification_cooldown: int = 30  # seconds
        self.percent_step: float = 0.0 # разница в процентах с прошлого diff процента: diff = 3; diff * (percent_step / 100)
        
       # filter_slugs_rules
        self.top_N_by_1d_volume: float = float('inf')
        self.max_USD_1d_volume: float = float('inf')
        self.min_USD_1d_volume: float = 0.0
        self.max_USD_top_offer: float = float('inf')
        self.min_USD_top_offer: float = 0.0

        # alert_rules
        self.diff_percent_offer_to_floor: float = float('-inf')

        if import_config and isinstance(import_config, dict):
            import_config['blacklist'] = set(import_config.get('blacklist', []))
            self.__dict__.update(import_config)
    
    def save_config(self):
           config = self.__dict__.copy()
           config['blacklist'] = sorted(self.blacklist)
           return config

def load_configs(file_path = "OpenSea/configs.json") -> dict[int, OpenSeaConfig]:
    configs  : dict[int, OpenSeaConfig] = {}

    try:
        with open(file_path, "r") as f:
            configs = { int(user_id) : OpenSeaConfig(cfg) for user_id, cfg in json.load(f).items() }
    except:
        pass

    return configs



class BuildConfigs:
        lock = asyncio.Lock()
        opensea: defaultdict[int, OpenSeaConfig] = defaultdict(OpenSeaConfig)
        opensea.update(load_configs('./OpenSea/configs.json'))

        @classmethod
        async def save_configs(cls, file_path = "OpenSea/configs.json"):
            async with cls.lock:
                async with aiofiles.open(file_path, "w") as f:
                    await f.write(json.dumps({str(user_id): config.save_config() for user_id, config in cls.opensea.items()}, indent=4))