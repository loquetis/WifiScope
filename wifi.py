"""Wi-Fi scanning and analysis for WifiScope: runs `netsh wlan` and parses its text WITHOUT relying on translated words
(structure, order and value shapes are used instead), then scores channel congestion. Nothing here touches the network."""
import ctypes
import os
import re
import subprocess
import threading
import time

MAC = r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}"
SSID_RE = re.compile(r"^\s*SSID\s+(\d+)\s*:\s?(.*)$")
BSSID_RE = re.compile(r"^\s*BSSID\s+(\d+)\s*:\s*(" + MAC + r")\s*$")
IF_SSID_RE = re.compile(r"^\s*SSID\s*:\s?(.*)$")
IF_BSSID_RE = re.compile(r"^\s*BSSID\s*:\s*(" + MAC + r")\s*$")
SIG_RE = re.compile(r"^(\d{1,3})\s*%$")
RADIO_RE = re.compile(r"^802\.11[a-z0-9/]{1,12}$")
BAND_RE = re.compile(r"^(\d(?:[.,]\d)?)\s*GHz$", re.I)
INT_RE = re.compile(r"^\d{1,3}$")
NUM_RE = re.compile(r"^\d{1,5}(?:[.,]\d{1,2})?$")
UTIL_RE = re.compile(r"^\d+\s*\(\s*(\d{1,3})\s*%\s*\)$")
RSSI_RE = re.compile(r"^-\d{2,3}$")
GUID_RE = re.compile(r"^[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
FIVE = set(list(range(36, 65, 4)) + list(range(100, 145, 4)) + list(range(149, 166, 4)))      # usable almost everywhere (169-177 exist only in a few regions)
DFS = set(range(52, 65, 4)) | set(range(100, 145, 4))
PSC = {5, 21, 37, 53, 69, 85, 101, 117, 133, 149, 165, 181, 197, 213, 229}
MAX_NETWORKS = 600


def _lines(text):
    return [l.replace("\u00a0", " ").replace("\u202f", " ").rstrip("\r") for l in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _kv(line):
    if ":" not in line:
        return None
    k, v = line.split(":", 1)
    return k.strip(), v.strip()


def dbm_from_pct(p):
    return int(round(p / 2.0 - 100))


def freq_mhz(band, ch):
    if band == "2.4":
        return 2484 if ch == 14 else 2407 + 5 * ch
    if band == "5":
        return 5000 + 5 * ch
    return 5950 + 5 * ch


def infer_band(ch, radio=""):
    """Only used when netsh prints no 'Band : x GHz' line (older Windows builds)."""
    if ch is None:
        return None
    if ch <= 14:
        return "2.4"
    if ch in FIVE:
        return "5"
    if (radio or "").lower().endswith(("ax", "be")) and (ch - 1) % 4 == 0:
        return "6"
    if 32 <= ch <= 177:
        return "5"
    return "6"


def security_label(auth, enc):
    a, e = (auth or "").lower(), (enc or "").lower()
    ent = bool(re.search(r"enterprise|entreprise|unternehmen|802\.1x", a))
    if re.search(r"wpa3|sae", a):
        return "WPA3-Enterprise" if ent else "WPA3"
    if "wpa2" in a or "rsn" in a:
        return "WPA2-Enterprise" if ent else "WPA2"
    if "wpa" in a:
        return "WPA-Enterprise" if ent else "WPA"
    if "wep" in a or "wep" in e or "shared" in a:
        return "WEP"
    if re.search(r"\bowe\b", a):
        return "Enhanced Open"
    if not a and not e:
        return "Unknown"
    if re.search(r"ccmp|tkip|gcmp", e):
        return "Secured"
    return "Open"


def generation(radio, band):
    r = (radio or "").lower()
    if r.endswith("be"):
        return "Wi-Fi 7"
    if r.endswith("ax"):
        return "Wi-Fi 6E" if band == "6" else "Wi-Fi 6"
    if r.endswith("ac"):
        return "Wi-Fi 5"
    if r.endswith("n"):
        return "Wi-Fi 4"
    return radio or ""


def parse_networks(text):
    """`netsh wlan show networks mode=bssid` -> list of access points (one per BSSID)."""
    ssids, cur, bs, mode = [], None, None, None
    for line in _lines(text):
        m = SSID_RE.match(line)
        if m and (cur is None and int(m.group(1)) >= 1 or cur is not None and int(m.group(1)) == len(ssids) + 1):
            cur = {"name": m.group(2).strip(), "kv": [], "bssids": []}
            ssids.append(cur)
            mode, bs = "ssid", None
            continue
        m = BSSID_RE.match(line)
        if m and cur is not None and int(m.group(1)) == len(cur["bssids"]) + 1:
            bs = {"mac": m.group(2).lower(), "kv": []}
            cur["bssids"].append(bs)
            mode = "bssid"
            continue
        kv = _kv(line)
        if kv is None or mode is None:
            continue
        (cur["kv"] if mode == "ssid" else bs["kv"]).append(kv)
    out = []
    for s in ssids:
        vals = [v for _k, v in s["kv"]]
        net_type = vals[0] if len(vals) > 0 else ""
        auth = vals[1] if len(vals) > 1 else ""
        enc = vals[2] if len(vals) > 2 else ""
        sec = security_label(auth, enc)
        for b in s["bssids"]:
            sig = radio = band_txt = ch = util = None
            for _k, v in b["kv"]:
                if sig is None and SIG_RE.match(v):
                    sig = min(100, int(SIG_RE.match(v).group(1)))
                elif radio is None and RADIO_RE.match(v):
                    radio = v.lower()
                elif band_txt is None and BAND_RE.match(v):
                    band_txt = BAND_RE.match(v).group(1).replace(",", ".")
                elif ch is None and INT_RE.match(v) and sig is not None:
                    ch = int(v)
                elif util is None and UTIL_RE.match(v):
                    util = min(100, int(UTIL_RE.match(v).group(1)))
            if sig is None or ch is None or ch < 1 or ch > 233:
                continue
            band = {"2.4": "2.4", "5": "5", "6": "6"}.get(band_txt) or infer_band(ch, radio or "")
            out.append({"ssid": s["name"], "hidden": s["name"] == "", "bssid": b["mac"], "signal": sig, "dbm": dbm_from_pct(sig), "channel": ch, "band": band,
                        "freq": freq_mhz(band, ch), "radio": radio or "", "gen": generation(radio, band), "security": sec, "open": sec == "Open",
                        "net_type": net_type, "util": util})
            if len(out) >= MAX_NETWORKS:
                return out
    return out


def parse_interfaces(text):
    """`netsh wlan show interfaces` -> list of adapters; each has connected (bool) and the live link details."""
    kvs = []
    for line in _lines(text):
        kv = _kv(line)
        if kv:
            kvs.append((line, kv))
    starts = [i - 2 for i, (_l, (_k, v)) in enumerate(kvs) if GUID_RE.match(v) and i >= 2]
    out = []
    for n, st in enumerate(starts):
        block = kvs[st:(starts[n + 1] if n + 1 < len(starts) else len(kvs))]
        d = {"name": block[0][1][1], "description": block[1][1][1], "guid": block[2][1][1], "mac": "", "connected": False, "ssid": "", "bssid": "", "signal": None, "rssi": None,
             "channel": None, "band": None, "radio": "", "rx": None, "tx": None, "security": ""}
        auth = enc = ""
        nums = []
        seen_sig = False
        for line, (k, v) in block[3:]:
            m = IF_BSSID_RE.match(line)
            if m:
                d["bssid"] = m.group(1).lower(); d["connected"] = True; continue
            m = IF_SSID_RE.match(line)
            if m:
                d["ssid"] = m.group(1).strip(); continue
            if re.match("^" + MAC + "$", v):
                # first MAC in the block is the adapter's own address; a second one is the access point (Windows 11 labels it
                # "AP BSSID", older builds "BSSID", other languages translate it) - so go by position, not by label
                if not d["mac"]:
                    d["mac"] = v.lower()
                elif not d["bssid"]:
                    d["bssid"] = v.lower(); d["connected"] = True
            elif SIG_RE.match(v) and not seen_sig:
                d["signal"] = min(100, int(SIG_RE.match(v).group(1))); seen_sig = True
            elif RSSI_RE.match(v) and d["rssi"] is None:
                d["rssi"] = int(v)
            elif RADIO_RE.match(v) and not d["radio"]:
                d["radio"] = v.lower()
            elif BAND_RE.match(v) and d["band"] is None:
                d["band"] = BAND_RE.match(v).group(1).replace(",", ".")
            elif d["connected"] and NUM_RE.match(v):
                nums.append(float(v.replace(",", ".")))
            elif re.match(r"^(WPA|WEP|Open|RSN)", v, re.I) and not auth:
                auth = v
            elif re.match(r"^(CCMP|TKIP|GCMP|WEP|None)", v, re.I) and not enc:
                enc = v
        # numeric values after BSSID/radio/band, in netsh order: channel, receive rate, transmit rate
        if d["connected"]:
            if nums:
                if nums[0] == int(nums[0]) and 1 <= nums[0] <= 233:
                    d["channel"] = int(nums.pop(0))
                if nums:
                    d["rx"] = nums[0]
                if len(nums) > 1:
                    d["tx"] = nums[1]
            if d["band"] not in ("2.4", "5", "6"):
                d["band"] = infer_band(d["channel"], d["radio"])
            d["security"] = security_label(auth, enc) if (auth or enc) else ""
            if d["signal"] is not None and d["rssi"] is None:
                d["rssi"] = dbm_from_pct(d["signal"])
            d["gen"] = generation(d["radio"], d["band"])
        out.append(d)
    return out


def diagnose(nets_text, if_text, nets):
    """-> (state, message). state: ok | location | no_adapter | service | empty | error"""
    low = (nets_text or "").lower() + "\n" + (if_text or "").lower()
    if nets:
        return "ok", ""
    if "ms-settings:privacy-location" in low or re.search(r"\blocation\b", low):
        return "location", "Windows needs location access turned on before apps can see nearby Wi-Fi networks."
    if "wlansvc" in low or "wlan autoconfig" in low or "wireless autoconfig" in low:
        return "service", "The Windows WLAN AutoConfig service is not running."
    ifaces = parse_interfaces(if_text)
    if not ifaces:
        return "no_adapter", "No Wi-Fi adapter was found, or Wi-Fi is turned off."
    return "empty", "The Wi-Fi adapter did not report any networks. It may still be scanning; try Scan now."


def first_message(*texts):
    for t in texts:
        for l in _lines(t):
            if l.strip():
                return l.strip()[:300]
    return ""


# ------------------------------------------------------------------ analysis
def overlap(band, d):
    d = abs(d)
    if band == "2.4":
        return max(0.0, 1 - d / 5.0)
    step = d / 4.0
    if band == "5":
        return 1.0 if step == 0 else 0.25 if step == 1 else 0.08 if step == 2 else 0.0
    return 1.0 if step == 0 else 0.15 if step == 1 else 0.0


def band_channels(band, seen):
    if band == "2.4":
        base = list(range(1, 14))
    elif band == "5":
        base = sorted(FIVE)
    else:
        base = list(range(1, 234, 4))
    return sorted(set(base) | set(seen))


def analyze(nets, connected=None):
    """Per band: channel table with AP counts and a congestion score, and a recommended channel.
    The connected network's own access points are left out when judging whether to move (they move with you)."""
    own_ssid = connected["ssid"] if connected and connected.get("connected") and connected.get("ssid") else None
    own_band = (connected or {}).get("band")
    result = []
    for band, label in (("2.4", "2.4 GHz"), ("5", "5 GHz"), ("6", "6 GHz")):
        aps = [n for n in nets if n["band"] == band]
        if not aps and not (own_band == band):
            result.append({"band": band, "label": label, "seen": False, "ap_count": 0, "channels": [], "recommended": None, "current": None, "aps": []})
            continue
        chans = band_channels(band, [a["channel"] for a in aps])

        def score(ch, exclude_own):
            s = 0.0
            for a in aps:
                if exclude_own and own_ssid is not None and a["ssid"] == own_ssid and band == own_band:
                    continue
                s += overlap(band, a["channel"] - ch) * max(a["signal"] / 100.0, 0.1)
            return s
        rows = []
        for ch in chans:
            rows.append({"ch": ch, "aps": sum(1 for a in aps if a["channel"] == ch), "score": round(score(ch, False), 2), "dfs": band == "5" and ch in DFS, "psc": band == "6" and ch in PSC})
        cands = [1, 6, 11] if band == "2.4" else [c for c in chans if (band == "6" or c in FIVE)]
        def bias(c):
            return 0.05 if band == "5" and c in DFS else (-0.02 if band == "6" and c in PSC else 0.0)   # tie-breakers only, never shown
        scored = sorted((score(c, True), c) for c in cands)
        scored.sort(key=lambda t: (t[0] + bias(t[1]), t[1]))
        cur = None
        if connected and connected.get("connected") and own_band == band and connected.get("channel"):
            cc = connected["channel"]
            cur = {"ch": cc, "score": round(score(cc, True), 2)}
        rec = None
        if scored:
            best_sc, best = scored[0]
            cur_raw = score(cur["ch"], True) if cur else None
            if cur and cur_raw - best_sc < 0.15 or cur and cur_raw <= best_sc * 1.2:
                best, best_sc = cur["ch"], cur_raw
                reason = "Your network is already on one of the least crowded channels."
            elif cur:
                reason = "Channel %d has less nearby traffic than your channel %d (%.1f vs %.1f)." % (best, cur["ch"], best_sc, cur["score"])
            else:
                reason = "Channel %d has the least nearby traffic on this band." % best
            if band == "5" and best in DFS:
                reason += " It is a DFS channel: some routers pause briefly if radar is detected."
            rec = {"ch": best, "score": round(best_sc, 2), "reason": reason, "alternatives": [{"ch": c, "score": round(s_, 2)} for s_, c in scored[:4] if c != best][:2]}
        result.append({"band": band, "label": label, "seen": True, "ap_count": len(aps), "channels": rows, "recommended": rec, "current": cur,
                       "aps": [{"ssid": a["ssid"], "bssid": a["bssid"], "channel": a["channel"], "signal": a["signal"]} for a in aps]})
    return result


# ------------------------------------------------------------------ running netsh / triggering a scan
BELOW_NORMAL, NO_WINDOW = 0x00004000, 0x08000000


def decode(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        import locale
        return b.decode(locale.getpreferredencoding(False), "replace")
    except Exception:  # noqa: BLE001
        return b.decode("latin-1", "replace")


class Netsh:
    """Runs netsh hidden, at low priority, with UTF-8 console output (so SSIDs with accents/CJK survive)."""
    def __init__(self):
        self._last_trigger = 0.0

    def run(self, what, timeout=25):
        if os.name != "nt":
            return 1, "netsh is only available on Windows"
        cmd = {"networks": "netsh wlan show networks mode=bssid", "interfaces": "netsh wlan show interfaces"}[what]
        try:
            p = subprocess.run(["cmd.exe", "/d", "/c", "chcp 65001>nul&" + cmd], capture_output=True, timeout=timeout, creationflags=NO_WINDOW | BELOW_NORMAL)
            return p.returncode, decode(p.stdout + p.stderr)
        except subprocess.TimeoutExpired:
            return 1, "netsh did not answer in time"
        except OSError as e:
            return 1, "could not run netsh: %s" % e

    def trigger_scan(self, min_gap=10.0):
        """Ask the Wi-Fi driver for a fresh scan (Windows otherwise serves a list that can be a minute old). Best effort."""
        if os.name != "nt" or time.time() - self._last_trigger < min_gap:
            return False
        self._last_trigger = time.time()
        try:
            api = ctypes.WinDLL("wlanapi")
            handle = ctypes.c_void_p()
            ver = ctypes.c_uint32()
            api.WlanOpenHandle.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p)]
            if api.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(handle)) != 0:
                return False
            try:
                lst = ctypes.c_void_p()
                api.WlanEnumInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
                if api.WlanEnumInterfaces(handle, None, ctypes.byref(lst)) != 0 or not lst.value:
                    return False
                try:
                    n = ctypes.c_uint32.from_address(lst.value).value
                    api.WlanScan.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
                    done = 0
                    for i in range(min(n, 8)):
                        guid_addr = lst.value + 8 + i * 532          # WLAN_INTERFACE_INFO is 532 bytes: GUID(16) + WCHAR[256] + state
                        if api.WlanScan(handle, ctypes.c_void_p(guid_addr), None, None, None) == 0:
                            done += 1
                    return done > 0
                finally:
                    api.WlanFreeMemory.argtypes = [ctypes.c_void_p]
                    api.WlanFreeMemory(lst)
            finally:
                api.WlanCloseHandle.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                api.WlanCloseHandle(handle, None)
        except Exception:  # noqa: BLE001
            return False
