"""Small persistent store (AI caption cache only)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


class RoundupStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, Any] = {}

    async def async_load(self) -> None:
        self.data = await self._store.async_load() or {}

    @callback
    def save(self) -> None:
        self._store.async_delay_save(lambda: self.data, 10)

    async def async_save(self) -> None:
        await self._store.async_save(self.data)
