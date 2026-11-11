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

from . import comparisons, insights
from .lts import async_read_lts

_LOGGER = logging.getLogger(__name__)
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


async def _stats(hass, start, end, ids, types, units=None, period="day"):
    ids = [i for i in ids if i]
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


def _hourly(rows: dict, ids: list[str]) -> dict[datetime, float]:
    """Sum 'change' across statistics into {local hour: kWh}."""
    out: dict[datetime, float] = defaultdict(float)
    for sid in ids:
        for r in rows.get(sid, []):
            if r.get("change") is not None:
                out[dt_util.as_local(dt_util.utc_from_timestamp(r["start"]))] += r["change"]
    return dict(out)


def _monthly(days: dict) -> list[float]:
    m = [0.0] * 12
    for d, v in days.items():
        m[d.month - 1] += v
    return [round(x, 1) for x in m]


def _sources(prefs: dict) -> dict[str, list[str]]:
    s: dict[str, list[str]] = defaultdict(list)
    for src in prefs.get("energy_sources", []):
        t = src.get("type")
        if t == "grid":
            for f in src.get("flow_from", []):
                s["grid"].append(f.get("stat_energy_from"))
                s["cost"].append(f.get("stat_cost"))
            for f in src.get("flow_to", []):
                s["export"].append(f.get("stat_energy_to"))
                s["comp"].append(f.get("stat_compensation"))
            # newer single-grid schema
            s["grid"].append(src.get("stat_energy_from"))
            s["export"].append(src.get("stat_energy_to"))
            s["cost"].append(src.get("stat_cost"))
        elif t == "solar":
            s["solar"].append(src.get("stat_energy_from"))
        elif t == "battery":
            s["batt_out"].append(src.get("stat_energy_from"))
            s["batt_in"].append(src.get("stat_energy_to"))
    return {k: [i for i in v if i] for k, v in s.items()}


async def _energy(hass: HomeAssistant, start: datetime, end: datetime, prefs: dict) -> dict | None:
    src = _sources(prefs)
    if not src.get("grid") and not src.get("solar"):
        return None
    energy_ids = src.get("grid", []) + src.get("solar", []) + src.get("export", []) + src.get("batt_out", []) + src.get("batt_in", [])
    rows = await _stats(hass, start, end, energy_ids, {"change"}, {"energy": "kWh"}, "hour")
    grid_h, solar_h = _hourly(rows, src.get("grid", [])), _hourly(rows, src.get("solar", []))
    grid_d, solar_d = insights.daily(grid_h), insights.daily(solar_h)
    out: dict[str, Any] = {}

    if grid_d:
        peak = max(grid_d.items(), key=lambda kv: kv[1])
        out["grid"] = {"total_kwh": round(sum(grid_d.values()), 1), "monthly_kwh": _monthly(grid_d),
                       "peak_day": {"date": peak[0].isoformat(), "kwh": round(peak[1], 1)}}
    if solar_d and sum(solar_d.values()) > 0:
        peak = max(solar_d.items(), key=lambda kv: kv[1])
        out["solar"] = {"total_kwh": round(sum(solar_d.values()), 1), "monthly_kwh": _monthly(solar_d),
                        "peak_day": {"date": peak[0].isoformat(), "kwh": round(peak[1], 1)}}
    exported = sum(_hourly(rows, src.get("export", [])).values())
    if exported > 0:
        out["export_kwh"] = round(exported, 1)
    if out.get("solar") and out.get("grid"):
        self_used = max(out["solar"]["total_kwh"] - exported, 0)
        used = out["grid"]["total_kwh"] + self_used
        out["self_powered_pct"] = round(100 * self_used / used) if used else None

    # Home battery
    b_out = sum(_hourly(rows, src.get("batt_out", [])).values())
    b_in = sum(_hourly(rows, src.get("batt_in", [])).values())
    if b_out > 0:
        out["battery"] = {"discharged_kwh": round(b_out, 1), "charged_kwh": round(b_in, 1),
                          "efficiency_pct": round(100 * b_out / b_in) if b_in else None}

    # Shape of the year
    prof = insights.profile(grid_h)
    out["hourly_profile"] = prof
    night_min: dict = {}
    for t, v in grid_h.items():
        if 1 <= t.hour <= 4:
            night_min[t.date()] = min(night_min.get(t.date(), v), v)
    if len(night_min) >= 7:
        out["standby_w"] = round(pystats.median(night_min.values()) * 1000)
    out["weekdays"] = insights.weekdays(grid_d)
    out["seasons"] = insights.seasons(grid_d, (hass.config.latitude or 0) < 0)
    out["quiet_hour"] = insights.quiet_hour(prof)
    out["day_of_year"] = insights.day_of_year(grid_d)
    if solar_d:
        out["sun_streak"] = insights.sun_streak(solar_d, grid_d)

    # Cost (Energy dashboard cost statistics)
    edata = hass.data.get("energy")
    cost_sensors = edata.get("cost_sensors", {}) if isinstance(edata, dict) else {}
    cost_ids = src.get("cost", []) + [cost_sensors[g] for g in src.get("grid", []) if g in cost_sensors]
    comp_ids = src.get("comp", []) + [cost_sensors[x] for x in src.get("export", []) if x in cost_sensors]
    if cost_ids:
        crow = await _stats(hass, start, end, cost_ids + comp_ids, {"change"}, None, "month")
        monthly: dict[int, float] = defaultdict(float)
        for sid in cost_ids:
            for r in crow.get(sid, []):
                if r.get("change") is not None:
                    monthly[dt_util.as_local(dt_util.utc_from_timestamp(r["start"])).month] += r["change"]
        earned = sum(r["change"] for sid in comp_ids for r in crow.get(sid, []) if r.get("change"))
        spent = sum(monthly.values())
        if spent > 0:
            cheap, dear = min(monthly, key=monthly.get), max(monthly, key=monthly.get)
            grid_kwh = (out.get("grid") or {}).get("total_kwh") or 0
            out["cost"] = {
                "currency": hass.config.currency, "spent": round(spent, 2), "earned": round(abs(earned), 2),
                "cheapest": {"month": MONTHS[cheap - 1], "value": round(monthly[cheap], 2)},
                "dearest": {"month": MONTHS[dear - 1], "value": round(monthly[dear], 2)},
                "per_day": round(spent / max(len(grid_d), 1), 2),
                "price_kwh": round(spent / grid_kwh, 3) if grid_kwh else None,
            }
    return out


