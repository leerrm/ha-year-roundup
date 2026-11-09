# Year Roundup (prototype)

A yearly story for your home: energy, lights, doors, automations, music, climate, devices added. Computed locally; nothing leaves the house.

## Install
Copy `custom_components/year_roundup` into your HA config, restart, then add **Year Roundup** under Settings → Devices & services. A **Year Roundup** sidebar panel appears. A notification fires on 1 December.

## Where the data comes from
| Section | Source | Backfills? |
|---|---|---|
| Energy, solar, hottest/coldest | Recorder long-term statistics | Yes, full year |
| Devices added, totals | Device/entity registries (`created_at`) | Yes |
| Lights, doors, motion, automations, music, persona, busiest day | Own counters in `.storage` | No, start at install |

The recorder purges raw history after ~10 days, so the event-based counters only work if the integration runs all year.

## Optional AI captions
In the integration options, pick an **AI Task** entity (Ollama, OpenAI, Google, Anthropic…) and write a style prompt ("roast me", "nature documentary narrator", "for kids"…).
- The model gets the computed facts only and is told not to change numbers. All numbers on the slides still come from local data; only the caption text changes.
- Captions are cached per year for a day; add `?refresh=1` to the panel URL to regenerate.
- No agent, a timeout (90 s) or an error → built-in text. If a cached caption exists, that is used instead.
- With a cloud agent the summary leaves the house, so the closing slide says who wrote the captions instead of "none of it left your home".

## Files
- `ai.py`: AI Task call, prompt, structured per-slide output
- `tracker.py`: listens to the event bus and keeps per-year counters
- `roundup.py`: builds the roundup (stats queries, top lists, persona, fun facts)
- `__init__.py`: websocket `year_roundup/get`, sidebar panel, Dec 1 notification
- `www/index.html`: tap-through story UI (opened on its own, it shows sample data)

## Next steps
- Test on a real instance. So far it has only been compiled, and the UI rendered with sample data.
- Add a shareable image export, slides for Assist voice stats and water/gas, and year-over-year comparisons.
- Longer term: propose it for HA core, which would need a frontend panel and an architecture discussion.
