"""Unit tests for the pure insight functions."""

from datetime import date, datetime, timedelta

from custom_components.year_roundup import insights


def _year(fn):
    start = datetime(2026, 1, 1)
    return {start + timedelta(hours=h): fn(start + timedelta(hours=h)) for h in range(365 * 24)}


def test_night_owl():
    hourly = _year(lambda t: 1.0 if t.hour in (22, 23, 0, 1) else 0.2)
    p = insights.profile(hourly)
    d = insights.daily(hourly)
    who = insights.personality(p, insights.weekdays(d), insights.seasons(d, False), None, None)
    assert who["type"] == "night_owl"
    assert who["peak_hour"] in (22, 23, 0, 1)


def test_seasonal_swinger_and_season():
    hourly = _year(lambda t: 1.0 if t.month in (12, 1, 2) else 0.3)
    d = insights.daily(hourly)
    s = insights.seasons(d, southern=False)
    assert s["top"] == "Winter"
    assert insights.seasons(d, southern=True)["top"] == "Summer"
    who = insights.personality(insights.profile(hourly), insights.weekdays(d), s, None, None)
    assert who["type"] == "seasonal_swinger"


def test_weekend_and_day_of_year():
    hourly = _year(lambda t: 0.6 if t.weekday() >= 5 else 0.4)
    hourly[datetime(2026, 12, 25, 18)] = 50
    d = insights.daily(hourly)
    wk = insights.weekdays(d)
    assert wk["busiest"] in ("Saturday", "Sunday") and wk["weekend_ratio"] > 1.4
    doy = insights.day_of_year(d)
    assert doy["date"] == "2026-12-25" and doy["times_normal"] > 4


def test_sun_streak():
    solar = {date(2026, 6, 1) + timedelta(days=i): (20 if 3 <= i < 13 else 2) for i in range(30)}
    grid = {k: 8 for k in solar}
    s = insights.sun_streak(solar, grid)
    assert s["days"] == 10 and s["from"] == "2026-06-04"


def test_quiet_hour_and_aura():
    hourly = _year(lambda t: 0.1 if t.hour == 3 else 0.5)
    q = insights.quiet_hour(insights.profile(hourly))
    assert q == {"hour": 3, "watts": 100}
    a = insights.aura(18, "Winter")
    assert len(a["colors"]) == 2 and "magenta" in a["words"] and "frost" in a["words"]
