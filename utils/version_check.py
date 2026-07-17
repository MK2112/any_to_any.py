import requests

from utils.version import VERSION


def check_for_update():
    try:
        url = "https://api.github.com/repos/MK2112/any_to_any.py/releases/latest"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        latest = response.json().get("tag_name", "").replace("v", "")
        if not latest:
            return None
        local_parts = [int(x) for x in VERSION.split(".")]
        latest_parts = [int(x) for x in latest.split(".")]
        if latest_parts > local_parts:
            return latest
    except Exception:
        pass
    return None
