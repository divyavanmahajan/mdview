"""Markdown parsing and rendering shared by the graphical and terminal UIs."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mdx", ".txt"}

_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S)


def slugify(title: str) -> str:
    """GitHub-style heading slug: ``"Hello, World!"`` -> ``"hello-world"``."""
    text = unicodedata.normalize("NFKC", title).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _highlight(code: str, lang: str, _attrs: str) -> str:
    lang = (lang or "").strip().lower()
    if lang == "mermaid":
        return f'<pre class="mermaid">{html.escape(code)}</pre>'
    if lang in ("math", "latex", "tex"):
        return f'<pre class="math block">{html.escape(code)}</pre>'
    if not lang:
        return ""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""
    inner = pygments_highlight(code, lexer, HtmlFormatter(nowrap=True))
    return f'<pre class="highlight"><code class="language-{html.escape(lang)}">{inner}</code></pre>'


def parse_front_matter(raw: str) -> list[tuple[str, str]] | None:
    """Parse simple ``key: value`` front matter. Returns None if it is not flat."""
    rows: list[tuple[str, str]] = []
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t-" and rows:  # continuation / list item of previous key
            key, value = rows[-1]
            rows[-1] = (key, f"{value} {line.strip()}".strip())
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            return None
        rows.append((key.strip(), value.strip().strip("\"'")))
    return rows


def _render_front_matter(self, tokens, idx, options, env) -> str:
    raw = tokens[idx].content
    rows = parse_front_matter(raw)
    if not rows:
        return f'<pre class="front-matter">{html.escape(raw)}</pre>\n'
    body = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows
    )
    return f'<table class="front-matter"><tbody>{body}</tbody></table>\n'


def make_parser() -> MarkdownIt:
    md = (
        MarkdownIt("gfm-like", {"highlight": _highlight})
        .use(front_matter_plugin)
        .use(footnote_plugin)
        .use(tasklists_plugin)
        .use(anchors_plugin, max_level=6, slug_func=slugify)
        .use(dollarmath_plugin, allow_space=False, double_inline=True)
    )
    md.add_render_rule("front_matter", _render_front_matter)
    return md


_parser = make_parser()


def render_html(text: str) -> str:
    """Render Markdown source to an HTML fragment.

    Raw HTML in the source is passed through; the GUI relies on a strict
    Content-Security-Policy so that it can never execute script.
    """
    return _parser.render(text)


def pygments_css() -> str:
    light = HtmlFormatter(style="default").get_style_defs(".highlight")
    dark = HtmlFormatter(style="monokai").get_style_defs(':root[data-theme="dark"] .highlight')
    return f"{light}\n{dark}\n"


def for_terminal(text: str) -> str:
    """Rewrite source for the terminal renderer, which knows no front matter."""
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return text
    rows = parse_front_matter(match.group(1))
    rest = text[match.end():]
    if not rows:
        return f"```yaml\n{match.group(1)}\n```\n\n{rest}"
    table = "| | |\n|---|---|\n" + "".join(
        f"| **{k}** | {v.replace('|', chr(92) + '|')} |\n" for k, v in rows
    )
    return f"{table}\n{rest}"


@dataclass(frozen=True)
class Link:
    text: str
    href: str


def extract_links(text: str) -> list[Link]:
    """All hyperlinks in the document, in order of appearance."""
    links: list[Link] = []
    for token in _parser.parse(text):
        children = token.children or []
        i = 0
        while i < len(children):
            child = children[i]
            if child.type == "link_open":
                href = str(child.attrGet("href") or "")
                label = []
                i += 1
                while i < len(children) and children[i].type != "link_close":
                    label.append(children[i].content)
                    i += 1
                links.append(Link("".join(label).strip() or href, href))
            i += 1
    return links


@dataclass(frozen=True)
class Target:
    """Where a link leads.

    kind is ``"anchor"`` (same document), ``"document"`` (a Markdown file to
    open in the viewer), ``"file"`` (some other local file) or ``"external"``.
    """

    kind: str
    path: str = ""
    anchor: str = ""
    url: str = ""


def resolve_link(href: str, current: str | Path | None) -> Target:
    href = href.strip()
    if href.startswith("#"):
        return Target("anchor", anchor=unquote(href[1:]))
    parts = urlsplit(href)
    is_drive = len(parts.scheme) == 1  # "C:\notes.md" parses as scheme "c"
    if parts.scheme and not is_drive and parts.scheme != "file":
        return Target("external", url=href)
    if parts.scheme == "file":
        raw = unquote(parts.path)
        if re.match(r"^/[A-Za-z]:", raw):
            raw = raw[1:]
        anchor = unquote(parts.fragment)
    elif is_drive:
        raw, _, anchor = href.partition("#")
    else:
        raw = unquote(parts.path)
        anchor = unquote(parts.fragment)
    if not raw:
        return Target("anchor", anchor=anchor)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        base = Path(current).parent if current else Path.cwd()
        path = base / path
    path = Path(_normalize(path))
    if path.is_dir():
        for name in ("README.md", "index.md", "readme.md"):
            if (path / name).is_file():
                path = path / name
                break
    elif not path.exists() and not path.suffix:
        with_md = path.with_name(path.name + ".md")  # wiki-style link without suffix
        if with_md.is_file():
            path = with_md
    if path.suffix.lower() in MARKDOWN_SUFFIXES:
        return Target("document", path=str(path), anchor=anchor)
    return Target("file", path=str(path), anchor=anchor)


def _normalize(path: Path) -> str:
    import os

    return os.path.abspath(path)


def read_text(path: str | Path) -> str:
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def write_text(path: str | Path, text: str) -> None:
    """Write atomically so a crash cannot truncate the user's document."""
    import os
    import tempfile

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if target.exists():
            try:
                os.chmod(tmp, target.stat().st_mode & 0o777)
            except OSError:
                pass
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
