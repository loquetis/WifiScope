import os, sys, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class Results:
    def __init__(self): self.r = {}; self.fail = 0
    def ok(self, name, cond, detail=""):
        self.r[name] = bool(cond); self.fail += (not cond)
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(detail)), flush=True)
    def done(self):
        print(f"{len(self.r) - self.fail}/{len(self.r)} passed"); raise SystemExit(1 if self.fail else 0)

def tmpstore():
    import storage
    d = tempfile.mkdtemp(prefix="ss-")
    return storage.Store(d), d
