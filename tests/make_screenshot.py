"""Make screenshot.png (+ -channels / -signal) with made-up demo networks, headless Chrome 1280x820."""
import math, os, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from fixtures import *
from playwright.sync_api import sync_playwright
PORT = 18824; os.environ["WIFISCOPE_PORT"] = str(PORT)
tmp = tempfile.mkdtemp(prefix="wsshot-"); os.environ["WIFISCOPE_DATA"] = tmp
import server
extra = [
 dict(ssid="Pixel_8812", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="3c:5a:b4:00:12:01", sig=48, radio="802.11n", band="2.4", ch=1)]),
 dict(ssid="Studio-Mesh", auth="WPA3-Personal", enc="CCMP", aps=[dict(mac="f0:9f:c2:10:00:01", sig=62, radio="802.11ax", band="5", ch=44), dict(mac="f0:9f:c2:10:00:02", sig=35, radio="802.11n", band="2.4", ch=11)]),
]
fake = FakeNetsh(APS + extra); server.init(netsh=fake, opener=lambda u: None, settle=0, settings_path=os.path.join(tmp, "settings.json"))
now = time.time(); N = 150
for i in range(N):
    t = now - (N - i) * 2.0; sig = int(86 + 5 * math.sin(i / 7.0) + 2 * math.sin(i / 2.3))
    if 70 < i < 80: sig = 60 - (i - 70)
    if i >= 80 and i < 95: sig = 70 + (i - 80)
    roam = i >= 80
    server.M.history.append({"t": t, "signal": sig, "rssi": sig // 2 - 100, "bssid": "aa:bb:cc:dd:ee:02" if roam and i < 120 else "aa:bb:cc:dd:ee:01", "channel": 6 if roam and i < 120 else 36, "ssid": "HomeNet"})
server.on_start(); httpd = server.build_server(PORT); threading.Thread(target=httpd.serve_forever, daemon=True).start()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_context(viewport={"width": 1280, "height": 820}).new_page()
    pg.goto("http://127.0.0.1:%d/" % PORT); pg.wait_for_selector("#rows tr"); pg.wait_for_timeout(2500)
    pg.click("[data-view='channels']"); pg.wait_for_selector("#bands canvas"); pg.wait_for_timeout(500); pg.screenshot(path="screenshot-channels.png")
    pg.click("[data-view='signal']"); pg.wait_for_timeout(2500); pg.click("[data-min='5']"); pg.wait_for_timeout(1200); pg.screenshot(path="screenshot-signal.png")
    pg.click("[data-view='networks']"); pg.wait_for_timeout(500); pg.screenshot(path="screenshot.png")
    b.close()
print("ok")
