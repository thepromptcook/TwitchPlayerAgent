# Config (`config.py`, TOML; `config.example.toml` mirrors it)

| Section | Fields (default) |
|---|---|
| `[twitch]` | channel ("") |
| `[game]` | name ("Pokemon Red"), buttons (no select), ai_notes (Pokémon Red text), commands ({}) |
| `[anarchy]` | max_queue (100) |
| `[democracy]` | window_seconds (20), max_presses (9) |
| `[meter]` | to_democracy (0.8), to_anarchy (0.5), vote_lifetime (60), min_votes (5), start_mode ("anarchy") |
| `[ai]` | enabled (false), provider ("claude" / "ollama"), model ("" = per-provider default), effort ("low"), ollama_url, window_seconds (10), max_presses (9) |
| `[backend]` | type ("pyboy" / "keyboard" / "gamepad" / "log"), hold_frames (2), release_frames (2) |
| `[backend.pyboy]` | rom, state_file, autosave_minutes (5), window ("SDL2"), scale (4), window_keyboard (false) |
| `[backend.keyboard]` | keys (button → key), hold_ms (50), gap_ms (50) |
| `[overlay]` | enabled (true), port (8080), max_lines (20), audio (true), ticker (""), ticker_file ("saves/ticker.txt") |

- Nested dataclasses are built recursively; unknown keys are errors; `validate()` checks
  enums and ranges.
- Layering: `load_config([a, b])` deep-merges the TOML files in order (later wins);
  `[game.commands]` is replaced whole. The CLI's `-c` can repeat: `-c config.toml -c
  games/gta6.toml` keeps channel, overlay, meter and AI settings and swaps the game.
- `[game.commands]` entry (`check_command`): `button` (one of `PAD_BUTTONS`: A B X Y LB RB LT RT
  LS RS START BACK UP DOWN LEFT RIGHT), `stick` ("left"/"right") with `x`, `y` in -1..1,
  `seconds` (press length, 0.1), `toggle` (held until repeated or a `release` command),
  `release` (let go of everything), `description` (for the AI). Needs backend `gamepad` (or
  `log`); a `gamepad` backend needs commands.
- TOML syntax errors show the offending line, with hints for unquoted text and curly quotes.
- Renaming or removing a field breaks the owner's existing `config.toml`: say which line to
  change in the same message.
- Gitignored: `roms/`, `saves/`, `*.gb`, `*.state`, `config.toml`, `overlay-shots/`.
