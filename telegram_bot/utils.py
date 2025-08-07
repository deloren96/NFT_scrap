from collections import defaultdict

class Utils:
    is_send_notifications: defaultdict[int, bool] = defaultdict(lambda: True)
