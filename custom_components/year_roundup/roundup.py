"""Assemble the yearly roundup.

Only data that covers the whole year is used: Home Assistant's long-term
statistics (never purged) plus the device/entity registries.
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
from .lts import async_read_lts

_LOGGER = logging.getLogger(__name__)


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


def _persona(hours: list[float]) -> dict | None:
    """Personality from the whole year's average energy use by hour."""
    if not any(hours):
        return None
    peak = max(range(24), key=lambda h: hours[h])
    blurb = f"Your home used the most energy around {peak:02d}:00."
    if peak >= 22 or peak <= 3:
        return {"title": "The Night Owl", "emoji": "🦉", "blurb": blurb, "peak_hour": peak}
    if 5 <= peak <= 8:
        return {"title": "The Early Bird", "emoji": "🐦", "blurb": blurb, "peak_hour": peak}
    return {"title": "The Homebody", "emoji": "🛋️", "blurb": blurb, "peak_hour": peak}


def _fact(metric: str, value: float | None, year: int) -> str | None:
    if not value:
        return None
    pick = comparisons.best(metric, value, year)
    return pick["text"] if pick else None


async def async_build_roundup(hass: HomeAssistant, year: int) -> dict[str, Any]:
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
    hours = (energy or {}).pop("hourly_profile", None) or [0] * 24

    out: dict[str, Any] = {
        "year": year,
        "home_name": hass.config.location_name,
        "persona": _persona(hours),
        "hours": hours,
        "setup": _setup(hass, start),
        "energy": energy,
        **lts,
    }

    if energy:
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
