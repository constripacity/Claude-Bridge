"""Claude Bridge — Terminal UI.

A Textual-based command-line companion to the web dashboard. Connects to the
same HTTP API exposed by the bridge (defaults to http://localhost:8765) and
provides a live view of channels, messages, an inspector, and a send composer.

Usage:
    python -m claude_bridge.tui                     # connect to localhost:8765 (sender id auto-detected from platform)
    python -m claude_bridge.tui --url http://...    # connect to a remote bridge
    python -m claude_bridge.tui --sender mac        # override sender id used in send composer

Design reference: docs/design/terminal/  (React/JSX mockups of every layout).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from typing import Any

import httpx
from rich.json import JSON as RichJSON
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from .tui_client import (
    TYPE_COLORS,
    BridgeClient,
    BridgeError,
    classify_message,
    sender_color,
)


POLL_INTERVAL = 2.0
DEFAULT_URL = "http://localhost:8765"


def _short_uptime(seconds: int) -> str:
    """Render uptime at the coarsest unit that's still useful.

    Sub-minute uptimes show seconds (boot phase); everything else rounds to
    minutes so the top bar doesn't tick — and therefore doesn't flicker — on
    every 2-second poll.
    """
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    rem = minutes % 60
    if hours < 24:
        return f"{hours}h{rem:02d}m" if rem else f"{hours}h"
    days = hours // 24
    rem_h = hours % 24
    return f"{days}d{rem_h}h" if rem_h else f"{days}d"


def default_sender() -> str:
    sys_name = platform.system().lower()
    if "darwin" in sys_name:
        return "mac"
    if "windows" in sys_name:
        return "windows"
    if "linux" in sys_name:
        return "linux"
    return "agent"


# ── Widgets ──────────────────────────────────────────────────────────────────

class TopBar(Static):
    """Top status bar — bridge name, online dot, uptime, counts.

    Implemented as a single Static so Textual only repaints it when the rendered
    markup string genuinely differs. With minute-precision uptime and a cache
    on the rendered string, the bar holds completely still until a count
    changes or the bridge flips online/offline.
    """

    _last_markup: str = ""

    def set_state(
        self,
        *,
        online: bool,
        url: str,
        uptime: str,
        n_channels: int,
        n_messages: int,
    ) -> None:
        status = (
            "[#3fb950]●[/] [bold #3fb950]ONLINE[/]" if online
            else "[#f85149]○[/] [bold #f85149]OFFLINE[/]"
        )
        markup = (
            f"[bold #e6edf3]CLAUDE BRIDGE[/]   {status}   "
            f"[#8b949e]{url}[/]   "
            f"[#8b949e]uptime[/] [#e6edf3]{uptime}[/]   "
            f"[#8b949e]channels[/] [#e6edf3]{n_channels}[/]   "
            f"[#8b949e]messages[/] [#e6edf3]{n_messages}[/]"
        )
        if markup == self._last_markup:
            return
        self._last_markup = markup
        self.update(markup)


class ChannelList(ListView):
    """Sidebar list of channels, grouped by 'group:' prefix."""

    BINDINGS = [Binding("up", "cursor_up", show=False), Binding("down", "cursor_down", show=False)]

    async def populate(self, channels: list[dict[str, Any]], active: str | None) -> str | None:
        """Rebuild the list. Returns the channel id that's currently selected
        (or None if there are no channels)."""
        await self.clear()
        if not channels:
            await self.append(ListItem(Label("[#484f58]no channels yet[/]")))
            return None

        # group by prefix
        groups: dict[str, list[dict[str, Any]]] = {}
        for ch in channels:
            groups.setdefault(ch.get("group", ""), []).append(ch)

        new_selected_index: int | None = None
        idx = 0
        for group in sorted(groups.keys()):
            label = group if group else "(no group)"
            total = sum(c["count"] for c in groups[group])
            await self.append(ListItem(
                Label(f"[bold #8b949e]▼ {label}:[/] [#6e7681]{total}[/]"),
            ))
            idx += 1
            for ch in groups[group]:
                ch_id = ch["id"]
                marker = "▶" if ch_id == active else " "
                name = ch["name"][:18].ljust(18)
                count = str(ch["count"]).rjust(4)
                item = ListItem(
                    Label(f"[#58a6ff]{marker}[/] [#e6edf3]{name}[/] [#6e7681]{count}[/]"),
                )
                item.channel_id = ch_id  # type: ignore[attr-defined]
                await self.append(item)
                if ch_id == active:
                    new_selected_index = idx
                idx += 1
        # Move cursor onto the active channel if known
        if new_selected_index is not None:
            self.index = new_selected_index
        return active


class FeedTable(DataTable):
    """Message feed for the active channel."""

    BINDINGS = [Binding("enter", "select_cursor", show=False)]

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = False
        self.add_columns("SEQ", "SENDER", "TIME", "CONTENT", "TYPE")

    def render_messages(self, messages: list[dict[str, Any]], filter_text: str = "") -> None:
        self.clear()
        for m in messages:
            content = m.get("preview") or m.get("content") or ""
            if filter_text and filter_text.lower() not in content.lower():
                continue
            mtype = classify_message(content)
            sender = m["sender"]
            seq = m["seq"]
            ts = m.get("ts") or ""
            scolor = sender_color(sender)
            tcolor = TYPE_COLORS.get(mtype, "#8b949e")

            seq_text = Text(f"[{seq:>4}]", style="#6e7681")
            sender_text = Text(sender[:10].ljust(10), style=f"bold {scolor}")
            ts_text = Text(ts, style="#6e7681")
            preview = content.replace("\n", " ")
            preview_text = Text(preview, style="#e6edf3")
            type_text = Text(mtype.rjust(7), style=f"bold {tcolor}")

            self.add_row(seq_text, sender_text, ts_text, preview_text, type_text, key=m["id"])


class Inspector(VerticalScroll):
    """Detail pane for the selected message."""

    DEFAULT_CSS = """
    Inspector {
        background: #0d1117;
        padding: 1 2;
        border: solid #21262d;
    }
    Inspector > .ins-kv-row {
        height: 1;
    }
    Inspector .ins-section {
        color: #e6edf3;
        text-style: bold;
        margin-top: 1;
    }
    """

    def show_empty(self) -> None:
        self.remove_children()
        self.mount(Label("[#6e7681]no message selected — press Enter on a row[/]"))

    def show_message(self, msg: dict[str, Any]) -> None:
        self.remove_children()
        scolor = sender_color(msg["sender"])
        mtype = classify_message(msg.get("content", ""))
        tcolor = TYPE_COLORS.get(mtype, "#8b949e")

        # Header
        self.mount(Label("[bold #e6edf3]INSPECTOR[/]"))
        self.mount(Static(f"[#6e7681]id      [/] [#e6edf3]{msg['id']}[/]"))
        self.mount(Static(f"[#6e7681]seq     [/] [#e6edf3]{msg['seq']}[/]"))
        self.mount(Static(f"[#6e7681]sender  [/] [bold {scolor}]{msg['sender']}[/]"))
        self.mount(Static(f"[#6e7681]channel [/] [#7dd3fc]{msg['channel']}[/]"))
        self.mount(Static(f"[#6e7681]time    [/] [#e6edf3]{msg['ts']}[/]"))
        self.mount(Static(f"[#6e7681]bytes   [/] [#e6edf3]{msg.get('bytes', '?')}[/]"))
        self.mount(Static(f"[#6e7681]type    [/] [bold {tcolor}]{mtype}[/]"))
        self.mount(Static(""))
        self.mount(Label("[bold #e6edf3]CONTENT[/]"))

        content = msg.get("content", "")
        parsed = msg.get("content_parsed")
        if parsed is not None:
            pretty = json.dumps(parsed, indent=2)
            self.mount(Static(_colorize_json(pretty)))
        else:
            self.mount(Static(Text(content, style="#e6edf3")))


def _colorize_json(text: str):
    """Return a Rich renderable for the given JSON text. Falls back to plain text."""
    try:
        json.loads(text)
        return RichJSON(text)
    except (ValueError, TypeError):
        return Text(text, style="#e6edf3")


# ── Modal screens ────────────────────────────────────────────────────────────

class SendModal(ModalScreen[bool]):
    """Compose-and-send a message."""

    DEFAULT_CSS = """
    SendModal {
        align: center middle;
    }
    SendModal > Vertical {
        width: 80%;
        max-width: 110;
        height: auto;
        background: #161b22;
        border: thick #58a6ff;
        padding: 1 2;
    }
    SendModal Label {
        color: #8b949e;
        margin-top: 1;
    }
    SendModal Input {
        background: #0d1117;
        color: #e6edf3;
        border: tall #30363d;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "cancel")]

    def __init__(self, channel: str, sender: str) -> None:
        super().__init__()
        self._channel = channel
        self._sender = sender

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"[bold #e6edf3]Send to[/] [#7dd3fc]{self._channel}[/] [bold #e6edf3]as[/] [#58a6ff]{self._sender}[/]")
            yield Label("content (plain text or JSON):")
            yield Input(id="content", placeholder='{"type": "task", ...}  or  hello world')
            yield Label("[#6e7681]enter send · esc cancel[/]")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        content = event.value
        if not content.strip():
            self.dismiss(False)
            return
        app: "BridgeTUI" = self.app  # type: ignore[assignment]
        app.send_message_now(self._channel, self._sender, content)
        self.dismiss(True)


