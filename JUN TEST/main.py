"""
main.py - Starts the web server for the Future City HMI.

Run it from the Team-Test folder:
    python3 "JUN TEST/main.py"
Then open http://localhost:8000 in your browser.  Stop it with Ctrl+C.

Uses only the Python standard library, so there is nothing to install.

Routes:
    GET  /              -> the HMI page (index.html)
    GET  /api/state     -> live data as JSON
    POST /api/control   -> change a control, body: {"zone": "north", "control": "streetlights", "value": false}
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config
from logic import CityState

HERE = Path(__file__).resolve().parent
INDEX_FILE = HERE / "index.html"

city = CityState()


def run_simulation():
    """Background thread: update the fake sensors forever."""
    while True:
        city.tick()
        time.sleep(config.SIMULATION_TICK_S)


class HMIHandler(BaseHTTPRequestHandler):

    def _send(self, status, body, content_type):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status, obj):
        self._send(status, json.dumps(obj), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = INDEX_FILE.read_text(encoding="utf-8")
            # let the page know how often to refresh
            page = page.replace("{{UPDATE_INTERVAL_MS}}", str(config.UPDATE_INTERVAL_MS))
            self._send(200, page, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send_json(200, city.snapshot())
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/control":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid JSON"})
            return

        ok, message = city.apply_command(body.get("zone"), body.get("control"), body.get("value"))
        self._send_json(200 if ok else 400, {"ok": ok, "error": None if ok else message})

    def log_message(self, fmt, *args):
        # Hide the noisy "GET /api/state" line every 2 seconds; show the rest.
        if "/api/state" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    threading.Thread(target=run_simulation, daemon=True).start()
    server = ThreadingHTTPServer((config.HOST, config.PORT), HMIHandler)
    print("{} HMI running at http://localhost:{}  (Ctrl+C to stop)".format(config.CITY_NAME, config.PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
