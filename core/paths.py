"""The two roots of the game.

- game root (read-only): shipped data and code assets (league JSONs, template DBs, frontend/dist).
  In dev it is the VERSION2.0 folder; in a PyInstaller build it is the bundle folder (sys._MEIPASS).
- user root (writable): saves, the active DB, built leagues, mods, logs, history files.
  HARDWOOD_USER_DIR overrides it (tests, smoke runs); in a frozen build it is Documents/Hardwood;
  in dev it is the VERSION2.0 folder, so dev behaviour and the owner's saves stay where they are.

Roots are computed on every call, never cached.
"""
import os
import sys

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USER_SUBDIRS = ("saves", os.path.join("data", "leagues"), "mods", "scratch", "logs")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def game_root() -> str:
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return _PROJECT_DIR


def _known_documents_folder() -> str:
    """Windows FOLDERID_Documents via SHGetKnownFolderPath (follows OneDrive redirection)."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

    # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
    folder_id = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                     (wintypes.BYTE * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
    out = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    result = shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out))
    if result != 0 or not out.value:
        raise OSError(f"SHGetKnownFolderPath failed ({result})")
    path = out.value
    ctypes.windll.ole32.CoTaskMemFree(out)
    return path


def documents_dir() -> str:
    try:
        return _known_documents_folder()
    except Exception:
        home = os.path.expanduser("~")
        docs = os.path.join(home, "Documents")
        return docs if os.path.isdir(docs) else home


def user_root() -> str:
    override = os.environ.get("HARDWOOD_USER_DIR")
    if override:
        return override
    if is_frozen():
        return _frozen_user_root(documents_dir())
    return game_root()


USER_FOLDER = "Hardwood"
LEGACY_USER_FOLDER = "NBASIM"  # the folder name before the game was named (builds up to 2026-11-16)


def _frozen_user_root(documents: str) -> str:
    """Documents/Hardwood. The first run after the rename moves an existing Documents/NBASIM there, so the
    player's saves come along; if the move fails (folder in use) the old folder keeps being used."""
    root = os.path.join(documents, USER_FOLDER)
    legacy = os.path.join(documents, LEGACY_USER_FOLDER)
    if not os.path.exists(root) and os.path.isdir(legacy):
        try:
            os.rename(legacy, root)
        except OSError:
            return legacy
    return root


def game_path(*parts: str) -> str:
    return os.path.join(game_root(), *parts)


def user_path(*parts: str) -> str:
    return os.path.join(user_root(), *parts)


def ensure_user_dirs() -> str:
    root = user_root()
    for sub in USER_SUBDIRS:
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    return root
