"""Shared test helpers. Import them with `from conftest import make_cfg, msg, drain`."""

from twitchplayeragent.chat import ChatMessage
from twitchplayeragent.config import Config


def msg(user: str, text: str) -> ChatMessage:
    return ChatMessage(user, user, text)


def make_cfg(**sections) -> Config:
    """Config with overrides per section, e.g. make_cfg(meter={"min_votes": 1})."""
    cfg = Config()
    for section, values in sections.items():
        for key, value in values.items():
            setattr(getattr(cfg, section), key, value)
    cfg.validate()
    return cfg


def drain(engine) -> list[str]:
    """Every press the engine has queued, in order."""
    out = []
    while (b := engine.next_press()) is not None:
        out.append(b)
    return out
