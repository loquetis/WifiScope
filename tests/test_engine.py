"""Parser + analysis tests (any OS)."""
import os, random, sys, tempfile, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from fixtures import *
import wifi, storage
R = Results(); ok = R.ok

# ---- parsing in several languages / line endings / with and without Band lines
total_aps = sum(len(n["aps"]) for n in APS)
base = None
for lang in LOC:
    for crlf in (False, True):
        for with_band in (True, False):
            for load in (False, True):
                t = nets_text(APS, lang, with_band, load, crlf)
                nets = wifi.parse_networks(t)
                key = [(n["ssid"], n["bssid"], n["signal"], n["channel"]) for n in nets]
                if base is None: base = key
                if len(nets) != total_aps or key != base: ok("parse %s crlf=%s band=%s load=%s" % (lang, crlf, with_band, load), False, (len(nets), key[:2])); break
ok("every language (en/de/fr/ja/ru), CRLF/LF, with/without Band line, with/without BSS Load: same %d access points" % total_aps, base is not None)
nets = wifi.parse_networks(nets_text(APS, "en", True, True))
by = {n["bssid"]: n for n in nets}
a = by["aa:bb:cc:dd:ee:01"]
ok("fields: ssid, signal, dbm, channel, band, freq, radio, generation, security", (a["ssid"], a["signal"], a["dbm"], a["channel"], a["band"], a["freq"], a["radio"], a["gen"], a["security"]) == ("HomeNet", 88, -56, 36, "5", 5180, "802.11ax", "Wi-Fi 6", "WPA2"), a)
ok("2.4 GHz: channel 6 -> 2437 MHz, Wi-Fi 4; ch 14 would be 2484", by["aa:bb:cc:dd:ee:02"]["freq"] == 2437 and by["aa:bb:cc:dd:ee:02"]["gen"] == "Wi-Fi 4" and wifi.freq_mhz("2.4", 14) == 2484)
ok("6 GHz band recognised, Wi-Fi 6E, channel 37 -> 6135 MHz", by["66:77:88:99:aa:01"]["band"] == "6" and by["66:77:88:99:aa:01"]["gen"] == "Wi-Fi 6E" and by["66:77:88:99:aa:01"]["freq"] == 6135)
ok("hidden network (empty SSID) is flagged", by["de:ad:be:ef:00:02"]["hidden"] is True and by["de:ad:be:ef:00:02"]["ssid"] == "")
ok("security labels: WPA3, WPA2-Enterprise, Open, WEP, WPA2", by["10:20:30:40:50:60"]["security"] == "WPA3" and by["00:11:22:33:44:55"]["security"] == "WPA2-Enterprise" and by["de:ad:be:ef:00:01"]["security"] == "Open" and by["de:ad:be:ef:00:01"]["open"] and by["ca:fe:00:00:00:09"]["security"] == "WEP" and not by["ca:fe:00:00:00:09"]["open"])
ok("BSS load / channel utilisation parsed when present", by["aa:bb:cc:dd:ee:01"]["util"] is None)   # fixture only adds load when util given
t = nets_text([dict(ssid="Busy", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="aa:aa:aa:aa:aa:aa", sig=50, radio="802.11ax", band="5", ch=100, util=37)])], "en", True, True)
ok("channel utilisation %", wifi.parse_networks(t)[0]["util"] == 37 and wifi.parse_networks(t)[0]["channel"] == 100)
nb = wifi.parse_networks(nets_text(APS, "en", False))
ok("without a Band line the band is inferred from the channel", {n["bssid"]: n["band"] for n in nb}["aa:bb:cc:dd:ee:02"] == "2.4" and {n["bssid"]: n["band"] for n in nb}["aa:bb:cc:dd:ee:01"] == "5" and {n["bssid"]: n["band"] for n in nb}["66:77:88:99:aa:01"] == "6")
ok("band inference: 1-14 -> 2.4, 36..165 -> 5, 233 -> 6", wifi.infer_band(6) == "2.4" and wifi.infer_band(100) == "5" and wifi.infer_band(165) == "5" and wifi.infer_band(233) == "6" and wifi.infer_band(None) is None)
# hostile / odd SSIDs
odd = [dict(ssid="<img src=x onerror=alert(1)>", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="01:00:00:00:00:01", sig=50, radio="802.11n", band="2.4", ch=1)]),
       dict(ssid="a : b : c", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="01:00:00:00:00:02", sig=51, radio="802.11n", band="2.4", ch=6)]),
       dict(ssid="日本語のネットワーク 😀", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="01:00:00:00:00:03", sig=52, radio="802.11n", band="2.4", ch=11)]),
       dict(ssid="  spaces  ", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="01:00:00:00:00:04", sig=53, radio="802.11n", band="2.4", ch=11)]),
       dict(ssid="X" * 32, auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="01:00:00:00:00:05", sig=54, radio="802.11n", band="2.4", ch=11)]),
       dict(ssid="Signal : 99%", auth="Open", enc="None", aps=[dict(mac="01:00:00:00:00:06", sig=55, radio="802.11n", band="2.4", ch=11)])]
