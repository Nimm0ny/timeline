from backend.app.services.date_utils import (
    build_display_label,
    date_key_to_iso,
    date_key_to_parts,
    extract_headline_from_legacy_label,
    make_date_key,
    parse_date_key,
)


def test_parse_date_key_supports_day_and_month_ranges():
    assert parse_date_key("1840-01-02") == 18400102
    assert parse_date_key("1840-02", is_end=True) == 18400229
    assert parse_date_key("-0001-01-02") == make_date_key(-1, 1, 2)
    assert parse_date_key("-1-01-02") == make_date_key(-1, 1, 2)
    assert parse_date_key("-0001-02", is_end=True) == make_date_key(-1, 2, 28)


def test_date_key_round_trip_and_display_label():
    key = make_date_key(1841, 2, 15)
    assert date_key_to_parts(key) == (1841, 2, 15)
    assert date_key_to_iso(key) == "1841-02-15"
    assert build_display_label(1841, 2, 15, "Mid Month") == "1841-02-15 Mid Month"

    bce_start = make_date_key(-1, 1, 1)
    bce_later = make_date_key(-1, 1, 31)
    assert bce_later > bce_start
    assert date_key_to_parts(bce_start) == (-1, 1, 1)
    assert date_key_to_iso(bce_start) == "-0001-01-01"


def test_extract_headline_from_legacy_label():
    assert extract_headline_from_legacy_label("1840年1月1日 鸦片战争") == "鸦片战争"
    assert extract_headline_from_legacy_label("1841-02-15 Another Year") == "Another Year"
