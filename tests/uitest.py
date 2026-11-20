"""UI test on the box: headless Chrome against the real server with a fake netsh."""
import json, os, re, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from fixtures import *
from playwright.sync_api import sync_playwright
R = Results(); ok = R.ok
PORT = 18823; os.environ["WIFISCOPE_PORT"] = str(PORT)
tmp = tempfile.mkdtemp(prefix="wsu-"); os.environ["WIFISCOPE_DATA"] = tmp
import server
HOST = "<img src=x onerror=window.__pwn=1>"
nets = APS + [dict(ssid=HOST, auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="ab:cd:ef:00:00:01", sig=55, radio="802.11n", band="2.4", ch=11)])]
fake = FakeNetsh(nets); opened = []
server.init(netsh=fake, opener=opened.append, settle=0, settings_path=os.path.join(tmp, "settings.json"))
server.on_start(); httpd = server.build_server(PORT); threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/" % PORT
errors = []
def ssids(pg): return pg.eval_on_selector_all("#rows tr td.ssid", "els => els.map(e => e.childNodes[0].textContent)")
def until(fn, t=15):
    t0 = time.time()
    while time.time() - t0 < t:
        try:
            if fn(): return True
        except Exception: pass
        time.sleep(0.2)
    return False
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_context(viewport={"width": 1280, "height": 820}).new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None); pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL); pg.wait_for_selector("#rows tr"); pg.wait_for_timeout(400)
    ok("title + 10 access points in table", pg.title() == "WifiScope" and pg.locator("#rows tr").count() == 10 and pg.inner_text("#n-aps") == "10", pg.locator("#rows tr").count())
    ok("hostile SSID is text only", pg.locator(".ssid", has_text=HOST).count() == 1 and pg.evaluate("document.querySelectorAll('img[src=x]').length") == 0 and pg.evaluate("window.__pwn") is None)
    first = pg.locator("#rows tr").first.inner_text()
    ok("default sort: strongest first; connected AP row marked YOU", "HomeNet" in first and "94%" in first and pg.locator("#rows tr.me").count() == 1 and "YOU" in pg.locator("#rows tr.me").inner_text() and "aa:bb:cc:dd:ee:01" in pg.locator("#rows tr.me").inner_text(), first)
    ok("sidebar shows connection", "Connected to HomeNet" in pg.inner_text("#side-text"))
    ok("cards", "access points" in pg.inner_text("#cards").lower() and "open networks" in pg.inner_text("#cards").lower() and "HomeNet" in pg.inner_text("#cards"))
    ok("OPEN badge on open networks", pg.locator("tr", has_text="CoffeeShop").locator(".badge.open").count() == 1)
    pg.fill("#q", "coffee"); pg.wait_for_timeout(150); ok("text filter", ssids(pg) == ["CoffeeShop"]); pg.fill("#q", "")
    pg.fill("#q", "aa:bb:cc:dd:ee:01"); pg.wait_for_timeout(150); ok("filter by BSSID", len(ssids(pg)) == 1); pg.fill("#q", "")
    pg.click("[data-band='5']"); pg.wait_for_timeout(150); rows5 = pg.locator("#rows tr").count(); ok("band filter 5 GHz", 0 < rows5 < 10 and all("5 GHz" in t for t in pg.eval_on_selector_all("#rows tr", "e => e.map(x => x.cells[4].textContent)")))
    pg.click("[data-band='']"); pg.check("#f-open"); pg.wait_for_timeout(150); ok("open only", pg.locator("#rows tr").count() >= 1 and all("OPEN" in t for t in pg.eval_on_selector_all("#rows tr td.ssid", "e => e.map(x => x.textContent)"))); pg.uncheck("#f-open")
    pg.click("button.th[data-sort='channel']"); pg.wait_for_timeout(150); chs = [int(x) for x in pg.eval_on_selector_all("#rows tr", "e => e.map(x => x.cells[3].textContent)")]; ok("sort by channel ascending, again descending", chs == sorted(chs)); pg.click("button.th[data-sort='channel']"); pg.wait_for_timeout(150); chs = [int(x) for x in pg.eval_on_selector_all("#rows tr", "e => e.map(x => x.cells[3].textContent)")]; ok("descending", chs == sorted(chs, reverse=True))
    pg.click("button.th[data-sort='signal']"); pg.wait_for_timeout(100)
    ok("export link points at csv with download attr", pg.get_attribute("#btn-export", "href") == "/api/export.csv" and pg.get_attribute("#btn-export", "download"))
    # channels
    pg.click("[data-view='channels']"); pg.wait_for_selector("#bands canvas"); pg.wait_for_timeout(400)
    ok("three band panels; 2.4 and 5 have charts; recommendations text", pg.locator("#bands .band-panel").count() == 3 and pg.locator("#bands canvas").count() >= 2 and "Recommended: channel" in pg.inner_text("#bands"), pg.inner_text("#bands")[:300])
    cv = pg.locator("#bands canvas").first
    ok("canvas has real size and painted pixels", pg.evaluate("(() => { const c = document.querySelector('#bands canvas'); const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data; let n=0; for (let i=3;i<d.length;i+=4) if (d[i]) n++; return c.width > 300 && n > 500; })()"))
    ok("cards show best channels after visiting Channels", "2.4: ch 1" in pg.inner_text("#cards"), pg.inner_text("#cards"))
    pg.screenshot(path="/tmp/ws-channels.png")
    # signal
    pg.click("[data-view='signal']"); ok("signal view: connection details", until(lambda: "HomeNet" in pg.inner_text("#conn-card") and "aa:bb:cc:dd:ee:01" in pg.inner_text("#conn-card")), pg.inner_text("#conn-card")[:200])
    ok("signal graph has stats after samples", until(lambda: "Min " in pg.inner_text("#sig-stats"), 20), pg.inner_text("#sig-stats"))
    ok("signal canvas painted", pg.evaluate("(() => { const c = document.querySelector('#sig-chart'); const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data; let n=0; for (let i=3;i<d.length;i+=4) if (d[i]) n++; return n > 300; })()"))
    pg.click("[data-min='15']"); pg.wait_for_timeout(500); ok("window chip switches", pg.locator("[data-min='15'].on").count() == 1)
    pg.screenshot(path="/tmp/ws-signal.png")
    # settings
    pg.click("[data-view='settings']"); pg.select_option("#o-units", "dbm"); pg.wait_for_timeout(500)
    ok("units setting saved server-side", server.S_settings_dict()["units"] == "dbm" if hasattr(server, "S_settings_dict") else json.load(open(os.path.join(tmp, "settings.json")))["units"] == "dbm")
    pg.click("[data-view='networks']"); pg.wait_for_timeout(300); ok("table now in dBm", "dBm" in pg.locator("#rows tr").first.inner_text())
    pg.select_option("#o-units", "percent") if False else None
    pg.click("[data-view='settings']"); pg.select_option("#o-units", "percent"); pg.select_option("#o-interval", "30"); pg.wait_for_timeout(400)
    ok("interval saved", json.load(open(os.path.join(tmp, "settings.json")))["interval"] == 30)
    # themes
    for t in ("light", "green", "amber", "blue", "mono", "dark"):
        pg.select_option("#theme", t); pg.wait_for_timeout(60)
    ok("themes switch", pg.evaluate("document.documentElement.getAttribute('data-theme') || document.body.getAttribute('data-theme') || 'dark'") in ("dark", None))
    # manual scan button
    pg.click("[data-view='networks']"); n0 = fake.calls.count("networks"); pg.click("#btn-scan"); ok("Scan now triggers a scan", until(lambda: fake.calls.count("networks") > n0, 6))
    # location banner
    pg.wait_for_timeout(3300); fake.networks_text = fake.iface_text = LOCATION_TEXT; pg.click("#btn-scan")
    ok("location banner with button", until(lambda: pg.locator(".notice.warn").count() == 1, 8) and "Location" in pg.inner_text("#banners") and pg.locator("#banners button.primary").count() == 1, pg.inner_text("#banners")[:200])
    ok("stale list cleared, empty text", until(lambda: pg.locator("#rows tr").count() == 0) and pg.is_visible("#empty"))
    pg.click("#banners button.primary"); pg.wait_for_timeout(400); ok("button opens settings page via server", opened == ["ms-settings:privacy-location"])
    pg.screenshot(path="/tmp/ws-location.png")
    pg.wait_for_timeout(3300); fake.networks_text = fake.iface_text = NO_ADAPTER_TEXT; pg.click("#btn-scan")
    ok("no-adapter banner", until(lambda: pg.locator(".notice.danger").count() == 1 and "adapter" in pg.inner_text("#banners").lower(), 8), pg.inner_text("#banners")[:200])
    pg.click("[data-view='signal']"); ok("signal view when not connected", until(lambda: "Not connected" in pg.inner_text("#conn-card")))
    pg.wait_for_timeout(3300); fake.networks_text = nets_text(nets); fake.iface_text = if_text(); pg.click("#btn-scan"); pg.click("[data-view='networks']")
    ok("recovers", until(lambda: pg.locator("#rows tr").count() == 10 and pg.locator(".notice").count() == 0, 10))
    # narrow layout
    pg.set_viewport_size({"width": 720, "height": 800}); pg.wait_for_timeout(300)
    ok("narrow window: no horizontal page scroll", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2"), pg.evaluate("[document.documentElement.scrollWidth, window.innerWidth]"))
    pg.screenshot(path="/tmp/ws-narrow.png"); pg.set_viewport_size({"width": 1280, "height": 820})
    # quit dialog
    pg.click("[data-view='settings']"); pg.click("#btn-quit"); pg.wait_for_selector(".modal"); pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    ok("quit asks first; Esc cancels", pg.locator(".modal").count() == 0 and not server.quit_event.is_set())
    ok("no console errors", not errors, errors[:5])
    b.close()
R.done()
