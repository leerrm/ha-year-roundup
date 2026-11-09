"""Year Roundup: a yearly 'wrapped' story for your home."""

from __future__ import annotations

import hashlib
from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend, persistent_notification, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .ai import async_ai_captions
from .const import CONF_AI_ENTITY, CONF_STYLE, DEFAULT_STYLE, DOMAIN, PANEL_URL, STATIC_URL
from .roundup import async_build_roundup
from .tracker import RoundupTracker

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    websocket_api.async_register_command(hass, ws_get_roundup)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), False)]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    tracker = RoundupTracker(hass)
    await tracker.async_start()
    hass.data[DOMAIN] = tracker

    frontend.async_register_built_in_panel(
        hass,
        "iframe",
        sidebar_title="Year Roundup",
        sidebar_icon="mdi:party-popper",
        frontend_url_path=PANEL_URL,
        config={"url": f"{STATIC_URL}/index.html"},
        require_admin=False,
    )

    @callback
    def _announce(now) -> None:
        if now.month == 12 and now.day == 1:
            persistent_notification.async_create(
                hass,
                f"Your {now.year} Year Roundup is ready. [Open it](/{PANEL_URL})",
                title="🎉 Year Roundup",
                notification_id=f"{DOMAIN}_{now.year}",
            )

    entry.async_on_unload(async_track_time_change(hass, _announce, hour=10, minute=0, second=0))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL)
    tracker: RoundupTracker = hass.data.pop(DOMAIN)
    await tracker.async_stop()
    return True


async def _async_captions(
    hass: HomeAssistant, entry: ConfigEntry, tracker: RoundupTracker, roundup: dict, refresh: bool
) -> dict | None:
    """AI captions, cached per year for a day (or until the agent/style changes)."""
    entity_id = entry.options.get(CONF_AI_ENTITY)
    if not entity_id:
        return None
    style = entry.options.get(CONF_STYLE) or DEFAULT_STYLE
    key = hashlib.sha256(
        f"{dt_util.now().date()}|{entity_id}|{style}".encode()
    ).hexdigest()
    cache = tracker.data.setdefault("_ai_cache", {})
    hit = cache.get(str(roundup["year"]))
    if hit and hit["key"] == key and not refresh:
        return hit["captions"]
    captions = await async_ai_captions(hass, entity_id, style, roundup)
    if captions:
        cache[str(roundup["year"])] = {"key": key, "captions": captions}
        tracker.save()
        return captions
    return hit["captions"] if hit else None  # stale beats nothing


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/get",
        vol.Optional("year"): int,
        vol.Optional("refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_get_roundup(hass: HomeAssistant, connection, msg: dict) -> None:
    tracker: RoundupTracker | None = hass.data.get(DOMAIN)
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if tracker is None or not entries:
        connection.send_error(msg["id"], "not_loaded", "Year Roundup is not set up")
        return
    year = msg.get("year") or dt_util.now().year
    roundup = await async_build_roundup(hass, tracker, year)
    roundup["ai"] = await _async_captions(hass, entries[0], tracker, roundup, msg["refresh"])
    if roundup["ai"] and (state := hass.states.get(entries[0].options[CONF_AI_ENTITY])):
        roundup["ai_agent"] = state.name
    connection.send_result(msg["id"], roundup)
