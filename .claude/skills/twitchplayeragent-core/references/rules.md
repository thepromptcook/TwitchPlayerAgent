# Rules: chat grammar, modes, engine

## Chat grammar (`commands.py`)
- A message counts only if the **whole message**, trimmed and lowercased, is a command.
- Buttons: a, b, up, down, left, right, start, select (`ALL_BUTTONS`); `[game].buttons` picks
  the allowed ones (`DEFAULT_BUTTONS` leaves out select).
- `parse_anarchy`: one button name.
- `parse_democracy`: `wait`, or button tokens with an optional repeat digit 1–9 run together:
  `up4`, `upleft`, `up2left3`, `start9`, `a2b`. Tokenize longest name first; merge adjacent
  repeats so `upup` == `up2` (canonical `str(Sequence)` is the vote key). Reject totals over
  `max_presses` (9), unknown tokens, `up0`, `up10`, `a+b`, `wait2`.
- `parse_mode_vote`: `anarchy` / `democracy`, in either mode.

## Modes (`modes.py`)
- `ModeMeter`: each user's latest mode vote lives `vote_lifetime` (60 s). Anarchy → democracy at
  democracy share ≥ `to_democracy` (0.80); back at anarchy share ≥ `to_anarchy` (0.50).
  Nothing switches below `min_votes` (5). An idle bar reads 0 % democracy.
  `threshold_for_switch()` is where the bar's marker sits.
- `DemocracyTally`: one vote per user per round, a later message replaces an earlier one; ties go
  to the input voted first; `close()` returns the winner and resets.
- `Mode.AI` is set by `[ai].enabled`, never by the meter.

## Engine (`engine.py`)
One `deque` of presses, `maxlen = [anarchy].max_queue` (oldest dropped):
- anarchy: append every valid button;
- democracy: the first vote opens a `window_seconds` round; `tick` closes it and appends the
  winner's presses (`wait` adds none);
- AI: every message goes to the `Planner`; `apply_ai` **replaces** the queue; the meter is off
  and mode votes are ordinary chat.
- A mode switch clears queue, tally and round.
- `recent` holds overlay lines (`user  input`, `>> winner`, `*** MODE ***`);
  `overlay_state(now)` is the JSON the page shows; `busy` means work is pending.
- `run(chat, backend)`: chat reader, 0.25 s clock (tick + overlay state), press worker
  (`asyncio.to_thread(backend.press)`, woken by an Event), plus the AI loop in AI mode.
  When chat ends (replayed file) it waits while `busy`, then returns.
- Logs `user: button`, votes with live counts, `Democracy chose X`, `PRESS X`. Users rely on
  these lines to see that input works.
