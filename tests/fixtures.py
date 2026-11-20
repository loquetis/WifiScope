"""Realistic `netsh wlan` output in several languages, plus a fake runner."""
import os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOC = {
    "en": dict(iface="Interface name", count="There are {n} networks currently visible.", nettype="Network type", infra="Infrastructure", auth="Authentication", enc="Encryption", sig="Signal", radio="Radio type", band="Band", ch="Channel", basic="Basic rates (Mbps)", other="Other rates (Mbps)", sep=" : "),
    "de": dict(iface="Schnittstellenname", count="Es sind {n} Netzwerke sichtbar.", nettype="Netzwerktyp", infra="Infrastruktur", auth="Authentifizierung", enc="Verschlüsselung", sig="Signal", radio="Funktyp", band="Band", ch="Kanal", basic="Basisraten (MBit/s)", other="Andere Raten (MBit/s)", sep=" : "),
    "fr": dict(iface="Nom de l’interface", count="{n} réseaux sont actuellement visibles.", nettype="Type de réseau", infra="Infrastructure", auth="Authentification", enc="Chiffrement", sig="Signal", radio="Type de radio", band="Bande", ch="Canal", basic="Taux de base (Mbits/s)", other="Autres taux (Mbits/s)", sep="\u00a0: "),
    "ja": dict(iface="インターフェイス名", count="現在表示できるネットワークは {n} 件です。", nettype="ネットワークの種類", infra="インフラストラクチャ", auth="認証", enc="暗号", sig="シグナル", radio="無線の種類", band="帯域", ch="チャネル", basic="基本レート (Mbps)", other="その他のレート (Mbps)", sep=" : "),
    "ru": dict(iface="Имя интерфейса", count="Видимых сетей: {n}.", nettype="Тип сети", infra="Инфраструктура", auth="Проверка подлинности", enc="Шифрование", sig="Сигнал", radio="Тип радио", band="Диапазон", ch="Канал", basic="Основные скорости (Мбит/с)", other="Другие скорости (Мбит/с)", sep=" : "),
}

