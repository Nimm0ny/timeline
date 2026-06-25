import re


DATE_LABEL_RE = re.compile(
    r"^\s*(?P<year>-?\d{1,6})"
    r"(?:[年/\-.](?P<month>\d{1,2}))?"
    r"(?:[月/\-.](?P<day>\d{1,2}))?"
    r"(?:日)?\s*(?P<headline>.*)$"
)


def normalize_date_key(value) -> int:
    return int(round(float(value)))


def floor_div(value: int, divisor: int) -> int:
    return value // divisor if value >= 0 else -((-value + divisor - 1) // divisor)


def date_key_to_parts(date_key: int) -> tuple[int, int, int]:
    normalized = normalize_date_key(date_key)
    year = floor_div(normalized, 10000)
    remainder = normalized - year * 10000
    month = remainder // 100
    day = remainder % 100
    return year, month, day


def make_date_key(year: int, month: int, day: int) -> int:
    return year * 10000 + month * 100 + day


def is_leap_year(year: int) -> bool:
    adjusted = abs(year)
    return adjusted % 4 == 0 and (adjusted % 100 != 0 or adjusted % 400 == 0)


def max_day_for_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if is_leap_year(year) else 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31


def validate_date_parts(year: int, month: int, day: int) -> None:
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")
    if day < 1 or day > max_day_for_month(year, month):
        raise ValueError("Day is out of range for the given month")


def date_key_to_iso(date_key: int) -> str:
    year, month, day = date_key_to_parts(date_key)
    sign = "-" if year < 0 else ""
    return f"{sign}{abs(year):04d}-{month:02d}-{day:02d}"


def date_key_to_day_label(date_key: int) -> str:
    year, month, day = date_key_to_parts(date_key)
    sign = "-" if year < 0 else ""
    return f"{sign}{abs(year):04d}-{month:02d}-{day:02d}"


def parse_date_key(value: str | None, *, is_end: bool = False) -> int | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    sign = -1 if raw.startswith("-") else 1
    unsigned_raw = raw[1:] if sign < 0 else raw
    compact = unsigned_raw.replace("-", "")
    if re.fullmatch(r"(?:\d{6}|\d{8})", compact):
        digits = compact
        if len(digits) == 8:
            year = int(digits[:4]) * sign
            month = int(digits[4:6])
            day = int(digits[6:8])
        else:
            year = int(digits[:4]) * sign
            month = int(digits[4:6])
            day = max_day_for_month(year, month) if is_end else 1
        validate_date_parts(year, month, day)
        return make_date_key(year, month, day)

    match = re.fullmatch(r"(-?\d{1,6})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", raw)
    if not match:
        raise ValueError(f"Invalid date value: {value}")

    year = int(match.group(1))
    month = int(match.group(2) or (12 if is_end else 1))
    day = int(match.group(3) or (max_day_for_month(year, month) if is_end else 1))
    validate_date_parts(year, month, day)
    return make_date_key(year, month, day)


def extract_headline_from_legacy_label(label: str, fallback: str = "") -> str:
    raw = str(label or "").strip()
    if not raw:
        return fallback.strip()
    match = DATE_LABEL_RE.match(raw)
    if not match:
        return raw
    headline = (match.group("headline") or "").strip()
    return headline or fallback.strip() or raw


def build_display_label(year: int, month: int, day: int, headline: str) -> str:
    date_label = date_key_to_day_label(make_date_key(year, month, day))
    text = str(headline or "").strip()
    return f"{date_label} {text}".strip()


def year_month_bucket(year: int, month: int) -> int:
    return year * 100 + month