async def _last_year(hass, start, end, prefs) -> dict | None:
    """Same date span last year, for year-over-year."""
    src = _sources(prefs)
    s0, e0 = start.replace(year=start.year - 1), end - (start - start.replace(year=start.year - 1))
    rows = await _stats(hass, s0, e0, src.get("grid", []) + src.get("solar", []), {"change"}, {"energy": "kWh"}, "hour")
    tot = lambda ids: sum(r["change"] for i in ids for r in rows.get(i, []) if r.get("change"))
    g, s = tot(src.get("grid", [])), tot(src.get("solar", []))
    return {"grid_kwh": round(g, 1), "solar_kwh": round(s, 1)} if g or s else None


def _setup(hass: HomeAssistant, start: datetime) -> dict:
    devices = dr.async_get(hass).devices.values()
    entities = er.async_get(hass).entities.values()
    new_devices = [d for d in devices if getattr(d, "created_at", None) and d.created_at >= start]
    new_automations = [e for e in entities if e.domain == "automation" and getattr(e, "created_at", None) and e.created_at >= start]
    newest = max(new_devices, key=lambda d: d.created_at) if new_devices else None
    first = min(new_devices, key=lambda d: d.created_at) if new_devices else None
    return {
        "devices_total": len(devices), "devices_added": len(new_devices),
        "entities_total": len(entities),
        "integrations": len({e.domain for e in hass.config_entries.async_entries()}),
        "automations": len(hass.states.async_entity_ids("automation")),
        "automations_added": len(new_automations),
        "newest_device": (newest.name_by_user or newest.name) if newest else None,
        "first_device": (first.name_by_user or first.name) if first else None,
    }


def _fact(metric: str, value: float | None, year: int) -> str | None:
    if not value:
        return None
    pick = comparisons.best(metric, value, year)
    return pick["text"] if pick else None


# --- Slide selection --------------------------------------------------------
# (id, category); this order is the story order
STORY = [
    ("numbers", "core"), ("personality", "core"), ("aura", "core"),
    ("energy", "energy"), ("top_devices", "core"), ("on_repeat", "devices"),
    ("screen_time", "devices"), ("day_of_year", "energy"), ("season", "energy"),
    ("weekdays", "energy"), ("quiet_hour", "energy"), ("vampire", "money"),
    ("bill", "money"), ("solar", "solar"), ("sun_streak", "solar"),
    ("home_battery", "solar"), ("glow_up", "energy"), ("water", "water"),
    ("gas", "energy"), ("air", "health"), ("out_and_about", "health"),
    ("rain", "outdoors"), ("battery_graveyard", "devices"), ("odds", "devices"),
    ("new_arrivals", "core"), ("share", "core"),
]
ALWAYS = {"numbers", "personality", "top_devices", "share"}
MAX_OPTIONAL, MAX_PER_CATEGORY = 10, 2


