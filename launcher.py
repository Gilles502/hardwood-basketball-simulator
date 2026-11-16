"""Hardwood Basketball Simulator launcher: the game in its own window (packaged build entry point, also runs from source).

Order matters: the user root is prepared and made the working directory BEFORE `server` (and `main`) are
imported, because some paths are module constants computed at import time (see core/paths.py).

    python launcher.py              # window (needs pywebview)
    python launcher.py --headless   # no window: writes the port to <user>/logs/port.txt (smoke test)
"""
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from typing import IO, Optional

from core import paths, version

WINDOW_TITLE = "Hardwood Basketball Simulator"
WINDOW_SIZE = (1440, 900)
WINDOW_MIN_SIZE = (1024, 700)
READY_TIMEOUT_S = 60.0
ALREADY_RUNNING = "Hardwood Basketball Simulator is already running."
BLOCKED_FILES = (
    "Windows blocked the game files because the zip was downloaded from the internet.\n\n"
    "Fix: delete the game folder, right-click Hardwood-*.zip > Properties > tick 'Unblock' > OK, "
    "then extract the zip again (outside Program Files)."
)


def find_free_port() -> int:
    """A free TCP port on 127.0.0.1 picked by the OS (never assumes 5000, the dev backend)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def acquire_single_instance(lock_path: str) -> Optional[IO]:
    """Locks the first byte of `lock_path`; returns the open handle (keep it open) or None if another
    process (or handle) holds it."""
    import msvcrt
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    fh = open(lock_path, "a+b")
    try:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return None
    return fh


def redirect_std_streams(log_path: str) -> None:
    """A windowed build has no console: sys.stdout/sys.stderr are None and print() would crash."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    stream = open(log_path, "a", encoding="utf-8", buffering=1, errors="replace")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def prepare_environment() -> str:
    """Creates the user folders and makes the user root the working directory. Run before `import server`."""
    root = paths.ensure_user_dirs()
    os.chdir(root)
    return root


def start_server(port: int):
    """Imports the backend, prepares the game state and serves it on 127.0.0.1:<port> in a daemon thread."""
    from werkzeug.serving import make_server
    import server
    server.init_game_state()
    srv = make_server("127.0.0.1", port, server.app, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, name="hardwood-server", daemon=True)
    thread.start()
    srv.hardwood_thread = thread
    return srv


def wait_until_ready(url: str, timeout: float = READY_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/saves", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def on_window_closed(srv) -> None:
    """Close = autosave of the open career (no career: nothing to save), then the server stops.
    The save waits for a running game request (a sim day...) to end, so it never saves a half-simulated league;
    a failed or hanging save is logged and never blocks the exit (the slot keeps its previous good save)."""
    try:
        import server
        from core.config import CONFIG
        if not server.wait_for_idle(CONFIG.SAVES.CLOSE_WAIT_TIMEOUT_S):
            print("Close: a game request was still running, saving anyway", file=sys.stderr)
        saver = threading.Thread(target=server.auto_save_active_game, name="hardwood-close-save", daemon=True)
        saver.start()
        saver.join(CONFIG.SAVES.CLOSE_SAVE_TIMEOUT_S)
        if saver.is_alive():
            print("Close: the save did not finish in time, exiting with the previous save", file=sys.stderr)
    except Exception:
        traceback.print_exc()
    srv.shutdown()


def unblock_downloaded_files(root: str) -> int:
    """Removes the 'downloaded from the internet' mark (the Zone.Identifier stream) from the game files.

    Explorer copies that mark from a downloaded zip to every extracted file, and .NET Framework then refuses to
    load pythonnet's Python.Runtime.dll, so the game window cannot open. Returns how many files were unblocked;
    files it cannot change (read-only folder) are left alone."""
    count = 0
    for folder, _dirs, files in os.walk(root):
        for name in files:
            try:
                os.remove(os.path.join(folder, name) + ":Zone.Identifier")
                count += 1
            except OSError:
                pass
    return count


def show_error(message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, 0x10)
    except Exception:
        print(message, file=sys.stderr)


def _log_crash() -> str:
    path = paths.user_path("logs", "crash.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("--- %Y-%m-%d %H:%M:%S ---") + f" {version.label()}\n")
            fh.write(traceback.format_exc())
    except Exception:
        pass
    return path


def main(argv: list) -> int:
    headless = "--headless" in argv
    report = (lambda m: print(m, file=sys.stderr)) if headless else show_error
    lock = None
    try:
        os.makedirs(paths.user_root(), exist_ok=True)
        lock = acquire_single_instance(paths.user_path("hardwood.lock"))
        if lock is None:
            report(ALREADY_RUNNING)
            return 1
        redirect_std_streams(paths.user_path("logs", "server.log"))
        print(time.strftime("--- %Y-%m-%d %H:%M:%S ---") + f" Hardwood Basketball Simulator {version.label()} starting", flush=True)
        prepare_environment()
        port = find_free_port()
        url = f"http://127.0.0.1:{port}"
        srv = start_server(port)
        if not wait_until_ready(url):
            report(f"Hardwood Basketball Simulator could not start its game server.\nDetails: {paths.user_path('logs', 'server.log')}")
            return 1
        if headless:
            with open(paths.user_path("logs", "port.txt"), "w", encoding="utf-8") as fh:
                fh.write(str(port))
            srv.hardwood_thread.join()
            return 0
        if getattr(sys, "frozen", False):
            unblocked = unblock_downloaded_files(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
            if unblocked:
                print(f"Unblocked {unblocked} downloaded game files", flush=True)
        import webview
        webview.create_window(WINDOW_TITLE, url, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
                              min_size=WINDOW_MIN_SIZE)
        try:
            webview.start()
        except Exception as exc:
            if "Python.Runtime" not in str(exc):
                raise
            # The GUI could not load before any window opened: pythonnet blocked (see unblock_downloaded_files).
            _log_crash()
            report(BLOCKED_FILES)
            srv.shutdown()
            return 1
        on_window_closed(srv)
        return 0
    except Exception:
        crash = _log_crash()
        report(f"Hardwood Basketball Simulator stopped because of an error.\nDetails: {crash}")
        return 1
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
