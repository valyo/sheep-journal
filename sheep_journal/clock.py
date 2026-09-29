from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app


def now():
    fixed = current_app.config.get("FIXED_NOW")
    if fixed is not None:
        return fixed
    return datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).replace(microsecond=0)


def today():
    return now().date()
