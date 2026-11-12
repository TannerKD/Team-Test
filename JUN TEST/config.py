"""
config.py - All the settings for the Future City HMI in one place.

Change values here instead of hunting through the code.
"""

# --- Server ---------------------------------------------------------------
HOST = "127.0.0.1"   # only reachable from this computer
PORT = 8000          # open http://localhost:8000 in your browser

# --- Display --------------------------------------------------------------
CITY_NAME = "Future City"
UPDATE_INTERVAL_MS = 2000   # how often the page asks for new data
SIMULATION_TICK_S = 1.0     # how often the fake sensors produce new values
MAX_ALARM_LOG = 30          # how many past alarms to keep

# --- City zones -----------------------------------------------------------
# Each zone gets its own card on the dashboard.
ZONES = [
    {"id": "north",   "name": "North District"},
    {"id": "central", "name": "City Centre"},
    {"id": "harbour", "name": "Harbour"},
    {"id": "east",    "name": "East Residential"},
]

# --- Alarm thresholds -----------------------------------------------------
# value >= warn  -> yellow "WARN"
# value >= alarm -> red    "ALARM"
THRESHOLDS = {
    "traffic":   {"warn": 70,  "alarm": 90,  "unit": "%",   "label": "Traffic congestion"},
    "aqi":       {"warn": 100, "alarm": 150, "unit": "AQI", "label": "Air quality index"},
    "grid_load": {"warn": 80,  "alarm": 95,  "unit": "%",   "label": "Grid load"},
}

# --- Controls the operator can change ------------------------------------
TRAFFIC_MODES = ["normal", "eco", "priority"]