no = wifi.parse_networks(nets_text(odd, "en")); names = [n["ssid"] for n in no]
ok("odd SSIDs (HTML, colons, CJK/emoji, spaces, 32 chars, 'Signal : 99%') parsed as plain text", len(no) == 6 and names[0].startswith("<img") and names[1] == "a : b : c" and names[2].startswith("日本語") and names[3] == "spaces" and names[4] == "X" * 32 and names[5] == "Signal : 99%" and no[5]["signal"] == 55, names)
inj = nets_text(APS[:1], "en").replace("SSID 1 : HomeNet", "SSID 1 : Evil\n    BSSID 1 : 66:66:66:66:66:66\n         Signal : 99%\n         Channel : 1\nSSID 5 : Fake")
ij = wifi.parse_networks(inj); ok("a SSID that contains fake 'SSID 5' / out-of-order lines does not create extra networks (sequence check)", all(n["ssid"] != "Fake" for n in ij))
ok("empty / garbage / location text give no networks, never raise", all(wifi.parse_networks(x) == [] for x in ["", "   ", "\x00\x01", "SSID", "SSID 1 :", LOCATION_TEXT, NO_ADAPTER_TEXT, "BSSID 1 : aa:bb:cc:dd:ee:ff", None]))
bad = 0
for i in range(300):
    t = list(nets_text(APS, random.choice(list(LOC)), True, True)); 
    for _ in range(random.randrange(0, 40)): t[random.randrange(len(t))] = random.choice("\n:%\x00 9ZX")
    t = "".join(t)[:random.randrange(1, len(t) + 1)]
    try: wifi.parse_networks(t); wifi.parse_interfaces(t)
    except Exception: bad += 1
