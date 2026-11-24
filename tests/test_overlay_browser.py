"""Opt-in: pytest -m browser. Renders the overlay in Chrome (see tools/overlay_check.py)."""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser
pytest.importorskip("playwright")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def test_overlay_renders_smoothly_with_sound():
    from overlay_check import check

    for name, r in check(out_dir=None).items():
        assert not r["errors"], (name, r["errors"])
        assert r["fps"] >= 50, (name, r["fps"])  # the game makes 60
        assert r["audio_per_s"] >= 40_000, (name, r["audio_per_s"])  # 48 kHz tone
