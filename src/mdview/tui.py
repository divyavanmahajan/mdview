"""Terminal UI built on Textual: editor and live preview side by side."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from textual import on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Input,
    Label,
    Markdown,
    OptionList,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from .render import (
    MARKDOWN_SUFFIXES,
    extract_links,
    for_terminal,
    read_text,
    resolve_link,
    write_text,
)

MODES = ("view", "split", "edit")


class ConfirmScreen(ModalScreen[str]):
    """A question with a row of buttons; dismisses with the chosen button id."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, question: str, buttons: list[tuple[str, str]]):
        super().__init__()
        self.question = question
        self.buttons = buttons

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.question, classes="dialog-title")
            with Horizontal(classes="dialog-buttons"):
                for index, (ident, label) in enumerate(self.buttons):
                    yield Button(label, id=ident, variant="primary" if index == 0 else "default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id or "cancel")

    def action_cancel(self) -> None:
        self.dismiss("cancel")


class MarkdownTree(DirectoryTree):
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [
            path
            for path in paths
            if not path.name.startswith(".")
            and (path.suffix.lower() in MARKDOWN_SUFFIXES or path.is_dir())
        ]


class PathScreen(ModalScreen[str]):
    """Choose a file to open or a path to save to. Dismisses with "" on cancel."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, directory: str, name: str = "", save: bool = False):
        super().__init__()
        self.heading = title
        self.directory = directory
        self.initial = name
        self.save = save

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall"):
            yield Label(self.heading, classes="dialog-title")
            yield Input(self.initial, placeholder="File name or path, then Enter", id="path-input")
            yield MarkdownTree(self.directory, id="path-tree")
            yield Label("Enter: confirm   Tab: browse files   Esc: cancel", classes="dialog-hint")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(DirectoryTree.FileSelected)
    def file_selected(self, event: DirectoryTree.FileSelected) -> None:
        if self.save:
            self.query_one(Input).value = str(event.path)
            self.query_one(Input).focus()
        else:
            self.dismiss(str(event.path))

    @on(DirectoryTree.DirectorySelected)
    def directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self.directory = str(event.path)

    @on(Input.Submitted)
    def submitted(self, event: Input.Submitted) -> None:
        typed = event.value.strip()
        if not typed:
            return
        path = Path(typed).expanduser()
        if not path.is_absolute():
            path = Path(self.directory) / path
        if path.is_dir():
            self.directory = str(path)
            self.query_one(MarkdownTree).path = path
            self.query_one(Input).value = ""
            return
        self.dismiss(os.path.abspath(path))

    def action_cancel(self) -> None:
        self.dismiss("")


class LinksScreen(ModalScreen[str]):
    """Keyboard access to every link in the document."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, links: list[tuple[str, str]]):
        super().__init__()
        self.links = links

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall"):
            yield Label("Follow a link", classes="dialog-title")
            yield OptionList(
                *(Option(f"{text}  →  {href}" if text != href else href) for text, href in self.links)
            )
            yield Label("Enter: follow   Esc: cancel", classes="dialog-hint")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.links[event.option_index][1])

    def action_cancel(self) -> None:
        self.dismiss("")


class Preview(VerticalScroll, can_focus=True):
    """The rendered document. Single-key commands work while it has focus."""

    BINDINGS = [
        Binding("e", "app.set_mode('split')", "Edit", show=False),
        Binding("l", "app.links", "Links", show=False),
        Binding("o", "app.open", "Open", show=False),
        Binding("b,backspace,left_square_bracket", "app.back", "Back", show=False),
        Binding("f,right_square_bracket", "app.forward", "Forward", show=False),
        Binding("q", "app.quit", "Quit", show=False),
        Binding("g,home", "scroll_home", "Top", show=False),
        Binding("G,end", "scroll_end", "Bottom", show=False),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("space", "page_down", "Page down", show=False),
    ]