ok("fuzz: 300 corrupted outputs never raise", bad == 0, bad)
many = nets_text([dict(ssid="N%d" % i, auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="02:00:00:00:%02x:%02x" % (i // 256, i % 256), sig=50, radio="802.11n", band="2.4", ch=1 + i % 11)]) for i in range(900)])
ok("result list is capped (600)", len(wifi.parse_networks(many)) == 600)
# signal range
s = nets_text([dict(ssid="Z", auth="Open", enc="None", aps=[dict(mac="03:00:00:00:00:01", sig=100, radio="802.11n", band="2.4", ch=1), dict(mac="03:00:00:00:00:02", sig=0, radio="802.11n", band="2.4", ch=1)])])
sn = wifi.parse_networks(s); ok("signal 100% / 0%, dBm mapping (pct/2 - 100)", [n["signal"] for n in sn] == [100, 0] and [n["dbm"] for n in sn] == [-50, -100] and wifi.dbm_from_pct(50) == -75)

# ---- interfaces
for lang in LOC:
    ifs = wifi.parse_interfaces(if_text(lang))
    i = ifs[0] if ifs else {}
    if not (len(ifs) == 1 and i["connected"] and i["ssid"] == "HomeNet" and i["bssid"] == "aa:bb:cc:dd:ee:01" and i["signal"] == 88 and i["channel"] == 36 and i["band"] == "5" and i["radio"] == "802.11ax" and i["rx"] == 866.7 and i["tx"] == 1201.0): ok("interface parse %s" % lang, False, i); break
ok("connected interface: ssid, bssid, signal, channel, band, radio, rx/tx rates (5 languages)", True)
i = wifi.parse_interfaces(if_text("en"))[0]; ok("derived: rssi from signal, generation, security", i["rssi"] == -56 and i["gen"] == "Wi-Fi 6" and i["security"] == "WPA2" and i["name"] == "Wi-Fi" and i["mac"] == "11:22:33:44:55:66", i)
w = wifi.parse_interfaces(if_text("en", bssid_label="AP BSSID", win11=True, ch=36, sig=86, rx="865", tx="865"))[0]
ok("Windows 11 24H2 layout ('AP BSSID', Akm-cipher, QoS lines): connected, bssid, channel, rates, signal", w["connected"] and w["bssid"] == "aa:bb:cc:dd:ee:01" and w["ssid"] == "HomeNet" and w["channel"] == 36 and w["rx"] == 865.0 and w["tx"] == 865.0 and w["signal"] == 86 and w["rssi"] == -57 and w["band"] == "5" and w["security"] == "WPA2", w)
for lab in ("AP-BSSID", "BSSID du point d\u2019acc\u00e8s", "AP \u7121\u7dda BSSID"):
    ok("connected detected by position when BSSID label is %r" % lab, wifi.parse_interfaces(if_text("en", bssid_label=lab, win11=True))[0]["bssid"] == "aa:bb:cc:dd:ee:01")
h = wifi.parse_interfaces(if_text("en", ssid="aa:bb:cc:dd:ee:ff", bssid_label="AP BSSID"))[0]; ok("SSID that looks like a MAC address does not become the BSSID", h["ssid"] == "aa:bb:cc:dd:ee:ff" and h["bssid"] == "aa:bb:cc:dd:ee:01")
d = wifi.parse_interfaces(if_text("en", connected=False)); ok("disconnected adapter: not connected, no signal", len(d) == 1 and d[0]["connected"] is False and d[0]["signal"] is None and d[0]["ssid"] == "")
m = wifi.parse_interfaces(if_text("en", extra_iface=True)); ok("two adapters are both listed", len(m) == 2 and m[0]["connected"] and not m[1]["connected"])
ok("rate with comma decimal and 2.4 GHz connection", wifi.parse_interfaces(if_text("en", ch=11, band="2.4", radio="802.11n", rx="72,2", tx="72,2", sig=45))[0]["rx"] == 72.2 and wifi.parse_interfaces(if_text("en", ch=11, band="2.4", radio="802.11n", sig=45))[0]["band"] == "2.4")
ok("interfaces: empty/garbage/no-adapter give []", all(wifi.parse_interfaces(x) == [] for x in ["", NO_ADAPTER_TEXT, SERVICE_TEXT, LOCATION_TEXT, "junk : value"]))

# ---- diagnose
ok("diagnose: networks present -> ok", wifi.diagnose(nets_text(APS), if_text(), nets) [0] == "ok")
ok("diagnose: location permission text -> location", wifi.diagnose(LOCATION_TEXT, "", [])[0] == "location" and wifi.diagnose("", LOCATION_TEXT, [])[0] == "location")
ok("diagnose: no adapter", wifi.diagnose(NO_ADAPTER_TEXT, NO_ADAPTER_TEXT, [])[0] == "no_adapter")
ok("diagnose: wlansvc not running", wifi.diagnose(SERVICE_TEXT, SERVICE_TEXT, [])[0] == "service")
ok("diagnose: adapter present but nothing visible -> empty", wifi.diagnose(nets_text([]), if_text(connected=False), [])[0] == "empty")
ok("first_message gives the first non-empty line, capped", wifi.first_message("", "\n  \nHello there\nmore") == "Hello there" and len(wifi.first_message("x" * 1000)) == 300)

# ---- analysis
conn = wifi.parse_interfaces(if_text("en"))[0]            # HomeNet on 5 GHz channel 36
an = {b["band"]: b for b in wifi.analyze(nets, conn)}
ok("analysis has a block per band; unseen band is marked", all(b in an for b in ("2.4", "5", "6")) and an["2.4"]["seen"] and an["5"]["seen"] and an["6"]["seen"])
only24 = {b["band"]: b for b in wifi.analyze([n for n in nets if n["band"] == "2.4"], None)}
ok("band with no networks: seen=False, no recommendation", only24["5"]["seen"] is False and only24["5"]["recommended"] is None and only24["6"]["channels"] == [])
c24 = {r["ch"]: r for r in an["2.4"]["channels"]}
ok("2.4 GHz table covers channels 1-13; AP counts per channel", sorted(c24)[:13] == list(range(1, 14)) and c24[6]["aps"] == 2 and c24[1]["aps"] == 1 and c24[11]["aps"] == 1 and c24[3]["aps"] == 1)
ok("overlap model: ch 6 neighbours score higher than far channels", c24[6]["score"] > c24[8]["score"] > c24[10]["score"] and wifi.overlap("2.4", 0) == 1 and wifi.overlap("2.4", 5) == 0 and wifi.overlap("2.4", -2) == 0.6)
rec24 = an["2.4"]["recommended"]; ok("2.4 GHz recommendation is one of 1/6/11 with the lowest score", rec24["ch"] in (1, 6, 11) and rec24["score"] <= min(c24[1]["score"], c24[6]["score"], c24[11]["score"]) + 1e-9, rec24)
heavy = [dict(ssid="A%d" % i, hidden=False, bssid="0a:00:00:00:00:%02x" % i, signal=80, dbm=-60, channel=ch, band="2.4", freq=0, radio="", gen="", security="WPA2", open=False, net_type="", util=None) for i, ch in enumerate([1, 1, 1, 6, 6, 6, 6, 11])]
r = [b for b in wifi.analyze(heavy, None) if b["band"] == "2.4"][0]; ok("busiest case: picks the quietest of 1/6/11 (11 has one AP)", r["recommended"]["ch"] == 11 and "11" in r["recommended"]["reason"], r["recommended"])
quiet = [dict(heavy[0], channel=6, ssid="Mine", bssid="0b:00:00:00:00:01")]
cq = dict(conn, band="2.4", channel=6, ssid="Mine", bssid="0b:00:00:00:00:01", connected=True)
r = [b for b in wifi.analyze(quiet, cq) if b["band"] == "2.4"][0]; ok("your own AP is not counted against its own channel: alone on ch 6 -> stay", r["current"]["ch"] == 6 and r["current"]["score"] == 0 and r["recommended"]["ch"] == 6 and "already" in r["recommended"]["reason"], r["recommended"])
cc = dict(cq, channel=1); r = [b for b in wifi.analyze(heavy + [dict(heavy[0], ssid="Mine", channel=1, bssid="0b:00:00:00:00:01")], cc) if b["band"] == "2.4"][0]
ok("current channel crowded -> says move, names both scores", r["recommended"]["ch"] == 11 and "than your channel 1" in r["recommended"]["reason"], r["recommended"])
c5 = {r["ch"]: r for r in an["5"]["channels"]}; ok("5 GHz: standard channel list (36-165), DFS flagged, same-channel scoring", 36 in c5 and 165 in c5 and 169 not in c5 and c5[52]["dfs"] and not c5[36]["dfs"] and c5[44]["aps"] == 1 and c5[149]["aps"] == 1 and c5[40]["score"] > 0 and c5[40]["aps"] == 0)
rec5 = an["5"]["recommended"]; ok("5 GHz recommendation exists, is a usual channel; barely-different scores say stay", rec5 and rec5["ch"] in wifi.FIVE and an["5"]["current"]["ch"] == 36 and rec5["ch"] == 36, rec5)
ok("5 GHz: with 1/2 steps neighbours the busy channels score higher than empty distant ones", c5[40]["score"] > c5[165]["score"])
ok("6 GHz: channels 1,5,...,233; PSC flagged; recommendation prefers a quiet channel", [r["ch"] for r in an["6"]["channels"]][:3] == [1, 5, 9] and an["6"]["channels"][-1]["ch"] == 233 and any(r["psc"] for r in an["6"]["channels"]) and an["6"]["recommended"]["ch"] != 37)
ok("scores are never negative (tie-break bias is hidden)", all(r["score"] >= 0 for b in an.values() for r in b["channels"]) and all(b["recommended"] is None or b["recommended"]["score"] >= 0 for b in an.values()))
ok("analysis works with zero networks", all(not b["seen"] for b in wifi.analyze([], None)))
# ---- settings
d = tempfile.mkdtemp(prefix="ws-"); p = os.path.join(d, "settings.json"); s = storage.Settings(p)
ok("settings defaults", s.data == {"interval": 15, "units": "percent"})
ok("settings validated and saved", s.update({"interval": 30, "units": "dbm"}) == {"interval": 30, "units": "dbm"} and storage.Settings(p).data == {"interval": 30, "units": "dbm"})
for bad in [{"interval": 7}, {"interval": True}, {"interval": "15"}, {"units": "mph"}, {"nope": 1}]:
    try: s.update(bad); r = False
    except ValueError: r = True
    if not r: ok("settings reject %r" % (bad,), False)
ok("settings validation", True); open(p, "w").write('{"interval": 99, "units": 3}'); ok("corrupt settings fall back to defaults", storage.Settings(p).data == storage.DEFAULTS)
ok("netsh runner on a non-Windows box says so instead of crashing", wifi.Netsh().run("networks")[0] != 0 or os.name == "nt")
ok("trigger_scan is a no-op off Windows", wifi.Netsh().trigger_scan() is False or os.name == "nt")
R.done()
