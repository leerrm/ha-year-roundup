"""Year-long metrics from Home Assistant's long-term statistics.

Long-term statistics are never purged, so everything here covers the whole
year (or since the sensor first existed). Each statistic is classified by
unit class, device class and unit, then summarised.
"""

from __future__ import annotations

from collections import defaultdict
import logging
import re
import statistics as pystats
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

POWER_ON_W = 5  # a device counts as "on" in an hour if it averaged more than this
POWER_MAX_DEVICE_W = 8000  # above this it's a whole-home meter / inverter, not a device
_NOT_A_DEVICE = re.compile(r"solar|pv|inverter|grid|mains|house|home|total|import|export|battery|phase", re.I)
_DATA_TO_GB = {"B": 1e-9, "kB": 1e-6, "KB": 1e-6, "MB": 1e-3, "GB": 1, "TB": 1e3, "PB": 1e6,
               "KiB": 1.024e-6, "MiB": 1.048576e-3, "GiB": 1.073741824, "TiB": 1099.511627776,
               "kbit": 1.25e-7, "Mbit": 1.25e-4, "Gbit": 0.125}


def _has_mean(meta: dict) -> bool:
    if meta.get("has_mean"):
        return True
    mean_type = meta.get("mean_type")
    try:
        return mean_type is not None and int(mean_type) != 0
    except (TypeError, ValueError):
        return str(mean_type).lower() not in ("none", "0", "")


def _day(ts: float) -> str:
    return dt_util.as_local(dt_util.utc_from_timestamp(ts)).date().isoformat()


async def _query(hass, start, end, ids, period, types, units=None) -> dict[str, list[dict]]:
    if not ids:
        return {}
    return await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, end, set(ids), period, units, set(types)
    )


class _Names:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.ents = er.async_get(hass)
        self.devs = dr.async_get(hass)
        self.areas = ar.async_get(hass)

    def name(self, sid: str, meta: dict) -> str:
        state = self.hass.states.get(sid)
        return (state.name if state else None) or meta.get("name") or sid

    def area(self, sid: str) -> str | None:
        ent = self.ents.async_get(sid)
        if not ent:
            return None
        area_id = ent.area_id
        if not area_id and ent.device_id and (dev := self.devs.async_get(ent.device_id)):
            area_id = dev.area_id
        area = self.areas.async_get_area(area_id) if area_id else None
        return area.name if area else None

    def platform(self, sid: str) -> str | None:
        ent = self.ents.async_get(sid)
        return ent.platform if ent else None


