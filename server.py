"""WifiScope routes and the background monitor. Scanning only runs while the page is open (it stops 45 s after the last
request) so a forgotten window does not keep the Wi-Fi radio busy."""
import collections
import csv
import io
import logging
import os
import threading
import time

import appserver
import storage
import wifi
from appserver import BadRequest

kit = appserver.Kit("WifiScope", "WIFISCOPE_PORT", 8775)
HOST, PORT = appserver.HOST, kit.port
last_seen = kit.last_seen
build_server = kit.build_server
VERSION = "1.0.0"
log = logging.getLogger("wifiscope.server")
quit_event = threading.Event()
ACTIVE_WINDOW = 45.0
LOCATION_URI = "ms-settings:privacy-location"


class Monitor:
    def __init__(self, netsh, settings, is_active, settle=4.0, clock=time.time):
        self.netsh, self.settings, self.is_active, self.settle, self.clock = netsh, settings, is_active, settle, clock
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.state, self.message, self.detail = "starting", "", ""
        self.networks, self.analysis, self.adapters = [], [], []
        self.connected = None
        self.last_scan = 0.0
        self.scanning = False
        self.scans = 0
        self.history = collections.deque(maxlen=1800)        # 1 sample / 2 s = 1 hour
        self._manual_at = 0.0

    # -- one scan: trigger the driver, wait a moment, read the list and the adapter
    def scan_once(self):
        with self.lock:
            self.scanning = True
        try:
            try:
                self.netsh.trigger_scan()
            except Exception:  # noqa: BLE001
                log.exception("trigger_scan failed")
            if self.settle:
                self.stop.wait(self.settle)
            rc1, t1 = self.netsh.run("networks")
            rc2, t2 = self.netsh.run("interfaces")
            nets = wifi.parse_networks(t1)
            adapters = wifi.parse_interfaces(t2)
            conn = next((a for a in adapters if a["connected"]), None)
            state, msg = wifi.diagnose(t1, t2, nets)
            detail = "" if state == "ok" else wifi.first_message(t1, t2)
            analysis = wifi.analyze(nets, conn)
            with self.lock:
                self.state, self.message, self.detail = state, msg, detail
                if state in ("ok", "empty"):
                    self.networks = nets
                else:
                    self.networks = []
                self.analysis, self.adapters, self.connected = analysis, adapters, conn
                self.last_scan = self.clock()
                self.scans += 1
        finally:
            with self.lock:
                self.scanning = False

    def poll_interface(self):
        rc, t = self.netsh.run("interfaces")
        adapters = wifi.parse_interfaces(t)
        conn = next((a for a in adapters if a["connected"]), None)
        with self.lock:
            self.adapters, self.connected = adapters, conn
            self.history.append({"t": self.clock(), "signal": conn["signal"] if conn else None, "rssi": conn["rssi"] if conn else None,
                                 "bssid": conn["bssid"] if conn else "", "channel": conn["channel"] if conn else None, "ssid": conn["ssid"] if conn else ""})

    def request_scan(self):
        now = self.clock()
        if now - self._manual_at < 3.0:
            return False
        self._manual_at = now
        self.wake.set()
        return True

    def _run(self):
        last_scan = last_if = 0.0
        while not self.stop.is_set():
            if not self.is_active():
                self.wake.wait(1.0)
                if not self.wake.is_set():
                    continue
            now = time.time()
            interval = self.settings.data["interval"]
            manual = self.wake.is_set()
            self.wake.clear()
            try:
                if manual or (self.scans == 0) or (interval and now - last_scan >= interval):
                    self.scan_once()
                    last_scan = last_if = time.time()
                elif now - last_if >= 2.0:
                    self.poll_interface()
                    last_if = time.time()
                    if self.state in ("starting",):
                        self.scan_once()
            except Exception:  # noqa: BLE001
                log.exception("scan loop error")
                with self.lock:
                    self.state, self.message = "error", "Something went wrong while scanning. See the log."
                self.stop.wait(5)
            self.wake.wait(0.5)

    def start(self):
        self.thread = threading.Thread(target=self._run, name="monitor", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(5)


M = None
SETTINGS = None
OPENER = None


def init(netsh=None, opener=None, settle=4.0, settings_path=None):
    global M, SETTINGS, OPENER
    SETTINGS = storage.Settings(settings_path)
    OPENER = opener or (lambda uri: os.startfile(uri))      # noqa: S606 - fixed Windows settings URI only
    M = Monitor(netsh or wifi.Netsh(), SETTINGS, lambda: time.time() - kit.last_seen() < ACTIVE_WINDOW, settle)


def on_start():
    if M is None:
        init()
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)
        except Exception:  # noqa: BLE001
            pass
    kit.touch()
    M.start()


