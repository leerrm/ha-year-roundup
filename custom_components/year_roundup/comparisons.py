"""Turn raw yearly metrics into relatable comparisons.

Every factor carries a source and a confidence level:
  sourced  - taken from the cited source
  derived  - calculated from sourced figures (working shown in `note`)
  assumed  - a reasonable round number with no single authoritative source

Numbers are always computed here, never by the AI. The AI may only reword.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

# --------------------------------------------------------------------------
# Reference factors
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Factor:
    value: float
    unit: str
    confidence: str  # sourced | derived | assumed
    source: str
    note: str = ""


F: dict[str, Factor] = {
    # Water
    "bath_l": Factor(80, "L per full bath", "sourced", "https://www.ccw.org.uk/save-money-and-water/averagewateruse/"),
    "shower_l": Factor(75, "L per shower", "sourced", "https://www.thameswater.co.uk/news/save-hundreds-on-your-bills-by-slashing-water-use-this-summer", "10 L/min x 7.5 min average shower"),
    "person_day_l": Factor(140, "L per person per day (UK)", "sourced", "https://www.water.org.uk/news-item/vast-majority-of-brits-have-no-idea-how-much-water-they-use-each-day/"),
    "olympic_pool_l": Factor(3_125_000, "L per Olympic pool", "derived", "https://resources.fina.org/fina/document/2026/05/21/59daca7b-55ff-4149-be49-46e0154c78c6/2026-03-11-WA-Pool-Certification-Swimming.docx", "50 m x 25 m x 2.5 m minimum depth (World Aquatics)"),
    "toilet_flush_l": Factor(6, "L per flush (max for new UK toilets)", "sourced", "https://www.legislation.gov.uk/uksi/1999/1148/schedule/2"),
    "washer_l": Factor(48, "L per washing machine cycle", "sourced", "https://inthewash.co.uk/?p=4598", "average of 20 popular models"),
    "dishwasher_l": Factor(10.5, "L per dishwasher cycle", "sourced", "https://www.fuseenergy.com/blog/are-dishwashers-expensive-to-run", "midpoint of 9-12 L"),
    "mug_l": Factor(0.25, "L per mug", "assumed", ""),
    # Electricity / energy
    "kettle_kwh_l": Factor(0.103, "kWh per litre boiled", "derived", "https://freepricecompare.com/?p=208236", "0.093 kWh/L to heat 20->100 C, at 90% kettle efficiency"),
    "ev_kwh_mile": Factor(0.346, "kWh per EV mile", "sourced", "https://ecocostsavings.com/average-electric-car-kwh-per-mile/", "average of 231 EVs on fueleconomy.gov; sales-weighted newer EVs ~0.29"),
    "phone_kwh": Factor(0.015, "kWh per phone charge", "derived", "https://www.energysage.com/electricity/house-watts/how-many-watts-does-a-phone-charger-use/", "~12-13 Wh battery plus charging losses"),
    "uk_home_kwh": Factor(2500, "kWh electricity per typical UK home per year", "sourced", "https://www.ofgem.gov.uk/sites/default/files/2026-06/Summary-of-changes-to-energy-price-cap-1-July-to-30-September-2026-revised-TDCV.pdf", "Ofgem TDCV from 1 July 2026"),
    "uk_home_gas_kwh": Factor(9500, "kWh gas per typical UK home per year", "sourced", "https://www.ofgem.gov.uk/sites/default/files/2026-06/Summary-of-changes-to-energy-price-cap-1-July-to-30-September-2026-revised-TDCV.pdf"),
    "aa_wh": Factor(4.3, "Wh per AA alkaline battery", "derived", "https://www.farnell.com/datasheets/1820687.pdf", "Energizer E91: 2850 mAh x 1.5 V"),
    "led_w": Factor(8, "W per LED bulb (60 W equivalent)", "sourced", "https://energysavingtrust.org.uk/advice/lighting/", "800 lm LED draws ~7-10 W"),
    "washer_kwh": Factor(0.46, "kWh per washing machine cycle", "sourced", "https://inthewash.co.uk/?p=4598"),
    "dishwasher_kwh": Factor(1.1, "kWh per dishwasher cycle", "sourced", "https://www.comparethemarket.com/energy/information/how-much-does-a-dishwasher-use", "Energy Saving Trust figure"),
    "bath_heat_kwh": Factor(2.8, "kWh to heat one bath", "derived", "", "80 L x 4.186 kJ/kg.K x 30 K rise / 3600"),
    "gas_kwh_m3": Factor(11.2, "kWh per m3 of gas", "derived", "https://www.britishgas.co.uk/business/help-and-support/connections-meters-readings/convert-gas-m3-to-kwh", "m3 x 1.02264 x 39.5 MJ/m3 / 3.6"),
    "grid_co2_kg_kwh": Factor(0.177, "kg CO2e per kWh (UK grid)", "sourced", "https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025", "DESNZ 2025 generation factor; check yearly"),
    "tree_kg_co2": Factor(60, "kg CO2 per tree seedling grown 10 years", "sourced", "https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator", "EPA: 0.060 t per urban seedling"),
    # Time
    "uk_tv_min_day": Factor(144, "min broadcast TV per person per day (UK 2024)", "sourced", "https://www.ofcom.org.uk/media-use-and-attitudes/media-habits-adults/nations-media-habits-revealed-in-annual-ofcom-report", "Ofcom Media Nations 2025"),
    "song_min": Factor(3.85, "min per chart song (2024)", "sourced", "https://www.thestar.co.uk/whats-on/arts-and-entertainment/tiktok-music-length-complexity-lyrics-not-shorter-5261212", "Startle study: 3:51 average"),
    "film_h": Factor(2, "h per feature film", "assumed", ""),
    "flight_lon_nyc_h": Factor(7.5, "h London -> New York flight", "assumed", ""),
    "year_h": Factor(8760, "h per year", "derived", "", "365 x 24"),
    # Distance
    "moon_km": Factor(384_400, "km Earth -> Moon (average)", "sourced", "https://science.nasa.gov/moon/facts/"),
    "earth_km": Factor(40_075, "km around the equator", "sourced", "https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html", "2 x pi x 6378.137 km"),
    "marathon_km": Factor(42.195, "km per marathon", "sourced", "https://worldathletics.org/about-iaaf/documents/book-of-rules"),
    "lejog_mi": Factor(874, "miles Land's End -> John o' Groats", "sourced", "https://en.wikipedia.org/wiki/Land%27s_End_to_John_o%27_Groats", "signposted road distance"),
}


# --------------------------------------------------------------------------
# Comparisons: metric -> ways to express it
# result = metric_value * mult / per  (then rounded nicely)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    metric: str
    id: str
    per: float  # metric units per "one thing"
    template: str  # {n} = the computed number
    tone: str  # proud | playful | cheeky | neutral
    factors: tuple[str, ...] = ()
    lo: float = 2  # sweet-spot range for {n}
    hi: float = 99_999


def _f(key: str) -> float:
    return F[key].value


C: list[Comparison] = [
    # 1 Water (L)
    Comparison("water_l", "baths", _f("bath_l"), "enough to fill {n} baths", "playful", ("bath_l",)),
    Comparison("water_l", "showers", _f("shower_l"), "the same as {n} average showers", "neutral", ("shower_l",)),
    Comparison("water_l", "mugs", _f("mug_l"), "{n} mugs of tea", "playful", ("mug_l",), hi=9_999_999),
    Comparison("water_l", "pools", _f("olympic_pool_l"), "{n} Olympic swimming pools", "playful", ("olympic_pool_l",), lo=1, hi=999),
    # 2 Water vs average household
    Comparison("water_per_person_day_l", "vs_uk", _f("person_day_l") / 100, "{n}% of the UK average per person", "neutral", ("person_day_l",), lo=10, hi=300),
    Comparison("water_per_person_day_l", "flushes", _f("toilet_flush_l"), "{n} toilet flushes a day each", "cheeky", ("toilet_flush_l",)),
    # 3 Grid electricity (kWh)
    Comparison("grid_kwh", "ev_miles", _f("ev_kwh_mile"), "enough to drive an EV {n} miles", "neutral", ("ev_kwh_mile",), hi=99_999),
    Comparison("grid_kwh", "kettles", _f("kettle_kwh_l") * 1.7, "{n} full kettles boiled", "playful", ("kettle_kwh_l",), hi=99_999),
    Comparison("grid_kwh", "phones", _f("phone_kwh"), "{n} phone charges", "playful", ("phone_kwh",), hi=9_999_999),
    Comparison("grid_kwh", "vs_uk_home", _f("uk_home_kwh") / 100, "{n}% of a typical UK home's electricity", "neutral", ("uk_home_kwh",), lo=10, hi=500),
    # 4 Solar generated (kWh)
    Comparison("solar_kwh", "lejog", _f("ev_kwh_mile") * _f("lejog_mi"), "enough to drive an EV from Land's End to John o' Groats {n} times", "proud", ("ev_kwh_mile", "lejog_mi")),
    Comparison("solar_kwh", "homes_year", _f("uk_home_kwh"), "enough to power {n} typical UK homes for a year", "proud", ("uk_home_kwh",), lo=0.3, hi=99),
    Comparison("solar_kwh", "aa", _f("aa_wh") / 1000, "{n} AA batteries' worth of sunshine", "playful", ("aa_wh",), hi=99_999_999),
    Comparison("solar_kwh", "around_world", _f("ev_kwh_mile") * _f("earth_km") / 1.609, "an EV trip {n} times around the Earth", "proud", ("ev_kwh_mile", "earth_km"), lo=1, hi=99),
    # 5 Solar CO2 avoided (kWh in -> trees)
    Comparison("solar_kwh", "trees", _f("tree_kg_co2") / _f("grid_co2_kg_kwh"), "the CO2 that {n} trees soak up in 10 years", "proud", ("tree_kg_co2", "grid_co2_kg_kwh")),
    # 6 Self-powered share (%)
    Comparison("self_powered_pct", "days", 100 / 365, "{n} days of the year running on your own sun", "proud", (), lo=1, hi=365),
    # 7 Exported to grid (kWh)
    Comparison("export_kwh", "neighbours", _f("uk_home_kwh") / 12, "a neighbour's electricity for {n} months", "proud", ("uk_home_kwh",), lo=1, hi=120),
    Comparison("export_kwh", "kettles", _f("kettle_kwh_l") * 1.7, "{n} kettles for the rest of the street", "playful", ("kettle_kwh_l",), hi=99_999),
    # 8 Gas (m3)
    Comparison("gas_m3", "baths", _f("bath_heat_kwh") / _f("gas_kwh_m3"), "enough to heat {n} hot baths", "neutral", ("bath_heat_kwh", "gas_kwh_m3"), hi=99_999),
    Comparison("gas_m3", "vs_uk", _f("uk_home_gas_kwh") / _f("gas_kwh_m3") / 100, "{n}% of a typical UK home's gas", "neutral", ("uk_home_gas_kwh", "gas_kwh_m3"), lo=10, hi=500),
    # 9 Standby / overnight base load (W, average)
    Comparison("standby_w", "bulbs", _f("led_w"), "like leaving {n} LED bulbs on all year", "cheeky", ("led_w",), lo=1, hi=999),
    Comparison("standby_w", "kettles_yr", _f("kettle_kwh_l") * 1.7 * 1000 / _f("year_h"), "{n} kettles boiled for nothing", "cheeky", ("kettle_kwh_l", "year_h"), hi=99_999),
    # 10 Automation runs (count -> 10 s saved each)
    Comparison("automation_runs", "films", _f("film_h") * 360, "{n} films' worth of time saved", "proud", ("film_h",), lo=1, hi=999),
    Comparison("automation_runs", "flights", _f("flight_lon_nyc_h") * 360, "{n} London to New York flights of time saved", "proud", ("flight_lon_nyc_h",), lo=1, hi=999),
    # 11 Light hours (sum of bulbs on)
    Comparison("light_hours", "one_bulb_years", _f("year_h"), "one bulb left on for {n} years", "playful", ("year_h",), lo=1, hi=999),
    Comparison("light_hours", "kwh_kettles", _f("kettle_kwh_l") * 1.7 * 1000 / _f("led_w"), "{n} kettles' worth of light (LED)", "neutral", ("kettle_kwh_l", "led_w"), hi=99_999),
    # 12 TV hours
    Comparison("tv_hours", "pct_year", _f("year_h") / 100, "{n}% of the whole year", "cheeky", ("year_h",), lo=1, hi=100),
    Comparison("tv_hours", "vs_uk", _f("uk_tv_min_day") * 365 / 60 / 100, "{n}% of the UK average", "neutral", ("uk_tv_min_day",), lo=10, hi=500),
    Comparison("tv_hours", "films", _f("film_h"), "{n} feature films back to back", "playful", ("film_h",)),
    # 13 Music hours
    Comparison("music_hours", "songs", _f("song_min") / 60, "about {n} songs", "playful", ("song_min",), hi=999_999),
    Comparison("music_hours", "lejog", 874 / 50, "a road trip from Land's End to John o' Groats {n} times at 50 mph", "playful", ("lejog_mi",), lo=1, hi=999),
    Comparison("music_hours", "days", 24, "{n} full days of non-stop music", "playful", (), lo=1, hi=365),
    # 14 Door opens
    Comparison("door_opens", "per_day", 365, "{n} times a day", "neutral", (), lo=1, hi=999),
    Comparison("door_opens", "per_waking_min", 365 * 16 * 60, "once every {n} waking minutes", "playful", (), lo=1, hi=999),  # inverted in code
    # 15 Fridge door open (minutes total)
    Comparison("fridge_open_min", "hours", 60, "fridge wide open for {n} hours straight", "cheeky", (), lo=1, hi=999),
    Comparison("fridge_open_min", "films", _f("film_h") * 60, "the length of {n} films", "cheeky", ("film_h",), lo=1, hi=999),
    # 16 Motion events
    Comparison("motion_events", "per_day", 365, "your home noticed you {n} times a day", "playful", (), lo=1, hi=9_999),
    # 17 Walking distance (km, from motion paths/steps estimate)
    Comparison("walk_km", "marathons", _f("marathon_km"), "{n} marathons around the house", "proud", ("marathon_km",), lo=1),
    Comparison("walk_km", "moon_pct", _f("moon_km") / 100, "{n}% of the way to the Moon", "playful", ("moon_km",), lo=1, hi=100),
    # 18 Coffee brews
    Comparison("coffee_brews", "per_day", 365, "{n} coffees a day", "playful", (), lo=0.5, hi=50),
    Comparison("coffee_brews", "baths", _f("bath_l") / 0.2, "{n} baths full of coffee", "cheeky", ("bath_l",), lo=0.2, hi=99),
    # 19 Kettle boils
    Comparison("kettle_boils", "ev_miles", _f("ev_kwh_mile") / (_f("kettle_kwh_l") * 1.0), "the same energy as driving an EV {n} miles", "cheeky", ("kettle_kwh_l", "ev_kwh_mile")),
    Comparison("kettle_boils", "per_day", 365, "{n} brews a day", "playful", (), lo=0.5, hi=50),
    # 20 Washing machine cycles
    Comparison("washer_cycles", "every_days", 365, "a load every {n} days", "neutral", (), lo=0.2, hi=60),  # inverted
    Comparison("washer_cycles", "pools_pct", _f("olympic_pool_l") / _f("washer_l") / 100, "{n}% of an Olympic pool in laundry water", "playful", ("olympic_pool_l", "washer_l"), lo=1, hi=100),
    # 21 Dishwasher cycles
    Comparison("dishwasher_cycles", "phones", _f("phone_kwh") / _f("dishwasher_kwh"), "the energy of {n} phone charges", "playful", ("phone_kwh", "dishwasher_kwh"), hi=9_999_999),
    Comparison("dishwasher_cycles", "baths", _f("bath_l") / _f("dishwasher_l"), "{n} baths of water", "neutral", ("bath_l", "dishwasher_l")),
    # 22 Heating on (hours)
    Comparison("heating_hours", "days", 24, "{n} days of cosy", "proud", (), lo=1, hi=365),
    Comparison("heating_hours", "pct_year", _f("year_h") / 100, "{n}% of the year", "neutral", ("year_h",), lo=1, hi=100),
    # 23 Thermostat changes
    Comparison("setpoint_changes", "per_week", 52, "{n} thermostat tweaks a week", "cheeky", (), lo=1, hi=999),
    # 24 Voice commands
    Comparison("voice_commands", "per_day", 365, "you talked to your home {n} times a day", "playful", (), lo=0.5, hi=999),
    # 25 Uptime (days)
    Comparison("uptime_days", "pct", 365 / 100, "online {n}% of the year", "proud", (), lo=50, hi=100),
    # 26 Batteries replaced (count of jumps)
    Comparison("batteries_replaced", "per_month", 12, "{n} battery swaps a month", "neutral", (), lo=0.2, hi=99),
    # 27 Robot vacuum distance (km)
    Comparison("vacuum_km", "marathons", _f("marathon_km"), "your vacuum ran {n} marathons", "proud", ("marathon_km",), lo=0.5),
    Comparison("vacuum_km", "lejog_pct", _f("lejog_mi") * 1.609 / 100, "{n}% of the way from Land's End to John o' Groats", "playful", ("lejog_mi",), lo=1, hi=100),
    # 28 EV charged at home (kWh)
    Comparison("ev_charge_kwh", "miles", _f("ev_kwh_mile"), "about {n} miles of driving", "neutral", ("ev_kwh_mile",), hi=99_999),
    Comparison("ev_charge_kwh", "moon_pct", _f("ev_kwh_mile") * _f("moon_km") / 1.609 / 100, "{n}% of a drive to the Moon", "playful", ("ev_kwh_mile", "moon_km"), lo=0.5, hi=100),
    # 29 Time at home (%)
    Comparison("home_pct", "days", 100 / 365, "{n} days at home", "neutral", (), lo=1, hi=365),
    # 30 Doorbell rings
    Comparison("doorbell_rings", "per_week", 52, "{n} visitors a week", "playful", (), lo=0.2, hi=999),
    # 31 Garage door opens
    Comparison("garage_opens", "per_day", 365, "{n} trips out a day", "neutral", (), lo=0.2, hi=99),
    # 32 Cat flap uses
    Comparison("catflap_uses", "per_day", 365, "your cat came and went {n} times a day", "playful", (), lo=0.5, hi=999),
    # 33 Plants watered (L)
    Comparison("irrigation_l", "baths", _f("bath_l"), "{n} baths for the garden", "proud", ("bath_l",)),
    # 34 Showers taken (count, from water flow / humidity)
    Comparison("showers", "hours", 60 / 7.5, "{n} hours in the shower", "cheeky", ("shower_l",), lo=1),
    # 35 Oven hours
    Comparison("oven_hours", "films", _f("film_h"), "{n} films' worth of baking", "playful", ("film_h",), lo=1),
    # 36 Printer pages
    Comparison("printer_pages", "books", 300, "{n} 300-page books printed", "cheeky", (), lo=0.2, hi=999),
]

# Comparisons phrased as "once every N" rather than "N per"
_INVERTED = {("door_opens", "per_waking_min"), ("washer_cycles", "every_days")}


def nice(n: float) -> str:
    """Round to something a human would say."""
    if n >= 100:
        mag = 10 ** (int(math.log10(n)) - 1)
        return f"{round(n / mag) * mag:,.0f}"
    if n >= 10:
        return f"{round(n):,}"
    if n >= 1:
        return f"{n:.1f}".rstrip("0").rstrip(".")
    return f"{n:.2g}"


def compute(c: Comparison, value: float) -> float:
    if (c.metric, c.id) in _INVERTED:
        return c.per / value if value else math.inf
    return value / c.per


def best(metric: str, value: float, year: int, tones: set[str] | None = None) -> dict | None:
    """Pick one comparison for a metric: in range, allowed tone, rotated by year."""
    if not value:
        return None
    options = [
        c for c in C
        if c.metric == metric and (tones is None or c.tone in tones) and c.lo <= compute(c, value) <= c.hi
    ]
    if not options:
        return None
    c = options[year % len(options)]  # rotate so the same home sees variety each year
    n = compute(c, value)
    return {
        "metric": metric,
        "id": c.id,
        "n": n,
        "text": c.template.format(n=nice(n)),
        "tone": c.tone,
        "sources": [F[k].source for k in c.factors if F[k].source],
    }


def all_for(metric: str, value: float, tones: set[str] | None = None) -> list[dict]:
    """Every in-range comparison (for AI to choose from / for screens to score)."""
    out = []
    for c in C:
        if c.metric == metric and (tones is None or c.tone in tones):
            n = compute(c, value) if value else 0
            if c.lo <= n <= c.hi:
                out.append({"id": c.id, "text": c.template.format(n=nice(n)), "tone": c.tone})
    return out
