"""
logic.py - The "brain" of the HMI.

It simulates sensor data for each city zone, decides whether a value is
OK / WARN / ALARM, and applies the commands the operator sends from the page.

Later, your back-end teammates can replace the random simulation in
`_simulate_zone` with real data, and the web page will not need to change.
"""

import random
import threading
import time

import config


def clamp(value, low, high):
    """Keep a number inside [low, high]."""
    return max(low, min(high, value))


def status_for(metric, value):
    """Return 'ok', 'warn' or 'alarm' for a metric based on config.THRESHOLDS."""
    limits = config.THRESHOLDS[metric]
    if value >= limits["alarm"]:
        return "alarm"
    if value >= limits["warn"]:
        return "warn"
    return "ok"


class CityState:
    """Holds the live state of every zone. Thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self.alarms = []          # newest first
        self.zones = {}
        for zone in config.ZONES:
            self.zones[zone["id"]] = {
                "id": zone["id"],
                "name": zone["name"],
                # sensor readings
                "traffic": random.uniform(30, 60),     # % congestion
                "aqi": random.uniform(40, 80),         # air quality index
                "demand_kw": random.uniform(800, 1200),
                "solar_kw": random.uniform(100, 300),
                "capacity_kw": 1600.0,
                # operator controls
                "streetlights": True,
                "traffic_mode": "normal",
                # remembered status so we only log changes
                "_last_status": {},
            }

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def tick(self):
        """Advance the simulation by one step."""
        with self._lock:
            for zone in self.zones.values():
                self._simulate_zone(zone)
                self._check_alarms(zone)

    def _simulate_zone(self, z):
        # Random drift so the numbers move like real sensors.
        z["traffic"] += random.uniform(-6, 6)
        z["aqi"] += random.uniform(-8, 8)
        z["demand_kw"] += random.uniform(-60, 60)
        z["solar_kw"] += random.uniform(-25, 25)

        # Operator controls have an effect on the numbers.
        if z["traffic_mode"] == "eco":
            z["traffic"] += 0.5      # slower flow...
            z["aqi"] -= 1.5          # ...but cleaner air
        elif z["traffic_mode"] == "priority":
            z["traffic"] -= 2.0      # clears congestion fast
            z["aqi"] += 0.5
        # Pollution follows traffic a little.
        z["aqi"] += (z["traffic"] - 50) * 0.05
        # Nudge values back toward a normal level so they don't get stuck at the edges.
        z["aqi"] += (60 - z["aqi"]) * 0.03
        z["traffic"] += (50 - z["traffic"]) * 0.03

        if z["streetlights"]:
            z["demand_kw"] += 5
        else:
            z["demand_kw"] -= 5

        z["traffic"] = clamp(z["traffic"], 0, 100)
        z["aqi"] = clamp(z["aqi"], 10, 300)
        z["demand_kw"] = clamp(z["demand_kw"], 300, z["capacity_kw"])
        z["solar_kw"] = clamp(z["solar_kw"], 0, 600)

    def _grid_load(self, z):
        """Net load as % of capacity (solar reduces what the grid supplies)."""
        net = max(z["demand_kw"] - z["solar_kw"], 0)
        return net / z["capacity_kw"] * 100 + 15   # +15 = base city load

    def _check_alarms(self, z):
        readings = {
            "traffic": z["traffic"],
            "aqi": z["aqi"],
            "grid_load": self._grid_load(z),
        }
        for metric, value in readings.items():
            new = status_for(metric, value)
            old = z["_last_status"].get(metric, "ok")
            if new != old and new != "ok":
                self._log(new, "{}: {} {} ({:.0f} {})".format(
                    z["name"],
                    config.THRESHOLDS[metric]["label"],
                    new.upper(),
                    value,
                    config.THRESHOLDS[metric]["unit"],
                ))
            z["_last_status"][metric] = new

    def _log(self, level, message):
        self.alarms.insert(0, {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        })
        del self.alarms[config.MAX_ALARM_LOG:]

    # ------------------------------------------------------------------
    # Data for the web page
    # ------------------------------------------------------------------
    def snapshot(self):
        """Everything the page needs, as plain dicts (ready for JSON)."""
        with self._lock:
            zones = []
            for z in self.zones.values():
                grid = self._grid_load(z)
                zones.append({
                    "id": z["id"],
                    "name": z["name"],
                    "traffic": round(z["traffic"], 1),
                    "aqi": round(z["aqi"]),
                    "grid_load": round(grid, 1),
                    "demand_kw": round(z["demand_kw"]),
                    "solar_kw": round(z["solar_kw"]),
                    "status": {
                        "traffic": status_for("traffic", z["traffic"]),
                        "aqi": status_for("aqi", z["aqi"]),
                        "grid_load": status_for("grid_load", grid),
                    },
                    "streetlights": z["streetlights"],
                    "traffic_mode": z["traffic_mode"],
                })

            total_demand = sum(z["demand_kw"] for z in zones)
            total_solar = sum(z["solar_kw"] for z in zones)
            active = sum(
                1 for z in zones for s in z["status"].values() if s == "alarm"
            )
            return {
                "city": config.CITY_NAME,
                "time": time.strftime("%H:%M:%S"),
                "summary": {
                    "total_demand_kw": total_demand,
                    "total_solar_kw": total_solar,
                    "solar_share": round(total_solar / total_demand * 100) if total_demand else 0,
                    "avg_aqi": round(sum(z["aqi"] for z in zones) / len(zones)),
                    "active_alarms": active,
                },
                "zones": zones,
                "alarms": list(self.alarms),
                "thresholds": config.THRESHOLDS,
                "traffic_modes": config.TRAFFIC_MODES,
            }

    # ------------------------------------------------------------------
    # Commands from the operator
    # ------------------------------------------------------------------
    def apply_command(self, zone_id, control, value):
        """
        Change a control. Returns (ok, message).
        Validates everything, because the page could send anything.
        """
        with self._lock:
            zone = self.zones.get(zone_id)
            if zone is None:
                return False, "Unknown zone: {}".format(zone_id)

            if control == "streetlights":
                if not isinstance(value, bool):
                    return False, "streetlights must be true or false"
                zone["streetlights"] = value
                text = "ON" if value else "OFF"
            elif control == "traffic_mode":
                if value not in config.TRAFFIC_MODES:
                    return False, "traffic_mode must be one of {}".format(config.TRAFFIC_MODES)
                zone["traffic_mode"] = value
                text = value.upper()
            else:
                return False, "Unknown control: {}".format(control)

            self._log("info", "Operator set {} {} -> {}".format(zone["name"], control, text))
            return True, "ok"
