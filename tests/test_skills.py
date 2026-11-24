"""Keep the Claude skills short, linked and in sync with the code."""

import re
from dataclasses import fields, is_dataclass
from pathlib import Path

from twitchplayeragent.config import Config

ROOT = Path(__file__).parent.parent
SKILLS = ROOT / ".claude" / "skills"
CORE = SKILLS / "twitchplayeragent-core"


def field_names(cls) -> set[str]:
    names = set()
    for f in fields(cls):
        default = getattr(cls(), f.name)
        names |= field_names(type(default)) if is_dataclass(default) else {f.name}
    return names


def test_skills_have_frontmatter_and_stay_short():
    skills = {p.parent.name for p in SKILLS.glob("*/SKILL.md")}
    assert skills >= {"twitchplayeragent-core", "pokemon-red"}
    for path in SKILLS.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if path.name == "SKILL.md":
            assert text.startswith(f"---\nname: {path.parent.name}\ndescription: "), path
        assert len(text.splitlines()) < 200, f"{path} is {len(text.splitlines())} lines"


def test_reference_links_resolve():
    for skill in SKILLS.glob("*/SKILL.md"):
        for link in re.findall(r"\]\((references/[^)]+)\)", skill.read_text(encoding="utf-8")):
            assert (skill.parent / link).is_file(), f"{skill}: broken link {link}"


def test_core_skill_names_every_module_and_config_field():
    text = "\n".join(p.read_text(encoding="utf-8") for p in CORE.rglob("*.md"))
    package = ROOT / "twitchplayeragent"
    modules = [p.name for p in package.glob("*.py") if p.name != "__init__.py"] + ["overlay.html"]
    missing = [m for m in modules if f"`{m}`" not in text]
    missing += [f for f in field_names(Config) if f not in text]
    assert not missing, f"Update {CORE.relative_to(ROOT)}: missing {sorted(missing)}"