def _scores(o: dict) -> dict[str, float]:
    """How interesting each optional slide is, 0..1."""
    e = o.get("energy") or {}
    sc: dict[str, float] = {}
    if e.get("grid"):
        sc["energy"] = 0.9
    if o.get("aura"):
        sc["aura"] = 0.7
    if d := e.get("day_of_year"):
        sc["day_of_year"] = min(1, (d["times_normal"] - 1) / 2)
    if s := e.get("seasons"):
        sc["season"] = min(1, abs(s["share_pct"][s["top"]] - 25) / 20)
    if w := e.get("weekdays"):
        sc["weekdays"] = min(1, w["spread_pct"] / 40)
    if e.get("quiet_hour"):
        sc["quiet_hour"] = 0.35
    if e.get("standby_w") and e.get("grid"):
        sc["vampire"] = min(1, e["standby_w"] * 8.76 / max(e["grid"]["total_kwh"], 1) * 2)
    if e.get("cost"):
        sc["bill"] = 0.75
    if e.get("solar"):
        sc["solar"] = 0.85
    if s := e.get("sun_streak"):
        sc["sun_streak"] = min(1, s["days"] / 30)
    if e.get("battery"):
        sc["home_battery"] = 0.7
    if (ly := o.get("last_year")) and ly.get("grid_change_pct") is not None:
        sc["glow_up"] = min(1, abs(ly["grid_change_pct"]) / 30)
    if o.get("on_repeat"):
        sc["on_repeat"] = 0.6
    if o.get("screen_time"):
        sc["screen_time"] = 0.65
    if o.get("water"):
        sc["water"] = 0.55
    if o.get("gas"):
        sc["gas"] = 0.45
    if a := o.get("air"):
        sc["air"] = min(1, 0.3 + a["stuffiest"].get("hours_over_1000", 0) / 800)
    if o.get("steps") or o.get("distance"):
        sc["out_and_about"] = 0.55
    if o.get("rain"):
        sc["rain"] = 0.3
    if b := o.get("batteries"):
        sc["battery_graveyard"] = min(1, 0.35 + b["replaced"] / 20)
    if o.get("data") or o.get("counters"):
        sc["odds"] = 0.2
    if o["setup"]["devices_added"]:
        sc["new_arrivals"] = 0.6
    return sc


def _select(o: dict, show_all: bool = False) -> list[str]:
    sc = _scores(o)
    available = set(sc) | {"numbers", "share"}
    if o.get("persona"):
        available.add("personality")
    if o.get("devices"):
        available.add("top_devices")
    if show_all:
        return [sid for sid, _ in STORY if sid in available]
    cats = dict(STORY)
    chosen = ALWAYS & available
    per_cat: dict[str, int] = defaultdict(int)
    optional = 0
    for sid in sorted(sc, key=sc.get, reverse=True):
        if optional >= MAX_OPTIONAL:
            break
        if sid in chosen:
            continue
        if per_cat[cats[sid]] < MAX_PER_CATEGORY:
            chosen.add(sid)
            per_cat[cats[sid]] += 1
            optional += 1
    return [sid for sid, _ in STORY if sid in chosen]


# --- Build ------------------------------------------------------------------

async def async_build_roundup(hass: HomeAssistant, year: int, show_all: bool = False) -> dict[str, Any]:
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
    last_year = await safe("last year", _last_year(hass, start, end, prefs))

    e = energy or {}
    prof = e.pop("hourly_profile", None) or [0] * 24
    standby_share = None
    if e.get("standby_w") and e.get("grid"):
        standby_share = e["standby_w"] * 8.76 / max(e["grid"]["total_kwh"], 1)
    persona = insights.personality(prof, e.get("weekdays"), e.get("seasons"), e.get("self_powered_pct"), standby_share)

    out: dict[str, Any] = {
        "year": year,
        "home_name": hass.config.location_name,
        "persona": persona,
        "aura": insights.aura(persona["peak_hour"] if persona else None, (e.get("seasons") or {}).get("top")),
        "hours": prof,
        "setup": _setup(hass, start),
        "energy": energy,
        "last_year": last_year,
        **lts,
    }

    # Sourced comparisons
    if energy:
        if e.get("grid"):
            e["fact"] = _fact("grid_kwh", e["grid"]["total_kwh"], year)
        if e.get("solar"):
            e["solar_fact"] = _fact("solar_kwh", e["solar"]["total_kwh"], year)
        if e.get("standby_w"):
            e["standby_fact"] = _fact("standby_w", e["standby_w"], year)
            if (c := e.get("cost")) and c.get("price_kwh"):
                e["standby_cost"] = round(e["standby_w"] * 8.76 * c["price_kwh"])
        if e.get("export_kwh"):
            e["export_fact"] = _fact("export_kwh", e["export_kwh"], year)
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
    if (ly := last_year) and e.get("grid") and ly.get("grid_kwh"):
        ly["grid_change_pct"] = round(100 * (e["grid"]["total_kwh"] / ly["grid_kwh"] - 1))
        if e.get("solar") and ly.get("solar_kwh"):
            ly["solar_change_pct"] = round(100 * (e["solar"]["total_kwh"] / ly["solar_kwh"] - 1))

    out["slides"] = _select(out, show_all)
    return out
