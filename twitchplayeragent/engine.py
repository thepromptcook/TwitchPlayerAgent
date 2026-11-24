"""The Twitch Plays engine: turns chat messages into button presses.

The decision logic (``handle``, ``tick``, ``next_press``) is synchronous and
takes an explicit ``now`` so it can be unit-tested without asyncio or a game.
``run`` wires it to a chat source and a backend.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import AsyncIterable

from .backends.base import Backend
from .chat import ChatMessage
from .commands import parse_anarchy, parse_democracy, parse_mode_vote
from .config import Config
from .modes import DemocracyTally, Mode, ModeMeter
from .overlay import Overlay

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, cfg: Config, overlay: Overlay | None = None) -> None:
        self.cfg = cfg
        self.allowed = cfg.allowed_buttons
        m = cfg.meter
        self.meter = ModeMeter(
            to_democracy=m.to_democracy, to_anarchy=m.to_anarchy,
            vote_lifetime=m.vote_lifetime, min_votes=m.min_votes,
            mode=Mode(m.start_mode),
        )
        self.tally = DemocracyTally()
        self.round_ends_at: float | None = None
        self.anarchy_queue: deque[str] = deque(maxlen=cfg.anarchy.max_queue)
        self.democracy_queue: deque[str] = deque()
        self.recent: deque[str] = deque(maxlen=cfg.overlay.max_lines)
        self.overlay = overlay
        self.dirty = True
        self._wake: asyncio.Event | None = None

    @property
    def mode(self) -> Mode:
        return self.meter.mode

    # ---- decision logic -------------------------------------------------

    def handle(self, msg: ChatMessage, now: float) -> None:
        """Process one chat message."""
        vote = parse_mode_vote(msg.text)
        if vote is not None:
            self.recent.append(f"{msg.display}  {vote.value}")
            self.dirty = True
            changed = self.meter.vote(msg.user, vote, now)
            anarchy, dem = self.meter.counts(now)
            log.info("%s votes %s (democracy %d / anarchy %d, need %d votes to switch)",
                     msg.display, vote.value, dem, anarchy, self.meter.min_votes)
            if changed:
                self._on_mode_change(changed, now)
            return

        if self.mode is Mode.ANARCHY:
            button = parse_anarchy(msg.text, self.allowed)
            if button is None:
                return
            self.anarchy_queue.append(button)  # oldest dropped if full
            self.recent.append(f"{msg.display}  {button}")
            log.info("%s: %s", msg.display, button)
        else:
            seq = parse_democracy(msg.text, self.allowed, self.cfg.democracy.max_presses)
            if seq is None:
                return
            if self.round_ends_at is None:  # first vote opens the round
                self.round_ends_at = now + self.cfg.democracy.window_seconds
            self.tally.vote(msg.user, seq)
            self.recent.append(f"{msg.display}  {seq}")
            log.info("%s votes %s", msg.display, seq)
        self.dirty = True
        self._notify()

    def tick(self, now: float) -> None:
        """Advance timers: vote decay on the meter and the democracy round clock."""
        changed = self.meter.update(now)
        if changed:
            self._on_mode_change(changed, now)
        if self.mode is Mode.DEMOCRACY and self.round_ends_at is not None and now >= self.round_ends_at:
            self.round_ends_at = None
            winner = self.tally.close()
            if winner is not None:
                log.info("Democracy chose %s", winner)
                self.recent.append(f">> {winner}")
                self.democracy_queue.extend(winner.presses())  # "wait" adds nothing
                self._notify()
            self.dirty = True

    def next_press(self) -> str | None:
        """The next button to send to the game, if any."""
        q = self.anarchy_queue if self.mode is Mode.ANARCHY else self.democracy_queue
        return q.popleft() if q else None

    def _on_mode_change(self, mode: Mode, now: float) -> None:
        log.info("Mode switched to %s", mode.value.upper())
        self.recent.append(f"*** {mode.value.upper()} ***")
        self.anarchy_queue.clear()
        self.democracy_queue.clear()
        self.tally.close()
        self.round_ends_at = None
        self.dirty = True

    # ---- async wiring ---------------------------------------------------

    def _notify(self) -> None:
        if self._wake is not None:
            self._wake.set()

    def render_overlay(self, now: float) -> None:
        if self.overlay is None or not self.dirty:
            return
        self.dirty = False
        self.overlay.write(
            inputs=list(self.recent),
            mode=self.mode.value,
            share=self.meter.democracy_share(now),
            threshold=self.meter.threshold_for_switch(),
            votes=self.tally.results(),
            total_votes=self.tally.total,
            seconds_left=None if self.round_ends_at is None else self.round_ends_at - now,
        )

    async def _read_chat(self, chat: AsyncIterable[ChatMessage]) -> None:
        async for msg in chat:
            self.handle(msg, time.monotonic())
        # Chat ended (e.g. end of piped stdin): let queued inputs and any open
        # democracy round finish before shutting down.
        while self.anarchy_queue or self.democracy_queue or self.round_ends_at is not None:
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)

    async def _clock(self) -> None:
        while True:
            now = time.monotonic()
            self.tick(now)
            if self.mode is Mode.DEMOCRACY and self.round_ends_at is not None:
                self.dirty = True  # keep the countdown moving
            self.render_overlay(now)
            await asyncio.sleep(0.25)

    async def _press_worker(self, backend: Backend) -> None:
        assert self._wake is not None
        while True:
            button = self.next_press()
            if button is None:
                self._wake.clear()
                await self._wake.wait()
                continue
            log.info("PRESS %s", button)
            await asyncio.to_thread(backend.press, button)

    async def run(self, chat: AsyncIterable[ChatMessage], backend: Backend) -> None:
        self._wake = asyncio.Event()
        tasks = [
            asyncio.create_task(self._read_chat(chat), name="chat"),
            asyncio.create_task(self._clock(), name="clock"),
            asyncio.create_task(self._press_worker(backend), name="presses"),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                t.result()  # surface errors
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
