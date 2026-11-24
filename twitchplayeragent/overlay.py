"""Stream overlay written as plain text files, for OBS "Text (GDI+/FreeType)"
sources with "Read from file" enabled.

Files (in [overlay].dir):
  inputs.txt     - scrolling list of recent "user  input" lines (newest at the bottom)
  mode.txt       - current mode and the anarchy/democracy bar
  democracy.txt  - live vote counts and countdown (blank in anarchy mode)
"""

from __future__ import annotations

import os
from pathlib import Path


def render_bar(share: float, threshold: float, width: int = 30) -> str:
    """ASCII anarchy/democracy bar. '#' is the democracy share, '|' is the
    dotted line the inactive mode has to reach."""
    share = min(max(share, 0.0), 1.0)
    filled = round(share * width)
    mark = min(width - 1, round(threshold * width))
    cells = ["#" if i < filled else "-" for i in range(width)]
    cells[mark] = "|"
    return "ANARCHY [" + "".join(cells) + "] DEMOCRACY"


class Overlay:
    def __init__(self, directory: str | os.PathLike, enabled: bool = True) -> None:
        self.dir = Path(directory)
        self.enabled = enabled
        if enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def _write(self, name: str, text: str) -> None:
        if not self.enabled:
            return
        path = self.dir / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # atomic, so OBS never reads a half-written file

    def write(self, *, inputs: list[str], mode: str, share: float, threshold: float,
              votes: list[tuple[str, int]], total_votes: int, seconds_left: float | None,
              summary: str = "") -> None:
        self._write("inputs.txt", "\n".join(inputs) + ("\n" if inputs else ""))
        if mode == "claude":  # no meter in Claude mode: show what Claude is doing
            self._write("mode.txt", f"CLAUDE\n{summary}\n")
        else:
            self._write("mode.txt", f"{mode.upper()}\n{render_bar(share, threshold)}\n")
        if mode == "democracy":
            lines = []
            if seconds_left is not None:
                lines.append(f"Next input in {max(0, int(seconds_left + 0.999))}s")
            else:
                lines.append("Waiting for votes")
            for key, n in votes[:5]:
                pct = 100 * n / total_votes if total_votes else 0
                lines.append(f"{key:<12} {n:>4}  {pct:3.0f}%")
            self._write("democracy.txt", "\n".join(lines) + "\n")
        else:
            self._write("democracy.txt", "")
