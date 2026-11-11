"""Assemble the yearly roundup.

Sources, best first:
  1. Long-term statistics (never purged): energy, water, gas, devices, power,
     batteries, air, steps, distance, data, counters.
  2. Recorder history or this integration's own counters, whichever reaches
     further back: lights, doors, motion, automations, media, people.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import logging
import statistics as pystats
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from . import comparisons
from .const import SECONDS_SAVED_PER_AUTOMATION
from .history import async_read_year
from .lts import async_read_lts
from .tracker import RoundupTracker

_LOGGER = logging.getLogger(__name__)


def _name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    return state.name if state else entity_id


def _top(hass: HomeAssistant, bucket: dict[str, float], n: int = 5, names: bool = True):
    ranked = sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"name": _name(hass, k) if names else k, "value": round(v, 1)} for k, v in ranked]


async def _stats(hass, start, end, ids, types, units=None, period="day"):
    if not ids:
        return {}
    return await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, end, set(ids), period, units, set(types)
    )


async def _prefs(hass: HomeAssistant) -> dict:
    try:
        from homeassistant.components.energy.data import async_get_manager

        return (await async_get_manager(hass)).data or {}
    except Exception:  # energy not set up
        return {}


async def _energy(hass: HomeAssistant, start: datetime, end: datetime, prefs: dict) -> dict | None:
    grid, export, solar = [], [], []
    for src in prefs.get("energy_sources", []):
        if src.get("type") == "grid":
            grid += [f["stat_energy_from"] for f in src.get("flow_from", []) if f.get("stat_energy_from")]
            export += [f["stat_energy_to"] for f in src.get("flow_to", []) if f.get("stat_energy_to")]
            if src.get("stat_energy_from"):
                grid.append(src["stat_energy_from"])
            if src.get("stat_energy_to"):
                export.append(src["stat_energy_to"])
        elif src.get("type") == "solar" and src.get("stat_energy_from"):
            solar.append(src["stat_energy_from"])
    if not grid and not solar:
        return None

    hourly = await _stats(hass, start, end, grid + solar + export, {"change"}, {"energy": "kWh"}, "hour")

    def series(ids):
        out = []
        for sid in ids:
            out += [(r["start"], r["change"]) for r in hourly.get(sid, []) if r.get("change") is not None]
        return out

    def summarise(rows):
        daily: dict[str, float] = defaultdict(float)
        for ts, kwh in rows:
            daily[dt_util.as_local(dt_util.utc_from_timestamp(ts)).date().isoformat()] += kwh
        if not daily:
            return None
        monthly = [0.0] * 12
        for day, kwh in daily.items():
            monthly[int(day[5:7]) - 1] += kwh
        peak = max(daily.items(), key=lambda kv: kv[1])
        return {
            "total_kwh": round(sum(daily.values()), 1),
            "monthly_kwh": [round(m, 1) for m in monthly],
            "peak_day": {"date": peak[0], "kwh": round(peak[1], 1)},
        }

    grid_rows = series(grid)
    out: dict[str, Any] = {"grid": summarise(grid_rows), "solar": summarise(series(solar))}
    exported = sum(k for _, k in series(export))
    if exported > 0:
        out["export_kwh"] = round(exported, 1)
    if out["solar"] and out["grid"]:
        self_used = max(out["solar"]["total_kwh"] - exported, 0)
        used = out["grid"]["total_kwh"] + self_used
        if used:
            out["self_powered_pct"] = round(100 * self_used / used)

    # Energy by hour of day (whole year) and overnight standby load
    profile, counts = [0.0] * 24, [0] * 24
    night_min: dict[str, float] = {}
    by_hour: dict[float, float] = defaultdict(float)
    for ts, kwh in grid_rows:
        by_hour[ts] += kwh
    for ts, kwh in by_hour.items():
        local = dt_util.as_local(dt_util.utc_from_timestamp(ts))
        profile[local.hour] += kwh
        counts[local.hour] += 1
        if 1 <= local.hour <= 4:
            day = local.date().isoformat()
            night_min[day] = min(night_min.get(day, kwh), kwh)
    if any(counts):
        out["hourly_profile"] = [round(p / c, 3) if c else 0 for p, c in zip(profile, counts)]
    if len(night_min) >= 7:
        out["standby_w"] = round(pystats.median(night_min.values()) * 1000)
    return out


def _setup(hass: HomeAssistant, start: datetime) -> dict:
    devices = dr.async_get(hass).devices.values()
    entities = er.async_get(hass).entities.values()
    new_devices = [d for d in devices if getattr(d, "created_at", None) and d.created_at >= start]
    new_automations = [
        e for e in entities
        if e.domain == "automation" and getattr(e, "created_at", None) and e.created_at >= start
    ]
    newest = max(new_devices, key=lambda d: d.created_at) if new_devices else None
    return {
        "devices_total": len(devices),
        "devices_added": len(new_devices),
        "entities_total": len(entities),
        "integrations": len({e.domain for e in hass.config_entries.async_entries()}),
        "automations": len(hass.states.async_entity_ids("automation")),
        "automations_added": len(new_automations),
        "newest_device": (newest.name_by_user or newest.name) if newest else None,
    }


def _persona(hours: list[float], automation_runs: int, manual: int, source: str) -> dict:
    if not any(hours):
        return {"title": "The Newcomer", "emoji": "🌱", "blurb": "Your story is just getting started."}
    peak = max(range(24), key=lambda h: hours[h])
    what = "used the most energy" if source == "energy" else "was busiest"
    blurb = f"Your home {what} around {peak:02d}:00."
    if automation_runs > manual * 3 and automation_runs > 100:
        return {"title": "The Automation Wizard", "emoji": "🧙", "blurb": "Your home mostly runs itself.", "peak_hour": peak}
    if peak >= 22 or peak <= 3:
        return {"title": "The Night Owl", "emoji": "🦉", "blurb": blurb, "peak_hour": peak}
    if 5 <= peak <= 8:
        return {"title": "The Early Bird", "emoji": "🐦", "blurb": blurb, "peak_hour": peak}
    return {"title": "The Homebody", "emoji": "🛋️", "blurb": blurb, "peak_hour": peak}


def _activity(tracker: RoundupTracker, recorder: dict, year: int) -> dict:
    """Use whichever of recorder history / own counters reaches further back."""
    own = tracker.data.get(str(year))
    rec_from = recorder["coverage"]["from"]
    if own and own.get("first_seen", "9999")[:10] < rec_from:
        own = dict(own)
        own["coverage"] = {
            "from": own["first_seen"][:10],
            "partial": own["first_seen"][:10] > f"{year}-01-02",
            "source": "counters",
        }
        return own
    recorder["coverage"]["source"] = "recorder"
    return recorder


def _fact(metric: str, value: float | None, year: int) -> str | None:
    if not value:
        return None
    pick = comparisons.best(metric, value, year)
    return pick["text"] if pick else None


async def async_build_roundup(hass: HomeAssistant, tracker: RoundupTracker, year: int) -> dict[str, Any]:
    tz = dt_util.get_default_time_zone()
    start = datetime(year, 1, 1, tzinfo=tz)
    end = min(datetime(year + 1, 1, 1, tzinfo=tz), dt_util.now())
    prefs = await _prefs(hass)

    async def safe(name, coro, default=None):
        try:
            return await coro
        except Exception:
            _LOGGER.exception("Year Roundup: failed building %s", name)
            return default

    energy = await safe("energy", _energy(hass, start, end, prefs))
    lts = await safe("statistics", async_read_lts(hass, start, end, prefs), {}) or {}
    recorder = await safe("history", async_read_year(hass, start, end))
    if recorder is None:
        recorder = {"coverage": {"from": end.date().isoformat(), "partial": True}}
    y = _activity(tracker, recorder, year)
    cov = y["coverage"]
    days_covered = (end.date() - datetime.fromisoformat(cov["from"]).date()).days + 1

    hours, hours_source = y.get("hours", [0] * 24), "activity"
    if (days_covered < 60 or not any(hours)) and energy and energy.get("hourly_profile"):
        hours, hours_source = energy["hourly_profile"], "energy"

    lights = {k: v for k, v in y.get("on_seconds", {}).items() if k.startswith("light.")}
    automation_runs = int(sum(y.get("automations", {}).values()))
    manual = int(sum(y.get("toggles", {}).values()))
    days = y.get("days", {})
    door_total = int(sum(y.get("door_opens", {}).values()))
    light_hours = round(sum(lights.values()) / 3600)
    music_hours = round(sum(y.get("media_seconds", {}).values()) / 3600)

    out: dict[str, Any] = {
        "year": year,
        "home_name": hass.config.location_name,
        "coverage": {**cov, "days": days_covered},
        "persona": _persona(hours, automation_runs, manual, hours_source),
        "hours": hours,
        "hours_source": hours_source,
        "busiest_day": (
            dict(zip(("date", "events"), max(days.items(), key=lambda kv: kv[1]))) if days else None
        ),
        "lights": {
            "total_hours": light_hours,
            "top": [{"name": t["name"], "value": round(t["value"] / 3600)} for t in _top(hass, lights)],
            "toggles": manual,
            "fact": _fact("light_hours", light_hours, year),
        },
        "doors": {
            "total": door_total,
            "top": _top(hass, y.get("door_opens", {})),
            "fact": _fact("door_opens", door_total * 365 / max(days_covered, 1), year),
        },
        "motion": int(sum(y.get("motion", {}).values())),
        "automations": {
            "runs": automation_runs,
            "top": _top(hass, y.get("automations", {}), names=False),
            "hours_saved": round(automation_runs * SECONDS_SAVED_PER_AUTOMATION / 3600, 1),
            "fact": _fact("automation_runs", automation_runs, year),
        },
        "music": {
            "hours": music_hours,
            "top_artists": _top(hass, y.get("artists", {}), names=False),
            "top_tracks": _top(hass, y.get("tracks", {}), names=False),
            "fact": _fact("music_hours", music_hours, year),
        },
        "people": {
            "arrivals": int(sum(y.get("arrivals", {}).values())),
            "top_zones": _top(hass, y.get("zones", {}), 3, names=False),
        },
        "setup": _setup(hass, start),
        "energy": energy,
        **lts,
    }

    # Comparisons for the year-long sections
    if energy:
        energy.pop("hourly_profile", None)
        if energy.get("grid"):
            energy["fact"] = _fact("grid_kwh", energy["grid"]["total_kwh"], year)
        if energy.get("solar"):
            energy["solar_fact"] = _fact("solar_kwh", energy["solar"]["total_kwh"], year)
        if energy.get("standby_w"):
            energy["standby_fact"] = _fact("standby_w", energy["standby_w"], year)
    if w := out.get("water"):
        w["fact"] = _fact("water_l", w["litres"], year)
    if g := out.get("gas"):
        g["fact"] = _fact("gas_m3", g["value"], year) if g["unit"] == "m³" else None
    if s := out.get("steps"):
        s["fact"] = _fact("walk_km", s["total"] * 0.0008, year)  # ~0.8 m per step (assumed)
    if b := out.get("batteries"):
        b["fact"] = _fact("batteries_replaced", b["replaced"], year)
    if st := out.get("screen_time"):
        st["fact"] = _fact("tv_hours", st["top"][0]["hours"], year)
    return out