def _classify(hass: HomeAssistant, metas: list[dict], exclude: set[str]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for meta in metas:
        sid = meta["statistic_id"]
        if sid in exclude:
            continue
        state = hass.states.get(sid)
        dc = state.attributes.get("device_class") if state else None
        unit = meta.get("statistics_unit_of_measurement") or meta.get("display_unit_of_measurement")
        uclass = meta.get("unit_class")
        has_sum, has_mean = bool(meta.get("has_sum")), _has_mean(meta)
        if uclass == "power" and has_mean:
            groups["power"].append(meta)
        elif dc == "battery" and unit == "%" and has_mean:
            groups["battery"].append(meta)
        elif dc == "carbon_dioxide" and has_mean:
            groups["co2"].append(meta)
        elif unit and unit.lower() in ("steps", "step") :
            groups["steps"].append(meta)
        elif dc == "precipitation" and has_sum:
            groups["rain"].append(meta)
        elif dc == "water" and has_sum:
            groups["water"].append(meta)
        elif dc == "gas" and has_sum:
            groups["gas"].append(meta)
        elif uclass == "distance" and has_sum:
            groups["distance"].append(meta)
        elif unit in _DATA_TO_GB and has_sum:
            groups["data"].append(meta)
        elif has_sum and not uclass and unit not in ("%",):
            groups["counter"].append(meta)
    return groups


async def async_read_lts(hass: HomeAssistant, start, end, prefs: dict) -> dict[str, Any]:
    """Return year-long metrics from long-term statistics."""
    metas = await get_instance(hass).async_add_executor_job(list_statistic_ids, hass)
    names = _Names(hass)
    sources = prefs.get("energy_sources", [])

    def pref_ids(kind: str, key: str = "stat_energy_from") -> list[str]:
        return [s[key] for s in sources if s.get("type") == kind and s.get(key)]

    water_pref, gas_pref = pref_ids("water"), pref_ids("gas")
    devices_pref = [d["stat_consumption"] for d in prefs.get("device_consumption", []) if d.get("stat_consumption")]
    exclude = set(water_pref + gas_pref + devices_pref)
    for s in sources:
        for f in s.get("flow_from", []) + s.get("flow_to", []):
            exclude.update(v for k, v in f.items() if k.startswith("stat_") and isinstance(v, str))
        exclude.update(v for k, v in s.items() if k.startswith("stat_") and isinstance(v, str))
    groups = _classify(hass, metas, exclude)
    by_id = {m["statistic_id"]: m for m in metas}
    out: dict[str, Any] = {}

    def total(rows: list[dict]) -> float:
        return sum(r["change"] for r in rows if r.get("change") is not None)

    # --- Energy per device (Energy dashboard "individual devices") ---
    if devices_pref:
        rows = await _query(hass, start, end, devices_pref, "month", {"change"}, {"energy": "kWh"})
        devs = sorted(
            ({"name": names.name(sid, by_id.get(sid, {})), "kwh": round(total(rows.get(sid, [])), 1)} for sid in devices_pref),
            key=lambda d: d["kwh"], reverse=True,
        )
        devs = [d for d in devs if d["kwh"] > 0]
        if devs:
            out["devices"] = {"top": devs[:5], "total_kwh": round(sum(d["kwh"] for d in devs), 1)}

    # --- Water & gas: prefer Energy dashboard sources, else the biggest meter ---
    async def biggest(ids: list[str], units: dict, daily: bool = False):
        if not ids:
            return None
        rows = await _query(hass, start, end, ids, "day", {"change"}, units)
        totals = {sid: total(r) for sid, r in rows.items()}
        if not totals:
            return None
        if ids is water_pref or ids is gas_pref:
            value = sum(totals.values())
            series = defaultdict(float)
            for r in rows.values():
                for row in r:
                    if row.get("change"):
                        series[_day(row["start"])] += row["change"]
        else:
            sid = max(totals, key=totals.get)
            value = totals[sid]
            series = {_day(row["start"]): row["change"] for row in rows[sid] if row.get("change")}
        if value <= 0:
            return None
        peak = max(series.items(), key=lambda kv: kv[1]) if series else None
        return {"total": round(value, 1), "peak_day": {"date": peak[0], "value": round(peak[1], 1)} if peak else None}

    water = await biggest(water_pref or [m["statistic_id"] for m in groups["water"]], {"volume": "L"})
    if water:
        out["water"] = {"litres": water["total"], "peak_day": water["peak_day"]}
    gas = await biggest(gas_pref or [m["statistic_id"] for m in groups["gas"]], {"volume": "m³", "energy": "kWh"})
    if gas:
        gas_id = (gas_pref or [m["statistic_id"] for m in groups["gas"]])[0]
        unit = (by_id.get(gas_id, {}).get("statistics_unit_of_measurement") or "m³")
        out["gas"] = {"value": gas["total"], "unit": "kWh" if "Wh" in unit else "m³", "peak_day": gas["peak_day"]}

    # --- Rain ---
    rain = await biggest([m["statistic_id"] for m in groups["rain"]], {"distance": "mm"})
    if rain:
        out["rain"] = {"mm": rain["total"], "wettest_day": rain["peak_day"]}

    # --- Devices on-time from power sensors (hourly means) ---
    power_ids = [m["statistic_id"] for m in groups["power"] if not _NOT_A_DEVICE.search(m["statistic_id"])]
    if power_ids:
        rows = await _query(hass, start, end, power_ids, "hour", {"mean"}, {"power": "W"})
        on = []
        for sid, series in rows.items():
            means = [r["mean"] for r in series if r.get("mean") is not None]
            if not means or max(means) > POWER_MAX_DEVICE_W:
                continue
            hours = sum(1 for m in means if m > POWER_ON_W)
            if hours:
                on.append({"name": names.name(sid, by_id[sid]), "hours": hours, "avg_w": round(pystats.fmean(means), 1)})
        on.sort(key=lambda d: d["hours"], reverse=True)
        if on:
            out["screen_time"] = {"top": on[:5]}
            always_on = max(on, key=lambda d: d["avg_w"])
            out["always_on"] = always_on

    # --- Batteries replaced (big daily jump on non-rechargeable devices) ---
    batt_ids = [m["statistic_id"] for m in groups["battery"] if names.platform(m["statistic_id"]) != "mobile_app"]
    if batt_ids:
        rows = await _query(hass, start, end, batt_ids, "day", {"min", "max"})
        swaps: list[dict] = []
        for sid, series in rows.items():
            count, prev_min, prev_max = 0, None, None
            for r in series:
                mx, mn = r.get("max"), r.get("min")
                # New battery: today's peak is high, yesterday went low, and today's
                # peak is well above yesterday's (so the day after a swap isn't counted)
                if (
                    None not in (prev_min, prev_max, mx)
                    and mx >= 90 and mx - prev_min >= 40 and mx - prev_max >= 30
                ):
                    count += 1
                prev_min, prev_max = mn, mx
            if 0 < count <= 12:  # more than monthly = rechargeable, skip
                swaps.append({"name": names.name(sid, by_id[sid]), "swaps": count})
        if swaps:
            swaps.sort(key=lambda d: d["swaps"], reverse=True)
            out["batteries"] = {"replaced": sum(s["swaps"] for s in swaps), "hungriest": swaps[0], "top": swaps[:5]}

    # --- Air quality (CO2) ---
    co2_ids = [m["statistic_id"] for m in groups["co2"]]
    if co2_ids:
        rows = await _query(hass, start, end, co2_ids, "day", {"mean", "max"})
        rooms = []
        for sid, series in rows.items():
            means = [r["mean"] for r in series if r.get("mean") is not None]
            if len(means) < 7:
                continue
            worst = max((r for r in series if r.get("max") is not None), key=lambda r: r["max"], default=None)
            rooms.append({
                "name": names.area(sid) or names.name(sid, by_id[sid]),
                "avg_ppm": round(pystats.fmean(means)),
                "worst": {"date": _day(worst["start"]), "ppm": round(worst["max"])} if worst else None,
            })
        if rooms:
            rooms.sort(key=lambda r: r["avg_ppm"], reverse=True)
            out["air"] = {"stuffiest": rooms[0], "freshest": rooms[-1], "rooms": len(rooms)}

    # --- Steps (companion app) ---
    step_metas = groups["steps"]
    if step_metas:
        sum_ids = [m["statistic_id"] for m in step_metas if m.get("has_sum")]
        mean_ids = [m["statistic_id"] for m in step_metas if not m.get("has_sum")]
        people = []
        if sum_ids:
            rows = await _query(hass, start, end, sum_ids, "month", {"change"})
            people += [{"name": names.name(s, by_id[s]), "steps": round(total(r))} for s, r in rows.items()]
        if mean_ids:  # daily counters that reset at midnight: sum the daily maxima
            rows = await _query(hass, start, end, mean_ids, "day", {"max"})
            people += [{"name": names.name(s, by_id[s]), "steps": round(sum(x["max"] for x in r if x.get("max")))} for s, r in rows.items()]
        people = sorted((p for p in people if p["steps"] > 0), key=lambda p: p["steps"], reverse=True)
        if people:
            out["steps"] = {"total": sum(p["steps"] for p in people), "top": people[:5]}

    # --- Distance counters (car odometer, vacuum, mower...) ---
    dist_ids = [m["statistic_id"] for m in groups["distance"]]
    if dist_ids:
        rows = await _query(hass, start, end, dist_ids, "month", {"change"}, {"distance": "km"})
        items = sorted(
            ({"name": names.name(s, by_id[s]), "km": round(total(r), 1)} for s, r in rows.items()),
            key=lambda d: d["km"], reverse=True,
        )
        items = [i for i in items if i["km"] >= 1]
        if items:
            out["distance"] = {"top": items[:5]}

    # --- Data transferred ---
    data_ids = [m["statistic_id"] for m in groups["data"]]
    if data_ids:
        rows = await _query(hass, start, end, data_ids, "month", {"change"})
        best = None
        for sid, r in rows.items():
            unit = by_id[sid].get("statistics_unit_of_measurement")
            gb = total(r) * _DATA_TO_GB.get(unit, 0)
            if best is None or gb > best["gb"]:
                best = {"name": names.name(sid, by_id[sid]), "gb": round(gb, 1)}
        if best and best["gb"] >= 1:
            out["data"] = best

    # --- Anything else that counts up (printer pages, cycles...) ---
    cnt_ids = [m["statistic_id"] for m in groups["counter"]]
    if cnt_ids:
        rows = await _query(hass, start, end, cnt_ids, "month", {"change"})
        items = sorted(
            ({"name": names.name(s, by_id[s]), "value": round(total(r)),
              "unit": by_id[s].get("statistics_unit_of_measurement") or ""} for s, r in rows.items()),
            key=lambda d: d["value"], reverse=True,
        )
        items = [i for i in items if i["value"] >= 10]
        if items:
            out["counters"] = {"top": items[:5]}

    # When do long-term statistics start?
    return out
