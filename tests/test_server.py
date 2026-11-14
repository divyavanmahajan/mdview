import json
import os
import urllib.error
import urllib.request

import pytest

from mdview.server import AppState, start_server


@pytest.fixture
def app(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# Title\n\n[next](other.md)\n", encoding="utf-8")
    state = AppState(str(doc))
    server, url = start_server(state)
    yield state, url, tmp_path
    server.shutdown()
    server.server_close()


def call(url, name, body=None, token=None, host=None):
    request = urllib.request.Request(
        f"{url}api/{name}", data=json.dumps(body or {}).encode(), method="POST"
    )
    if token:
        request.add_header("X-MDView-Token", token)
    if host:
        request.add_header("Host", host)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def get(url):
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def test_index_embeds_token_and_sets_csp(app):
    state, url, _ = app
    status, headers, body = get(url)
    assert status == 200 and state.token.encode() in body
    assert "script-src 'self'" in headers["Content-Security-Policy"]


def test_static_assets_are_served_and_traversal_is_refused(app):
    _, url, _ = app
    status, headers, body = get(url + "static/app.js")
    assert status == 200 and headers["Content-Type"].startswith("text/javascript") and body
    assert get(url + "static/vendor/katex.min.css")[0] == 200
    assert get(url + "static/vendor/mermaid.min.js")[0] == 200
    assert get(url + "static/../server.py")[0] == 404
    assert get(url + "static/%2e%2e/server.py")[0] == 404


def test_api_requires_token_and_loopback_host(app):
    state, url, _ = app
    assert call(url, "state")[0] == 403
    assert call(url, "state", token="wrong")[0] == 403
    assert call(url, "state", token=state.token, host="evil.example")[0] == 403
    status, data = call(url, "state", token=state.token)
    assert status == 200 and data["initial"] == state.initial


def test_open_render_resolve(app):
    state, url, tmp = app
    _, doc = call(url, "open", {"path": state.initial}, state.token)
    assert doc["exists"] and '<h1 id="title">' in doc["html"]
    _, rendered = call(url, "render", {"text": "*hi*"}, state.token)
    assert "<em>hi</em>" in rendered["html"]
    _, target = call(url, "resolve", {"href": "other.md#a", "base": state.initial}, state.token)
    assert target == {"kind": "document", "path": str(tmp / "other.md"), "anchor": "a",
                      "url": "", "exists": False}
    _, missing = call(url, "open", {"path": str(tmp / "other.md")}, state.token)
    assert missing["exists"] is False and missing["text"] == ""


def test_save_detects_conflicts(app):
    state, url, tmp = app
    path = state.initial
    _, doc = call(url, "open", {"path": path}, state.token)
    status, saved = call(url, "save", {"path": path, "text": "one", "mtime": doc["mtime"]}, state.token)
    assert status == 200 and open(path).read() == "one"

    os.utime(path, (saved["mtime"] + 10, saved["mtime"] + 10))  # another program wrote the file
    status, _ = call(url, "save", {"path": path, "text": "two", "mtime": saved["mtime"]}, state.token)
    assert status == 409 and open(path).read() == "one"
    status, _ = call(url, "save", {"path": path, "text": "two", "mtime": None, "force": True}, state.token)
    assert status == 200 and open(path).read() == "two"

    new = str(tmp / "sub" / "new.md")
    assert call(url, "save", {"path": new, "text": "x", "mtime": None}, state.token)[0] == 200
    assert call(url, "save", {"path": new, "text": "y", "mtime": None}, state.token)[0] == 409


def test_media_serves_only_media_with_token(app):
    state, url, tmp = app
    (tmp / "a.png").write_bytes(b"\x89PNG")
    from urllib.parse import quote

    ok = get(f"{url}media/{state.token}?path={quote(str(tmp / 'a.png'))}")
    assert ok[0] == 200 and ok[1]["Content-Type"] == "image/png"
    assert get(f"{url}media/{state.token}?path={quote(state.initial)}")[0] == 404
    assert get(f"{url}media/wrong?path={quote(str(tmp / 'a.png'))}")[0] == 404


def test_list_and_external_links(app):
    state, url, tmp = app
    (tmp / "folder").mkdir()
    (tmp / "notes.txt").write_text("x")
    (tmp / "data.bin").write_text("x")
    _, listing = call(url, "list", {"dir": str(tmp)}, state.token)
    assert [e["name"] for e in listing["entries"]] == ["folder", "doc.md", "notes.txt"]
    status, _ = call(url, "open-external", {"url": "javascript:alert(1)"}, state.token)
    assert status == 400
