"""CityMind entry point."""
import os
import sys

# Allow `from core...` style imports when run from this folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _ensure_qt_font_dir():
    """Qt 6 emits 'Cannot find font directory' and falls back to a broken
    bitmap font if its internal fonts dir does not exist.  We silence
    that and guarantee real glyphs by creating the directory (empty is
    fine — Qt still falls through to system fonts) and by making sure
    Windows has a sane font substitution family.
    """
    try:
        import PyQt6
        pkg_root = os.path.dirname(PyQt6.__file__)
        fonts_dir = os.path.join(pkg_root, "Qt6", "lib", "fonts")
        if not os.path.isdir(fonts_dir):
            os.makedirs(fonts_dir, exist_ok=True)
    except Exception:
        pass


_ensure_qt_font_dir()

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontDatabase
from ui.display import CityMindApp


# Candidate Windows system TTFs in order of preference.
_WINDOWS_FONT_FILES = [
    ("segoeui.ttf",    "Segoe UI"),
    ("segoeuib.ttf",   "Segoe UI"),   # bold — same family
    ("tahoma.ttf",     "Tahoma"),
    ("tahomabd.ttf",   "Tahoma"),
    ("arial.ttf",      "Arial"),
    ("arialbd.ttf",    "Arial"),
    ("verdana.ttf",    "Verdana"),
    ("consola.ttf",    "Consolas"),
]


def _install_windows_fonts():
    """Explicitly load Windows TTFs into Qt's font DB.

    On some PyQt6 installs Qt cannot enumerate the installed system fonts
    (its own fonts dir is missing), so `QFontDatabase.families()` returns
    only a couple of generic names and every widget falls back to a
    broken bitmap glyph set.  Registering the TTFs directly guarantees
    real Segoe UI / Tahoma / Arial rendering.

    Returns the first family that was successfully registered.
    """
    win_fonts_dir = os.environ.get("WINDIR", r"C:\Windows")
    win_fonts_dir = os.path.join(win_fonts_dir, "Fonts")
    loaded_family = None
    for fname, family in _WINDOWS_FONT_FILES:
        path = os.path.join(win_fonts_dir, fname)
        if not os.path.isfile(path):
            continue
        fid = QFontDatabase.addApplicationFont(path)
        if fid >= 0 and loaded_family is None:
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                loaded_family = fams[0]
    return loaded_family


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CityMind")
    app.setStyle("Fusion")

    # 1. Register real Windows fonts so Qt stops using its broken fallback.
    primary = _install_windows_fonts() or "Sans Serif"

    # 2. Apply as application-wide default.
    f = QFont(primary, 10)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(f)

    # 3. Redirect every common generic name to the real font we just loaded
    #    so stylesheet strings like "Segoe UI, Tahoma, Arial, sans-serif"
    #    always resolve to a proper family.
    for alias in ("MS Shell Dlg 2", "Sans Serif", "sans-serif",
                  "Segoe UI", "Tahoma", "Arial", "Verdana"):
        QFont.insertSubstitution(alias, primary)

    print(f"[UI] Using font family: {primary}")
    win = CityMindApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
