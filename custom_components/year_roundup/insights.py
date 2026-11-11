"""Wrapped-style insights derived from hourly long-term statistics.

Pure functions (no Home Assistant calls) so they're easy to test.
Hourly series are dicts of {local datetime of hour start: kWh}.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import statistics as pystats

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SEASON_NORTH = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
                6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}
_FLIP = {"Winter": "Summer", "Summer": "Winter", "Spring": "Autumn", "Autumn": "Spring"}


def daily(hourly: dict[datetime, float]) -> dict[date, float]:
    out: dict[date, float] = defaultdict(float)
    for t, v in hourly.items():
        out[t.date()] += v
    return dict(out)


def profile(hourly: dict[datetime, float]) -> list[float]:
    """Average kWh for each hour of the day across the year."""
    tot, n = [0.0] * 24, [0] * 24
    for t, v in hourly.items():
        tot[t.hour] += v
        n[t.hour] += 1
    return [round(a / b, 4) if b else 0.0 for a, b in zip(tot, n)]


def weekdays(days: dict[date, float]) -> dict | None:
    buckets: dict[int, list[float]] = defaultdict(list)
    for d, v in days.items():
        buckets[d.weekday()].append(v)
    if len(buckets) < 7 or min(len(b) for b in buckets.values()) < 4:
        return None
    avg = [pystats.fmean(buckets[i]) for i in range(7)]
    weekday_avg, weekend_avg = pystats.fmean(avg[:5]), pystats.fmean(avg[5:])
    hi, lo = max(range(7), key=avg.__getitem__), min(range(7), key=avg.__getitem__)
    return {
        "avg_kwh": [round(a, 2) for a in avg],
        "busiest": WEEKDAYS[hi], "quietest": WEEKDAYS[lo],
        "spread_pct": round(100 * (avg[hi] / avg[lo] - 1)) if avg[lo] else 0,
        "weekend_ratio": round(weekend_avg / weekday_avg, 3) if weekday_avg else 1,
    }


def seasons(days: dict[date, float], southern: bool) -> dict | None:
    tot: dict[str, float] = defaultdict(float)
    cnt: dict[str, int] = defaultdict(int)
    for d, v in days.items():
        s = SEASON_NORTH[d.month]
        s = _FLIP[s] if southern else s
        tot[s] += v
        cnt[s] += 1
    if len(cnt) < 2:
        return None
    # Compare daily averages so a part-year doesn't skew it
    per_day = {s: tot[s] / cnt[s] for s in tot}
    total = sum(per_day.values())
    share = {s: round(100 * v / total) for s, v in per_day.items()}
    top = max(share, key=share.get)
    return {"share_pct": share, "top": top, "complete": len(cnt) == 4}


def quiet_hour(prof: list[float]) -> dict | None:
    if not any(prof):
        return None
    h = min(range(24), key=prof.__getitem__)
    return {"hour": h, "watts": round(prof[h] * 1000)}


def day_of_year(days: dict[date, float]) -> dict | None:
    """The day furthest above a normal day (vs the median)."""
    if len(days) < 30:
        return None
    med = pystats.median(days.values())
    if med <= 0:
        return None
    d, v = max(days.items(), key=lambda kv: kv[1])
    return {"date": d.isoformat(), "kwh": round(v, 1), "times_normal": round(v / med, 1),
            "weekday": WEEKDAYS[d.weekday()]}


def sun_streak(solar: dict[date, float], grid: dict[date, float]) -> dict | None:
    """Longest run of days where solar produced at least as much as was imported."""
    best = cur = None
    for d in sorted(solar):
        if solar[d] > 0 and solar[d] >= grid.get(d, 0):
            cur = (cur[0], d, cur[2] + 1) if cur and (d - cur[1]).days == 1 else (d, d, 1)
            if not best or cur[2] > best[2]:
                best = cur
        else:
            cur = None
    sunny = sum(1 for d in solar if solar[d] > 0 and solar[d] >= grid.get(d, 0))
    if not best:
        return None
    return {"days": best[2], "from": best[0].isoformat(), "to": best[1].isoformat(), "total_days": sunny}


def personality(prof: list[float], wk: dict | None, ss: dict | None,
                self_pct: float | None, standby_share: float | None) -> dict | None:
    """Pick the strongest of eight energy personalities."""
    total = sum(prof)
    if not total:
        return None
    share = lambda hours: sum(prof[h] for h in hours) / total / (len(hours) / 24)  # 1.0 = average
    peak = max(range(24), key=prof.__getitem__)
    lo = min(p for p in prof if p > 0) if any(prof) else 0
    flat = max(prof) / lo if lo else 99
    winter = summer = None
    if ss and ss.get("share_pct"):
        winter, summer = ss["share_pct"].get("Winter"), ss["share_pct"].get("Summer")

    cand = {
        "night_owl": share([22, 23, 0, 1, 2]) - 1.05,
        "early_bird": share([5, 6, 7, 8]) - 1.1,
        "weekend_warrior": (wk["weekend_ratio"] - 1.08) * 3 if wk else -1,
        "seasonal_swinger": ((winter / summer) - 1.6) / 2 if winter and summer else -1,
        "sun_chaser": (self_pct - 35) / 40 if self_pct is not None else -1,
        "peak_dodger": 0.85 - share([16, 17, 18, 19]),
        "always_on": (standby_share - 0.35) * 2 if standby_share is not None else -1,
        "steady_eddie": (1.8 - flat) / 2,
    }
    key = max(cand, key=cand.get)
    if cand[key] <= 0:
        key = "homebody"
    copy = {
        "night_owl": ("The Night Owl", "🦉", "Your home comes alive after dark."),
        "early_bird": ("The Early Bird", "🐦", "Your home is up and running before most."),
        "weekend_warrior": ("The Weekend Warrior", "🎉", f"Weekends ran {round((wk or {}).get('weekend_ratio', 1) * 100 - 100)}% hotter than weekdays."),
        "seasonal_swinger": ("The Seasonal Swinger", "🍂", f"Winter days used {round((winter or 1) / (summer or 1), 1)}× a summer day."),
        "sun_chaser": ("The Sun Chaser", "🌞", f"{round(self_pct or 0)}% of your power came from your own roof."),
        "peak_dodger": ("The Peak Dodger", "🥷", "You quietly sidestepped the 4–8pm rush."),
        "always_on": ("The Always-On", "🔌", "A big slice of your energy goes on things that never switch off."),
        "steady_eddie": ("The Steady Eddie", "🧘", "Your home hums along at a remarkably even pace."),
        "homebody": ("The Homebody", "🛋️", f"Your home used the most energy around {peak:02d}:00."),
    }[key]
    return {"type": key, "title": copy[0], "emoji": copy[1], "blurb": copy[2], "peak_hour": peak}


_HOUR_HUE = [(range(22, 24), 250), (range(0, 5), 250), (range(5, 10), 38), (range(10, 17), 185), (range(17, 22), 330)]
_SEASON_HUE = {"Winter": 210, "Spring": 125, "Summer": 48, "Autumn": 20}
_HOUR_WORD = {250: "midnight indigo", 38: "sunrise amber", 185: "daylight teal", 330: "evening magenta"}
_SEASON_WORD = {"Winter": "frost blue", "Spring": "fresh green", "Summer": "sunshine yellow", "Autumn": "ember orange"}


def aura(peak_hour: int | None, top_season: str | None) -> dict | None:
    if peak_hour is None:
        return None
    hue = next(h for r, h in _HOUR_HUE if peak_hour in r)
    s_hue = _SEASON_HUE.get(top_season or "", (hue + 60) % 360)
    words = _HOUR_WORD[hue] + (f" with a {_SEASON_WORD[top_season]} glow" if top_season in _SEASON_WORD else "")
    return {"colors": [f"hsl({hue} 80% 55%)", f"hsl({s_hue} 85% 50%)"], "words": words}
