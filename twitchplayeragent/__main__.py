"""Command-line entry point: `python -m twitchplayeragent --config config.toml`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import threading

from .backends import make_backend
from .chat import StdinChat, TwitchIrcChat
from .config import load_config
from .engine import Engine
from .overlay import Overlay

log = logging.getLogger("twitchplayeragent")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="twitchplayeragent", description=__doc__)
    p.add_argument("-c", "--config", help="path to a TOML config (see config.example.toml)")
    p.add_argument("--stdin", action="store_true",
                   help="read chat from the terminal instead of Twitch (lines like `ash: up`)")
    p.add_argument("--dry-run", action="store_true",
                   help="log button presses instead of sending them to a game")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    cfg = load_config(args.config)
    if args.dry_run:
        cfg.backend.type = "log"

    t = cfg.twitch
    chat = StdinChat() if args.stdin else TwitchIrcChat(t.channel, t.nick, t.oauth_token, t.host, t.port)
    backend = make_backend(cfg)
    engine = Engine(cfg, Overlay(cfg.overlay.dir, cfg.overlay.enabled))

    backend.start()
    stop = threading.Event()

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
            backend.run_main_loop(stop)  # returns when the window closes or stop is set
        else:
            run_engine()
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        stop.set()
        backend.stop()


if __name__ == "__main__":
    main()
