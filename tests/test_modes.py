from twitchplayeragent.commands import ModeVote, parse_democracy
from twitchplayeragent.modes import DemocracyTally, Mode, ModeMeter


def meter(**kw):
    kw.setdefault("min_votes", 1)
    return ModeMeter(**kw)


def test_needs_80_percent_to_enter_democracy():
    m = meter(min_votes=10)
    for i in range(7):
        m.vote(f"d{i}", ModeVote.DEMOCRACY, 0)
    for i in range(3):
        m.vote(f"a{i}", ModeVote.ANARCHY, 0)
    assert m.mode is Mode.ANARCHY  # 70% isn't enough
    m.vote("a0", ModeVote.DEMOCRACY, 1)  # now 8/10
    assert m.mode is Mode.DEMOCRACY


def test_needs_only_50_percent_to_return_to_anarchy():
    m = meter(mode=Mode.DEMOCRACY, min_votes=10)
    for i in range(6):
        m.vote(f"d{i}", ModeVote.DEMOCRACY, 0)
    for i in range(4):
        m.vote(f"a{i}", ModeVote.ANARCHY, 0)
    assert m.mode is Mode.DEMOCRACY  # 40% anarchy
    m.vote("d0", ModeVote.ANARCHY, 1)  # 5/10 anarchy
    assert m.mode is Mode.ANARCHY


def test_one_vote_per_user():
    m = meter(min_votes=2)
    for _ in range(10):
        m.vote("spammer", ModeVote.DEMOCRACY, 0)
    assert m.counts(0) == (0, 1)
    assert m.mode is Mode.ANARCHY  # below min_votes


def test_votes_expire_and_democracy_falls_back():
    m = meter(vote_lifetime=60)
    m.vote("x", ModeVote.DEMOCRACY, 0)
    assert m.mode is Mode.DEMOCRACY
    m.vote("y", ModeVote.ANARCHY, 30)  # 1/2 anarchy -> back to anarchy
    assert m.mode is Mode.ANARCHY
    assert m.democracy_share(100) == 0.0  # all expired


def test_tally_majority_wins_and_resets():
    t = DemocracyTally()
    t.vote("a", parse_democracy("up2"))
    t.vote("b", parse_democracy("upup"))  # same vote as up2
    t.vote("c", parse_democracy("left"))
    assert t.results() == [("up2", 2), ("left", 1)]
    assert str(t.close()) == "up2"
    assert t.close() is None


def test_tally_latest_vote_per_user_and_ties():
    t = DemocracyTally()
    t.vote("a", parse_democracy("left"))
    t.vote("b", parse_democracy("right"))
    t.vote("a", parse_democracy("right"))  # a changes their mind
    assert t.results() == [("right", 2)]
    t.vote("c", parse_democracy("b"))
    t.vote("c", parse_democracy("a"))
    t.close()
    t.vote("x", parse_democracy("down"))
    t.vote("y", parse_democracy("up"))
    assert str(t.close()) == "down"  # tie goes to the earlier input
