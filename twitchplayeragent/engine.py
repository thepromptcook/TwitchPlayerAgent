"""The Twitch Plays engine: chat messages in, one queue of presses out. Anarchy appends every
input, democracy appends each round's winner, AI mode replaces the queue with each decision,
and a mode switch clears it. The decision methods are synchronous and take `now`, so tests
drive them directly; run() wires them to a chat source and a backend."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from pathlib import Path
from typing import AsyncIterable

from .backends import Backend
from .chat import ChatMessage
from .commands import parse_anarchy, parse_democracy, parse_mode_vote
from .config import Config
from .llm import Planner, unavailable
from .modes import DemocracyTally, Mode, ModeMeter
from .overlay import Overlay

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, cfg: Config, overlay: Overlay | None = None) -> None:
        self.cfg, self.overlay = cfg, overlay
        m = cfg.meter
        self.meter = ModeMeter(m.to_democracy, m.to_anarchy, m.vote_lifetime, m.min_votes, Mode(m.start_mode))
        self.tally = DemocracyTally()
        self.round_ends_at: float | None = None
        self.queue: deque[str] = deque(maxlen=cfg.anarchy.max_queue)
        self.planner = Planner(cfg)
        self.ai_on = cfg.ai.enabled  # !mode switches it too
        self.ai_summary = ""
        self.recent: deque[str] = deque(maxlen=cfg.overlay.max_lines)  # the overlay's input lines
        saved = Path(cfg.overlay.ticker_file)  # the last !ticker beats the config default
        self.ticker = saved.read_text(encoding="utf-8").strip() if saved.is_file() else cfg.overlay.ticker
        self.pressing = self.thinking = False
        self._wake = asyncio.Event()  # tells the press worker there's something to press

    @property
    def mode(self) -> Mode:
        return Mode.AI if self.ai_on else self.meter.mode

    def handle(self, msg: ChatMessage, now: float) -> None:
        """One chat message."""
        word, _, rest = msg.text.strip().partition(" ")
        if word.lower() in ("!ticker", "!mode"):  # streamer commands, never game input
            if msg.mod:
                (self.set_ticker if word.lower() == "!ticker" else self.force_mode)(rest, msg.display)
            return
        if self.ai_on:  # all chat goes to the AI
            self.planner.add(msg)
            return
        vote = parse_mode_vote(msg.text)
        if vote is not None:
            changed = self.meter.vote(msg.user, vote, now)
            anarchy, dem = self.meter.counts(now)
            log.info("%s votes %s (democracy %d / anarchy %d, need %d votes to switch)",
                     msg.display, vote.value, dem, anarchy, self.meter.min_votes)
            self.recent.append(f"{msg.display}  {vote.value}")
            if changed:
                self._switch(changed)
        elif self.mode is Mode.ANARCHY:
            command = parse_anarchy(msg.text, self.cfg.allowed_commands)
            if command is not None:
                self.queue.append(command)
                log.info("%s: %s", msg.display, command)
                self.recent.append(f"{msg.display}  {command}")
                self._wake.set()
        else:
            seq = parse_democracy(msg.text, self.cfg.allowed_commands, self.cfg.democracy.max_presses)
            if seq is not None:
                if self.round_ends_at is None:  # the first vote opens the round
                    self.round_ends_at = now + self.cfg.democracy.window_seconds
                self.tally.vote(msg.user, seq)
                log.info("%s votes %s", msg.display, seq)
                self.recent.append(f"{msg.display}  {seq}")

    def tick(self, now: float) -> None:
        """Advance the clocks: vote decay on the meter and the democracy round."""
        if self.ai_on:
            return
        changed = self.meter.update(now)
        if changed:
            self._switch(changed)
        if self.round_ends_at is not None and now >= self.round_ends_at:
            self.round_ends_at = None
            winner = self.tally.close()
            if winner is not None:
                log.info("Democracy chose %s", winner)
                self.queue.extend(winner.presses())  # "wait" adds nothing
                self.recent.append(f">> {winner}")
                self._wake.set()

    def force_mode(self, name: str, by: str = "") -> None:
        """!mode anarchy|democracy|ai from the streamer or a moderator."""
        name = name.strip().lower()
        if name not in ("anarchy", "democracy", "ai"):
            log.info("!mode needs anarchy, democracy or ai, got %r", name)
            return
        problem = unavailable(self.cfg, check_server=False) if name == "ai" else ""
        if problem:
            log.warning("!mode ai ignored: %s", problem)
            return
        mode = Mode(name)
        changed, self.ai_on = mode is not self.mode, mode is Mode.AI
        if not self.ai_on:
            self.meter.force(mode)
        self.planner.buffer.clear()  # the AI only reads chat from after the switch
        log.info("Mode set to %s by %s", name.upper(), by or "the streamer")
        if changed:
            self._switch(mode)

    def set_ticker(self, text: str, by: str = "") -> None:
        """The scrolling message ("" hides it), saved for the next start."""
        self.ticker = " ".join(text.split())[:500]
        log.info("Ticker %s%s", f"set by {by}: " if by else "set: ", self.ticker or "(cleared)")
        path = Path(self.cfg.overlay.ticker_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.ticker, encoding="utf-8")
        except OSError as exc:
            log.warning("Couldn't save the ticker to %s: %s", path, exc)

    def apply_ai(self, summary: str, presses: list[str]) -> None:
        """An AI decision replaces any presses still queued from the last one."""
        self.queue.clear()
        self.queue.extend(presses)
        self.ai_summary = summary
        self.recent.append(f">> {' '.join(presses) or 'wait'}")
        self._wake.set()

    def next_press(self) -> str | None:
        return self.queue.popleft() if self.queue else None

    @property
    def busy(self) -> bool:
        """Work left: presses queued or running, an open round, or chat the AI hasn't answered."""
        return bool(self.queue or self.pressing or self.thinking or self.round_ends_at is not None
                    or (self.ai_on and self.planner.buffer))

    def _switch(self, mode: Mode) -> None:
        log.info("Mode switched to %s", mode.value.upper())
        self.queue.clear()
        self.tally.close()
        self.round_ends_at = None
        self.recent.append(f"*** {mode.value.upper()} ***")

    def overlay_state(self, now: float) -> dict:
        """What the overlay page shows, JSON-ready."""
        return {
            "mode": self.mode.value, "inputs": list(self.recent), "summary": self.ai_summary,
            "share": self.meter.democracy_share(now), "threshold": self.meter.threshold_for_switch(),
            "votes": self.tally.results(), "total_votes": self.tally.total, "ticker": self.ticker,
            "seconds_left": None if self.round_ends_at is None else max(0.0, self.round_ends_at - now),
        }

    async def run(self, chat: AsyncIterable[ChatMessage], backend: Backend) -> None:
        """Read chat, run the clocks, press, and ask the AI while it's on, until chat ends."""
        jobs = [self._read_chat(chat), self._clock(), self._press_worker(backend), self._ai_loop()]
        tasks = [asyncio.create_task(j) for j in jobs]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                t.result()  # surface errors
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _read_chat(self, chat: AsyncIterable[ChatMessage]) -> None:
        async for msg in chat:
            self.handle(msg, time.monotonic())
        while self.busy:  # chat ended (a replayed file): finish what's pending, then stop
            await asyncio.sleep(0.02)

    async def _clock(self) -> None:
        while True:
            now = time.monotonic()
            self.tick(now)
            if self.overlay is not None:
                self.overlay.update(self.overlay_state(now))
            await asyncio.sleep(0.25)

    async def _ai_loop(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:  # a fixed cadence: a slow call shortens the next wait instead of drifting
            deadline = max(deadline + self.cfg.ai.window_seconds, loop.time())
            await asyncio.sleep(deadline - loop.time())
            if self.ai_on and self.planner.buffer:
                self.thinking = True
                decision = await self.planner.decide()
                self.thinking = False
                if decision is not None and self.ai_on:  # a !mode switch may land mid-call
                    self.apply_ai(*decision)

    async def _press_worker(self, backend: Backend) -> None:
        while True:
            command = self.next_press()
            if command is None:
                self._wake.clear()
                await self._wake.wait()
                continue
            log.info("PRESS %s", command)
            self.pressing = True
            await asyncio.to_thread(backend.press, command)
            self.pressing = False