class MdviewApp(App[int]):
    TITLE = "mdview"
    ENABLE_COMMAND_PALETTE = True

    CSS = """
    #status { height: 1; padding: 0 1; background: $primary; color: $text; }
    #panes { height: 1fr; }
    #editor { width: 1fr; border: none; border-right: solid $primary-darken-2; }
    #preview { width: 1fr; padding: 0 1; }
    #preview:focus { background: $surface; }
    Screen.-view #editor { display: none; }
    Screen.-edit #preview { display: none; }
    Screen.-edit #editor { border-right: none; }
    ModalScreen { align: center middle; }
    .dialog { width: 72; max-width: 95%; height: auto; padding: 1 2; background: $surface; border: thick $primary; }
    .dialog.tall { height: 80%; }
    .dialog-title { text-style: bold; margin-bottom: 1; width: 100%; }
    .dialog-hint { color: $text-muted; margin-top: 1; }
    .dialog-buttons { height: auto; align-horizontal: right; }
    .dialog-buttons Button { margin-left: 2; }
    #path-tree, OptionList { height: 1fr; margin-top: 1; }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("ctrl+o", "open", "Open", priority=True),
        Binding("ctrl+e", "cycle_mode", "View/Split/Edit", priority=True),
        Binding("ctrl+l", "links", "Links", priority=True),
        Binding("alt+left", "back", "Back", priority=True),
        Binding("alt+right", "forward", "Forward", priority=True),
        Binding("f6", "switch_pane", "Switch pane", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(self, path: str | None = None, mode: str | None = None):
        super().__init__()
        self.initial_path = path
        self.initial_mode = mode
        self.path: str | None = None
        self.saved_text = ""
        self.mtime: float | None = None
        self.mode = "split"
        self.history: list[dict] = []
        self.index = -1
        self._render_timer: Timer | None = None
        self._noticed_mtime: float | None = None

    # -- layout -------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(id="status", markup=False)
        with Horizontal(id="panes"):
            yield TextArea(
                "", id="editor", soft_wrap=True, tab_behavior="indent", show_line_numbers=True
            )
            with Preview(id="preview"):
                yield Markdown("", id="markdown", open_links=False)
        yield Footer()

    @property
    def editor(self) -> TextArea:
        return self.query_one("#editor", TextArea)

    @property
    def markdown(self) -> Markdown:
        return self.query_one("#markdown", Markdown)

    @property
    def preview(self) -> Preview:
        return self.query_one("#preview", Preview)

    async def on_mount(self) -> None:
        try:
            self.editor.language = "markdown"  # needs the optional textual[syntax] extra
        except Exception:
            pass
        exists = bool(self.initial_path) and os.path.exists(self.initial_path)
        self.action_set_mode(self.initial_mode or ("view" if exists else "split"))
        if self.initial_path:
            await self.load(self.initial_path)
        else:
            self.history.append({"path": None, "scroll": 0})
            self.index = 0
            self.refresh_status()
        self.set_interval(2.0, self.check_disk)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield SystemCommand("Save as…", "Save the document under a new name", self.action_save_as)
        yield SystemCommand("New document", "Start an empty document", self.action_new)
        yield SystemCommand("Open…", "Open a Markdown file", self.action_open)
        yield SystemCommand("Links", "List the links in this document", self.action_links)

    # -- state --------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        return self.editor.text != self.saved_text

    def refresh_status(self) -> None:
        name = self.path or "Untitled"
        mark = " ●" if self.dirty else ""
        self.query_one("#status", Static).update(f"{name}{mark}  ·  {self.mode}")
        self.sub_title = os.path.basename(name)

    def action_set_mode(self, mode: str) -> None:
        self.mode = mode
        for name in MODES:
            self.screen.set_class(name == mode, f"-{name}")
        (self.preview if mode == "view" else self.editor).focus()
        self.refresh_status()

    def action_cycle_mode(self) -> None:
        self.action_set_mode(MODES[(MODES.index(self.mode) + 1) % len(MODES)])

    def action_switch_pane(self) -> None:
        if self.mode == "split":
            (self.preview if self.editor.has_focus else self.editor).focus()

    # -- rendering ----------------------------------------------------------
    @on(TextArea.Changed, "#editor")
    def editor_changed(self) -> None:
        self.refresh_status()
        if self._render_timer:
            self._render_timer.stop()
        self._render_timer = self.set_timer(0.15, self.render_preview)

    async def render_preview(self) -> None:
        self._render_timer = None
        await self.markdown.update(for_terminal(self.editor.text))

    # -- documents ----------------------------------------------------------
    async def confirm_leave(self) -> bool:
        """Resolve unsaved changes. Must run inside a worker. False means stay."""
        if not self.dirty:
            return True
        name = os.path.basename(self.path) if self.path else "Untitled"
        answer = await self.push_screen_wait(
            ConfirmScreen(
                f"Save changes to {name}?",
                [("save", "Save"), ("discard", "Discard"), ("cancel", "Cancel")],
            )
        )
        if answer == "save":
            return await self.save()
        return answer == "discard"

    async def set_document(self, path: str | None, text: str, mtime: float | None) -> None:
        self.path = path
        self.saved_text = text
        self.mtime = mtime
        self._noticed_mtime = None
        self.editor.load_text(text)
        if self._render_timer:
            self._render_timer.stop()
        await self.render_preview()
        self.refresh_status()

    async def load(self, path: str, anchor: str = "", record: bool = True, scroll: float = 0) -> bool:
        path = os.path.abspath(path)
        exists = os.path.exists(path)
        try:
            text = read_text(path) if exists else ""
            mtime = os.stat(path).st_mtime if exists else None
        except OSError as exc:
            self.notify(str(exc), severity="error")
            return False
        if record:
            if self.index >= 0:
                self.history[self.index]["scroll"] = self.preview.scroll_y
            del self.history[self.index + 1:]
            self.history.append({"path": path, "scroll": 0})
            self.index = len(self.history) - 1
        await self.set_document(path, text, mtime)
        if not exists:
            if self.mode == "view":
                self.action_set_mode("split")
            self.notify(f"{os.path.basename(path)} does not exist yet. It will be created when you save.")
        if anchor:
            self.call_after_refresh(self.goto_anchor, anchor)
        else:
            self.call_after_refresh(self.preview.scroll_to, y=scroll, animate=False)
        return True

    def goto_anchor(self, anchor: str) -> None:
        if not self.markdown.goto_anchor(anchor):
            self.notify(f'No section "#{anchor}" in this document', severity="warning")

    async def save(self, path: str | None = None, force: bool = False) -> bool:
        """Must run inside a worker (it may ask questions)."""
        target = path or self.path
        if not target:
            return await self.save_as()
        try:
            current = os.stat(target).st_mtime if os.path.exists(target) else None
            expected = self.mtime if target == self.path else None
            if not force and current is not None and current != expected:
                question = (
                    f"{os.path.basename(target)} was changed on disk by another program. Overwrite it?"
                    if target == self.path
                    else f"{os.path.basename(target)} already exists. Replace it?"
                )
                answer = await self.push_screen_wait(
                    ConfirmScreen(question, [("cancel", "Cancel"), ("overwrite", "Overwrite")])
                )
                if answer != "overwrite":
                    return False
            text = self.editor.text
            write_text(target, text)
            self.mtime = os.stat(target).st_mtime
        except OSError as exc:
            self.notify(f"Could not save: {exc.strerror or exc}", severity="error")
            return False
        self.path = target
        self.saved_text = text
        self._noticed_mtime = None
        if self.index >= 0:
            self.history[self.index]["path"] = target
        self.refresh_status()
        self.notify(f"Saved {os.path.basename(target)}")
        return True

    async def save_as(self) -> bool:
        directory = os.path.dirname(self.path) if self.path else os.getcwd()
        name = os.path.basename(self.path) if self.path else "untitled.md"
        chosen = await self.push_screen_wait(PathScreen("Save as", directory, name, save=True))
        if not chosen:
            return False
        if not Path(chosen).suffix:
            chosen += ".md"
        return await self.save(chosen)

    async def check_disk(self) -> None:
        if not self.path or self.mtime is None or len(self.screen_stack) > 1:
            return
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            return
        if mtime == self.mtime:
            return
        if not self.dirty:
            scroll = self.preview.scroll_y
            await self.set_document(self.path, read_text(self.path), mtime)
            self.call_after_refresh(self.preview.scroll_to, y=scroll, animate=False)
        elif mtime != self._noticed_mtime:
            self._noticed_mtime = mtime
            self.notify("This file was changed on disk by another program.", severity="warning")

    # -- actions ------------------------------------------------------------
    @work
    async def action_save(self) -> None:
        await self.save()

    @work
    async def action_save_as(self) -> None:
        await self.save_as()

    @work
    async def action_open(self) -> None:
        directory = os.path.dirname(self.path) if self.path else os.getcwd()
        chosen = await self.push_screen_wait(PathScreen("Open a Markdown file", directory))
        if chosen and await self.confirm_leave():
            await self.load(chosen)

    @work
    async def action_new(self) -> None:
        if not await self.confirm_leave():
            return
        if self.index >= 0:
            self.history[self.index]["scroll"] = self.preview.scroll_y
        del self.history[self.index + 1:]
        self.history.append({"path": None, "scroll": 0})
        self.index = len(self.history) - 1
        await self.set_document(None, "", None)
        self.action_set_mode("split")

    @work
    async def action_links(self) -> None:
        links = [(link.text, link.href) for link in extract_links(self.editor.text)]
        if not links:
            self.notify("This document has no links.")
            return
        href = await self.push_screen_wait(LinksScreen(links))
        if href:
            await self.follow(href)

    async def go(self, delta: int) -> None:
        index = self.index + delta
        if not 0 <= index < len(self.history):
            self.notify("No more history in that direction.")
            return
        if not await self.confirm_leave():
            return
        self.history[self.index]["scroll"] = self.preview.scroll_y
        entry = self.history[index]
        self.index = index
        if entry["path"]:
            await self.load(entry["path"], record=False, scroll=entry["scroll"])
        else:
            await self.set_document(None, "", None)

    @work
    async def action_back(self) -> None:
        await self.go(-1)

    @work
    async def action_forward(self) -> None:
        await self.go(1)

    @work
    async def action_quit(self) -> None:
        if await self.confirm_leave():
            self.exit(0)

    # -- links --------------------------------------------------------------
    async def follow(self, href: str) -> None:
        """Must run inside a worker."""
        target = resolve_link(href, self.path)
        if target.kind == "anchor":
            self.goto_anchor(target.anchor)
        elif target.kind == "external":
            self.open_url(target.url)
            self.notify(f"Opening {target.url}")
        elif target.kind == "document":
            if target.path == self.path:
                if target.anchor:
                    self.goto_anchor(target.anchor)
            elif await self.confirm_leave():
                await self.load(target.path, anchor=target.anchor)
        elif os.path.exists(target.path):
            self.open_url(Path(target.path).as_uri())
        else:
            self.notify(f"{target.path} does not exist", severity="warning")

    @on(Markdown.LinkClicked)
    def link_clicked(self, event: Markdown.LinkClicked) -> None:
        event.stop()
        self.follow_link(event.href)

    @work
    async def follow_link(self, href: str) -> None:
        await self.follow(href)


def run(path: str | None = None, mode: str | None = None) -> int:
    result = MdviewApp(path, mode).run()
    return int(result or 0)
