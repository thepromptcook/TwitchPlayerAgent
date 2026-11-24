---
name: gta6-xbox
description: GTA VI on an Xbox Series X|S through Xbox Remote Play and a virtual Xbox controller (games/gta6.toml) - how the bridge works, why the commands are mapped as they are, tuning, and what's unverified. Use with twitchplayeragent-core when setting up, tuning or debugging GTA VI, or adding another controller game.
---

# GTA VI on Xbox (`games/gta6.toml`)

GTA VI is console-only (PS5, Xbox Series X|S; PC later). The bot is a virtual Xbox 360 controller
(`GamepadBackend`: vgamepad + ViGEmBus) and Xbox Remote Play in the Xbox app forwards it to the
console. All of the game is `games/gta6.toml`, layered on the owner's config; the owner's steps
are in the README ("GTA 6 on Xbox").

## Must-knows
- **The Xbox app only looks for controllers when it starts.** Start the bot, then fully quit
  (tray icon or Task Manager) and reopen the Xbox app; closing the Remote Play window isn't
  enough. The pad worked in `joy.cpl` but Remote Play ignored it until then (verified on the
  owner's PC); `GamepadBackend.start` logs the reminder.
- **Default** control scheme: Classic moves run to A and jump to X. **Story mode only**: GTA Online
  has anti-cheat and other players.
- Keep the Remote Play window in front (it likely reads controllers only while focused); a PC left
  alone and managed from a phone suits this.
- OBS: a Window Capture of the Xbox app (or a capture card) under the Browser Source, whose game
  area is transparent with no emulator; Application Audio Capture of the Xbox app for sound;
  Twitch content classification for a mature game.

## How the commands are mapped
- The Twitch Plays words keep their meaning: `up` `down` `left` `right` push the left stick briefly
  (1 s / 0.6 s; they steer in cars), `a` = RT (shoot), `b` = LT toggle (aim; it locks on).
- Toggles stay on until repeated or `stop` (a `release` command): `goup`/`godown`/`goleft`/`goright`
  (a new direction on the same stick replaces the old), `sprint` (stick up + LS: GTA VI runs on a
  left-stick click), `drive` (RT), `reverse` (LT). Momentary commands act on top, so `left` steers
  while `drive` holds RT.
- `a` and `drive` share RT, `b` and `reverse` share LT: toggling one turns the shared trigger off.
- Taps: `jump` A, `crouch` B, `cover` RB, `melee` X, `enter` Y (vehicles, interact), `holster` LB,
  `handbrake` A for 0.6 s. Camera: `lookleft`/`lookright`/`lookup`/`lookdown`/`lookback` push the
  right stick briefly; to turn further, raise their `seconds` (or `x`).
- Not mapped on purpose: View (map), Menu (pause), the D-pad (phone, radio), holding LB (weapon
  wheel): chat would get stuck in menus.
- `[anarchy].max_queue = 10` (commands last up to a second, so the backlog stays short) and 5 s
  democracy rounds (Pokémon's 20 s is too slow for driving).
- AI mode works unchanged: the prompt lists each command's `description`, and `ai_notes` explains
  the toggles. It can't see the screen, so explicit commands work best.

## Unverified (only checkable on the owner's PC)
- The button map comes from published Default-scheme guides; handbrake on A and running on an LS
  click are the least certain. The camera turn sizes likely need tuning to GTA's sensitivity.
- Remote Play adds roughly 50–100 ms on top of Twitch's delay.
- ViGEmBus is retired upstream (no updates) but still installs and works; a Windows update could
  break it.
