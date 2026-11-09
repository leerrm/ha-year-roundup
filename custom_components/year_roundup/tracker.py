"""Live counters that survive recorder purges.

The recorder keeps raw state history for ~10 days by default, so a year-long
roundup cannot be rebuilt from history alone. This tracker listens to the
event bus and keeps compact per-year counters in .storage.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOOR_CLASSES,
    IGNORED_STATES,
    MOTION_CLASSES,
    ON_OFF_DOMAINS,
    STORAGE_KEY,
    STORAGE_VERSION,
)

EVENT_AUTOMATION_TRIGGERED = "automation_triggered"


def _empty_year() -> dict[str, Any]:
    return {
        "first_seen": dt_util.now().isoformat(),
        "on_seconds": {},  # entity_id -> seconds on
        "toggles": {},  # entity_id -> count
        "door_opens": {},  # entity_id -> count
        "motion": {},  # entity_id -> count
        "automations": {},  # automation name -> runs
        "artists": {},  # artist -> plays
        "tracks": {},  # "artist — title" -> plays
        "media_seconds": {},  # entity_id -> seconds playing
        "arrivals": {},  # person -> times arrived home
        "zones": {},  # zone name -> visits
        "hours": [0] * 24,  # human activity by hour of day
        "days": {},  # ISO date -> activity count
    }


def _inc(bucket: dict[str, float], key: str, amount: float = 1) -> None:
    bucket[key] = bucket.get(key, 0) + amount


class RoundupTracker:
    """Accumulate yearly counters from the event bus."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, dict[str, Any]] = {}
        self._on_since: dict[str, float] = {}
        self._play_since: dict[str, float] = {}
        self._unsubs: list = []

    async def async_start(self) -> None:
        self.data = await self._store.async_load() or {}
        now = time.time()
        for state in self.hass.states.async_all(ON_OFF_DOMAINS):
            if state.state == "on":
                self._on_since[state.entity_id] = now
        for state in self.hass.states.async_all("media_player"):
            if state.state == "playing":
                self._play_since[state.entity_id] = now
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._state_changed)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_AUTOMATION_TRIGGERED, self._automation)
        )

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._flush_open_timers()
        await self._store.async_save(self.data)

    def year(self, year: int | None = None) -> dict[str, Any]:
        key = str(year or dt_util.now().year)
        if key not in self.data:
            self.data[key] = _empty_year()
        return self.data[key]

    @callback
    def save(self) -> None:
        self._store.async_delay_save(lambda: self.data, 60)

    _save = save

    @callback
    def _flush_open_timers(self) -> None:
        now = time.time()
        y = self.year()
        for eid, since in self._on_since.items():
            _inc(y["on_seconds"], eid, now - since)
        for eid, since in self._play_since.items():
            _inc(y["media_seconds"], eid, now - since)
        self._on_since = dict.fromkeys(self._on_since, now)
        self._play_since = dict.fromkeys(self._play_since, now)

    @callback
    def _automation(self, event: Event) -> None:
        name = event.data.get("name") or event.data.get("entity_id") or "unknown"
        _inc(self.year()["automations"], str(name))
        self._save()

    @callback
    def _activity(self, y: dict[str, Any]) -> None:
        now = dt_util.now()
        y["hours"][now.hour] += 1
        _inc(y["days"], now.date().isoformat())

    @callback
    def _state_changed(self, event: Event) -> None:
        new: State | None = event.data.get("new_state")
        old: State | None = event.data.get("old_state")
        if new is None or old is None:
            return
        eid: str = event.data["entity_id"]
        domain = eid.split(".", 1)[0]
        ts = time.time()
        y = self.year()

        if domain == "media_player":
            self._media(eid, old, new, ts, y)
            return

        if new.state == old.state or new.state in IGNORED_STATES or old.state in IGNORED_STATES:
            return

        if domain in ON_OFF_DOMAINS:
            _inc(y["toggles"], eid)
            if new.state == "on":
                self._on_since[eid] = ts
            elif old.state == "on" and eid in self._on_since:
                _inc(y["on_seconds"], eid, ts - self._on_since.pop(eid))
            self._activity(y)
        elif domain == "binary_sensor" and new.state == "on":
            device_class = new.attributes.get("device_class")
            if device_class in DOOR_CLASSES:
                _inc(y["door_opens"], eid)
                self._activity(y)
            elif device_class in MOTION_CLASSES:
                _inc(y["motion"], eid)
                self._activity(y)
            else:
                return
        elif domain == "person":
            if new.state == "home":
                _inc(y["arrivals"], eid)
            elif new.state != "not_home":
                _inc(y["zones"], new.state)
        else:
            return
        self._save()

    @callback
    def _media(self, eid: str, old: State, new: State, ts: float, y: dict[str, Any]) -> None:
        if new.state == "playing":
            title = new.attributes.get("media_title")
            artist = new.attributes.get("media_artist")
            new_track = title != old.attributes.get("media_title") or old.state not in (
                "playing",
                "paused",
            )
            if title and new_track:
                if artist:
                    _inc(y["artists"], artist)
                _inc(y["tracks"], f"{artist} — {title}" if artist else title)
            if old.state != "playing":
                self._play_since[eid] = ts
        elif old.state == "playing" and eid in self._play_since:
            _inc(y["media_seconds"], eid, ts - self._play_since.pop(eid))
        else:
            return
        self._save()
