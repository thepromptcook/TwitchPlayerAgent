"""Keep the Claude skills short and in sync with the code."""

from dataclasses import fields, is_dataclass
from pathlib import Path

from twitchplayeragent.config import Config

ROOT = Path(__file__).parent.parent
SKILLS = ROOT / ".claude" / "skills"
CORE = SKILLS / "twitchplayeragent-core" / "SKILL.md"


def all_field_names(cls) -> set[str]:
    names = set()
    for f in fields(cls):
        default = cls().__getattribute__(f.name)
        if is_dataclass(default):
            names |= all_field_names(type(default))
        else:
            names.add(f.name)
    return names


def test_skills_have_frontmatter_and_stay_under_200_lines():
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    assert {p.parent.name for p in skills} >= {"twitchplayeragent-core", "pokemon-red"}
    for path in skills:
        text = path.read_text(encoding="utf-8")
        assert text.startswith(f"---\nname: {path.parent.name}\ndescription: "), path
        assert len(text.splitlines()) < 200, f"{path} is {len(text.splitlines())} lines"


def test_core_skill_names_every_module_and_config_field():
    text = CORE.read_text(encoding="utf-8")
    modules = [p.name for p in (ROOT / "twitchplayeragent").glob("*.py") if p.name != "__init__.py"]
    missing = [m for m in modules if f"`{m}`" not in text]
    missing += [f for f in all_field_names(Config) if f not in text]
    assert not missing, f"Update {CORE.relative_to(ROOT)}: missing {sorted(missing)}"
