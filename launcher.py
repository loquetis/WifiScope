"""WifiScope desktop entry point (packaged as WifiScope.exe with PyInstaller --noconsole).

Same reviewed pattern as QuickFind / PulseScope 1.0.2: private Edge app-mode profile (no
extensions, sync or sign-in), already running (port probe + named mutex) = open its window, stays up while its own window is open
(minimized pages have throttled timers) and exits shortly after the window closes. Written by hand.
"""
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

APP = "WifiScope"
PORT_ENV = "WIFISCOPE_PORT"
WINDOW_SIZE = "1320,860"


def _arg_port(argv):
    if "--port" in argv:
        i = argv.index("--port")
        try:
            p = int(argv[i + 1])
            if 1024 <= p <= 65535:
                return p
        except (IndexError, ValueError):
            pass
        raise SystemExit("--port needs a number between 1024 and 65535")
    return None


ARGV = sys.argv[1:]
_port = _arg_port(ARGV)
if _port:
    os.environ[PORT_ENV] = str(_port)            # must happen before importing server
if sys.stdout is None:                            # --noconsole build: give print() somewhere to go
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import storage  # noqa: E402

os.makedirs(storage.DATA_DIR, exist_ok=True)
logging.basicConfig(filename=os.path.join(storage.DATA_DIR, APP.lower() + ".log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(APP.lower())


def find_edge():
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            c = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.isfile(c):
                return c
    return shutil.which("msedge")


def open_window(url):
    edge = find_edge() if os.name == "nt" else None
    if edge:
        profile = os.path.join(storage.DATA_DIR, "window-profile")
        try:
            return subprocess.Popen([edge, "--app=" + url, "--user-data-dir=" + profile, "--no-first-run",
                                     "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                                     "--disable-features=msImplicitSignin,msEdgeSyncConsent,msShowWelcomePage",
                                     "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                                     "--disable-backgrounding-occluded-windows",
                                     "--window-size=" + WINDOW_SIZE])
        except OSError:
            log.exception("could not start Edge; falling back to the default browser")
    webbrowser.open(url)
    return None


def should_exit(has_window, window_gone, idle):
    """Decide whether the launcher should quit, given seconds since the page's last request.

    A minimized Edge page has its timers throttled to about once a minute after 5 minutes, so
    heartbeats can stop arriving while the window is still open. With our own Edge window we
    therefore stay up while it is open and quit soon after it closes. 30 minutes is only a safety
    net for a hung window. Without a window object (default browser fallback) the heartbeat is
    all we have, so the limit is generous.
    """
    if has_window:
        return (window_gone and idle > 10) or idle > 1800
    return idle > 180


_mutex = None


def already_running(port):
    """Windows lets two processes listen on the same port (SO_REUSEADDR), so a failed bind cannot be relied on to detect a
    running copy. Ask the port instead, and also hold a named mutex so two copies starting at the same moment cannot both win."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        pass
    global _mutex
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateMutexW.restype = ctypes.c_void_p
            k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
            _mutex = k.CreateMutexW(None, False, "Local\\%s-single-instance-%d" % (APP, port))
            if ctypes.get_last_error() == 183:           # ERROR_ALREADY_EXISTS
                return True
        except Exception:  # noqa: BLE001
            log.exception("could not create the single-instance mutex")
    return False


def main():
    import server  # imported late so the port env var and logging are already set up
    url = f"http://{server.HOST}:{server.PORT}/"
    no_window = "--no-window" in ARGV
    try:
        if already_running(server.PORT):
            raise OSError("already running")
        httpd = server.build_server()
    except OSError:
        log.info("port %s busy: assuming %s is already running, opening its window", server.PORT, APP)
        if not no_window:
            open_window(url)
        return 0
    server.on_start()
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    log.info("serving %s (pid %s)", url, os.getpid())
    window = None if no_window else open_window(url)
    started = time.time()
    try:
        while not server.quit_event.is_set():
            time.sleep(2)
            if no_window:
                continue
            idle = time.time() - max(server.last_seen(), started)
            window_gone = window is not None and window.poll() is not None
            if should_exit(window is not None, window_gone, idle):
                log.info("window closed / idle for %.0fs: exiting", idle)
                break
    except KeyboardInterrupt:
        pass
    finally:
        if window is not None and window.poll() is None:
            window.terminate()   # only our own private-profile Edge process
        server.on_stop()
        httpd.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        log.error("fatal error\n%s", traceback.format_exc())
        sys.exit(1)
