from __future__ import annotations

import logging
import time

from .base import Backend

log = logging.getLogger(__name__)


class LogBackend(Backend):
    """Dry-run backend: logs each press instead of sending it anywhere."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.pressed: list[str] = []

    def press(self, button: str) -> None:
        self.pressed.append(button)
        log.info("PRESS %s", button)
        if self.delay:
            time.sleep(self.delay)
