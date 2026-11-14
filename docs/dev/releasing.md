# Releasing

The version is not written anywhere in the source. `hatch-vcs` derives it from the git tag at build
time (`v1.2.3` gives `1.2.3`) and writes `src/mdview/_version.py`, which is not committed. Between
tags, builds get a development version such as `0.2.dev3+g1a2b3c4`.

To release, tag a commit on `main` and push the tag:

```bash
git tag v1.2.3
```

```bash
git push origin v1.2.3
```

`.github/workflows/publish.yml` then builds, checks that the built version equals the tag, creates
the GitHub release with the built files attached, and uploads to PyPI through trusted publishing
(project `dvm-mdview`, workflow `publish.yml`, environment `pypi`; configured once on pypi.org).
The GitHub release and the PyPI upload are separate jobs, so one can be re-run without the other.

Do not create the release by hand in the GitHub UI; the workflow would then fail to create it.

To check a build locally:

```bash
uv build
```

```bash
uvx --from dist/*.whl dvm-mdview --version
```

Builds need git history and tags; in CI, check out with `fetch-depth: 0`.

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
