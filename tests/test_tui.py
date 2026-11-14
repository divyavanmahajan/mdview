import pytest

from mdview.tui import ConfirmScreen, LinksScreen, MdviewApp
from textual.widgets import Markdown


@pytest.fixture
def docs(tmp_path):
    (tmp_path / "index.md").write_text(
        "---\ntitle: Demo\n---\n# Index\n\n[second](second.md#target) and [web](https://example.com)\n",
        encoding="utf-8",
    )
    (tmp_path / "second.md").write_text("# Second\n\n## Target\n\n[back](index.md)\n", encoding="utf-8")
    return tmp_path


async def settle(pilot):
    await pilot.app.workers.wait_for_complete()
    await pilot.pause(0.3)


def rendered(app) -> str:
    return "\n".join(
        str(block._content) for block in app.query_one(Markdown).query("MarkdownBlock") if hasattr(block, "_content")
    )


async def test_opens_in_view_mode_and_renders(docs):
    app = MdviewApp(str(docs / "index.md"))
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.mode == "view"
        assert not app.editor.display and app.preview.display
        assert "Index" in rendered(app)
        assert not app.dirty


async def test_live_preview_while_typing_then_save(docs):
    app = MdviewApp(str(docs / "index.md"), "split")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.editor.has_focus
        app.editor.move_cursor(app.editor.document.end)
        await pilot.press("enter", "#", "space", "L", "i", "v", "e")
        await settle(pilot)
        assert app.dirty
        assert "Live" in rendered(app)
        await pilot.press("ctrl+s")
        await settle(pilot)
        assert not app.dirty
        assert (docs / "index.md").read_text(encoding="utf-8").endswith("\n# Live")


async def test_follow_links_and_history(docs):
    app = MdviewApp(str(docs / "index.md"))
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("l")
        await pilot.pause(0.3)  # the worker is now waiting on the dialog
        assert isinstance(app.screen, LinksScreen)
        await pilot.press("enter")  # first link: second.md#target
        await settle(pilot)
        assert app.path == str(docs / "second.md")
        assert "Second" in rendered(app)
        await pilot.press("b")
        await settle(pilot)
        assert app.path == str(docs / "index.md")
        await pilot.press("f")
        await settle(pilot)
        assert app.path == str(docs / "second.md")


async def test_clicked_link_event_navigates(docs):
    app = MdviewApp(str(docs / "second.md"))
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        md = app.query_one(Markdown)
        md.post_message(Markdown.LinkClicked(md, "index.md"))
        await pilot.pause()
        await settle(pilot)
        assert app.path == str(docs / "index.md")


async def test_unsaved_changes_are_guarded(docs):
    app = MdviewApp(str(docs / "index.md"), "split")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("x")
        await pilot.press("ctrl+q")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("escape")
        await settle(pilot)
        assert app.is_running and app.dirty
        await pilot.press("ctrl+q")
        await pilot.pause(0.3)
        await pilot.click("#discard")
        await settle(pilot)
    assert not (docs / "index.md").read_text(encoding="utf-8").startswith("x")


async def test_missing_file_is_created_on_save(docs):
    target = docs / "new" / "note.md"
    app = MdviewApp(str(target))
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.mode == "split"
        await pilot.press("h", "i")
        await pilot.press("ctrl+s")
        await settle(pilot)
        assert target.read_text(encoding="utf-8") == "hi"
