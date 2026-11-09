# Comparison library

Generated from `comparisons.py`. **sourced** = taken from source; **derived** = calculated from sourced figures; **assumed** = round number, no single source.

## Reference factors

| Key | Value | Unit | Confidence | Source | Note |
|---|---|---|---|---|---|
| `bath_l` | 80 | L per full bath | sourced | [link](https://www.ccw.org.uk/save-money-and-water/averagewateruse/) |  |
| `shower_l` | 75 | L per shower | sourced | [link](https://www.thameswater.co.uk/news/save-hundreds-on-your-bills-by-slashing-water-use-this-summer) | 10 L/min x 7.5 min average shower |
| `person_day_l` | 140 | L per person per day (UK) | sourced | [link](https://www.water.org.uk/news-item/vast-majority-of-brits-have-no-idea-how-much-water-they-use-each-day/) |  |
| `olympic_pool_l` | 3,125,000 | L per Olympic pool | derived | [link](https://resources.fina.org/fina/document/2026/05/21/59daca7b-55ff-4149-be49-46e0154c78c6/2026-03-11-WA-Pool-Certification-Swimming.docx) | 50 m x 25 m x 2.5 m minimum depth (World Aquatics) |
| `toilet_flush_l` | 6 | L per flush (max for new UK toilets) | sourced | [link](https://www.legislation.gov.uk/uksi/1999/1148/schedule/2) |  |
| `washer_l` | 48 | L per washing machine cycle | sourced | [link](https://inthewash.co.uk/?p=4598) | average of 20 popular models |
| `dishwasher_l` | 10.5 | L per dishwasher cycle | sourced | [link](https://www.fuseenergy.com/blog/are-dishwashers-expensive-to-run) | midpoint of 9-12 L |
| `mug_l` | 0.25 | L per mug | assumed | — |  |
| `kettle_kwh_l` | 0.103 | kWh per litre boiled | derived | [link](https://freepricecompare.com/?p=208236) | 0.093 kWh/L to heat 20->100 C, at 90% kettle efficiency |
| `ev_kwh_mile` | 0.346 | kWh per EV mile | sourced | [link](https://ecocostsavings.com/average-electric-car-kwh-per-mile/) | average of 231 EVs on fueleconomy.gov; sales-weighted newer EVs ~0.29 |
| `phone_kwh` | 0.015 | kWh per phone charge | derived | [link](https://www.energysage.com/electricity/house-watts/how-many-watts-does-a-phone-charger-use/) | ~12-13 Wh battery plus charging losses |
| `uk_home_kwh` | 2,500 | kWh electricity per typical UK home per year | sourced | [link](https://www.ofgem.gov.uk/sites/default/files/2026-06/Summary-of-changes-to-energy-price-cap-1-July-to-30-September-2026-revised-TDCV.pdf) | Ofgem TDCV from 1 July 2026 |
| `uk_home_gas_kwh` | 9,500 | kWh gas per typical UK home per year | sourced | [link](https://www.ofgem.gov.uk/sites/default/files/2026-06/Summary-of-changes-to-energy-price-cap-1-July-to-30-September-2026-revised-TDCV.pdf) |  |
| `aa_wh` | 4.3 | Wh per AA alkaline battery | derived | [link](https://www.farnell.com/datasheets/1820687.pdf) | Energizer E91: 2850 mAh x 1.5 V |
| `led_w` | 8 | W per LED bulb (60 W equivalent) | sourced | [link](https://energysavingtrust.org.uk/advice/lighting/) | 800 lm LED draws ~7-10 W |
| `washer_kwh` | 0.46 | kWh per washing machine cycle | sourced | [link](https://inthewash.co.uk/?p=4598) |  |
| `dishwasher_kwh` | 1.1 | kWh per dishwasher cycle | sourced | [link](https://www.comparethemarket.com/energy/information/how-much-does-a-dishwasher-use) | Energy Saving Trust figure |
| `bath_heat_kwh` | 2.8 | kWh to heat one bath | derived | — | 80 L x 4.186 kJ/kg.K x 30 K rise / 3600 |
| `gas_kwh_m3` | 11.2 | kWh per m3 of gas | derived | [link](https://www.britishgas.co.uk/business/help-and-support/connections-meters-readings/convert-gas-m3-to-kwh) | m3 x 1.02264 x 39.5 MJ/m3 / 3.6 |
| `grid_co2_kg_kwh` | 0.177 | kg CO2e per kWh (UK grid) | sourced | [link](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025) | DESNZ 2025 generation factor; check yearly |
| `tree_kg_co2` | 60 | kg CO2 per tree seedling grown 10 years | sourced | [link](https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator) | EPA: 0.060 t per urban seedling |
| `uk_tv_min_day` | 144 | min broadcast TV per person per day (UK 2024) | sourced | [link](https://www.ofcom.org.uk/media-use-and-attitudes/media-habits-adults/nations-media-habits-revealed-in-annual-ofcom-report) | Ofcom Media Nations 2025 |
| `song_min` | 3.85 | min per chart song (2024) | sourced | [link](https://www.thestar.co.uk/whats-on/arts-and-entertainment/tiktok-music-length-complexity-lyrics-not-shorter-5261212) | Startle study: 3:51 average |
| `film_h` | 2 | h per feature film | assumed | — |  |
| `flight_lon_nyc_h` | 7.5 | h London -> New York flight | assumed | — |  |
| `year_h` | 8,760 | h per year | derived | — | 365 x 24 |
| `moon_km` | 384,400 | km Earth -> Moon (average) | sourced | [link](https://science.nasa.gov/moon/facts/) |  |
| `earth_km` | 40,075 | km around the equator | sourced | [link](https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html) | 2 x pi x 6378.137 km |
| `marathon_km` | 42.195 | km per marathon | sourced | [link](https://worldathletics.org/about-iaaf/documents/book-of-rules) |  |
| `lejog_mi` | 874 | miles Land's End -> John o' Groats | sourced | [link](https://en.wikipedia.org/wiki/Land%27s_End_to_John_o%27_Groats) | signposted road distance |

## Comparisons (65)

| Metric | Template | Tone | Uses |
|---|---|---|---|
| `water_l` | enough to fill {n} baths | playful | bath_l |
| `water_l` | the same as {n} average showers | neutral | shower_l |
| `water_l` | {n} mugs of tea | playful | mug_l |
| `water_l` | {n} Olympic swimming pools | playful | olympic_pool_l |
| `water_per_person_day_l` | {n}% of the UK average per person | neutral | person_day_l |
| `water_per_person_day_l` | {n} toilet flushes a day each | cheeky | toilet_flush_l |
| `grid_kwh` | enough to drive an EV {n} miles | neutral | ev_kwh_mile |
| `grid_kwh` | {n} full kettles boiled | playful | kettle_kwh_l |
| `grid_kwh` | {n} phone charges | playful | phone_kwh |
| `grid_kwh` | {n}% of a typical UK home's electricity | neutral | uk_home_kwh |
| `solar_kwh` | enough to drive an EV from Land's End to John o' Groats {n} times | proud | ev_kwh_mile, lejog_mi |
| `solar_kwh` | enough to power {n} typical UK homes for a year | proud | uk_home_kwh |
| `solar_kwh` | {n} AA batteries' worth of sunshine | playful | aa_wh |
| `solar_kwh` | an EV trip {n} times around the Earth | proud | ev_kwh_mile, earth_km |
| `solar_kwh` | the CO2 that {n} trees soak up in 10 years | proud | tree_kg_co2, grid_co2_kg_kwh |
| `self_powered_pct` | {n} days of the year running on your own sun | proud | calendar maths |
| `export_kwh` | a neighbour's electricity for {n} months | proud | uk_home_kwh |
| `export_kwh` | {n} kettles for the rest of the street | playful | kettle_kwh_l |
| `gas_m3` | enough to heat {n} hot baths | neutral | bath_heat_kwh, gas_kwh_m3 |
| `gas_m3` | {n}% of a typical UK home's gas | neutral | uk_home_gas_kwh, gas_kwh_m3 |
| `standby_w` | like leaving {n} LED bulbs on all year | cheeky | led_w |
| `standby_w` | {n} kettles boiled for nothing | cheeky | kettle_kwh_l, year_h |
| `automation_runs` | {n} films' worth of time saved | proud | film_h |
| `automation_runs` | {n} London to New York flights of time saved | proud | flight_lon_nyc_h |
| `light_hours` | one bulb left on for {n} years | playful | year_h |
| `light_hours` | {n} kettles' worth of light (LED) | neutral | kettle_kwh_l, led_w |
| `tv_hours` | {n}% of the whole year | cheeky | year_h |
| `tv_hours` | {n}% of the UK average | neutral | uk_tv_min_day |
| `tv_hours` | {n} feature films back to back | playful | film_h |
| `music_hours` | about {n} songs | playful | song_min |
| `music_hours` | a road trip from Land's End to John o' Groats {n} times at 50 mph | playful | lejog_mi |
| `music_hours` | {n} full days of non-stop music | playful | calendar maths |
| `door_opens` | {n} times a day | neutral | calendar maths |
| `door_opens` | once every {n} waking minutes | playful | calendar maths |
| `fridge_open_min` | fridge wide open for {n} hours straight | cheeky | calendar maths |
| `fridge_open_min` | the length of {n} films | cheeky | film_h |
| `motion_events` | your home noticed you {n} times a day | playful | calendar maths |
| `walk_km` | {n} marathons around the house | proud | marathon_km |
| `walk_km` | {n}% of the way to the Moon | playful | moon_km |
| `coffee_brews` | {n} coffees a day | playful | calendar maths |
| `coffee_brews` | {n} baths full of coffee | cheeky | bath_l |
| `kettle_boils` | the same energy as driving an EV {n} miles | cheeky | kettle_kwh_l, ev_kwh_mile |
| `kettle_boils` | {n} brews a day | playful | calendar maths |
| `washer_cycles` | a load every {n} days | neutral | calendar maths |
| `washer_cycles` | {n}% of an Olympic pool in laundry water | playful | olympic_pool_l, washer_l |
| `dishwasher_cycles` | the energy of {n} phone charges | playful | phone_kwh, dishwasher_kwh |
| `dishwasher_cycles` | {n} baths of water | neutral | bath_l, dishwasher_l |
| `heating_hours` | {n} days of cosy | proud | calendar maths |
| `heating_hours` | {n}% of the year | neutral | year_h |
| `setpoint_changes` | {n} thermostat tweaks a week | cheeky | calendar maths |
| `voice_commands` | you talked to your home {n} times a day | playful | calendar maths |
| `uptime_days` | online {n}% of the year | proud | calendar maths |
| `batteries_replaced` | {n} battery swaps a month | neutral | calendar maths |
| `vacuum_km` | your vacuum ran {n} marathons | proud | marathon_km |
| `vacuum_km` | {n}% of the way from Land's End to John o' Groats | playful | lejog_mi |
| `ev_charge_kwh` | about {n} miles of driving | neutral | ev_kwh_mile |
| `ev_charge_kwh` | {n}% of a drive to the Moon | playful | ev_kwh_mile, moon_km |
| `home_pct` | {n} days at home | neutral | calendar maths |
| `doorbell_rings` | {n} visitors a week | playful | calendar maths |
| `garage_opens` | {n} trips out a day | neutral | calendar maths |
| `catflap_uses` | your cat came and went {n} times a day | playful | calendar maths |
| `irrigation_l` | {n} baths for the garden | proud | bath_l |
| `showers` | {n} hours in the shower | cheeky | shower_l |
| `oven_hours` | {n} films' worth of baking | playful | film_h |
| `printer_pages` | {n} 300-page books printed | cheeky | calendar maths |
