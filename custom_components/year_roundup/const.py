"""Constants for Year Roundup."""

DOMAIN = "year_roundup"
STORAGE_KEY = f"{DOMAIN}.counters"
STORAGE_VERSION = 1
PANEL_URL = "year-roundup"
STATIC_URL = f"/{DOMAIN}_static"

CONF_AI_ENTITY = "ai_task_entity"
CONF_STYLE = "style"
DEFAULT_STYLE = "Warm, playful and a little cheeky, like a friend reading out your highlights."

# Domains whose on-time and toggles we track
ON_OFF_DOMAINS = ("light", "switch", "fan")
DOOR_CLASSES = ("door", "garage_door", "window", "opening")
MOTION_CLASSES = ("motion", "occupancy", "presence")
IGNORED_STATES = ("unavailable", "unknown")

# Fun-fact conversion factors
KWH_PER_KETTLE = 0.11  # boiling ~1 L of water
KWH_PER_EV_KM = 0.17
SECONDS_SAVED_PER_AUTOMATION = 10
