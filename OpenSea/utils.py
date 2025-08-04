
def get_usd_price(data, key):
    """Получает цену в USD проверяя на ошибки"""
    return value["pricePerItem"]["usd"] if (value := data.get(key)) else None

def get_native_price(data, key):
    """Получает цену в нативной валюте проверяя на ошибки"""
    return {'price': native['unit'], 'currency': native['symbol']} if (value := data.get(key)) and (native := value["pricePerItem"]["native"]) and native.get("unit") and native.get("symbol") else None

def deep_dict_update(dict_for_update: dict, new_data: dict):
    for key, value in new_data.items():
        if isinstance(value, dict) and isinstance(dict_for_update.get(key), dict): deep_dict_update(dict_for_update[key], value)
        else: dict_for_update[key] = value
