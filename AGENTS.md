# mdview

Markdown viewer and editor with live preview. One Python package (`dvm-mdview` on PyPI, import
name `mdview`) with a graphical UI and a terminal UI that share one renderer.

## Rules that always apply

1. **No mention of Claude, Anthropic, AI or AI assistance** in commit messages (including trailers),
   pull request or issue text, comments, or any file. Only `AGENTS.md`, `CLAUDE.md` and
   `docs/dev/git.md` may mention it, because they state the rule.
2. **Commit as the repository owner**, never under a tool or bot identity. Set author and committer
   on every commit; the exact commands are in `docs/dev/git.md`.
3. **Must run on macOS and Windows through `uvx`.** Pure Python only, no build step, no new
   dependency without wheels for both.

## Everyday commands

```bash
uv sync
```

```bash
uv run pytest -q
```

```bash
uv run mdview --browser README.md
```

```bash
uv run mdview --tui README.md
```

## Read more only when the task needs it

| If you are about to... | Read |
|---|---|
| commit, push, or write a pull request | `docs/dev/git.md` |
| change rendering, the backend, or either UI | `docs/dev/architecture.md` |
| add or debug tests, or check a UI change by hand | `docs/dev/testing.md` |
| cut a release or update the bundled Mermaid / KaTeX | `docs/dev/releasing.md` |

User-facing behaviour, options and keys are documented in `README.md`; keep it in step with changes.
