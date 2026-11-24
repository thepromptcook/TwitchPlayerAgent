"""Twitch chat plays a game, Twitch Plays Pokémon style: python -m twitchplayeragent -c config.toml"""

from __future__ import annotations

import argparse
import asyncio
import logging
import logging.handlers
import queue
import signal
import sys
import threading

from .backends import make_backend
from .chat import StdinChat, TwitchIrcChat
from .config import load_config
from .engine import Engine
from .llm import model_name, unavailable
from .overlay import Overlay

log = logging.getLogger("twitchplayeragent")


def setup_logging(verbose: bool) -> logging.handlers.QueueListener:
    """Log calls only queue the line and a thread prints it, so a stalled terminal can't freeze
    the game loop."""
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    lines: queue.SimpleQueue = queue.SimpleQueue()
    queued = logging.handlers.QueueHandler(lines)
    queued.setFormatter(logging.Formatter("%(message)s"))  # basicConfig's default doubled every prefix
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=[queued])
    listener = logging.handlers.QueueListener(lines, console)
    listener.start()
    return listener


def stop_on_ctrl_c(stop: threading.Event):
    """A SIGINT handler: the first Ctrl+C saves and quits, a second forces. A KeyboardInterrupt
    raised inside PyBoy's compiled frame limiter is swallowed, so PyBoy can't take it itself."""

    def handler(signum, frame) -> None:
        if stop.is_set():
            raise KeyboardInterrupt
        log.info("Ctrl+C: saving and quitting (press again to force)")
        stop.set()

    return handler


def disable_quick_edit() -> None:
    """Windows: a click in a QuickEdit console pauses every program printing to it, which froze
    the game window ("Not Responding"). Turn QuickEdit off for this console."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle, mode = kernel32.GetStdHandle(-10), ctypes.c_uint32()  # STD_INPUT_HANDLE
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS = 0x0040, 0x0080
            kernel32.SetConsoleMode(handle, (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS)
    except Exception:  # not a console (e.g. redirected output): nothing to do
        pass


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="twitchplayeragent", description=__doc__)
    p.add_argument("-c", "--config", action="append", help="TOML config (see config.example.toml); "
                   "repeat it to layer a game on top: -c config.toml -c games/gta6.toml")
    p.add_argument("--stdin", action="store_true", help="read chat from the terminal (lines like `ash: up`)")
    p.add_argument("--dry-run", action="store_true", help="log presses instead of sending them to a game")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    listener = setup_logging(args.verbose)
    disable_quick_edit()
    cfg = load_config(args.config)
    if args.dry_run:
        cfg.backend.type = "log"
    if cfg.ai.enabled:
        problem = unavailable(cfg)
        if problem:
            raise SystemExit(f"AI mode is on in your config, but {problem}")
        log.info("AI mode: %s (%s) reads chat every %gs and picks the presses",
                 model_name(cfg), cfg.ai.provider, cfg.ai.window_seconds)

    chat = StdinChat() if args.stdin else TwitchIrcChat(cfg.twitch.channel)
    backend = make_backend(cfg)
    overlay = None
    if cfg.overlay.enabled:
        overlay = Overlay(cfg.overlay.port, cfg.overlay.audio)
        overlay.start()
        backend.on_frame = overlay.set_frame
        if cfg.overlay.audio:
            backend.on_audio = overlay.add_audio
    engine = Engine(cfg, overlay)
    backend.start()
    stop = threading.Event()
    if args.stdin:
        log.info("Type commands in THIS terminal, e.g. `up` or `ash: a`, then Enter. If a game "
                 "window opens, click back here first; keys typed in the game window are not chat.")

    def run_engine() -> None:
        try:
            asyncio.run(engine.run(chat, backend))
        except Exception:
            log.exception("Engine stopped with an error")
        finally:
            stop.set()

    try:
        if backend.needs_main_thread:  # SDL windows need the main thread, so the engine moves
            threading.Thread(target=run_engine, name="engine", daemon=True).start()
            signal.signal(signal.SIGINT, stop_on_ctrl_c(stop))
            backend.run_main_loop(stop)  # returns when the window closes or stop is set
        else:
            run_engine()
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        stop.set()
        backend.stop()
        if overlay is not None:
            overlay.stop()
        listener.stop()  # flush the remaining log lines


if __name__ == "__main__":
    main()