def nets_text(networks, lang="en", with_band=True, with_load=False, crlf=False, ifname="Wi-Fi"):
    """networks: list of dicts(ssid, auth, enc, aps=[dict(mac, sig, radio, band, ch, util)])"""
    L = LOC[lang]; sp = L["sep"]; out = ["", "%s%s%s " % (L["iface"], sp, ifname), L["count"].format(n=len(networks)), ""]
    for i, n in enumerate(networks, 1):
        out.append("SSID %d%s%s" % (i, sp, n["ssid"]))
        out.append("    %-24s%s%s" % (L["nettype"], sp, L["infra"]))
        out.append("    %-24s%s%s" % (L["auth"], sp, n["auth"]))
        out.append("    %-24s%s%s" % (L["enc"], sp, n["enc"]))
        for j, a in enumerate(n["aps"], 1):
            out.append("    %-24s%s%s" % ("BSSID %d" % j, sp, a["mac"]))
            out.append("         %-20s%s%d%%" % (L["sig"], sp, a["sig"]))
            out.append("         %-20s%s%s" % (L["radio"], sp, a["radio"]))
            if with_band and a.get("band"): out.append("         %-20s%s%s GHz" % (L["band"], sp, a["band"]))
            out.append("         %-20s%s%d" % (L["ch"], sp, a["ch"]))
            if with_load and a.get("util") is not None:
                out.append("         BSS Load:"); out.append("             Connected Stations:  3"); out.append("             Channel Utilization: %d (%d %%)" % (a["util"] * 255 // 100, a["util"])); out.append("             Medium Time Available: 12000")
            out.append("         %-20s%s6 12 24" % (L["basic"], sp)); out.append("         %-20s%s9 18 36 48 54" % (L["other"], sp))
        out.append("")
    t = "\n".join(out) + "\n"
    return t.replace("\n", "\r\n") if crlf else t

def if_text(lang="en", connected=True, ssid="HomeNet", bssid="aa:bb:cc:dd:ee:01", sig=88, ch=36, band="5", radio="802.11ax", rx="866.7", tx="1201", extra_iface=False, auth="WPA2-Personal", enc="CCMP", bssid_label="BSSID", win11=False):
    L = LOC[lang]; sp = L["sep"]
    def block(name, conn):
        r = ["", "    %-24s%s%s" % ("Name" if lang == "en" else L["iface"], sp, name), "    %-24s%s%s" % ("Description", sp, "Intel(R) Wi-Fi 6E AX211 160MHz"), "    %-24s%s%s" % ("GUID", sp, "6d2f3a5e-1b7c-4d1a-9f7e-%012x" % (hash(name) & 0xFFFFFFFFFFFF)),
             "    %-24s%s%s" % ("Physical address", sp, "11:22:33:44:55:66"), "    %-24s%s%s" % ("Interface type", sp, "Primary"), "    %-24s%s%s" % ("State", sp, "connected" if conn else "disconnected")]
        if conn:
            r += ["    %-24s%s%s" % ("SSID", sp, ssid), "    %-24s%s%s" % (bssid_label, sp, bssid), "    %-24s%s%s" % (L["nettype"], sp, L["infra"]), "    %-24s%s%s" % (L["radio"], sp, radio),
                  "    %-24s%s%s" % (L["auth"], sp, auth), "    %-24s%s%s" % ("Cipher", sp, enc), "    %-24s%s%s" % ("Connection mode", sp, "Auto Connect"), "    %-24s%s%s GHz" % (L["band"], sp, band),
                  "    %-24s%s%d" % (L["ch"], sp, ch), "    %-24s%s%s" % ("Receive rate (Mbps)", sp, rx), "    %-24s%s%s" % ("Transmit rate (Mbps)", sp, tx), "    %-24s%s%d%%" % (L["sig"], sp, sig), "    %-24s%s%s" % ("Profile", sp, ssid)]
        if conn and win11:
            r += ["    %-24s%s%s" % ("Connected Akm-cipher", sp, "[ akm = 00-0f-ac:02, cipher =  00-0f-ac:04 ]"), "    %-24s%s%d" % ("Rssi", sp, sig // 2 - 100),
                  "    %-28s%s%s" % ("QoS MSCS Configured", sp, "0"), "    %-28s%s%s" % ("QoS Map Configured", sp, "0"), "    %-28s%s%s" % ("QoS Map Allowed by Policy", sp, "0")]
        if not win11: r += ["    %-24s%s%s" % ("Hosted network status", sp, "Not available")]
        r += [""]
        return r
    out = ["", "There is 1 interface on the system:" if not extra_iface else "There are 2 interfaces on the system:", ""] + block("Wi-Fi", connected)
    if extra_iface: out += block("Wi-Fi 2", False)
    return "\n".join(out) + "\n"

APS = [
    dict(ssid="HomeNet", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="aa:bb:cc:dd:ee:01", sig=88, radio="802.11ax", band="5", ch=36), dict(mac="aa:bb:cc:dd:ee:02", sig=94, radio="802.11n", band="2.4", ch=6)]),
    dict(ssid="Neighbor-5G", auth="WPA3-Personal", enc="CCMP", aps=[dict(mac="10:20:30:40:50:60", sig=70, radio="802.11ac", band="5", ch=44)]),
    dict(ssid="CoffeeShop", auth="Open", enc="None", aps=[dict(mac="de:ad:be:ef:00:01", sig=40, radio="802.11n", band="2.4", ch=6)]),
    dict(ssid="", auth="WPA2-Personal", enc="CCMP", aps=[dict(mac="de:ad:be:ef:00:02", sig=33, radio="802.11n", band="2.4", ch=1)]),
    dict(ssid="Corp-WiFi", auth="WPA2-Enterprise", enc="CCMP", aps=[dict(mac="00:11:22:33:44:55", sig=61, radio="802.11ac", band="5", ch=149), dict(mac="00:11:22:33:44:56", sig=58, radio="802.11n", band="2.4", ch=11)]),
    dict(ssid="Wi-Fi 6E Lab", auth="WPA3-Personal", enc="CCMP", aps=[dict(mac="66:77:88:99:aa:01", sig=75, radio="802.11ax", band="6", ch=37)]),
    dict(ssid="Old-WEP", auth="Open", enc="WEP", aps=[dict(mac="ca:fe:00:00:00:09", sig=20, radio="802.11g", band="2.4", ch=3)]),
]

class FakeNetsh:
    def __init__(self, networks=None, iface=None, lang="en", delay=0):
        self.networks_text = nets_text(networks if networks is not None else APS, lang); self.iface_text = iface if iface is not None else if_text(lang)
        self.calls = []; self.triggers = 0; self.delay = delay; self.rc = 0; self.fail = False
    def run(self, what, timeout=25):
        self.calls.append(what)
        if self.delay: import time; time.sleep(self.delay)
        if self.fail: return 1, "netsh did not answer in time"
        return (self.rc, self.networks_text if what == "networks" else self.iface_text)
    def trigger_scan(self, min_gap=10.0):
        self.triggers += 1; return True

LOCATION_TEXT = "Network shell commands need location permission to access WLAN information.\nTurn on Location services on the Location page in Privacy & security settings:\nms-settings:privacy-location\n"
NO_ADAPTER_TEXT = "There is no wireless interface on the system.\n"
SERVICE_TEXT = "The Wireless AutoConfig Service (wlansvc) is not running.\n"
