"""1.0.2 regression test: a minimized window (heartbeats throttled to ~1/min or stopped) must not quit."""
import ast, pathlib
src = pathlib.Path(__file__).resolve().parents[1].joinpath("launcher.py").read_text(encoding="utf-8")
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "should_exit")
ns = {}; exec(compile(ast.Module([fn], []), "launcher.py", "exec"), ns); should_exit = ns["should_exit"]
cases = [
    ((True, False, 60), False, "own window open, 1-min throttled heartbeat gap"),
    ((True, False, 6 * 60), False, "own window minimized 6 min, heartbeats stopped"),
    ((True, False, 29 * 60), False, "own window open, 29 min without heartbeat"),
    ((True, False, 1801), True, "safety net for a hung window"),
    ((True, True, 5), False, "window just closed, page may still ping"),
    ((True, True, 11), True, "window closed -> exit"),
    ((False, False, 120), False, "default-browser fallback, 2 min gap"),
    ((False, False, 181), True, "default-browser fallback, tab gone"),
]
bad = 0
for args, want, what in cases:
    got = should_exit(*args); bad += got != want
    print(("PASS " if got == want else "FAIL ") + what, args, got)
# old 1.0.1 rule for contrast: it would quit in the minimized case
old = lambda has, gone, idle: (gone and idle > 10) or idle > 45
print("1.0.1 rule would exit on a 6-min minimized gap:", old(True, False, 360))
print(f"{len(cases) - bad}/{len(cases)} passed"); raise SystemExit(1 if bad else 0)
