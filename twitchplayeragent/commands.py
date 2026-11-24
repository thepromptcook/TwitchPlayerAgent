"""Chat message parsing, following the original Twitch Plays Pokémon (Red) scheme.

Rules mirrored from the 2014 run:

* A message counts only if the *whole* message is a command (case-insensitive,
  surrounding whitespace ignored). "up" works, "go up pls" does not.
* Buttons: a, b, up, down, left, right, start, select. Select was disabled
  during the Red run after it was used to soft-reset, so it is off by default.
  A controller game (e.g. GTA VI) replaces these with the command names in its
  ``[game.commands]`` table; the grammar below is the same for any vocabulary.
* Anarchy mode: a single button name. Every one is executed, in order.
* Democracy mode: compound / sequenced inputs are allowed, e.g. "up2",
  "upleft", "start9", "a2b", plus "wait" (do nothing this round).
* "anarchy" and "democracy" are mode votes that feed the mode meter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from enum import Enum

ALL_BUTTONS: tuple[str, ...] = ("a", "b", "up", "down", "left", "right", "start", "select")
DEFAULT_BUTTONS: frozenset[str] = frozenset(b for b in ALL_BUTTONS if b != "select")

WAIT = "wait"


class ModeVote(Enum):
    ANARCHY = "anarchy"
    DEMOCRACY = "democracy"


@dataclass(frozen=True)
class Sequence:
    """A democracy-mode input: an ordered tuple of (button, repeat_count) steps.

    Adjacent repeats are merged so "upup" and "up2" are the same vote.
    An empty sequence means "wait".
    """

    steps: tuple[tuple[str, int], ...]

    @property
    def is_wait(self) -> bool:
        return not self.steps

    @property
    def total_presses(self) -> int:
        return sum(n for _, n in self.steps)

    def presses(self) -> list[str]:
        """Flatten into the individual button presses to send to the game."""
        return [button for button, n in self.steps for _ in range(n)]

    def __str__(self) -> str:  # canonical text, used as the vote key and on screen
        if self.is_wait:
            return WAIT
        return "".join(b if n == 1 else f"{b}{n}" for b, n in self.steps)


@lru_cache(maxsize=8)
def _token_re(allowed: frozenset[str]) -> re.Pattern:
    # Longest names first, so "goup" is one token rather than "go" + "up".
    names = sorted(allowed, key=len, reverse=True)
    return re.compile(r"(" + "|".join(map(re.escape, names)) + r")([1-9])?")


def normalize(message: str) -> str:
    return message.strip().lower()


def parse_mode_vote(message: str) -> ModeVote | None:
    text = normalize(message)
    try:
        return ModeVote(text)
    except ValueError:
        return None


def parse_anarchy(message: str, allowed: frozenset[str] = DEFAULT_BUTTONS) -> str | None:
    """Return the button for an anarchy-mode message, or None if it isn't one."""
    text = normalize(message)
    return text if text in allowed else None


def parse_democracy(
    message: str,
    allowed: frozenset[str] = DEFAULT_BUTTONS,
    max_presses: int = 9,
) -> Sequence | None:
    """Parse a democracy-mode message into a Sequence, or None if invalid.

    Accepts "wait", a single button, a button with a repeat digit ("up4"),
    or several of those run together ("up2left", "a2b", "start9").
    The total number of presses is capped at ``max_presses``.
    """
    text = normalize(message)
    if not text:
        return None
    if text == WAIT:
        return Sequence(())

    steps: list[tuple[str, int]] = []
    pos = 0
    while pos < len(text):
        m = _token_re(allowed).match(text, pos)
        if m is None:
            return None
        button = m.group(1)
        if button not in allowed:
            return None
        count = int(m.group(2) or 1)
        if steps and steps[-1][0] == button:
            steps[-1] = (button, steps[-1][1] + count)
        else:
            steps.append((button, count))
        pos = m.end()

    seq = Sequence(tuple(steps))
    if seq.total_presses > max_presses:
        return None
    return seq
