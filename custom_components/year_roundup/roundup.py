"""Assemble the yearly roundup from live counters + long-term statistics."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import KWH_PER_EV_KM, KWH_PER_KETTLE, SECONDS_SAVED_PER_AUTOMATION
from .tracker import RoundupTracker

_LOGGER = logging.getLogger(__name__)
_SKIP_TEMP = ("cpu", "processor", "battery", "chip", "nvme", "disk", "soc", "gpu")


def _name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    return state.name if state else entity_id


def _top(hass: HomeAssistant, bucket: dict[str, float], n: int = 5, names: bool = True):
    ranked = sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [
        {"name": _name(hass, k) if names else k, "value": round(v, 1)} for k, v in ranked
    ]


async def _stats(hass, start, end, ids, types, units=None):
    if not ids:
        return {}
    return await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, end, set(ids), "day", units, set(types)
    )


async def _energy(hass: HomeAssistant, start: datetime, end: datetime) -> dict | None:
    try:
        from homeassistant.components.energy.data import async_get_manager

        prefs = (await async_get_manager(hass)).data or {}
    except Exception:  # energy not configured / API changed
        return None

    grid, solar = [], []
    for src in prefs.get("energy_sources", []):
        if src.get("type") == "grid":
            grid += [f["stat_energy_from"] for f in src.get("flow_from", [])]
            if src.get("stat_energy_from"):
                grid.append(src["stat_energy_from"])
        elif src.get("type") == "solar":
            solar.append(src["stat_energy_from"])
    if not grid and not solar:
        return None

    rows = await _stats(hass, start, end, grid + solar, {"change"}, {"energy": "kWh"})

    def summarise(ids):
        daily: dict[str, float] = defaultdict(float)
        for sid in ids:
            for row in rows.get(sid, []):
                if row.get("change") is not None:
                    day = dt_util.as_local(dt_util.utc_from_timestamp(row["start"])).date()
                    daily[day.isoformat()] += row["change"]
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

    grid_s, solar_s = summarise(grid), summarise(solar)
    out = {"grid": grid_s, "solar": solar_s}
    if grid_s:
        out["kettles"] = round(grid_s["total_kwh"] / KWH_PER_KETTLE)
        out["ev_km"] = round(grid_s["total_kwh"] / KWH_PER_EV_KM)
    return out


async def _climate(hass: HomeAssistant, start: datetime, end: datetime) -> dict | None:
    ids = [
        s.entity_id
        for s in hass.states.async_all("sensor")
        if s.attributes.get("device_class") == "temperature"
        and s.attributes.get("state_class") == "measurement"
        and not any(word in s.entity_id for word in _SKIP_TEMP)
    ]
    unit = hass.config.units.temperature_unit
    rows = await _stats(hass, start, end, ids, {"max", "min"}, {"temperature": unit})
    hottest = coldest = None
    for sid, series in rows.items():
        for row in series:
            day = dt_util.as_local(dt_util.utc_from_timestamp(row["start"])).date().isoformat()
            if row.get("max") is not None and (hottest is None or row["max"] > hottest["value"]):
                hottest = {"value": round(row["max"], 1), "date": day, "name": _name(hass, sid)}
            if row.get("min") is not None and (coldest is None or row["min"] < coldest["value"]):
                coldest = {"value": round(row["min"], 1), "date": day, "name": _name(hass, sid)}
    if not hottest:
        return None
    return {"unit": unit, "hottest": hottest, "coldest": coldest}


def _setup(hass: HomeAssistant, start: datetime) -> dict:
    devices = dr.async_get(hass).devices.values()
    entities = er.async_get(hass).entities.values()
    new_devices = [
        d for d in devices if getattr(d, "created_at", None) and d.created_at >= start
    ]
    newest = max(new_devices, key=lambda d: d.created_at) if new_devices else None
    return {
        "devices_total": len(devices),
        "devices_added": len(new_devices),
        "entities_total": len(entities),
        "integrations": len({e.domain for e in hass.config_entries.async_entries()}),
        "automations": len(hass.states.async_entity_ids("automation")),
        "newest_device": (newest.name_by_user or newest.name) if newest else None,
    }


def _persona(hours: list[int], automation_runs: int, manual: int) -> dict:
    if sum(hours) == 0:
        return {"title": "The Newcomer", "emoji": "🌱", "blurb": "Your story is just getting started."}
    peak = max(range(24), key=lambda h: hours[h])
    if automation_runs > manual * 3:
        return {"title": "The Automation Wizard", "emoji": "🧙", "blurb": "Your home mostly runs itself.", "peak_hour": peak}
    if peak >= 22 or peak <= 3:
        return {"title": "The Night Owl", "emoji": "🦉", "blurb": f"Your home was busiest around {peak:02d}:00.", "peak_hour": peak}
    if 5 <= peak <= 8:
        return {"title": "The Early Bird", "emoji": "🐦", "blurb": f"Things got going around {peak:02d}:00.", "peak_hour": peak}
    return {"title": "The Homebody", "emoji": "🛋️", "blurb": f"Peak activity hit at {peak:02d}:00.", "peak_hour": peak}


async def async_build_roundup(hass: HomeAssistant, tracker: RoundupTracker, year: int) -> dict[str, Any]:
    tz = dt_util.get_default_time_zone()
    start = datetime(year, 1, 1, tzinfo=tz)
    end = min(datetime(year + 1, 1, 1, tzinfo=tz), dt_util.now())
    y = tracker.data.get(str(year)) or {}

    lights = {k: v for k, v in y.get("on_seconds", {}).items() if k.startswith("light.")}
    automation_runs = int(sum(y.get("automations", {}).values()))
    manual = int(sum(y.get("toggles", {}).values()))
    days = y.get("days", {})

    out: dict[str, Any] = {
        "year": year,
        "home_name": hass.config.location_name,
        "tracking_since": y.get("first_seen"),
        "persona": _persona(y.get("hours", [0] * 24), automation_runs, manual),
        "hours": y.get("hours", [0] * 24),
        "busiest_day": (
            dict(zip(("date", "events"), max(days.items(), key=lambda kv: kv[1]))) if days else None
        ),
        "lights": {
            "total_hours": round(sum(lights.values()) / 3600),
            "top": [{"name": t["name"], "value": round(t["value"] / 3600)} for t in _top(hass, lights)],
            "toggles": manual,
        },
        "doors": {"total": int(sum(y.get("door_opens", {}).values())), "top": _top(hass, y.get("door_opens", {}))},
        "motion": int(sum(y.get("motion", {}).values())),
        "automations": {
            "runs": automation_runs,
            "top": _top(hass, y.get("automations", {}), names=False),
            "hours_saved": round(automation_runs * SECONDS_SAVED_PER_AUTOMATION / 3600, 1),
        },
        "music": {
            "hours": round(sum(y.get("media_seconds", {}).values()) / 3600),
            "top_artists": _top(hass, y.get("artists", {}), names=False),
            "top_tracks": _top(hass, y.get("tracks", {}), names=False),
        },
        "people": {
            "arrivals": int(sum(y.get("arrivals", {}).values())),
            "top_zones": _top(hass, y.get("zones", {}), 3, names=False),
        },
        "setup": _setup(hass, start),
    }
    for key, fn in (("energy", _energy), ("climate", _climate)):
        try:
            out[key] = await fn(hass, start, end)
        except Exception:
            _LOGGER.exception("Failed building %s section", key)
            out[key] = None
    return out
