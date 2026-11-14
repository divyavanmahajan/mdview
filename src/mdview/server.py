"""Local HTTP backend for the graphical UI.

The GUI is a small web app. It is shown in a native window (pywebview) or, as
a fallback, in the default browser. Either way it talks to this server, which
is bound to the loopback interface and guarded by a per-run secret token.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .render import (
    MARKDOWN_SUFFIXES,
    pygments_css,
    read_text,
    render_html,
    resolve_link,
    write_text,
)

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https: http:; media-src 'self' https: http:; font-src 'self' data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-src 'none'; object-src 'none'"
)
MEDIA_PREFIXES = ("image/", "video/", "audio/")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class AppState:
    """State shared between the HTTP handlers and the window host."""

    def __init__(self, initial: str | None = None, mode: str | None = None):
        self.token = secrets.token_urlsafe(24)
        self.initial = initial
        self.mode = mode
        self.dirty = False
        # Hooks installed by the native window host; absent in browser mode.
        self.native_dialog: Callable[[str, str, str], str | None] | None = None
        self.set_title: Callable[[str], None] | None = None
        self.close_window: Callable[[], None] | None = None


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _web_root():
    return resources.files("mdview") / "web"


class Handler(BaseHTTPRequestHandler):
    server_version = f"mdview/{__version__}"
    protocol_version = "HTTP/1.1"
    state: AppState

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if os.environ.get("MDVIEW_DEBUG"):
            sys.stderr.write("mdview: " + format % args + "\n")

    # -- plumbing ---------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _host_ok(self) -> bool:
        # Reject DNS-rebinding: the Host header must name the loopback address.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost")

    # -- GET --------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        url = urlsplit(self.path)
        path = url.path
        if path in ("/", "/index.html"):
            page = (_web_root() / "index.html").read_text(encoding="utf-8")
            page = page.replace("{{token}}", self.state.token)
            return self._send(200, page.encode(), "text/html; charset=utf-8")
        if path == "/pygments.css":
            return self._send(200, pygments_css().encode(), "text/css; charset=utf-8", cache=True)
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == f"/media/{self.state.token}":
            return self._media(parse_qs(url.query).get("path", [""])[0])
        self._send(404, b"not found", "text/plain")

    do_HEAD = do_GET  # noqa: N815

    def _static(self, rel: str) -> None:
        parts = [p for p in rel.split("/") if p]
        if not parts or any(p in ("..", ".") or "\\" in p for p in parts):
            return self._send(404, b"not found", "text/plain")
        node = _web_root()
        for part in parts:
            node = node / part
        if not node.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(parts[-1])[0] or "application/octet-stream"
        if parts[-1].endswith(".js"):
            ctype = "text/javascript"  # the Windows registry sometimes maps .js to text/plain
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, node.read_bytes(), ctype, cache=True)

    def _media(self, raw: str) -> None:
        path = Path(raw)
        ctype = mimetypes.guess_type(path.name)[0] or ""
        if not raw or not path.is_absolute() or not ctype.startswith(MEDIA_PREFIXES):
            return self._send(404, b"not found", "text/plain")
        try:
            data = path.read_bytes()
        except OSError:
            return self._send(404, b"not found", "text/plain")
        self._send(200, data, ctype)

    # -- POST -------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        # Always drain the body first so a refused request cannot desync keep-alive.
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        except ValueError:
            raw = b""
        token = self.headers.get("X-MDView-Token") or ""
        if not self._host_ok() or not secrets.compare_digest(token, self.state.token):
            return self._json({"error": "forbidden"}, 403)
        name = urlsplit(self.path).path.removeprefix("/api/").replace("-", "_")
        method = getattr(self, f"api_{name}", None)
        if method is None:
            return self._json({"error": "unknown endpoint"}, 404)
        try:
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict):
                raise ApiError("expected a JSON object")
            self._json(method(body))
        except ApiError as exc:
            self._json({"error": str(exc)}, exc.status)
        except OSError as exc:
            self._json({"error": exc.strerror or str(exc)}, 400)
        except Exception as exc:  # keep the UI alive whatever happens
            self._json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    @staticmethod
    def _path(body: dict, key: str = "path") -> Path:
        raw = body.get(key)
        if not isinstance(raw, str) or not raw:
            raise ApiError(f"missing {key}")
        path = Path(raw).expanduser()
        return Path(os.path.abspath(path))

    def api_state(self, body: dict) -> dict:
        return {
            "initial": self.state.initial,
            "mode": self.state.mode,
            "cwd": os.getcwd(),
            "native": self.state.native_dialog is not None,
            "version": __version__,
            "sep": os.sep,
        }

    def api_render(self, body: dict) -> dict:
        return {"html": render_html(str(body.get("text", "")))}

    def api_open(self, body: dict) -> dict:
        path = self._path(body)
        if path.is_dir():
            raise ApiError(f"{path} is a folder")
        if not path.exists():
            return {"path": str(path), "text": "", "html": "", "mtime": None, "exists": False}
        text = read_text(path)
        return {
            "path": str(path),
            "text": text,
            "html": render_html(text),
            "mtime": _mtime(path),
            "exists": True,
        }

    def api_save(self, body: dict) -> dict:
        path = self._path(body)
        expected = body.get("mtime")
        current = _mtime(path)
        if not body.get("force") and current is not None and expected != current:
            # Covers both "changed on disk since loaded" and "Save As onto an existing file".
            raise ApiError("conflict", 409)
        write_text(path, str(body.get("text", "")))
        return {"path": str(path), "mtime": _mtime(path)}

    def api_stat(self, body: dict) -> dict:
        return {"mtime": _mtime(self._path(body))}

    def api_resolve(self, body: dict) -> dict:
        target = resolve_link(str(body.get("href", "")), body.get("base") or None)
        return {
            "kind": target.kind,
            "path": target.path,
            "anchor": target.anchor,
            "url": target.url,
            "exists": bool(target.path) and Path(target.path).exists(),
        }

    def api_open_external(self, body: dict) -> dict:
        url = str(body.get("url") or "")
        if body.get("path"):
            path = self._path(body)
            if not path.exists():
                raise ApiError(f"{path} does not exist", 404)
            url = path.as_uri()
        elif urlsplit(url).scheme not in ("http", "https", "mailto"):
            raise ApiError("refusing to open this kind of link")
        webbrowser.open(url)
        return {"ok": True}

    def api_list(self, body: dict) -> dict:
        directory = self._path(body, "dir") if body.get("dir") else Path.cwd()
        if not directory.is_dir():
            directory = directory.parent
        entries = []
        for entry in os.scandir(directory):
            if entry.name.startswith("."):
                continue
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if is_dir or Path(entry.name).suffix.lower() in MARKDOWN_SUFFIXES:
                entries.append({"name": entry.name, "dir": is_dir})
        entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        parent = directory.parent
        return {
            "dir": str(directory),
            "parent": str(parent) if parent != directory else None,
            "entries": entries,
        }

    def api_dialog(self, body: dict) -> dict:
        if self.state.native_dialog is None:
            return {"native": False}
        kind = "save" if body.get("kind") == "save" else "open"
        chosen = self.state.native_dialog(
            kind, str(body.get("dir") or os.getcwd()), str(body.get("name") or "")
        )
        return {"native": True, "path": chosen}

    def api_session(self, body: dict) -> dict:
        """The page reports its dirty flag and title so the window can follow."""
        self.state.dirty = bool(body.get("dirty"))
        if self.state.set_title and isinstance(body.get("title"), str):
            self.state.set_title(body["title"])
        return {"ok": True}

    def api_close(self, body: dict) -> dict:
        self.state.dirty = False
        if self.state.close_window:
            threading.Thread(target=self.state.close_window, daemon=True).start()
        return {"ok": True}


def start_server(state: AppState, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the backend on a loopback port; returns the server and its URL."""
    handler = type("BoundHandler", (Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="mdview-http", daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"
