# Year Roundup (prototype)

A yearly story for your home, built from a full year of Home Assistant's long-term statistics. Computed locally; nothing leaves the house.

## Install
Copy `custom_components/year_roundup` into your HA config, restart, then add **Year Roundup** under Settings → Devices & services. A **Year Roundup** sidebar panel appears. A notification fires on 1 December.

## Where the data comes from
Only data that covers the **whole year** is used: Home Assistant's long-term statistics (hourly mean/min/max/sum for any sensor with a `state_class`, never purged) and the device/entity registries. Recorder history is not used, because by default it only keeps 10 days. Slides only appear when the data exists.

| Slide | Source |
|---|---|
| Year in numbers, energy, solar, export, % self-powered | Energy dashboard + long-term statistics |
| Personality (8 types) and energy aura | All-year energy by hour, weekday, season, solar share, standby |
| Day of the year, your season, weekday vs weekend, quiet hour | Hourly grid statistics |
| Vampire hunter, the bill | Overnight standby load, Energy dashboard cost statistics |
| Sun streak, home battery | Solar vs grid by day, battery charge/discharge |
| Glow-up | Same dates last year |
| Top energy users | Energy dashboard individual devices |
| On repeat, screen time | Power (W) sensors, hourly means |
| Water, gas | Energy dashboard or water/gas meters |
| Breathe easy | CO2 sensors (hours above 1,000 ppm) |
| Out and about, rain, odds & ends | Steps, distance, rain, data and other counters |
| Battery graveyard | Battery % sensors (big upward jumps) |
| New arrivals | Registries (`created_at`) |
| Share card | Summary image, downloadable as PNG |

### Which slides are shown
Year in numbers, personality, top energy users and the share card always appear (when there's data). The rest are scored for how interesting they are (how unusual the number is, records, change vs last year) and the top 10 are shown, at most 2 per category, in story order. Add `?all=1` to the panel URL to see every slide that has data.

## Optional AI captions
In the integration options, pick an **AI Task** entity (Ollama, OpenAI, Google, Anthropic…) and write a style prompt ("roast me", "nature documentary narrator", "for kids"…).
- The model gets the computed facts only and is told not to change numbers. All numbers on the slides still come from local data; only the caption text changes.
- Captions are cached per year for a day; add `?refresh=1` to the panel URL to regenerate.
- No agent, a timeout (90 s) or an error → built-in text. If a cached caption exists, that is used instead.
- With a cloud agent the summary leaves the house, so the closing slide says who wrote the captions instead of "none of it left your home".

## Files
- `ai.py`: AI Task call, prompt, structured per-slide output
- `lts.py`: scans all long-term statistics and turns them into year-long metrics
- `store.py`: AI caption cache
- `comparisons.py`: sourced "that's like X bathtubs" comparisons (see COMPARISONS.md)
- `insights.py`: personality, aura, seasons, weekdays, day of the year, sun streak
- `roundup.py`: builds the roundup, energy/cost/battery/last-year queries, slide scoring and selection
- `__init__.py`: websocket `year_roundup/get`, sidebar panel, Dec 1 notification
- `www/index.html`: tap-through story UI (opened on its own, it shows sample data)

## Next steps
- Tests: `pytest` (uses pytest-homeassistant-custom-component with a real recorder).
- Add a shareable image export, slides for Assist voice stats and water/gas, and year-over-year comparisons.
- Longer term: propose it for HA core, which would need a frontend panel and an architecture discussion.
