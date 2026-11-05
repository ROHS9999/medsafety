import re

DAYS_PER_UNIT = {"d": 1, "day": 1, "w": 7, "wk": 7, "week": 7, "mth": 30, "month": 30}

# a number, then a unit, standing on their own ("x 5 days", "2 wks", "1 mth")
PATTERN = re.compile(
    r"(?<![a-z0-9])(\d{1,3})\s*(days?|d|weeks?|wks?|w|months?|mths?)(?![a-z0-9])",
    re.IGNORECASE,
)


def suggest_days(text):
    """Turn '5 days', 'x 2 wks' or 'x 1 mth' into a number of days.
    Returns None when it is not sure ('Continue', or two different numbers)."""
    if not text:
        return None
    matches = PATTERN.findall(text)
    if len(matches) != 1:
        return None
    number, unit = matches[0]
    unit = unit.lower().rstrip("s")        # days -> day, wks -> wk, months -> month
    days = int(number) * DAYS_PER_UNIT[unit]
    return days if 1 <= days <= 3650 else None
