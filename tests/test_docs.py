"""The docs stay true: skills short, linked and naming every module; config.example.toml shows
every field at its default; every game file loads and has a skill."""

import re
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from twitchplayeragent.config import Config, load_config

ROOT = Path(__file__).parent.parent
SKILLS = ROOT / ".claude" / "skills"


def field_names(obj) -> set[str]:
    names = set()
    for f in fields(obj):
        value = getattr(obj, f.name)
        names |= field_names(value) if is_dataclass(value) else {f.name}
    return names


def test_skills_have_frontmatter_stay_short_and_link_correctly():
    assert {p.parent.name for p in SKILLS.glob("*/SKILL.md")} >= {"twitchplayeragent-core", "pokemon-red", "gta6-xbox"}
    for path in SKILLS.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if path.name == "SKILL.md":
            assert text.startswith(f"---\nname: {path.parent.name}\ndescription: "), path
        assert len(text.splitlines()) < 200, f"{path} is {len(text.splitlines())} lines"
        for link in re.findall(r"\]\((references/[^)]+)\)", text):
            assert (path.parent / link).is_file(), f"{path}: broken link {link}"


def test_core_skill_names_every_module():
    text = "\n".join(p.read_text(encoding="utf-8") for p in (SKILLS / "twitchplayeragent-core").rglob("*.md"))
    modules = [p.name for p in (ROOT / "twitchplayeragent").glob("*.py") if p.name != "__init__.py"]
    missing = [m for m in modules + ["overlay.html"] if f"`{m}`" not in text]
    assert not missing, f"Add {missing} to .claude/skills/twitchplayeragent-core"


def test_example_config_shows_every_field_at_its_default():
    text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
    missing = [f for f in field_names(Config()) if not re.search(rf"^#? ?{f} =|\.{f}\]", text, re.M)]
    assert not missing, f"Document {sorted(missing)} in config.example.toml"
    cfg = load_config(ROOT / "config.example.toml")
    cfg.twitch.channel = ""  # the one placeholder
    assert cfg == Config(), "config.example.toml and the defaults in config.py differ"


@pytest.mark.parametrize("game", sorted((ROOT / "games").glob("*.toml")), ids=lambda p: p.stem)
def test_every_game_loads_and_has_a_skill(game):
    load_config([ROOT / "config.example.toml", game])
    skills = "\n".join(p.read_text(encoding="utf-8") for p in SKILLS.glob("*/SKILL.md"))
    assert f"games/{game.name}" in skills, f"Add a skill for {game.name}"
