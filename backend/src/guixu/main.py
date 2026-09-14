from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import secrets
import socket
import sys
import threading
from pathlib import Path

import uvicorn
from platformdirs import user_data_path

from guixu.api.app import create_app
from guixu.desktop.bridge import DesktopBridge
from guixu.desktop.single_instance import SingleInstance


WEBVIEW2_CLIENT_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"


def find_project_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        if (bundle_root / "contracts" / "database.sql").is_file():
            return bundle_root
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "contracts" / "database.sql").exists() and (candidate / "seed" / "default-settings.json").exists():
            return candidate
    raise RuntimeError("Guixu project resources were not found")


def webview2_runtime_version() -> str | None:
    """Return the Evergreen Runtime version without starting a browser or network request."""
    if os.name != "nt":
        return None
    import winreg

    locations = (
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}"),
    )
    for hive, key_name in locations:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                version = str(winreg.QueryValueEx(key, "pv")[0]).strip()
            if version and version != "0.0.0.0":
                return version
        except OSError:
            continue
    return None


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def application_data_dir() -> Path:
    test_override = os.environ.get("GUIXU_TEST_DATA_DIR")
    if os.environ.get("GUIXU_TEST_MODE") == "1" and test_override:
        return Path(test_override).resolve()
    return Path(user_data_path("Guixu", appauthor=False))


def run_desktop() -> int:
    import webview

    project_root = find_project_root()
    data_dir = application_data_dir()
    if webview2_runtime_version() is None:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "未检测到 Microsoft Edge WebView2 Runtime。\n\n"
            "请从 Microsoft 官方页面安装 Evergreen Runtime 后重新启动归序：\n"
            f"{WEBVIEW2_DOWNLOAD_URL}",
            "归序无法启动",
            0x10,
        )
        return 3
    instance = SingleInstance(data_dir / "guixu.lock")
    instance.acquire()
    token = secrets.token_urlsafe(32)
    port = reserve_port()
    origin = f"http://127.0.0.1:{port}"
    app = create_app(project_root=project_root, data_dir=data_dir, session_token=token, allowed_origins={origin})
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", workers=1)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="guixu-api", daemon=True)
    thread.start()
    shutdown_lock = threading.Lock()
    shutdown_finished = threading.Event()

    def shutdown_resources() -> None:
        if shutdown_finished.is_set():
            return
        with shutdown_lock:
            if shutdown_finished.is_set():
                return
            server.should_exit = True
            thread.join(timeout=10)
            app.state.database.close()
            instance.release()
            shutdown_finished.set()

    bridge = DesktopBridge(app.state.registry)
    window = webview.create_window(
        "归序 Guixu",
        origin,
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(1024, 680),
    )

    def inject_session() -> None:
        window.evaluate_js(f"window.__GUIXU_SESSION__={token!r};window.dispatchEvent(new Event('guixu-ready'))")

    def window_closed() -> None:
        def finish() -> None:
            shutdown_resources()
            if getattr(sys, "frozen", False):
                os._exit(0)

        threading.Thread(target=finish, name="guixu-shutdown", daemon=True).start()

    window.events.closed += window_closed

    try:
        webview.start(inject_session, gui="edgechromium", debug=False)
    finally:
        shutdown_resources()
    return 0


def run_diagnostics() -> int:
    """Exercise frozen resources and AppData database initialization without opening the GUI."""
    project_root = find_project_root()
    override = os.environ.get("GUIXU_DIAGNOSTIC_DATA_DIR")
    data_dir = Path(override).resolve() if override else Path(user_data_path("Guixu", appauthor=False))
    app = create_app(project_root=project_root, data_dir=data_dir, session_token=secrets.token_urlsafe(32))
    try:
        result = {
            "status": "ok",
            "frozen": bool(getattr(sys, "frozen", False)),
            "resource_root": str(project_root),
            "frontend_present": (project_root / "frontend" / "dist" / "index.html").is_file(),
            "database_path": str(app.state.database.path),
            "database_outside_install_dir": Path(app.state.database.path).resolve().parent
            != Path(sys.executable).resolve().parent,
            "webview2_runtime": webview2_runtime_version(),
        }
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        (data_dir / "diagnostics.json").write_text(encoded, "utf-8")
        print(encoded)
        return 0 if result["frontend_present"] and result["database_outside_install_dir"] else 2
    finally:
        app.state.database.close()


def main() -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    args, remaining = parser.parse_known_args()
    if args.worker:
        from guixu.worker import main as worker_main

        return worker_main(remaining)
    if remaining:
        parser.error(f"unrecognized arguments: {' '.join(remaining)}")
    if args.diagnose:
        return run_diagnostics()
    return run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
