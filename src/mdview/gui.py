"""Graphical UI: a native window (pywebview) around the local web app."""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

from .server import AppState, start_server

FILE_TYPES = ("Markdown (*.md;*.markdown;*.mdown;*.mkd;*.mdx;*.txt)", "All files (*.*)")


def has_display() -> bool:
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def run_browser(state: AppState, port: int = 0, open_browser: bool = True) -> int:
    """Serve the UI and show it in the default browser until interrupted."""
    server, url = start_server(state, port)
    print(f"mdview is running at {url}\nPress Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print()
    finally:
        server.shutdown()
    return 0


def run_window(state: AppState) -> int:
    """Show the UI in a native window. Raises ImportError if pywebview is unusable."""
    import logging

    import webview

    logging.getLogger("pywebview").setLevel(logging.CRITICAL)  # we report failures ourselves
    server, url = start_server(state)
    window = webview.create_window(
        "mdview", url, width=1200, height=820, min_size=(480, 320), text_select=True
    )
    closing_for_real = threading.Event()

    def native_dialog(kind: str, directory: str, name: str) -> str | None:
        try:
            dialogs = webview.FileDialog  # pywebview >= 6
            open_kind, save_kind = dialogs.OPEN, dialogs.SAVE
        except AttributeError:
            open_kind, save_kind = webview.OPEN_DIALOG, webview.SAVE_DIALOG
        if not os.path.isdir(directory):
            directory = os.getcwd()
        if kind == "save":
            result = window.create_file_dialog(
                save_kind, directory=directory, save_filename=name or "untitled.md",
                file_types=FILE_TYPES,
            )
        else:
            result = window.create_file_dialog(
                open_kind, directory=directory, allow_multiple=False, file_types=FILE_TYPES
            )
        if not result:
            return None
        return result if isinstance(result, str) else result[0]

    def on_closing():
        if closing_for_real.is_set() or not state.dirty:
            return True
        # Unsaved changes: cancel the close and let the page ask Save / Discard.
        # evaluate_js must not run on the GUI thread that is delivering this event.
        threading.Thread(
            target=lambda: window.evaluate_js("window.mdviewRequestClose()"), daemon=True
        ).start()
        return False

    def close_window() -> None:
        closing_for_real.set()
        window.destroy()

    state.native_dialog = native_dialog
    state.set_title = window.set_title
    state.close_window = close_window
    window.events.closing += on_closing
    try:
        webview.start(private_mode=True)
    finally:
        server.shutdown()
    return 0


def run(state: AppState, browser: bool = False, port: int = 0, open_browser: bool = True) -> int:
    if browser:
        return run_browser(state, port, open_browser)
    try:
        return run_window(state)
    except Exception as exc:  # no web engine, missing GTK/Qt, pythonnet trouble, ...
        print(f"mdview: native window unavailable ({exc}); using the browser.", file=sys.stderr)
        state.native_dialog = state.set_title = state.close_window = None
        return run_browser(state, port, open_browser)
