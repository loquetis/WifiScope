"""Server tests (box): API, monitor behaviour with a fake netsh, security rules, launcher smoke test."""
import json, os, re, subprocess, sys, tempfile, threading, time, urllib.request, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from fixtures import *
R = Results(); ok = R.ok
PORT = 18821; os.environ["WIFISCOPE_PORT"] = str(PORT)
tmp = tempfile.mkdtemp(prefix="wss-"); os.environ["WIFISCOPE_DATA"] = tmp
import server, wifi
fake = FakeNetsh(); opened = []
server.init(netsh=fake, opener=opened.append, settle=0, settings_path=os.path.join(tmp, "settings.json"))
httpd = server.build_server(PORT); threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d" % PORT
def req(path, method="GET", body=None, headers=None):
    r = urllib.request.Request(URL + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp: return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e: return e.code, e.read(), dict(e.headers)
s, page, hdr = req("/"); token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
J = {"Content-Type": "application/json", "X-App-Token": token}
def get(path): s, b, h = req(path); return s, json.loads(b)
def post(path, obj, headers=None): s, b, h = req(path, "POST", json.dumps(obj).encode(), headers or J); return s, json.loads(b)
ok("index: token, strict CSP, no inline code", s == 200 and "unsafe-inline" not in hdr["Content-Security-Policy"] and not re.search(rb"<script(?![^>]*src=)[^>]*>|style=|onclick=|onerror=|javascript:", page))
_js = re.sub(r"/\*.*?\*/", "", open(os.path.join(ROOT, "web", "app.js")).read() + open(os.path.join(ROOT, "web", "core.js")).read(), flags=re.S)
ok("no innerHTML/eval/document.write in JS", not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function", _js))
for f in ("app.js", "core.js", "styles.css", "app.css", "favicon.svg"): ok("static " + f, req("/" + f)[0] == 200)
ok("path traversal / bad Host blocked", req("/..%2f..%2fwifi.py")[0] == 404 and req("/api/status", headers={"Host": "evil.example"})[0] == 403)
ok("POST without token -> 403, wrong type -> 415, bad JSON -> 400", req("/api/scan", "POST", b"{}", {"Content-Type": "application/json"})[0] == 403 and req("/api/scan", "POST", b"{}", {"Content-Type": "text/plain", "X-App-Token": token})[0] == 415 and req("/api/scan", "POST", b"[1]", J)[0] == 400)
# monitor is idle until the page has been used; start it
server.on_start(); time.sleep(1.5)
s, st = get("/api/status")
ok("first scan runs by itself once the page is active; trigger_scan was asked", st["state"] == "ok" and st["aps"] == 9 and st["scans"] >= 1 and fake.triggers >= 1, st)
ok("status: ssid/hidden/open counts, connected adapter, version", st["ssids"] == 6 and st["hidden"] == 1 and st["open"] == 1 and st["connected"]["ssid"] == "HomeNet" and st["connected"]["channel"] == 36 and st["version"] == "1.0.0" and st["adapters"] == ["Wi-Fi"], st)
s, r = get("/api/networks"); ok("networks list with connected bssid", s == 200 and len(r["networks"]) == 9 and r["connected_bssid"] == "aa:bb:cc:dd:ee:01" and r["networks"][0]["ssid"] in ("HomeNet", "Neighbor-5G", "CoffeeShop", "") )
s, r = get("/api/channels"); b = {x["band"]: x for x in r["bands"]}; ok("channels analysis served for 3 bands with recommendations", s == 200 and b["2.4"]["recommended"] and b["5"]["seen"] and b["6"]["seen"] and r["connected"]["band"] == "5")
# history grows (interface polling every ~2 s)
time.sleep(5.5); s, r = get("/api/signal?minutes=1")
ok("signal history: samples taken while active, connected network listed", len(r["points"]) >= 2 and r["points"][-1]["signal"] == 88 and r["points"][-1]["bssid"] == "aa:bb:cc:dd:ee:01" and r["connected"]["ssid"] == "HomeNet", len(r["points"]))
ok("signal validation", get("/api/signal?minutes=7")[0] == 400 and get("/api/signal?minutes=x")[0] == 400 and get("/api/signal?minutes=60")[0] == 200)
# manual scan, rate limit
n0 = fake.calls.count("networks"); r1 = post("/api/scan", {})[1]; time.sleep(1.5); r2 = post("/api/scan", {})[1]
ok("manual scan runs now; a second press within 3 s is ignored politely", r1["started"] is True and fake.calls.count("networks") == n0 + 1 and r2["started"] is False)
# state transitions
fake.networks_text = LOCATION_TEXT; fake.iface_text = LOCATION_TEXT; time.sleep(3.2); post("/api/scan", {}); time.sleep(1.5)
s, st = get("/api/status"); ok("location permission blocked -> state 'location', clear message, no stale list", st["state"] == "location" and "location" in st["message"].lower() and st["aps"] == 0 and st["detail"].startswith("Network shell commands"), st["state"])
ok("open-location button opens only the fixed Settings URI", post("/api/open-location", {})[1]["ok"] and opened == ["ms-settings:privacy-location"])
fake.networks_text = fake.iface_text = NO_ADAPTER_TEXT; time.sleep(3.2); post("/api/scan", {}); time.sleep(1.5); ok("no adapter", get("/api/status")[1]["state"] == "no_adapter" and get("/api/status")[1]["connected"] is None)
fake.networks_text = fake.iface_text = SERVICE_TEXT; time.sleep(3.2); post("/api/scan", {}); time.sleep(1.5); ok("wlansvc not running", get("/api/status")[1]["state"] == "service")
fake.networks_text = nets_text([]); fake.iface_text = if_text(connected=False); time.sleep(3.2); post("/api/scan", {}); time.sleep(1.5); st = get("/api/status")[1]; ok("adapter present, nothing visible -> 'empty', not connected", st["state"] == "empty" and st["connected"] is None)
fake.networks_text = nets_text(APS, "de"); fake.iface_text = if_text("de"); time.sleep(3.2); post("/api/scan", {}); time.sleep(1.5); st = get("/api/status")[1]; ok("recovers when permission is granted / adapter back (German output)", st["state"] == "ok" and st["aps"] == 9 and st["connected"]["ssid"] == "HomeNet")
fake.fail = True; time.sleep(3.2); post("/api/scan", {}); time.sleep(1.5); st = get("/api/status")[1]; ok("netsh timing out is reported, not a crash", st["state"] in ("no_adapter", "error", "empty") and st["detail"].startswith("netsh did not answer"), st)
fake.fail = False
# settings
ok("settings validated and persisted", post("/api/settings", {"interval": 30, "units": "dbm"})[1]["settings"] == {"interval": 30, "units": "dbm"} and post("/api/settings", {"interval": 5})[0] == 400 and post("/api/settings", {"units": "x"})[0] == 400 and post("/api/settings", {"zzz": 1})[0] == 400 and json.load(open(os.path.join(tmp, "settings.json"))) == {"interval": 30, "units": "dbm"})
post("/api/settings", {"interval": 10, "units": "percent"})
# CSV export
fake.networks_text = nets_text([dict(ssid="=HYPERLINK(\"http://evil\")", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="aa:00:00:00:00:01", sig=70, radio="802.11n", band="2.4", ch=6)]), dict(ssid='Quote"d, name', auth="Open", enc="None", aps=[dict(mac="aa:00:00:00:00:02", sig=60, radio="802.11n", band="2.4", ch=1)])]); time.sleep(3.2); post("/api/scan", {}); time.sleep(1.5)
s, body, h = req("/api/export.csv"); txt = body.decode("utf-8-sig")
ok("CSV export: attachment, header row, formula-looking names neutralised, quotes escaped", s == 200 and h["Content-Type"].startswith("text/csv") and "attachment" in h["Content-Disposition"] and txt.startswith("SSID,BSSID") and "'=HYPERLINK" in txt and '"Quote""d, name"' in txt, txt[:200])
# monitor stops when nobody looks
n1 = len(fake.calls); server.kit._last_seen = time.time() - 120; time.sleep(4.5); n2 = len(fake.calls)
ok("no scanning while the page is closed (idle > 45 s)", n2 == n1, (n1, n2))
get("/api/status"); time.sleep(3); ok("resumes when the page is used again", len(fake.calls) > n2)
ok("quit sets the event", post("/api/quit", {})[1]["ok"] and server.quit_event.is_set())
server.on_stop()
# ---- launcher smoke
env = dict(os.environ, WIFISCOPE_DATA=tempfile.mkdtemp(prefix="wsl-"), WIFISCOPE_PORT="18822")
p = subprocess.Popen([sys.executable, os.path.join(ROOT, "launcher.py"), "--no-window", "--port", "18822"], env=env, cwd=ROOT)
try:
    for _ in range(60):
        try: urllib.request.urlopen("http://127.0.0.1:18822/", timeout=2); break
        except Exception: time.sleep(0.25)
    pg = urllib.request.urlopen("http://127.0.0.1:18822/", timeout=5).read(); tk = re.search(rb'name="app-token" content="([^"]+)"', pg).group(1).decode()
    st2 = json.loads(urllib.request.urlopen("http://127.0.0.1:18822/api/status", timeout=5).read())
    ok("launcher serves; non-Windows says no adapter instead of crashing", st2["version"] == "1.0.0" and st2["state"] in ("no_adapter", "starting", "empty", "error"), st2)
    p2 = subprocess.run([sys.executable, os.path.join(ROOT, "launcher.py"), "--no-window", "--port", "18822"], env=env, cwd=ROOT, timeout=20)
    ok("second instance exits 0, first keeps running", p2.returncode == 0 and p.poll() is None)
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18822/api/quit", data=b"{}", method="POST", headers={"Content-Type": "application/json", "X-App-Token": tk}), timeout=5)
    try: p.wait(15)
    except subprocess.TimeoutExpired: pass
finally:
    if p.poll() is None: p.terminate(); p.wait(10)
ok("launcher exits after /api/quit", p.returncode == 0, p.returncode)
shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(env["WIFISCOPE_DATA"], ignore_errors=True)
R.done()
