# mdview

A Markdown viewer and editor with live preview, for macOS, Windows and Linux.
It has two interfaces that share one renderer:

- a **graphical UI** in a native window, and
- a **terminal UI** for use in a shell or over SSH.

Published on PyPI as **`dvm-mdview`**.

## Run it

With [uv](https://docs.astral.sh/uv/) installed, nothing else needs installing:

```bash
uvx dvm-mdview README.md
```

```bash
uvx dvm-mdview --tui README.md
```

Or install it, which gives you the shorter `mdview` command:

```bash
uv tool install dvm-mdview
```

```bash
mdview notes.md
```

| Option | Effect |
|---|---|
| *(none)* | Graphical UI. Falls back to the terminal UI when there is no display. |
| `-t`, `--tui` | Terminal UI. |
| `-b`, `--browser` | Graphical UI in your default browser instead of a native window. |
| `-e`, `--edit` | Start with editor and preview side by side. |
| `-r`, `--read` | Start with the preview only. |

A file that does not exist yet is opened empty and created when you save.
Passing a folder opens its `README.md`.

## Features

- **Live preview.** View, Split (editor and preview side by side) and Edit layouts. The preview
  updates as you type.
- **Link navigation.** Links to other Markdown files open in place, with back and forward history.
  Links to headings scroll to them. Web links open in your browser. A link to a file that does not
  exist starts a new document at that path.
- **Markdown.** CommonMark with GitHub tables, task lists, strikethrough and autolinks, plus
  footnotes, YAML front matter and heading anchors.
- **Code highlighting** in both interfaces.
- **Mermaid diagrams and LaTeX math** rendered in the graphical UI (shown as source in the terminal).
  Both work offline; the libraries are bundled.
- **Safe saving.** Files are written atomically, you are asked before unsaved changes are lost, and
  a file changed by another program is reloaded (or flagged, if you have edits of your own).
- Outline sidebar, light and dark themes, and relative images in the graphical UI.

## Keys

### Graphical UI

`Cmd` replaces `Ctrl` on macOS.

| Key | Action |
|---|---|
| `Ctrl+E` | Cycle View / Split / Edit |
| `Ctrl+S`, `Ctrl+Shift+S` | Save, Save as |
| `Ctrl+O`, `Ctrl+N` | Open, New |
| `Alt+Left`, `Alt+Right` | Back, Forward |
| `Ctrl+B`, `Ctrl+I`, `Ctrl+K` | Bold, italic, link |

### Terminal UI

| Key | Action |
|---|---|
| `Ctrl+E` | Cycle View / Split / Edit |
| `F6` | Switch between editor and preview |
| `Ctrl+S` | Save |
| `Ctrl+O` | Open |
| `Ctrl+L` | List the document's links and follow one |
| `Alt+Left`, `Alt+Right` | Back, Forward |
| `Ctrl+P` | Command palette (Save as, New, theme, ...) |
| `Ctrl+Q` | Quit |

Links can also be clicked with the mouse. While the preview has focus, single keys work too:
`e` edit, `l` links, `o` open, `b` back, `f` forward, `j`/`k` scroll, `q` quit.

## How it is built

| Part | Library |
|---|---|
| Markdown parsing | [markdown-it-py](https://github.com/executablebooks/markdown-it-py) and [mdit-py-plugins](https://github.com/executablebooks/mdit-py-plugins) |
| Code highlighting | [Pygments](https://pygments.org/) |
| Native window | [pywebview](https://pywebview.flowrl.com/) (WebKit on macOS, WebView2 on Windows) |
| Terminal UI | [Textual](https://textual.textualize.io/) |
| Diagrams and math | [Mermaid](https://mermaid.js.org/) and [KaTeX](https://katex.org/), bundled |

The graphical UI is a small web app served by a local backend (`src/mdview/server.py`) that listens
only on `127.0.0.1` and requires a per-run secret token. Raw HTML in a document is displayed, but a
strict Content-Security-Policy stops any script in it from running.

On Linux a native window needs GTK or Qt bindings for pywebview; without them mdview uses the
browser automatically.

## Development

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run mdview README.md
```

### Releasing

1. Bump `version` in `pyproject.toml` and `src/mdview/__init__.py`.
2. On pypi.org, add this repository as a *trusted publisher* for `dvm-mdview`
   (workflow `publish.yml`, environment `pypi`). This is needed once.
3. Publish a GitHub release. The `Publish to PyPI` workflow builds and uploads it.

To publish by hand instead: `uv build` then `uv publish` with a PyPI token.

## License

MIT. Bundled Mermaid and KaTeX are MIT licensed; their licences are in `src/mdview/web/vendor/`.
