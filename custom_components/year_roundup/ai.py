"""Optional AI-written captions via Home Assistant's AI Task integration.

If no AI Task entity is configured, or the call fails, the roundup falls back
to the built-in template text in the frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
TIMEOUT = 90
MAX_LEN = 300

# slide key -> what the caption should cover
SLIDES: dict[str, str] = {
    "intro": "Opening line welcoming the household to their year in review.",
    "persona": "One or two sentences explaining the home's personality and peak hour.",
    "energy": "Comment on grid energy use, the monthly trend and the peak day.",
    "solar": "Comment on solar production and the best day.",
    "lights": "Comment on hours of light and the top lights.",
    "doors": "Comment on door openings and the busiest door.",
    "automations": "Comment on automation runs, time saved and the top automation.",
    "music": "Comment on hours of music and top artists/track.",
    "climate": "Comment on the hottest and coldest days and the busiest day.",
    "setup": "Comment on devices added and how the setup grew.",
    "outro": "Closing line wrapping up the year.",
}


def _facts(roundup: dict[str, Any]) -> dict[str, Any]:
    """Strip the roundup down to what the model needs."""
    skip = {"hours", "tracking_since", "ai", "ai_agent"}
    facts = {k: v for k, v in roundup.items() if k not in skip and v}
    if (energy := facts.get("energy")) and (grid := energy.get("grid")):
        grid = dict(grid)
        grid.pop("monthly_kwh", None)
        facts["energy"] = {**energy, "grid": grid}
    return facts


async def async_ai_captions(
    hass: HomeAssistant, entity_id: str, style: str, roundup: dict[str, Any]
) -> dict[str, str] | None:
    """Ask the AI Task entity for one caption per slide. Returns None on failure."""
    instructions = (
        "You write short captions for a 'year in review' story about a smart home, "
        "shown one slide at a time on a phone.\n"
        f"Style and tone: {style}\n"
        "Rules: use ONLY the facts below; never invent or change numbers; "
        "max 30 words per caption; plain text, no markdown; "
        "leave a field empty if its facts are missing.\n\n"
        f"Facts (JSON):\n{json.dumps(_facts(roundup), ensure_ascii=False, default=str)}"
    )
    structure = {
        key: {"description": desc, "required": False, "selector": {"text": {}}}
        for key, desc in SLIDES.items()
    }
    try:
        async with asyncio.timeout(TIMEOUT):
            response = await hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "task_name": f"Year Roundup {roundup['year']}",
                    "entity_id": entity_id,
                    "instructions": instructions,
                    "structure": structure,
                },
                blocking=True,
                return_response=True,
            )
    except Exception:  # noqa: BLE001 - any failure means fall back to templates
        _LOGGER.warning("AI captions failed; using built-in text", exc_info=True)
        return None

    data = (response or {}).get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    captions = {
        k: str(v).strip()[:MAX_LEN] for k, v in data.items() if k in SLIDES and v and str(v).strip()
    }
    return captions or None
