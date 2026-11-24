"""Anarchy/democracy logic: the mode meter and the democracy vote tally."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum

from .commands import ModeVote, Sequence


class Mode(Enum):
    ANARCHY = "anarchy"
    DEMOCRACY = "democracy"
    AI = "ai"  # set by [ai].enabled, never by the meter


@dataclass
class ModeMeter:
    """The anarchy/democracy bar.

    Each user's most recent "anarchy"/"democracy" message counts as their vote
    until it is ``vote_lifetime`` seconds old. Like the original run, the bar
    is asymmetric: switching *to* democracy needs ``to_democracy`` (80%) of
    live votes, switching *back* to anarchy needs only ``to_anarchy`` (50%).
    ``min_votes`` stops one or two people flipping the mode on a quiet stream.
    """

    to_democracy: float = 0.80
    to_anarchy: float = 0.50
    vote_lifetime: float = 60.0
    min_votes: int = 5
    mode: Mode = Mode.ANARCHY
    _votes: dict[str, tuple[ModeVote, float]] = field(default_factory=dict)

    def vote(self, user: str, choice: ModeVote, now: float) -> Mode | None:
        """Record a vote; return the new mode if this vote flipped it."""
        self._votes[user] = (choice, now)
        return self.update(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.vote_lifetime
        stale = [u for u, (_, t) in self._votes.items() if t < cutoff]
        for u in stale:
            del self._votes[u]

    def counts(self, now: float) -> tuple[int, int]:
        """(anarchy_votes, democracy_votes) currently live."""
        self._prune(now)
        dem = sum(1 for v, _ in self._votes.values() if v is ModeVote.DEMOCRACY)
        return len(self._votes) - dem, dem

    def democracy_share(self, now: float) -> float:
        """Fraction of live votes for democracy (0.0-1.0). 0.0 when nobody voted
        recently, so an idle bar drifts back to anarchy, the default mode."""
        anarchy, dem = self.counts(now)
        total = anarchy + dem
        return dem / total if total else 0.0

    def update(self, now: float) -> Mode | None:
        """Re-evaluate thresholds; return the new mode if it changed."""
        anarchy, dem = self.counts(now)
        total = anarchy + dem
        if total < self.min_votes:
            return None
        if self.mode is Mode.ANARCHY and dem / total >= self.to_democracy:
            self.mode = Mode.DEMOCRACY
            return self.mode
        if self.mode is Mode.DEMOCRACY and anarchy / total >= self.to_anarchy:
            self.mode = Mode.ANARCHY
            return self.mode
        return None

    def threshold_for_switch(self) -> float:
        """Where the dotted line sits on the bar, as a democracy share."""
        if self.mode is Mode.ANARCHY:
            return self.to_democracy
        return 1.0 - self.to_anarchy


@dataclass
class DemocracyTally:
    """Votes for one democracy round. One vote per user; a later message from
    the same user replaces their earlier one. Ties go to the input that was
    voted for first."""

    _by_user: dict[str, str] = field(default_factory=dict)
    _sequences: "OrderedDict[str, Sequence]" = field(default_factory=OrderedDict)

    def vote(self, user: str, seq: Sequence) -> None:
        key = str(seq)
        self._sequences.setdefault(key, seq)
        self._by_user[user] = key

    def results(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {k: 0 for k in self._sequences}
        for key in self._by_user.values():
            counts[key] += 1
        order = {k: i for i, k in enumerate(self._sequences)}
        ranked = [(k, n) for k, n in counts.items() if n > 0]
        ranked.sort(key=lambda kv: (-kv[1], order[kv[0]]))
        return ranked

    @property
    def total(self) -> int:
        return len(self._by_user)

    def close(self) -> Sequence | None:
        """End the round: return the winning Sequence (None if no votes) and reset."""
        ranked = self.results()
        winner = self._sequences[ranked[0][0]] if ranked else None
        self._by_user.clear()
        self._sequences.clear()
        return winner
