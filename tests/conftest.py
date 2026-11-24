"""Shared test helpers: `from conftest import drain, gta_cfg, make_cfg, msg`."""

from twitchplayeragent.chat import ChatMessage
from twitchplayeragent.config import Config, load_config


def msg(user: str, text: str, mod: bool = False) -> ChatMessage:
    return ChatMessage(user, user, text, mod)


def make_cfg(**sections) -> Config:
    """Defaults with overrides per section, e.g. make_cfg(meter={"min_votes": 1})."""
    cfg = Config()
    for section, values in sections.items():
        for key, value in values.items():
            setattr(getattr(cfg, section), key, value)
    cfg.validate()
    return cfg


def gta_cfg() -> Config:
    return load_config(["config.example.toml", "games/gta6.toml"])


def drain(engine) -> list[str]:
    """Every press the engine has queued, in order."""
    return list(iter(engine.next_press, None))