class NewChannelModal(ModalScreen[str | None]):
    DEFAULT_CSS = SendModal.DEFAULT_CSS

    BINDINGS = [Binding("escape", "cancel", "cancel")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold #e6edf3]new channel[/]  [#6e7681](e.g. demo:orchestrator)[/]")
            yield Input(id="name", placeholder="project:role")
            yield Label("[#6e7681]enter create · esc cancel[/]")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)


class ConfirmModal(ModalScreen[bool]):
    DEFAULT_CSS = SendModal.DEFAULT_CSS

    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
        Binding("y", "yes", "yes"),
        Binding("n", "cancel", "no"),
    ]

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._prompt)
            yield Label("[#6e7681]y confirm · n / esc cancel[/]")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_yes(self) -> None:
        self.dismiss(True)


class FilterModal(ModalScreen[str | None]):
    DEFAULT_CSS = SendModal.DEFAULT_CSS

    BINDINGS = [Binding("escape", "cancel", "cancel")]

    def __init__(self, current: str = "") -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold #e6edf3]filter feed[/]  [#6e7681](case-insensitive substring; empty to clear)[/]")
            yield Input(id="q", value=self._current, placeholder="text to match")
            yield Label("[#6e7681]enter apply · esc cancel[/]")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


# ── Main app ─────────────────────────────────────────────────────────────────

