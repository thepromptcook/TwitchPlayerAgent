"""Chat sources: async iterators of ChatMessage."""

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
    user: str  # login name: the identity for one vote per user
    display: str  # display name, for the overlay
    text: str
    mod: bool = False  # the channel owner or a moderator: may use !mode and !ticker


def parse_irc_line(line: str) -> ChatMessage | None:
    """A Twitch IRC PRIVMSG line (IRCv3 tags optional) as a ChatMessage, else None."""
    tags: dict[str, str] = {}
    if line.startswith("@"):
        raw, _, line = line[1:].partition(" ")
        tags = dict(item.partition("=")[::2] for item in raw.split(";"))
    prefix, _, rest = line.partition(" ")
    command, _, rest = rest.partition(" ")
    login = prefix[1:].split("!", 1)[0].lower()
    if not prefix.startswith(":") or command != "PRIVMSG" or not login:
        return None
    mod = tags.get("mod") == "1" or "broadcaster/" in tags.get("badges", "")
    return ChatMessage(login, tags.get("display-name") or login, rest.partition(" :")[2], mod)


class TwitchIrcChat:
    """A channel's chat, read anonymously (the bot never posts) over TLS IRC; reconnects with
    backoff when the connection drops."""

    HOST, PORT = "irc.chat.twitch.tv", 6697

    def __init__(self, channel: str) -> None:
        if not channel:
            raise SystemExit("Set [twitch].channel in your config (or use --stdin).")
        self.channel = channel.lower().lstrip("#")
        self.nick = f"justinfan{random.randint(10000, 99999)}"  # Twitch's anonymous login

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
        reader, writer = await asyncio.open_connection(self.HOST, self.PORT, ssl=ssl.create_default_context())
        try:
            for line in ("CAP REQ :twitch.tv/tags twitch.tv/commands", f"NICK {self.nick}", f"JOIN #{self.channel}"):
                writer.write(f"{line}\r\n".encode())
            await writer.drain()
            log.info("Joined #%s as %s", self.channel, self.nick)
            while True:
                raw = await reader.readline()
                if not raw:
                    raise ConnectionError("server closed the connection")
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith("PING"):
                    writer.write(f"PONG{line[4:]}\r\n".encode())
                    await writer.drain()
                elif " RECONNECT" in line:
                    raise ConnectionError("server requested reconnect")
                elif (msg := parse_irc_line(line)) is not None:
                    yield msg
        finally:
            writer.close()


class StdinChat:
    """Lines typed in the terminal, `ash: up` or just `up`. Whoever types there runs the bot, so
    they count as a moderator."""

    async def __aiter__(self) -> AsyncIterator[ChatMessage]:
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[str] = asyncio.Queue()

        def reader() -> None:  # a daemon thread: an executor thread is joined at exit and hung it
            for raw in sys.stdin:
                loop.call_soon_threadsafe(lines.put_nowait, raw)
            loop.call_soon_threadsafe(lines.put_nowait, "")  # EOF

        threading.Thread(target=reader, name="stdin", daemon=True).start()
        while line := await lines.get():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            user, sep, text = line.partition(":")
            user = user.strip() if sep and user.strip() else "you"
            yield ChatMessage(user.lower(), user, (text if sep else line).strip(), mod=True)
