import pytest

from twitchplayeragent.commands import (
    ALL_BUTTONS,
    DEFAULT_BUTTONS,
    ModeVote,
    parse_anarchy,
    parse_democracy,
    parse_mode_vote,
)


@pytest.mark.parametrize("msg,expected", [
    ("up", "up"), ("A", "a"), ("  Start ", "start"), ("left", "left"),
    ("select", None),  # disabled by default, as in the Red run
    ("up2", None),  # compound inputs are democracy-only
    ("go up", None), ("upp", None), ("", None), ("anarchy", None),
])
def test_anarchy(msg, expected):
    assert parse_anarchy(msg) == expected


def test_select_can_be_enabled():
    assert parse_anarchy("select", frozenset(ALL_BUTTONS)) == "select"
    assert "select" not in DEFAULT_BUTTONS


@pytest.mark.parametrize("msg,canonical,presses", [
    ("up", "up", ["up"]),
    ("up4", "up4", ["up"] * 4),
    ("upleft", "upleft", ["up", "left"]),
    ("start9", "start9", ["start"] * 9),
    ("a2b", "a2b", ["a", "a", "b"]),
    ("upup", "up2", ["up", "up"]),  # merged so it counts with "up2"
    ("UP2Left3", "up2left3", ["up", "up", "left", "left", "left"]),
    ("wait", "wait", []),
])
def test_democracy_valid(msg, canonical, presses):
    seq = parse_democracy(msg)
    assert seq is not None
    assert str(seq) == canonical
    assert seq.presses() == presses


@pytest.mark.parametrize("msg", [
    "up0", "up10", "start5start5", "select", "upx", "2up", "", "a+b", "wait2",
])
def test_democracy_invalid(msg):
    assert parse_democracy(msg) is None


def test_mode_votes():
    assert parse_mode_vote("Democracy") is ModeVote.DEMOCRACY
    assert parse_mode_vote(" anarchy ") is ModeVote.ANARCHY
    assert parse_mode_vote("vote democracy") is None