class BridgeTUI(App):
    """Terminal UI for Claude Bridge."""

    CSS = """
    Screen {
        background: #0d1117;
        color: #e6edf3;
    }
    TopBar {
        height: 1;
        background: #161b22;
        color: #e6edf3;
        padding: 0 2;
    }
    #body {
        height: 1fr;
    }
    #sidebar {
        width: 28;
        background: #0d1117;
        border-right: solid #21262d;
    }
    #sidebar-header {
        height: 1;
        padding: 0 2;
        color: #e6edf3;
        text-style: bold;
        background: #161b22;
    }
    ChannelList {
        background: #0d1117;
    }
    ChannelList > ListItem {
        padding: 0 1;
        background: #0d1117;
    }
    ChannelList > ListItem.--highlight {
        background: #1c2333;
    }
    #feed-pane {
        width: 2fr;
    }
    #feed-header {
        height: 1;
        background: #161b22;
        padding: 0 2;
        color: #e6edf3;
        text-style: bold;
        border-bottom: solid #21262d;
    }
    FeedTable {
        background: #0d1117;
    }
    FeedTable > .datatable--header {
        background: #161b22;
        color: #8b949e;
    }
    FeedTable > .datatable--cursor {
        background: #1c2333;
    }
    Inspector {
        width: 1fr;
        background: #0d1117;
        border-left: solid #21262d;
    }
    #status {
        height: 1;
        background: #161b22;
        color: #8b949e;
        padding: 0 2;
        border-top: solid #21262d;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("ctrl+c", "quit", show=False),
        Binding("tab", "focus_next", "panel"),
        Binding("shift+tab", "focus_previous", show=False),
        Binding("s", "send", "send"),
        Binding("f", "filter", "filter"),
        Binding("slash", "filter", show=False),
        Binding("n", "new_channel", "new chan"),
        Binding("c", "clear_channel", "clear"),
        Binding("i", "toggle_inspector", "inspector"),
        Binding("space", "toggle_pause", "pause"),
        Binding("question_mark", "help", "help"),
        Binding("r", "refresh", show=False),
    ]

    # Reactive state — what's currently selected
    active_channel: reactive[str | None] = reactive(None)
    paused: reactive[bool] = reactive(False)
    filter_text: reactive[str] = reactive("")
    inspector_visible: reactive[bool] = reactive(True)

    def __init__(self, url: str, sender: str) -> None:
        super().__init__()
        self._url = url
        self._sender = sender
        self._client: BridgeClient | None = None
        self._last_seen_id: dict[str, str] = {}      # channel -> last msg id polled
        self._cached_messages: dict[str, list[dict[str, Any]]] = {}
        self._all_channels: list[dict[str, Any]] = []
        self._inspected_id: str | None = None        # msg id currently in inspector

    def compose(self) -> ComposeResult:
        yield TopBar(id="topbar")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("[bold #e6edf3]CHANNELS[/]", id="sidebar-header")
                yield ChannelList(id="channels")
            with Vertical(id="feed-pane"):
                yield Static("[bold #e6edf3]FEED[/]  [#6e7681]select a channel[/]", id="feed-header")
                yield FeedTable(id="feed")
            yield Inspector(id="inspector")
        yield Static(
            "[bold #58a6ff][S][/] send  "
            "[bold #58a6ff][N][/] new  "
            "[bold #58a6ff][C][/] clear  "
            "[bold #58a6ff][F][/] filter  "
            "[bold #58a6ff][I][/] inspector  "
            "[bold #58a6ff][Space][/] pause  "
            "[bold #58a6ff][?][/] help  "
            "[bold #58a6ff][Q][/] quit",
            id="status",
        )
        yield Footer()

    async def on_mount(self) -> None:
        self._client = BridgeClient(self._url)
        topbar = self.query_one(TopBar)
        topbar.set_state(online=True, url=self._url, uptime="—", n_channels=0, n_messages=0)
        inspector = self.query_one(Inspector)
        inspector.show_empty()
        self.set_interval(POLL_INTERVAL, self.refresh_state)
        # Initial fetch
        await self.refresh_state()

    async def on_unmount(self) -> None:
        if self._client:
            await self._client.aclose()

    # ── Polling ──

    async def refresh_state(self) -> None:
        if self.paused or not self._client:
            return
        topbar = self.query_one(TopBar)
        try:
            state = await self._client.state()
        except (httpx.HTTPError, BridgeError):
            topbar.set_state(
                online=False, url=self._url, uptime="—",
                n_channels=0, n_messages=0,
            )
            return
        topbar.set_state(
            online=True,
            url=self._url,
            uptime=_short_uptime(state.get("uptime_seconds", 0)),
            n_channels=len(state.get("channels", [])),
            n_messages=state.get("total_messages", 0),
        )

        channels = state.get("channels", [])
        self._all_channels = channels

        sidebar = self.query_one(ChannelList)
        await sidebar.populate(channels, self.active_channel)

        # Auto-pick the first channel if nothing's active
        if self.active_channel is None and channels:
            self.active_channel = channels[0]["id"]
            self._update_feed_header(channels[0])

        # Refresh feed for the active channel
        if self.active_channel:
            await self._refresh_feed(self.active_channel)

    async def _refresh_feed(self, channel: str) -> None:
        if not self._client:
            return
        try:
            data = await self._client.messages(channel, limit=200)
        except (httpx.HTTPError, BridgeError):
            return
        messages = data.get("messages", [])
        prev = self._cached_messages.get(channel, [])
        self._cached_messages[channel] = messages
        feed = self.query_one(FeedTable)
        feed.render_messages(messages, self.filter_text)

        # Auto-inspect the latest message when:
        #   • feed was previously empty (first load on a channel), OR
        #   • a new message arrived since last poll AND inspector is currently
        #     showing nothing or showing the previously-latest message.
        if not messages:
            return
        latest = messages[-1]
        prev_latest_id = prev[-1]["id"] if prev else None
        if not prev or (prev_latest_id != latest["id"] and self._inspected_id in (None, prev_latest_id)):
            await self._inspect(latest["id"])
            try:
                feed.move_cursor(row=feed.row_count - 1)
            except Exception:
                pass

    def _update_feed_header(self, channel: dict[str, Any]) -> None:
        hdr = self.query_one("#feed-header", Static)
        n = channel["count"]
        senders = len(channel.get("senders", []))
        last = channel.get("last_ts", "—")
        hdr.update(
            f"[bold #e6edf3]FEED[/]  [bold #7dd3fc]{channel['id']}[/]  "
            f"[#6e7681]·  {n} msgs  ·  {senders} senders  ·  last {last}[/]"
            + (f"  [bold #d97706]· filter: {self.filter_text!r}[/]" if self.filter_text else "")
            + ("  [bold #d97706]· PAUSED[/]" if self.paused else "")
        )

    # ── Event handlers ──

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if item is None:
            return
        ch_id = getattr(item, "channel_id", None)
        if not ch_id:
            return
        self.active_channel = ch_id
        for ch in self._all_channels:
            if ch["id"] == ch_id:
                self._update_feed_header(ch)
                break
        # fire-and-forget refresh
        self.run_worker(self._refresh_feed(ch_id), exclusive=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        msg_id = event.row_key.value
        if msg_id:
            self.run_worker(self._inspect(msg_id), exclusive=True)

    async def _inspect(self, msg_id: str) -> None:
        if not self._client:
            return
        try:
            detail = await self._client.message_detail(msg_id)
        except (httpx.HTTPError, BridgeError):
            return
        inspector = self.query_one(Inspector)
        inspector.show_message(detail)
        self._inspected_id = msg_id

    # ── Actions ──

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        for ch in self._all_channels:
            if ch["id"] == self.active_channel:
                self._update_feed_header(ch)
                break

    def action_toggle_inspector(self) -> None:
        self.inspector_visible = not self.inspector_visible
        inspector = self.query_one(Inspector)
        inspector.display = self.inspector_visible

    def action_refresh(self) -> None:
        self.run_worker(self.refresh_state(), exclusive=True)

    @work
    async def action_send(self) -> None:
        if not self.active_channel:
            self.bell()
            return
        await self.push_screen_wait(SendModal(self.active_channel, self._sender))

    def send_message_now(self, channel: str, sender: str, content: str) -> None:
        async def _send() -> None:
            if not self._client:
                return
            try:
                await self._client.send(channel, sender, content)
            except BridgeError:
                return
            await self.refresh_state()
        self.run_worker(_send(), exclusive=False)

    @work
    async def action_new_channel(self) -> None:
        name = await self.push_screen_wait(NewChannelModal())
        if not name:
            return
        # A channel comes into existence when its first message is written.
        # Drop a hello marker as the current sender.
        if self._client:
            try:
                await self._client.send(name, self._sender, json.dumps({
                    "type": "hello",
                    "from": self._sender,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }))
            except BridgeError:
                pass
        self.active_channel = name
        await self.refresh_state()

    @work
    async def action_clear_channel(self) -> None:
        if not self.active_channel:
            self.bell()
            return
        ch = self.active_channel
        ok = await self.push_screen_wait(ConfirmModal(
            f"[bold #f85149]clear all messages from[/] [#7dd3fc]{ch}[/]?"
        ))
        if not ok or not self._client:
            return
        try:
            await self._client.clear(ch)
        except BridgeError:
            return
        await self.refresh_state()

    @work
    async def action_filter(self) -> None:
        result = await self.push_screen_wait(FilterModal(self.filter_text))
        if result is None:  # cancelled
            return
        self.filter_text = result
        if self.active_channel:
            await self._refresh_feed(self.active_channel)
            for ch in self._all_channels:
                if ch["id"] == self.active_channel:
                    self._update_feed_header(ch)
                    break

    @work
    async def action_help(self) -> None:
        await self.push_screen_wait(ConfirmModal(
            "[bold #e6edf3]Claude Bridge TUI[/]\n\n"
            "[#8b949e]Q[/] quit   [#8b949e]Tab[/] switch panel   [#8b949e]↑↓[/] navigate   [#8b949e]Enter[/] inspect\n"
            "[#8b949e]S[/] send   [#8b949e]N[/] new channel   [#8b949e]C[/] clear   [#8b949e]F[/] filter   [#8b949e]I[/] toggle inspector   [#8b949e]Space[/] pause\n\n"
            "[#6e7681]y to dismiss[/]"
        ))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Claude Bridge — Terminal UI")
    p.add_argument("--url", default=DEFAULT_URL, help=f"Bridge HTTP base URL (default: {DEFAULT_URL})")
    p.add_argument("--sender", default=default_sender(), help="Sender id used by the send composer")
    args = p.parse_args(argv)

    app = BridgeTUI(url=args.url, sender=args.sender)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
