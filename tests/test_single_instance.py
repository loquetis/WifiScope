"""already_running(): true when something listens on the port, false (and the OS mutex logic harmless) when nothing does."""
import ast, os, pathlib, socket, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import *
R = Results(); ok = R.ok
src = pathlib.Path(__file__).resolve().parents[1].joinpath("launcher.py").read_text(encoding="utf-8")
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "already_running")
import logging
ns = {"os": os, "log": logging.getLogger("t"), "APP": "SingleInstanceTest", "_mutex": None}
exec(compile(ast.Module([fn], []), "launcher.py", "exec"), ns); already_running = ns["already_running"]
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1); port = s.getsockname()[1]
ok("listening port -> already running", already_running(port) is True)
s.close()
ok("free port -> not running (first call; on Windows this takes the mutex)", already_running(port) is False)
if os.name == "nt":
    # a different process must see the mutex held by this one
    import subprocess
    code = ("import ast,sys,logging,os\nsrc=open(sys.argv[1],encoding='utf-8').read()\nfn=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name=='already_running')\n"
            "ns={'os':os,'log':logging.getLogger('t'),'APP':'SingleInstanceTest','_mutex':None}\nexec(compile(ast.Module([fn],[]),'l','exec'),ns)\nprint(ns['already_running'](int(sys.argv[2])))")
    out = subprocess.run([sys.executable, "-c", code, str(pathlib.Path(__file__).resolve().parents[1] / "launcher.py"), str(port)], capture_output=True, text=True, timeout=30).stdout.strip()
    ok("Windows: another process sees our mutex -> already running", out == "True", out)
R.done()
