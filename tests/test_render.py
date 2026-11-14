import os

from mdview.render import (
    extract_links,
    for_terminal,
    read_text,
    render_html,
    resolve_link,
    slugify,
    write_text,
)


def test_gfm_features():
    html = render_html("| a |\n|---|\n| 1 |\n\n- [x] done\n\n~~gone~~ www.example.com")
    assert "<table>" in html
    assert 'type="checkbox"' in html and "checked" in html
    assert "<s>gone</s>" in html
    assert 'href="http://www.example.com"' in html


def test_code_is_highlighted_and_mermaid_is_left_for_the_browser():
    html = render_html("```python\nprint(1)\n```\n\n```mermaid\ngraph TD; A-->B\n```")
    assert 'class="highlight"' in html and "<span" in html
    assert '<pre class="mermaid">graph TD; A--&gt;B' in html


def test_math_front_matter_footnotes_and_anchors():
    html = render_html("---\ntitle: T\n---\n# Hello, World!\n\n$x^2$ note[^1]\n\n$$\ny\n$$\n\n[^1]: fn")
    assert '<table class="front-matter">' in html and "<th>title</th><td>T</td>" in html
    assert '<h1 id="hello-world">' in html
    assert '<span class="math inline">x^2</span>' in html
    assert '<div class="math block">' in html
    assert 'class="footnotes"' in html


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  API v2.0 (beta) ") == "api-v20-beta"


def test_extract_links():
    links = extract_links("See [the *docs*](docs/a.md#x) and <https://example.com>.")
    assert [(l.text, l.href) for l in links] == [
        ("the docs", "docs/a.md#x"),
        ("https://example.com", "https://example.com"),
    ]


def test_resolve_link(tmp_path):
    current = tmp_path / "docs" / "index.md"
    current.parent.mkdir()
    (tmp_path / "docs" / "guide").mkdir()
    (tmp_path / "docs" / "guide" / "README.md").write_text("x")
    (tmp_path / "docs" / "wiki.md").write_text("x")
    (tmp_path / "docs" / "pic.png").write_text("x")

    assert resolve_link("#top", current).kind == "anchor"
    assert resolve_link("https://example.com/a.md", current).kind == "external"
    assert resolve_link("mailto:a@example.com", current).kind == "external"

    target = resolve_link("../other%20file.md#sec", current)
    assert (target.kind, target.path, target.anchor) == (
        "document", str(tmp_path / "other file.md"), "sec")
    assert resolve_link("guide", current).path == str(tmp_path / "docs" / "guide" / "README.md")
    assert resolve_link("wiki", current).path == str(tmp_path / "docs" / "wiki.md")
    assert resolve_link("pic.png", current).kind == "file"
    assert resolve_link((tmp_path / "docs" / "wiki.md").as_uri(), None).kind == "document"


def test_for_terminal_turns_front_matter_into_a_table():
    out = for_terminal("---\ntitle: T\n---\n# H\n")
    assert out.startswith("| | |") and "| **title** | T |" in out and out.endswith("# H\n")
    assert for_terminal("# plain") == "# plain"


def test_write_is_atomic_and_keeps_line_endings(tmp_path):
    path = tmp_path / "new" / "a.md"
    write_text(path, "a\r\nb\n")
    assert path.read_bytes() == b"a\r\nb\n"
    assert read_text(path) == "a\r\nb\n"
    assert os.listdir(path.parent) == ["a.md"]


def test_read_text_handles_bom_and_legacy_encodings(tmp_path):
    path = tmp_path / "a.md"
    path.write_bytes(b"\xef\xbb\xbf# hi")
    assert read_text(path) == "# hi"
    path.write_bytes("caf\xe9".encode("latin-1"))
    assert read_text(path) == "caf\xe9"
