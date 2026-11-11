"""Read a year of activity straight from the recorder database.

Everything here comes from data Home Assistant already stored:
  - states table:  light/switch/door/motion/person/media changes
  - events table:  automation_triggered events
How far back this goes depends on the recorder's `purge_keep_days`.
"""

from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from sqlalchemy import bindparam, text

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.util import session_scope
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOOR_CLASSES, IGNORED_STATES, MOTION_CLASSES, ON_OFF_DOMAINS

_STATE_ROWS = text(
    """
    SELECT metadata_id, state, last_updated_ts FROM states
    WHERE metadata_id IN :ids AND last_updated_ts >= :start AND last_updated_ts < :end
      AND (last_changed_ts IS NULL OR last_changed_ts = last_updated_ts)
    ORDER BY metadata_id, last_updated_ts
    """
).bindparams(bindparam("ids", expanding=True))

_MEDIA_ROWS = text(
    """
    SELECT s.metadata_id, s.state, s.last_updated_ts, a.shared_attrs FROM states s
    LEFT JOIN state_attributes a ON s.attributes_id = a.attributes_id
    WHERE s.metadata_id IN :ids AND s.last_updated_ts >= :start AND s.last_updated_ts < :end
    ORDER BY s.metadata_id, s.last_updated_ts
    """
).bindparams(bindparam("ids", expanding=True))

_AUTOMATION_ROWS = text(
    """
    SELECT d.shared_data FROM events e
    JOIN event_types t ON e.event_type_id = t.event_type_id
    LEFT JOIN event_data d ON e.data_id = d.data_id
    WHERE t.event_type = 'automation_triggered'
      AND e.time_fired_ts >= :start AND e.time_fired_ts < :end
    """
)

_META = text("SELECT metadata_id, entity_id FROM states_meta WHERE entity_id IN :e").bindparams(
    bindparam("e", expanding=True)
)


def _inc(bucket: dict, key: str, amount: float = 1) -> None:
    bucket[key] = bucket.get(key, 0) + amount


def _select_entities(hass: HomeAssistant) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for st in hass.states.async_all():
        if st.domain in ON_OFF_DOMAINS:
            groups["on_off"].append(st.entity_id)
        elif st.domain == "binary_sensor":
            dc = st.attributes.get("device_class")
            if dc in DOOR_CLASSES:
                groups["door"].append(st.entity_id)
            elif dc in MOTION_CLASSES:
                groups["motion"].append(st.entity_id)
        elif st.domain == "person":
            groups["person"].append(st.entity_id)
        elif st.domain == "media_player":
            groups["media"].append(st.entity_id)
    return groups


def _read(hass: HomeAssistant, groups: dict[str, list[str]], start: float, end: float) -> dict[str, Any]:
    """Runs in the recorder executor."""
    all_ids = [e for ids in groups.values() for e in ids]
    with session_scope(hass=hass, read_only=True) as session:
        first_ts = session.execute(text("SELECT MIN(last_updated_ts) FROM states")).scalar()
        meta = dict(session.execute(_META, {"e": all_ids}).all()) if all_ids else {}
        by_group = {g: [m for m, e in meta.items() if e in set(ids)] for g, ids in groups.items()}

        def rows(query, group):
            ids = by_group.get(group) or []
            if not ids:
                return []
            return session.execute(query, {"ids": ids, "start": start, "end": end}).all()

        out = {
            "first_ts": first_ts,
            "meta": meta,
            "on_off": rows(_STATE_ROWS, "on_off"),
            "door": rows(_STATE_ROWS, "door"),
            "motion": rows(_STATE_ROWS, "motion"),
            "person": rows(_STATE_ROWS, "person"),
            "media": rows(_MEDIA_ROWS, "media"),
            "automations": [r[0] for r in session.execute(_AUTOMATION_ROWS, {"start": start, "end": end})],
        }
    return out


async def async_read_year(hass: HomeAssistant, start, end) -> dict[str, Any]:
    """Aggregate the year's recorder history into counters."""
    start_ts, end_ts = start.timestamp(), end.timestamp()
    raw = await get_instance(hass).async_add_executor_job(
        _read, hass, _select_entities(hass), start_ts, end_ts
    )
    meta = raw["meta"]
    res: dict[str, Any] = {
        "on_seconds": {}, "toggles": {}, "door_opens": {}, "motion": {},
        "automations": {}, "artists": {}, "tracks": {}, "media_seconds": {},
        "arrivals": {}, "zones": {}, "hours": [0] * 24, "days": {},
    }

    def activity(ts: float) -> None:
        local = dt_util.as_local(dt_util.utc_from_timestamp(ts))
        res["hours"][local.hour] += 1
        _inc(res["days"], local.date().isoformat())

    # Lights / switches / fans: toggles + on-time
    prev: dict[int, tuple[str, float]] = {}
    for mid, state, ts in raw["on_off"]:
        eid = meta[mid]
        if state in IGNORED_STATES:
            continue
        last = prev.get(mid)
        if last and last[0] == state:
            continue
        if last:
            _inc(res["toggles"], eid)
            activity(ts)
            if last[0] == "on":
                _inc(res["on_seconds"], eid, ts - last[1])
        prev[mid] = (state, ts)
    for mid, (state, ts) in prev.items():
        if state == "on":
            _inc(res["on_seconds"], meta[mid], max(0, min(end_ts, dt_util.utcnow().timestamp()) - ts))

    # Doors / motion: count 'on'
    for group, bucket in (("door", "door_opens"), ("motion", "motion")):
        for mid, state, ts in raw[group]:
            if state == "on":
                _inc(res[bucket], meta[mid])
                activity(ts)

    # People
    for mid, state, _ts in raw["person"]:
        if state == "home":
            _inc(res["arrivals"], meta[mid])
        elif state not in ("not_home", *IGNORED_STATES):
            _inc(res["zones"], state)

    # Media: plays (new title while playing) + listening time
    mprev: dict[int, tuple[str, str | None, float]] = {}
    for mid, state, ts, attrs in raw["media"]:
        try:
            title_artist = json.loads(attrs) if attrs else {}
        except ValueError:
            title_artist = {}
        title, artist = title_artist.get("media_title"), title_artist.get("media_artist")
        last = mprev.get(mid)
        if state == "playing" and title:
            if not last or last[1] != title or last[0] not in ("playing", "paused"):
                if artist:
                    _inc(res["artists"], artist)
                _inc(res["tracks"], f"{artist} — {title}" if artist else title)
        if last and last[0] == "playing" and state != "playing":
            _inc(res["media_seconds"], meta[mid], ts - last[2])
        if not last or last[0] != state or state != "playing":
            mprev[mid] = (state, title, ts)
        else:
            mprev[mid] = (state, title, last[2])

    # Automations
    for data in raw["automations"]:
        try:
            d = json.loads(data) if data else {}
        except ValueError:
            d = {}
        _inc(res["automations"], str(d.get("name") or d.get("entity_id") or "unknown"))

    first_ts = raw["first_ts"]
    covered_from = max(start_ts, first_ts) if first_ts else end_ts
    res["coverage"] = {
        "from": dt_util.as_local(dt_util.utc_from_timestamp(covered_from)).date().isoformat(),
        "days": round((end_ts - covered_from) / 86400),
        "partial": covered_from > start_ts + 86400,
        "keep_days": getattr(get_instance(hass), "keep_days", None),
    }
    return res
