"""WifiScope data folder (%APPDATA%\\WifiScope): only settings.json and a log. Scan results are never written to disk."""
import json
import os

APP = "WifiScope"
DATA_DIR = os.environ.get("WIFISCOPE_DATA") or os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.local/share"), APP)
INTERVALS = (0, 10, 15, 30, 60)          # seconds between scans; 0 = only when asked
DEFAULTS = {"interval": 15, "units": "percent"}


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(DATA_DIR, "settings.json")
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        raw = raw if isinstance(raw, dict) else {}
        if raw.get("interval") in INTERVALS and not isinstance(raw.get("interval"), bool):
            self.data["interval"] = raw["interval"]
        if raw.get("units") in ("percent", "dbm"):
            self.data["units"] = raw["units"]

    def update(self, body):
        new = dict(self.data)
        for k, v in body.items():
            if k == "interval":
                if isinstance(v, bool) or v not in INTERVALS:
                    raise ValueError("interval must be one of %s seconds" % ", ".join(map(str, INTERVALS)))
                new[k] = v
            elif k == "units":
                if v not in ("percent", "dbm"):
                    raise ValueError("units must be percent or dbm")
                new[k] = v
            else:
                raise ValueError("unknown setting %s" % k)
        self.data = new
        _atomic_write(self.path, json.dumps(new, indent=1))
        return dict(new)
