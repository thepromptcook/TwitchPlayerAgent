"""Chat sources. Each yields ChatMessage objects as an async iterator."""

from __future__ import annotations

import asyncio
import logging
import random
import ssl
import sys
import threading
from dataclasses import dataclass
from typing import AsyncIterator

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatMessage:
    user: str  # stable login name, used for one-vote-per-user
    display: str  # display name, shown on the overlay
    text: str


def parse_irc_line(line: str) -> ChatMessage | None:
    """Parse a Twitch IRC PRIVMSG line (with or without IRCv3 tags)."""
    tags: dict[str, str] = {}
    rest = line
    if rest.startswith("@"):
        raw_tags, _, rest = rest[1:].partition(" ")
        for item in raw_tags.split(";"):
            k, _, v = item.partition("=")
            tags[k] = v
    if not rest.startswith(":"):
        return None
    prefix, _, rest = rest[1:].partition(" ")
    command, _, rest = rest.partition(" ")
    if command != "PRIVMSG":
        return None
    _channel, _, text = rest.partition(" :")
    login = prefix.split("!", 1)[0].lower()
    if not login:
        return None
    display = tags.get("display-name") or login
    return ChatMessage(user=login, display=display, text=text)


class TwitchIrcChat:
    """Reads a Twitch channel's chat over TLS IRC. Anonymous by default (read-only),
    reconnecting with backoff if the connection drops."""

    def __init__(self, channel: str, nick: str = "", oauth_token: str = "",
                 host: str = "irc.chat.twitch.tv", port: int = 6697) -> None:
        if not channel:
            raise ValueError("Set [twitch].channel in your config (or use --stdin)")
        self.channel = channel.lower().lstrip("#")
        self.nick = nick.lower() or f"justinfan{random.randint(10000, 99999)}"
        self.token = oauth_token
        self.host, self.port = host, port

    async def __aiter__(self) -> AsyncIterator[ChatMessage]:
        backoff = 1.0
        while True:
            try:
                async for msg in self._session():
                    backoff = 1.0
                    yield msg
            except (OSError, asyncio.IncompleteReadError, ConnectionError) as exc:
                log.warning("Chat connection lost (%s); reconnecting in %.0fs", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _session(self) -> AsyncIterator[ChatMessage]:
        reader, writer = await asyncio.open_connection(
            self.host, self.port, ssl=ssl.create_default_context()
        )
        try:
            def send(line: str) -> None:
                writer.write((line + "\r\n").encode())

            send("CAP REQ :twitch.tv/tags twitch.tv/commands")
            if self.token:
                token = self.token if self.token.startswith("oauth:") else f"oauth:{self.token}"
                send(f"PASS {token}")
            send(f"NICK {self.nick}")
            send(f"JOIN #{self.channel}")
            await writer.drain()
            log.info("Joined #%s as %s", self.channel, self.nick)

            while True:
                raw = await reader.readline()
                if not raw:
                    raise ConnectionError("server closed the connection")
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith("PING"):
                    send("PONG" + line[4:])
                    await writer.drain()
                    continue
                if " RECONNECT" in line:
                    raise ConnectionError("server requested reconnect")
                msg = parse_irc_line(line)
                if msg is not None:
                    yield msg
        finally:
            writer.close()


class StdinChat:
    """Local testing: type lines like `ash: up` (or just `up`) into the terminal."""

    async def __aiter__(self) -> AsyncIterator[ChatMessage]:
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[str] = asyncio.Queue()

        # A daemon thread, not run_in_executor: executor threads are joined at
        # exit, which would hang the program on a blocked readline() after the
        # game window is closed.
        def reader() -> None:
            for raw in sys.stdin:
                loop.call_soon_threadsafe(lines.put_nowait, raw)
            loop.call_soon_threadsafe(lines.put_nowait, "")  # EOF

        threading.Thread(target=reader, name="stdin", daemon=True).start()
        while True:
            line = await lines.get()
            if not line:
                return
            line = line.strip()
            if not line:
                continue
            user, sep, text = line.partition(":")
            if not sep:
                user, text = "you", line
            user = user.strip() or "you"
            yield ChatMessage(user=user.lower(), display=user, text=text.strip())
