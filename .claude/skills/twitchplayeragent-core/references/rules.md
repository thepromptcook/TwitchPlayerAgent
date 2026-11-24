# Rules: chat grammar, modes, engine

## Grammar (`commands.py`)
- A message counts only if the **whole message**, trimmed and lowercased, is a command.
- The vocabulary is `Config.allowed_commands` (parser and AI schema alike): `[game].buttons` from
  `ALL_BUTTONS` (a b up down left right start select; `DEFAULT_BUTTONS` leaves out select), or a
  controller game's `[game.commands]` names (lowercase letters, never `wait`/`anarchy`/`democracy`).
- `parse_anarchy`: one command. `parse_mode_vote`: `anarchy` / `democracy`, in any mode.
- `parse_democracy`: `wait`, or commands with an optional repeat digit 1–9 run together: `up4`,
  `upleft`, `up2left3`, `start9`, `a2b`. Tokens match longest name first (`_token_re`, cached per
  vocabulary: `goup` isn't `go` + `up`); adjacent repeats merge (`upup` is `up2`, and
  `str(Sequence)` is the vote key). Rejected: over `max_presses` (9) in total, unknown tokens,
  `up0`, `up10`, `a+b`, `wait2`.

## Modes (`modes.py`)
- `ModeMeter`: each user's latest vote lives `vote_lifetime` (60 s). Anarchy → democracy at a
  democracy share ≥ `to_democracy` (0.80), back at an anarchy share ≥ `to_anarchy` (0.50), never on
  fewer than `min_votes` (5). An idle bar reads 0 % democracy. `threshold_for_switch()` places the
  bar's marker; `force(mode)` (for `!mode`) switches and forgets the votes.
- `DemocracyTally`: one vote per user per round (a later message replaces it), ties to the input
  voted first, `close()` returns the winner and resets.

## Engine (`engine.py`)
One `deque` of presses, `maxlen = [anarchy].max_queue` (oldest dropped):
- anarchy appends every valid command;
- democracy: the first vote opens a `window_seconds` round; `tick` closes it and appends the
  winner's presses (`wait` adds none);
- AI (`ai_on`, shown as `Mode.AI`, never set by the meter): every message goes to the `Planner`
  and each decision **replaces** the queue (`apply_ai`); mode votes are ordinary chat;
- a mode switch clears the queue, tally and round.

Streamer commands (first word, any case) are never game input and need `ChatMessage.mod` (the
`mod` tag or a `broadcaster/` badge; terminal chat counts):
- `!mode anarchy|democracy|ai` (`force_mode`): `ai` first checks `unavailable(cfg,
  check_server=False)`, so chat never waits on the network, and stays put with a logged reason;
  any switch clears the AI's unread chat.
- `!ticker <text>` (`set_ticker`): spaces normalized, ≤ 500 characters, saved to `ticker_file`,
  which beats `[overlay].ticker` at the next start even when empty; `!ticker` alone clears.

`recent` holds the overlay's lines (`user  input`, `>> winner`, `*** MODE ***`) and
`overlay_state(now)` is the page's JSON. `run(chat, backend)` runs the chat reader, a 0.25 s clock
(tick + overlay state), the press worker (`asyncio.to_thread(backend.press)`, woken by an Event)
and the AI loop (fixed cadence; calls only while `ai_on` and chat arrived). When chat ends (a
replayed file) it waits while `busy` (presses queued or running, an open round, an AI call or
unread chat), then returns. It logs `user: command`, votes with live counts, `Democracy chose X`
and `PRESS X`: the owner relies on these to see input working.
