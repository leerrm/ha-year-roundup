"""End-to-end tests against a real recorder (SQLite) and statistics."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from homeassistant.components.recorder.models import StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.year_roundup.const import DOMAIN
from custom_components.year_roundup.lts import async_read_lts

YEAR = dt_util.now().year


def _meta(sid, unit, unit_class, mean=False, sum_=False, name=None):
    return StatisticMetaData(
        source="recorder", statistic_id=sid, name=name, unit_of_measurement=unit,
        unit_class=unit_class, has_sum=sum_,
        mean_type=StatisticMeanType.ARITHMETIC if mean else StatisticMeanType.NONE,
    )


def _hours(days):
    start = dt_util.start_of_local_day(dt_util.now() - timedelta(days=days))
    return [start + timedelta(hours=h) for h in range(days * 24)]


async def _seed_statistics(hass: HomeAssistant):
    # A TV smart plug: 100 W from 18:00-23:00 every day, 1 W otherwise
    hass.states.async_set("sensor.tv_power", "1", {"device_class": "power", "state_class": "measurement", "unit_of_measurement": "W", "friendly_name": "Living room TV"})
    rows = [{"start": t, "mean": 100.0 if 18 <= dt_util.as_local(t).hour < 23 else 1.0, "min": 0, "max": 100} for t in _hours(30)]
    async_import_statistics(hass, _meta("sensor.tv_power", "W", "power", mean=True), rows)

    # A door lock battery: drains, replaced twice
    hass.states.async_set("sensor.lock_battery", "80", {"device_class": "battery", "state_class": "measurement", "unit_of_measurement": "%", "friendly_name": "Front door lock battery"})
    level, rows = 100.0, []
    for i, t in enumerate(_hours(30)):
        level = 100.0 if i in (200, 500) else max(level - 0.3, 5)
        rows.append({"start": t, "mean": level, "min": level, "max": level})
    async_import_statistics(hass, _meta("sensor.lock_battery", "%", None, mean=True), rows)

    # Heat pump energy (an Energy dashboard individual device), 1 kWh/h
    hass.states.async_set("sensor.heat_pump_energy", "0", {"device_class": "energy", "state_class": "total_increasing", "unit_of_measurement": "kWh", "friendly_name": "Heat pump"})
    rows = [{"start": t, "state": i + 1.0, "sum": i + 1.0} for i, t in enumerate(_hours(30))]
    async_import_statistics(hass, _meta("sensor.heat_pump_energy", "kWh", "energy", sum_=True), rows)

    # Grid import 0.5 kWh/h
    hass.states.async_set("sensor.grid_import", "0", {"device_class": "energy", "state_class": "total_increasing", "unit_of_measurement": "kWh"})
    rows = [{"start": t, "state": (i + 1) * 0.5, "sum": (i + 1) * 0.5} for i, t in enumerate(_hours(30))]
    async_import_statistics(hass, _meta("sensor.grid_import", "kWh", "energy", sum_=True), rows)
    # Grid cost (0.30/kWh) and a home battery
    hass.states.async_set("sensor.grid_cost", "0", {"state_class": "total_increasing", "unit_of_measurement": "EUR"})
    rows = [{"start": t, "state": (i + 1) * 0.15, "sum": (i + 1) * 0.15} for i, t in enumerate(_hours(30))]
    async_import_statistics(hass, _meta("sensor.grid_cost", "EUR", None, sum_=True), rows)
    for sid, per_h in (("sensor.batt_out", 0.2), ("sensor.batt_in", 0.25)):
        hass.states.async_set(sid, "0", {"device_class": "energy", "state_class": "total_increasing", "unit_of_measurement": "kWh"})
        rows = [{"start": t, "state": (i + 1) * per_h, "sum": (i + 1) * per_h} for i, t in enumerate(_hours(30))]
        async_import_statistics(hass, _meta(sid, "kWh", "energy", sum_=True), rows)
    await async_wait_recording_done(hass)


PREFS = {
    "energy_sources": [
        {"type": "grid", "flow_from": [{"stat_energy_from": "sensor.grid_import", "stat_cost": "sensor.grid_cost"}], "flow_to": []},
        {"type": "battery", "stat_energy_from": "sensor.batt_out", "stat_energy_to": "sensor.batt_in"},
    ],
    "device_consumption": [{"stat_consumption": "sensor.heat_pump_energy"}],
}


async def test_long_term_statistics(recorder_mock, hass: HomeAssistant):
    await _seed_statistics(hass)
    start = datetime(YEAR, 1, 1, tzinfo=dt_util.get_default_time_zone())
    out = await async_read_lts(hass, start, dt_util.now(), PREFS)

    assert out["devices"]["top"][0]["name"] == "Heat pump"
    assert out["devices"]["top"][0]["kwh"] == pytest.approx(30 * 24 - 1, abs=2)
    tv = out["screen_time"]["top"][0]
    assert tv["name"] == "Living room TV"
    assert tv["hours"] == pytest.approx(30 * 5, abs=6)
    assert out["batteries"]["replaced"] == 2
    assert out["batteries"]["hungriest"]["name"] == "Front door lock battery"


async def test_websocket_end_to_end(recorder_mock, hass: HomeAssistant, hass_ws_client):
    await _seed_statistics(hass)
    from homeassistant.components.energy.data import async_get_manager

    manager = await async_get_manager(hass)
    await manager.async_update(PREFS)
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")  # frontend package not installed in tests
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    with patch("homeassistant.components.frontend.async_register_built_in_panel") as panel:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert panel.called

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/get", "refresh": False, "all": False})
    msg = await client.receive_json()
    assert msg["success"], msg
    r = msg["result"]
    assert r["year"] == YEAR
    assert r["screen_time"]["top"][0]["name"] == "Living room TV"
    assert r["batteries"]["replaced"] == 2
    assert "climate" not in r and "lights" not in r and "automations" not in r
    assert r["persona"]["peak_hour"] is not None
    assert r["energy"]["grid"]["total_kwh"] > 0
    assert r["slides"][0] == "numbers" and r["slides"][-1] == "share"
    assert {"personality", "top_devices"} <= set(r["slides"])
    assert r["on_repeat"]["name"] == "Living room TV"
    cost = r["energy"]["cost"]
    assert cost["spent"] == pytest.approx(cost["price_kwh"] * r["energy"]["grid"]["total_kwh"], rel=0.02)
    assert cost["price_kwh"] == pytest.approx(0.30, abs=0.01)
    assert r["energy"]["battery"]["efficiency_pct"] == 80

    await client.send_json({"id": 2, "type": f"{DOMAIN}/get", "all": True})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert len(msg["result"]["slides"]) >= len(r["slides"])
    assert r["devices"]["top"][0]["name"] == "Heat pump"
    assert r["ai"] is None
