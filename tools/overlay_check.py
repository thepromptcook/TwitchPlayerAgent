"""Render the overlay in Chrome and measure it, without a game or OBS.

    python tools/overlay_check.py        # screenshots to overlay-shots/, prints fps, sound, errors
    pytest -m browser                    # the same checks as assertions

Feeds a striped test pattern at 60 fps and a 440 Hz tone in PyBoy's sample format, then
for each layout and mode: screenshot, count distinct frames painted per second, count
audio samples scheduled per second, and collect JavaScript errors.
Needs: pip install playwright, and Chrome (or `playwright install chromium`).
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from twitchplayeragent.overlay import Overlay  # noqa: E402

STATES = {
    "anarchy": {"mode": "anarchy", "share": 0.35, "threshold": 0.8, "votes": [], "total_votes": 0,
                "seconds_left": None, "summary": ""},
    "democracy": {"mode": "democracy", "share": 0.82, "threshold": 0.5, "total_votes": 22, "seconds_left": 13.4,
                  "votes": [["up2left", 12], ["start9", 7], ["a", 3]], "summary": ""},
    "ai": {"mode": "ai", "share": 0, "threshold": 0.8, "votes": [], "total_votes": 0, "seconds_left": None,
           "summary": "Chat wants to heal first, so heading back to the Pokémon Center.",
           "ticker": "Welcome to Twitch Plays! Type up, down, left, right, a or b to play. "
                     "Vote anarchy or democracy to change how inputs are counted."},
}
INPUTS = ["ash  up", "Misty  a", "BrockRocks  start", "*** DEMOCRACY ***", "gary  up2left",
          "oak  democracy", "red  wait", ">> up2left", "someone_with_a_very_long_name  a2b"]


def feed(overlay: Overlay, stop: threading.Event) -> None:
    """60 fps test pattern (frame number in pixel 0) and a 440 Hz tone, values 0..127 like PyBoy."""
    shades = [(15, 56, 15), (48, 98, 48), (139, 172, 15), (155, 188, 15)]
    base = bytearray()
    for y in range(144):
        for x in range(160):
            border = x in (0, 159) or y in (0, 143)
            base += bytes((255, 255, 255, 255) if border else (*shades[((x + y) // 12) % 4], 255))
    n = t = 0
    while not stop.is_set():
        frame = bytearray(base)
        frame[0], frame[1] = n % 256, (n // 256) % 256
        overlay.set_frame(160, 144, bytes(frame))
        tone = bytearray()
        for _ in range(800):
            v = 100 if (t * 440 // 48000) % 2 else 20
            tone += bytes((v, v))
            t += 1
        overlay.add_audio(48000, bytes(tone))
        n += 1
        time.sleep(1 / 60)


def check(out_dir: str | None = "overlay-shots") -> dict:
    """Run every layout and mode; returns {name: {"fps", "audio_per_s", "errors"}}."""
    from playwright.sync_api import sync_playwright

    overlay = Overlay(port=0)
    overlay.start()
    stop = threading.Event()
    threading.Thread(target=feed, args=(overlay, stop), daemon=True).start()
    results = {}
    chrome = shutil.which("google-chrome") or shutil.which("chrome") or shutil.which("chromium")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome, args=[
                "--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
            for layout in ("bar", "sidebar"):
                for mode, state in STATES.items():
                    overlay.update({**state, "inputs": INPUTS})
                    page = browser.new_page(viewport={"width": 1920, "height": 1080})
                    errors: list[str] = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    page.goto(f"http://127.0.0.1:{overlay.port}/?layout={layout}")
                    page.wait_for_timeout(1000)
                    samples0 = page.evaluate("window.audioFramesPlayed || 0")
                    distinct = page.evaluate("""() => new Promise(done => {
                      const c = document.getElementById('game').getContext('2d'), ids = new Set(), t0 = performance.now();
                      (function loop() { const d = c.getImageData(0, 0, 1, 1).data; ids.add(d[0] + 256 * d[1]);
                        if (performance.now() - t0 < 2000) requestAnimationFrame(loop); else done(ids.size); })();
                    })""")
                    samples = page.evaluate("window.audioFramesPlayed || 0") - samples0
                    name = f"{layout}-{mode}"
                    if out_dir:
                        Path(out_dir).mkdir(exist_ok=True)
                        page.screenshot(path=f"{out_dir}/{name}.png")
                    results[name] = {"fps": distinct / 2, "audio_per_s": samples / 2, "errors": errors}
                    page.close()
            browser.close()
    finally:
        stop.set()
        overlay.stop()
    return results


if __name__ == "__main__":
    for name, r in check().items():
        print(f"{name:18} {r['fps']:5.1f} fps  {r['audio_per_s']:7.0f} samples/s  "
              f"{'errors: ' + '; '.join(r['errors']) if r['errors'] else 'no errors'}")
    print("Screenshots in overlay-shots/")
