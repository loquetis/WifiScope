# PyInstaller spec: one-file, windowed WifiScope.exe with the web UI bundled.
# Build:  pyinstaller --noconfirm --clean WifiScope.spec
a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    datas=[('web', 'web')],
    hiddenimports=['server', 'wifi', 'storage', 'appserver'],
    excludes=['tkinter', 'unittest', 'pydoc', 'test', 'numpy'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='WifiScope',
    console=False,
    icon='wifiscope.ico',
    upx=False,
    version='version_info.txt',
)
