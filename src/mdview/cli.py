"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdview",
        description="Markdown viewer and live-preview editor (graphical and terminal UI).",
    )
    parser.add_argument("file", nargs="?", help="Markdown file to open (created on save if missing)")
    ui = parser.add_mutually_exclusive_group()
    ui.add_argument("-t", "--tui", action="store_true", help="use the terminal UI")
    ui.add_argument("-g", "--gui", action="store_true", help="use the graphical UI (default)")
    ui.add_argument(
        "-b", "--browser", action="store_true",
        help="graphical UI in the default web browser instead of a native window",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("-e", "--edit", action="store_true", help="start with editor and preview side by side")
    mode.add_argument("-r", "--read", action="store_true", help="start in read-only preview")
    parser.add_argument("--port", type=int, default=0, help="port for --browser (default: any free port)")
    parser.add_argument("--no-open", action="store_true", help="with --browser, do not launch the browser")
    parser.add_argument("-V", "--version", action="version", version=f"mdview {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = os.path.abspath(os.path.expanduser(args.file)) if args.file else None
    if path and os.path.isdir(path):
        for name in ("README.md", "index.md", "readme.md"):
            if os.path.isfile(os.path.join(path, name)):
                path = os.path.join(path, name)
                break
        else:
            print(f"mdview: {path} is a folder without a README.md", file=sys.stderr)
            return 2
    mode = "split" if args.edit else "view" if args.read else None

    from .gui import has_display

    use_tui = args.tui
    if not (args.tui or args.gui or args.browser) and not has_display():
        use_tui = True  # e.g. an SSH session: no display to open a window on
    if use_tui:
        from .tui import run as run_tui

        return run_tui(path, mode)

    from .gui import run as run_gui
    from .server import AppState

    return run_gui(AppState(path, mode), args.browser, args.port, not args.no_open)


if __name__ == "__main__":
    sys.exit(main())
