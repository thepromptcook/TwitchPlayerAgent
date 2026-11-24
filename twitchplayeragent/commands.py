"""Chat text -> commands, with the original Twitch Plays Pokémon grammar: a message counts only if
the whole message (trimmed, any case) is a command, and democracy also takes compound inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

ALL_BUTTONS = ("a", "b", "up", "down", "left", "right", "start", "select")
DEFAULT_BUTTONS = frozenset(ALL_BUTTONS) - {"select"}  # select was disabled during the Red run
WAIT = "wait"


class ModeVote(Enum):
    ANARCHY = "anarchy"
    DEMOCRACY = "democracy"


@dataclass(frozen=True)
class Sequence:
    """A democracy input: (command, count) steps, adjacent repeats merged so "upup" is "up2".
    No steps means "wait"."""

    steps: tuple[tuple[str, int], ...]

    def presses(self) -> list[str]:
        return [command for command, n in self.steps for _ in range(n)]

    def __str__(self) -> str:  # canonical text: the vote key and what the overlay shows
        return "".join(c if n == 1 else f"{c}{n}" for c, n in self.steps) or WAIT


@lru_cache(maxsize=8)
def _token_re(allowed: frozenset[str]) -> re.Pattern:
    names = sorted(allowed, key=len, reverse=True)  # longest first: "goup" isn't "go" + "up"
    return re.compile("(" + "|".join(map(re.escape, names)) + ")([1-9])?")


def parse_mode_vote(message: str) -> ModeVote | None:
    try:
        return ModeVote(message.strip().lower())
    except ValueError:
        return None


def parse_anarchy(message: str, allowed: frozenset[str] = DEFAULT_BUTTONS) -> str | None:
    """The command, or None if the message isn't exactly one."""
    text = message.strip().lower()
    return text if text in allowed else None


def parse_democracy(message: str, allowed: frozenset[str] = DEFAULT_BUTTONS, max_presses: int = 9) -> Sequence | None:
    """ "wait", or commands each with an optional repeat digit, run together ("up4", "upleft",
    "a2b", "start9"), at most max_presses in total. None if the message isn't one."""
    text = message.strip().lower()
    if text == WAIT:
        return Sequence(())
    steps: list[tuple[str, int]] = []
    pos = 0
    while pos < len(text):
        m = _token_re(allowed).match(text, pos)
        if m is None or not m.group(1):
            return None
        command, count = m.group(1), int(m.group(2) or 1)
        if steps and steps[-1][0] == command:
            steps[-1] = (command, steps[-1][1] + count)
        else:
            steps.append((command, count))
        pos = m.end()
    if not steps or sum(n for _, n in steps) > max_presses:
        return None
    return Sequence(tuple(steps))