def on_stop():
    if M:
        M.shutdown()


def _conn_view(c):
    if not c:
        return None
    return {k: c.get(k) for k in ("name", "description", "ssid", "bssid", "signal", "rssi", "channel", "band", "radio", "gen", "rx", "tx", "security")}


@kit.get("/api/status")
def status(_q):
    with M.lock:
        ssids = {n["ssid"] for n in M.networks if n["ssid"]}
        return {"version": VERSION, "state": M.state, "message": M.message, "detail": M.detail, "last_scan": M.last_scan or None, "scanning": M.scanning,
                "settings": dict(SETTINGS.data), "aps": len(M.networks), "ssids": len(ssids), "hidden": sum(1 for n in M.networks if n["hidden"]),
                "open": sum(1 for n in M.networks if n["open"]), "connected": _conn_view(M.connected), "adapters": [a["name"] for a in M.adapters], "scans": M.scans}


@kit.get("/api/networks")
def networks(_q):
    with M.lock:
        return {"state": M.state, "last_scan": M.last_scan or None, "networks": list(M.networks), "connected_bssid": (M.connected or {}).get("bssid", "")}


@kit.get("/api/channels")
def channels(_q):
    with M.lock:
        return {"state": M.state, "bands": M.analysis, "connected": _conn_view(M.connected)}


@kit.get("/api/signal")
def signal(q):
    try:
        minutes = int(q.get("minutes", "5"))
    except ValueError:
        raise BadRequest("minutes must be a number") from None
    if minutes not in (1, 5, 15, 60):
        raise BadRequest("minutes must be 1, 5, 15 or 60")
    cutoff = M.clock() - minutes * 60
    with M.lock:
        pts = [p for p in M.history if p["t"] >= cutoff]
        return {"minutes": minutes, "points": pts, "connected": _conn_view(M.connected), "state": M.state}


def _cell(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@kit.raw("/api/export.csv")
def export_csv(_q):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["SSID", "BSSID", "Signal %", "Signal dBm (approx)", "Channel", "Band GHz", "Frequency MHz", "Security", "Wi-Fi", "Radio type", "Channel utilization %", "Connected"])
    with M.lock:
        nets = list(M.networks)
        cb = (M.connected or {}).get("bssid", "")
    for n in sorted(nets, key=lambda x: -x["signal"]):
        w.writerow([_cell(n["ssid"] or "(hidden)"), n["bssid"], n["signal"], n["dbm"], n["channel"], n["band"], n["freq"], n["security"], n["gen"], n["radio"], "" if n["util"] is None else n["util"], "yes" if n["bssid"] == cb else ""])
    body = ("\ufeff" + buf.getvalue()).encode("utf-8")
    return 200, body, "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="wifi-networks.csv"'}


@kit.post("/api/scan")
def scan(_b):
    started = M.request_scan()
    return {"ok": True, "started": started}


@kit.post("/api/settings")
def settings(body):
    try:
        return {"ok": True, "settings": SETTINGS.update(body)}
    except ValueError as e:
        raise BadRequest(str(e)) from None


@kit.post("/api/open-location")
def open_location(_b):
    try:
        OPENER(LOCATION_URI)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "Could not open Settings: %s. Open Windows Settings > Privacy & security > Location yourself." % e}


@kit.post("/api/quit")
def quit_app(_b):
    quit_event.set()
    return {"ok": True}
