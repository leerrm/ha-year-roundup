# Year Roundup (prototype)

A yearly story for your home: energy, lights, doors, automations, music, devices added. Computed locally; nothing leaves the house.

## Install
Copy `custom_components/year_roundup` into your HA config, restart, then add **Year Roundup** under Settings → Devices & services. A **Year Roundup** sidebar panel appears. A notification fires on 1 December.

## Where the data comes from
Home Assistant keeps **long-term statistics** (hourly mean/min/max/sum for any sensor with a `state_class`) forever, so most slides cover the full year, even on a fresh install.

| Slide | Source | Full year? |
|---|---|---|
| Energy, solar, export, % self-powered, standby, energy-by-hour personality | Energy dashboard + long-term statistics | Yes |
| Biggest energy users | Energy dashboard "individual devices" | Yes |
| Screen time (hours each device was on) | Power (W) sensors, hourly means | Yes |
| Water, gas | Energy dashboard or water/gas meters | Yes |
| Batteries replaced | Battery % sensors (big upward jumps) | Yes |
| Air quality | CO2 sensors | Yes |
| Steps, distance, data, other counters | Any statistic by unit (steps, km, GB, pages...) | Yes |
| Devices/automations added | Registries (`created_at`) | Yes |
| Lights, doors, automation runs, music | Recorder history *or* Year Roundup's own counters, whichever goes back further | Only as far as the recorder keeps detail (`purge_keep_days`, default 10). From install, Year Roundup counts these itself, so future years are complete. Slides are labelled "since <date>" when partial. |

## Optional AI captions
In the integration options, pick an **AI Task** entity (Ollama, OpenAI, Google, Anthropic…) and write a style prompt ("roast me", "nature documentary narrator", "for kids"…).
- The model gets the computed facts only and is told not to change numbers. All numbers on the slides still come from local data; only the caption text changes.
- Captions are cached per year for a day; add `?refresh=1` to the panel URL to regenerate.
- No agent, a timeout (90 s) or an error → built-in text. If a cached caption exists, that is used instead.
- With a cloud agent the summary leaves the house, so the closing slide says who wrote the captions instead of "none of it left your home".

## Files
- `ai.py`: AI Task call, prompt, structured per-slide output
- `lts.py`: scans all long-term statistics and turns them into year-long metrics
- `history.py`: reads lights/doors/automations/media from the recorder database
- `tracker.py`: counts those events from install onwards, so future years are complete
- `comparisons.py`: sourced "that's like X bathtubs" comparisons (see COMPARISONS.md)
- `roundup.py`: builds the roundup (stats queries, top lists, persona, fun facts)
- `__init__.py`: websocket `year_roundup/get`, sidebar panel, Dec 1 notification
- `www/index.html`: tap-through story UI (opened on its own, it shows sample data)

## Next steps
- Tests: `pytest` (uses pytest-homeassistant-custom-component with a real recorder).
- Add a shareable image export, slides for Assist voice stats and water/gas, and year-over-year comparisons.
- Longer term: propose it for HA core, which would need a frontend panel and an architecture discussion.
