# Releasing

1. Set the same version in `pyproject.toml` and `src/mdview/__init__.py`.
2. Check the build and that the wheel runs the way `uvx` runs it:

```bash
uv build
```

```bash
uvx --from dist/*.whl dvm-mdview --version
```

3. Publish a GitHub release. `.github/workflows/publish.yml` uploads to PyPI through trusted
   publishing (project `dvm-mdview`, workflow `publish.yml`, environment `pypi`; configured once on
   pypi.org).

The wheel must contain `mdview/web/` including `vendor/`; `uv build` output can be checked with
`python -m zipfile -l dist/*.whl`.

## Updating bundled Mermaid and KaTeX

Currently Mermaid 12.3.0 and KaTeX 0.19.1. They are copied from the npm packages, not built:

```bash
npm pack mermaid katex
```

From the unpacked packages copy `mermaid/dist/mermaid.min.js`, `katex/dist/katex.min.js`,
`katex/dist/katex.min.css`, `katex/dist/fonts/*.woff2` and both `LICENSE` files into
`src/mdview/web/vendor/` (licences as `LICENSE-mermaid` and `LICENSE-katex`). Update the versions
above, then check a Mermaid block and a math block in the graphical UI.
