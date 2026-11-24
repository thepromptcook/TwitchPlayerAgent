"""The Twitch Plays engine: turns chat messages into button presses.

The decision logic (``handle``, ``tick``, ``apply_ai``, ``next_press``) is
synchronous and takes an explicit ``now``, so tests drive it without asyncio
or a game. ``run`` wires it to a chat source and a backend.

All modes feed one queue of presses:
* anarchy appends every valid input (oldest dropped when full),
* democracy appends the winning input when a round closes,
* AI mode replaces the queue with each new decision.
Switching mode clears it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import AsyncIterable

from .backends import Backend
from .chat import ChatMessage
from .commands import parse_anarchy, parse_democracy, parse_mode_vote
from .config import Config
from .llm import Planner
from .modes import DemocracyTally, Mode, ModeMeter
from .overlay import Overlay

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, cfg: Config, overlay: Overlay | None = None) -> None:
        self.cfg = cfg
        m = cfg.meter
        self.meter = ModeMeter(to_democracy=m.to_democracy, to_anarchy=m.to_anarchy,
                               vote_lifetime=m.vote_lifetime, min_votes=m.min_votes,
                               mode=Mode(m.start_mode))
        self.tally = DemocracyTally()
        self.round_ends_at: float | None = None
        self.queue: deque[str] = deque(maxlen=cfg.anarchy.max_queue)
        self.planner = Planner(cfg) if cfg.ai.enabled else None  # AI mode: meter is off
        self.ai_summary = ""
        self.recent: deque[str] = deque(maxlen=cfg.overlay.max_lines)
        self.overlay = overlay
        self.dirty = True
        self._wake: asyncio.Event | None = None

    @property
    def mode(self) -> Mode:
        return Mode.AI if self.planner else self.meter.mode

    # ---- decision logic -------------------------------------------------

    def handle(self, msg: ChatMessage, now: float) -> None:
        """Process one chat message."""
        if self.planner is not None:  # AI mode: all chat goes to the AI
            self.planner.add(msg)
            return

        vote = parse_mode_vote(msg.text)
        if vote is not None:
            changed = self.meter.vote(msg.user, vote, now)
            anarchy, dem = self.meter.counts(now)
            log.info("%s votes %s (democracy %d / anarchy %d, need %d votes to switch)",
                     msg.display, vote.value, dem, anarchy, self.meter.min_votes)
            self._show(f"{msg.display}  {vote.value}")
            if changed:
                self._switch(changed)
            return

        if self.mode is Mode.ANARCHY:
            button = parse_anarchy(msg.text, self.cfg.allowed_buttons)
            if button is None:
                return
            self.queue.append(button)
            log.info("%s: %s", msg.display, button)
            self._show(f"{msg.display}  {button}")
            self._wake_presser()
        else:
            seq = parse_democracy(msg.text, self.cfg.allowed_buttons, self.cfg.democracy.max_presses)
            if seq is None:
                return
            if self.round_ends_at is None:  # the first vote opens the round
                self.round_ends_at = now + self.cfg.democracy.window_seconds
            self.tally.vote(msg.user, seq)
            log.info("%s votes %s", msg.display, seq)
            self._show(f"{msg.display}  {seq}")

    def tick(self, now: float) -> None:
        """Advance timers: vote decay on the meter and the democracy round clock."""
        if self.planner is not None:
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
                self._show(f">> {winner}")
                self._wake_presser()

    def apply_ai(self, summary: str, presses: list[str]) -> None:
        """An AI decision replaces any presses still queued from the last one."""
        self.queue.clear()
        self.queue.extend(presses)
        self.ai_summary = summary
        self._show(f">> {' '.join(presses) or 'wait'}")
        self._wake_presser()

    def next_press(self) -> str | None:
        return self.queue.popleft() if self.queue else None

    @property
    def busy(self) -> bool:
        """Inputs still pending: queued presses, an open round, or unread AI chat."""
        return bool(self.queue or self.round_ends_at is not None
                    or (self.planner is not None and self.planner.buffer))

    def _switch(self, mode: Mode) -> None:
        log.info("Mode switched to %s", mode.value.upper())
        self.queue.clear()
        self.tally.close()
        self.round_ends_at = None
        self._show(f"*** {mode.value.upper()} ***")

    def _show(self, line: str) -> None:
        self.recent.append(line)
        self.dirty = True

    def _wake_presser(self) -> None:
        if self._wake is not None:
            self._wake.set()

    def render_overlay(self, now: float) -> None:
        if self.overlay is None or not self.dirty:
            return
        self.dirty = False
        self.overlay.write(
            inputs=list(self.recent), mode=self.mode.value,
            share=self.meter.democracy_share(now), threshold=self.meter.threshold_for_switch(),
            votes=self.tally.results(), total_votes=self.tally.total,
            seconds_left=None if self.round_ends_at is None else self.round_ends_at - now,
            summary=self.ai_summary,
        )

    # ---- async wiring ---------------------------------------------------

    async def _read_chat(self, chat: AsyncIterable[ChatMessage]) -> None:
        async for msg in chat:
            self.handle(msg, time.monotonic())
        # Chat ended (e.g. a replayed file): finish pending inputs, then stop.
        while self.busy:
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)

    async def _clock(self) -> None:
        while True:
            now = time.monotonic()
            self.tick(now)
            if self.round_ends_at is not None:
                self.dirty = True  # keep the countdown moving
            self.render_overlay(now)
            await asyncio.sleep(0.25)

    async def _ai_loop(self) -> None:
        assert self.planner is not None
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:
            # Fixed cadence: a slow call shortens the next wait instead of drifting.
            deadline = max(deadline + self.cfg.ai.window_seconds, loop.time())
            await asyncio.sleep(deadline - loop.time())
            decision = await self.planner.decide()
            if decision is not None:
                self.apply_ai(*decision)

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
        jobs = [self._read_chat(chat), self._clock(), self._press_worker(backend)]
        if self.planner is not None:
            jobs.append(self._ai_loop())
        tasks = [asyncio.create_task(j) for j in jobs]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                t.result()  # surface errors
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
