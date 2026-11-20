# WifiScope 1.0.0

Wi-Fi analyzer: nearby networks, channel congestion with a recommended channel, and a live signal graph for the connected network. It never connects to or changes anything.

- **How it works:** a Python localhost-only server (127.0.0.1:8775, env `WIFISCOPE_PORT`) plus a web UI in a private Edge app window. A random per-launch token is required on every change request, strict CSP, text-only DOM building (charts on canvas).
- **Data:** `%APPDATA%\WifiScope` (settings.json with the scan interval and units, log). Scan results and the signal history live in memory only. Override with `WIFISCOPE_DATA`.
- **Reading networks:** `netsh wlan show networks mode=bssid` and `netsh wlan show interfaces` (run through `cmd /c chcp 65001` so SSIDs with accents and CJK survive), parsed by line structure and value shape, not by English words (tested with en/de/fr/ja/ru layouts, the Windows 11 "AP BSSID" layout and comma decimals). A fresh scan is requested with `WlanScan` (rate limited). Scanning only runs while the page is open.
- **States:** Windows 11 location permission (clear message + button that opens `ms-settings:privacy-location`), no adapter, WLAN service not running, nothing visible, netsh timeout.
- **Channels:** per band (2.4 / 5 / 6 GHz) congestion from overlap and strength (2.4 GHz overlaps +/-4 channels; 5 GHz adjacent channels count a little; 6 GHz preferred scanning channels), the connected network's own access points excluded when judging a move, recommended channel plus next best, DFS channels noted.
- **Signal graph:** connected network sampled every 2 s, 1/5/15/60 minutes, roaming markers, percent or approximate dBm (percent / 2 - 100).
- **Run:** `WifiScope.exe` (`--no-window`, `--port N`). Build: `build.ps1` (PyInstaller one-file, windowed; edit the venv path at the top).
- **Tests:** `python tests/test_engine.py` (parsers, analysis), `tests/test_server.py`, `tests/uitest.py` (Playwright), `tests/test_should_exit.py`, `tests/test_single_instance.py`; `tests/test_windows.py` reads the real netsh output on Windows (read-only).
- **Not code-signed.** SmartScreen may warn.
