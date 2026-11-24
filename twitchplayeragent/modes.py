"""The anarchy/democracy meter and the democracy vote tally."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from .commands import ModeVote, Sequence


class Mode(Enum):
    ANARCHY = "anarchy"
    DEMOCRACY = "democracy"
    AI = "ai"  # Engine.ai_on, never set by the meter


@dataclass
class ModeMeter:
    """The bar. Each user's latest vote counts for vote_lifetime seconds. Like the original it's
    asymmetric: entering democracy takes to_democracy (80 %) of live votes, leaving it only
    to_anarchy (50 %), and nothing switches on fewer than min_votes."""

    to_democracy: float = 0.80
    to_anarchy: float = 0.50
    vote_lifetime: float = 60.0
    min_votes: int = 5
    mode: Mode = Mode.ANARCHY
    _votes: dict[str, tuple[ModeVote, float]] = field(default_factory=dict)

    def vote(self, user: str, choice: ModeVote, now: float) -> Mode | None:
        """Record a vote; the new mode if it flipped the bar."""
        self._votes[user] = (choice, now)
        return self.update(now)

    def force(self, mode: Mode) -> None:
        """!mode: switch now and forget the votes, so the bar doesn't flip straight back."""
        self._votes.clear()
        self.mode = mode

    def counts(self, now: float) -> tuple[int, int]:
        """(anarchy, democracy) live votes."""
        self._votes = {u: v for u, v in self._votes.items() if v[1] >= now - self.vote_lifetime}
        dem = sum(choice is ModeVote.DEMOCRACY for choice, _ in self._votes.values())
        return len(self._votes) - dem, dem

    def democracy_share(self, now: float) -> float:
        """0.0-1.0, and 0.0 with no live votes, so an idle bar drifts back to anarchy."""
        anarchy, dem = self.counts(now)
        return dem / (anarchy + dem) if anarchy + dem else 0.0

    def update(self, now: float) -> Mode | None:
        """Re-check the thresholds; the new mode if it changed."""
        anarchy, dem = self.counts(now)
        total = anarchy + dem
        if total < max(1, self.min_votes):
            return None
        if self.mode is Mode.ANARCHY and dem / total >= self.to_democracy:
            self.mode = Mode.DEMOCRACY
        elif self.mode is Mode.DEMOCRACY and anarchy / total >= self.to_anarchy:
            self.mode = Mode.ANARCHY
        else:
            return None
        return self.mode

    def threshold_for_switch(self) -> float:
        """Where the bar's marker sits, as a democracy share."""
        return self.to_democracy if self.mode is Mode.ANARCHY else 1.0 - self.to_anarchy


@dataclass
class DemocracyTally:
    """One round's votes: one per user (a later message replaces it); ties go to the input that
    was voted for first."""

    _by_user: dict[str, str] = field(default_factory=dict)
    _sequences: dict[str, Sequence] = field(default_factory=dict)  # in order of first vote

    def vote(self, user: str, seq: Sequence) -> None:
        self._sequences.setdefault(str(seq), seq)
        self._by_user[user] = str(seq)

    def results(self) -> list[tuple[str, int]]:
        """(input, votes), most first."""
        counts = Counter(self._by_user.values())
        return sorted(((k, counts[k]) for k in self._sequences if counts[k]), key=lambda kv: -kv[1])

    @property
    def total(self) -> int:
        return len(self._by_user)

    def close(self) -> Sequence | None:
        """End the round: the winner (None without votes), then reset."""
        ranked = self.results()
        winner = self._sequences[ranked[0][0]] if ranked else None
        self._by_user.clear()
        self._sequences.clear()
        return winner
