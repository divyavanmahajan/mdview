# Architecture

All code is in `src/mdview/`.

| File | Role |
|---|---|
| `cli.py` | Argument parsing; picks terminal UI, native window or browser. |
| `render.py` | Everything both UIs share: Markdown to HTML, link resolution, link extraction, reading and atomic writing of files. |
| `server.py` | Loopback HTTP backend for the graphical UI. |
| `gui.py` | Hosts the web app in a pywebview window, or the default browser as fallback. |
| `tui.py` | Textual app. |
| `web/` | The graphical UI: `index.html`, `app.js`, `app.css`, and `vendor/` (bundled Mermaid and KaTeX). |

## Rendering

- `render.py` builds one markdown-it-py parser (`gfm-like` preset plus front matter, footnotes,
  task lists, anchors, dollar math). Pygments highlights fenced code in Python.
- Mermaid fences become `<pre class="mermaid">` and math becomes `.math` elements; `app.js` renders
  them in the page with the bundled libraries.
- The terminal UI uses Textual's own `Markdown` widget. `for_terminal()` rewrites front matter into
  a table first. Mermaid and math stay as source there.
- Link behaviour must stay identical in both UIs: change `resolve_link()`, not the callers.

## Graphical UI

- The page calls the backend with `POST /api/<name>` and JSON. Each endpoint is a method
  `api_<name>` on `Handler` in `server.py`.
- The window host installs hooks on `AppState` (`native_dialog`, `set_title`, `close_window`).
  When they are absent (browser mode) the page uses its own in-page file chooser.
- `--browser` mode serves exactly the same app, which is how the UI is tested without a display.

## Security constraints (do not weaken)

- The server binds to `127.0.0.1` only and checks the `Host` header.
- Every API call needs the per-run token in `X-MDView-Token`; media URLs carry it in the path and
  serve only image, video and audio types.
- Raw HTML from documents is inserted into the page. The Content-Security-Policy in `server.py`
  (`script-src 'self'`, no inline script) is what makes that safe. No inline scripts or inline
  event handlers in `web/`.
- `open-external` accepts only `http`, `https` and `mailto` URLs, or an existing local path.

## Saving

`write_text()` writes to a temporary file and replaces the target. Both UIs compare the file's
modification time before saving and ask before overwriting a file changed elsewhere.
