"""Windows-only checks with the real netsh and wlanapi. Read-only: it never connects, disconnects or changes a setting.
Works with or without a Wi-Fi adapter (a desktop PC just takes the 'no adapter' path). Run: python tests\\test_windows.py"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import *
if os.name != "nt": print("SKIP: Windows only"); raise SystemExit(0)
import wifi
R = Results(); ok = R.ok
n = wifi.Netsh()
t0 = time.time(); rc, nt = n.run("networks"); dt = time.time() - t0
ok("netsh networks answers (rc=%s, %.1fs)" % (rc, dt), isinstance(nt, str) and len(nt) > 0 and dt < 20, nt[:200])
rc2, it = n.run("interfaces"); ok("netsh interfaces answers", isinstance(it, str) and len(it) > 0, it[:200])
nets = wifi.parse_networks(nt); ifs = wifi.parse_interfaces(it)
state, msg = wifi.diagnose(nt, it, nets)
print("INFO state=%s aps=%d adapters=%d msg=%s" % (state, len(nets), len(ifs), msg))
ok("diagnose gives a known state", state in ("ok", "location", "no_adapter", "service", "empty"))
if state == "ok":
    ok("every parsed AP has a valid BSSID, signal 0-100, channel and band", all(len(a["bssid"]) == 17 and 0 <= a["signal"] <= 100 and a["channel"] > 0 and a["band"] in ("2.4", "5", "6") for a in nets), nets[:2])
    print("INFO real data shape: " + ", ".join("%s GHz ch%s sig%s%% %s" % (a["band"], a["channel"], a["signal"], a["security"]) for a in nets[:6]))
    ok("analysis runs on the real list", len(wifi.analyze(nets, next((a for a in ifs if a["connected"]), None))) == 3)
else:
    ok("non-ok state yields no networks and a readable message", not nets and len(msg) > 10)
    ok("non-ok output still parses interfaces without crashing", isinstance(ifs, list))
t0 = time.time(); r = n.trigger_scan(); ok("wlanapi scan trigger returns quickly and doesn't crash (returned %s)" % r, time.time() - t0 < 5 and r in (True, False))
ok("trigger is rate limited", n.trigger_scan(min_gap=60) is False)
if ifs and any(a["connected"] for a in ifs):
    c = next(a for a in ifs if a["connected"]); ok("connected adapter parsed: ssid, bssid, channel", c["ssid"] and len(c["bssid"]) == 17 and c["channel"] > 0)
else: print("INFO: not connected to Wi-Fi on this PC; connected-adapter parsing exercised by fake-output tests only")
R.done()
