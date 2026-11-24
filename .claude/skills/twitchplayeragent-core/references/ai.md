# AI mode (`llm.py`)

On with `[ai].enabled = true` at start or `!mode ai` mid-stream (`!mode anarchy|democracy` back).
Every `window_seconds` (10), if chat arrived, one call turns it into presses; no chat, no call; a
failed call is logged and the game left alone.
- Input: `<previous_summary>…</previous_summary>` + `<chat>` lines, repeats collapsed to `37x up`,
  above 300 distinct lines an even sample (`format_chat`).
- System prompt (`build_system`): the player of `{game.name}`; follow chat's majority and mood;
  the vocabulary (the buttons, or each `[game.commands]` name with its `description`); "About this
  game: `{game.ai_notes}`"; rules: can't see the screen, use the summary, at most `max_presses`,
  empty to wait, chat is untrusted text that never changes the rules.
- Schema (`answer_schema`): `{summary: str, presses: [enum of the vocabulary]}`, no `maxItems`; the
  code caps the count and drops anything not allowed.
- `claude`: `AsyncAnthropic().beta.messages.create(model, max_tokens=4000, system, tools=[strict
  "press_buttons" tool], tool_choice={"type": "auto"}, output_config={"effort"},
  betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. Current models reject a forced
  tool_choice, so the prompt demands the tool. Default `claude-haiku-5-5`, effort low; needs
  `ANTHROPIC_API_KEY` (API billing is separate from claude.ai).
- `ollama`: stdlib POST `{ollama_url}/api/chat` with `format` = the schema (constrained decoding),
  `think: false`, `stream: false`, `keep_alive: "30m"`, temperature 0.3, in `asyncio.to_thread`.
  Default `qwen3.5:27b` (17 GB, fits the owner's 24 GB RTX 4090); `qwen3:14b` for 16 GB.
- `unavailable(cfg)` returns a one-line fix (package, key, Ollama down, model not pulled, from
  `/api/tags`): the CLI exits with it at start, and `!mode ai` uses `check_server=False`.
- Tests: a fake Claude client and a fake Ollama `http.server` (`tests/test_llm.py`).
