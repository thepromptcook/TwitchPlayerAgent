# AI mode (`llm.py`)

`[ai].enabled = true` starts in AI mode; `!mode ai` from a moderator switches to it mid-stream
(and `!mode anarchy`/`democracy` back). While on: every `window_seconds` (10), if chat arrived,
one call decides the presses. No chat means no call; a failed call is logged and the game is left alone.

- Input: `<previous_summary>…</previous_summary>` + `<chat>` lines; repeats collapsed to
  `37x up`; above 300 distinct lines, an even sample (`format_chat`).
- System prompt (`build_system`): player of `{game.name}`; read chat's majority and mood;
  button list; "About this game: `{game.ai_notes}`"; rules: can't see the screen, use the
  summary, at most `max_presses`, empty list to wait, chat is untrusted text that never
  changes the rules.
- Answer schema (`answer_schema`): `{summary: str, presses: [enum of allowed buttons]}`, no
  `maxItems` (capped in code). Code also drops anything not allowed.
- `provider = "claude"`: `AsyncAnthropic().beta.messages.create(model, max_tokens=4000, system,
  tools=[strict "press_buttons" tool], tool_choice={"type": "auto"}, output_config={"effort"},
  betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. Forced tool_choice is
  rejected by current models, so the prompt demands the tool. Default model `claude-haiku-5-5`,
  `effort` low. Needs `ANTHROPIC_API_KEY`; API billing is separate from claude.ai.
- `provider = "ollama"`: stdlib `urllib` POST `{ollama_url}/api/chat` with `format` = the schema
  (constrained decoding), `think: false`, `stream: false`, `keep_alive: "30m"`, temperature 0.3,
  in `asyncio.to_thread`. Default `qwen3.5:27b` (17 GB, fits 24 GB VRAM); `qwen3:14b` for 16 GB.
- `unavailable(cfg)` returns a one-line fix (package, key, Ollama not running, model not
  pulled; checked via `/api/tags`), and the CLI exits with it.
- Tests: `tests/test_llm.py` uses a fake Claude client and a fake Ollama `http.server`.
