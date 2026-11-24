"""Command-line entry point: `python -m twitchplayeragent --config config.toml`."""

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
    """Log calls only queue the line; a background thread prints it. A terminal that
    stops accepting output (see below) then can't freeze the game loop."""
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    lines: queue.SimpleQueue = queue.SimpleQueue()
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        handlers=[logging.handlers.QueueHandler(lines)])
    listener = logging.handlers.QueueListener(lines, console)
    listener.start()
    return listener


def stop_on_ctrl_c(stop: threading.Event):
    """A SIGINT handler: the first Ctrl+C asks the game loop to save and quit; a second
    one forces it. Needed because a KeyboardInterrupt that lands inside PyBoy's frame
    limiter (compiled code) is printed as "Exception ignored" and swallowed."""

    def handler(signum, frame) -> None:
        if stop.is_set():
            raise KeyboardInterrupt
        log.info("Ctrl+C: saving and quitting (press again to force)")
        stop.set()

    return handler


def disable_quick_edit() -> None:
    """Windows: clicking in a terminal with QuickEdit on starts a text selection that
    pauses every program printing to it until a key is pressed, which froze the
    game window ("Not Responding"). Turn QuickEdit off for this terminal."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS = 0x0040, 0x0080
            kernel32.SetConsoleMode(handle, (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS)
    except Exception:  # not a console (e.g. redirected output): nothing to do
        pass


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="twitchplayeragent", description=__doc__)
    p.add_argument("-c", "--config", help="path to a TOML config (see config.example.toml)")
    p.add_argument("--stdin", action="store_true",
                   help="read chat from the terminal instead of Twitch (lines like `ash: up`)")
    p.add_argument("--dry-run", action="store_true",
                   help="log button presses instead of sending them to a game")
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
        log.info("Type commands in THIS terminal, e.g. `up` or `ash: a`, then Enter. "
                 "If a game window opens, click back here first; keys typed in "
                 "the game window are not chat.")

    def run_engine() -> None:
        try:
            asyncio.run(engine.run(chat, backend))
        except Exception:
            log.exception("Engine stopped with an error")
        finally:
            stop.set()

    try:
        if backend.needs_main_thread:
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
        listener.stop()  # flush remaining log lines


if __name__ == "__main__":
    main()
