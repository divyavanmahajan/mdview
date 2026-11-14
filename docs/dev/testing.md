# Testing

```bash
uv run pytest -q
```

| File | Covers |
|---|---|
| `tests/test_render.py` | Rendering features, slugs, link resolution, file reading and writing. |
| `tests/test_server.py` | Backend endpoints, token and host checks, save conflicts, media serving. |
| `tests/test_tui.py` | Terminal UI through Textual's pilot. |

## Terminal UI tests

Actions that open a dialog run in a worker that waits for the dialog. Do not call
`app.workers.wait_for_complete()` while a dialog is open; it never returns. Use `pilot.pause()`,
then act on the dialog.

## Checking the graphical UI

There are no automated browser tests in the repository. To check a change, run the app in browser
mode and drive it with a browser (by hand or with Playwright):

```bash
uv run mdview --browser --no-open --port 8765 README.md
```

Wait for `body[data-ready]` before interacting. Check at least: live preview while typing, a link to
another file and back, an anchor link, save, and a Mermaid block and a math block.

## What cannot be tested on Linux without a display

The native pywebview window, native file dialogs, and the close prompt with unsaved changes. These
need a manual check on macOS and Windows. CI runs the test suite on all three systems but does not
open a window.
