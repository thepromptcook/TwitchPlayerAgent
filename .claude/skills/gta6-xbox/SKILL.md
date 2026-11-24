---
name: gta6-xbox
description: Game knowledge for playing GTA VI on an Xbox Series X|S with TwitchPlayerAgent - Xbox Remote Play bridge, the virtual Xbox controller, GTA VI's Default control scheme mapped to chat commands (games/gta6.toml), OBS capture and what's still unverified. Use with twitchplayeragent-core when setting up, tuning or debugging GTA VI, or adding another controller game.
---

# GTA VI on Xbox (`games/gta6.toml`)

GTA VI is console-only (PS5, Xbox Series X|S; PC later). The bot runs on the PC as a virtual
Xbox controller (`[backend].type = "gamepad"`, vgamepad + ViGEmBus); Xbox Remote Play in the Xbox
app forwards it to the console. Everything game-specific is `games/gta6.toml`, layered on the
owner's main config: `python -m twitchplayeragent -c config.toml -c games/gta6.toml`.

## Setup on the owner's PC
1. Xbox: Settings > Devices & connections > Remote features > Enable remote features.
2. PC: `pip install -e ".[gamepad]"` (vgamepad runs the ViGEmBus installer; accept it). **Start
   the bot first, then the Xbox app**: the app only enumerates controllers at startup, so it must
   be fully quit (tray/Task Manager) and reopened once the virtual pad exists; closing the Remote
   Play window isn't enough. Verified on the owner's PC. Then Remote Play → console → GTA VI.
3. GTA VI: **Default** control scheme (Settings > Control Scheme). Classic moves run to A and
   jump to X, so `sprint` and `jump` would need new buttons. **Story mode only**: GTA Online has
   anti-cheat and other players.
4. Keep the Xbox app's Remote Play window in front (it likely only reads controllers while
   focused); a PC left alone and managed from a phone suits this.
5. OBS: Window Capture of the Xbox app (or an HDMI capture card from the console) under the
   Browser Source; with no emulator frames the page's game area is transparent and only the
   bottom bar shows. Sound: Application Audio Capture of the Xbox app (or the capture card).
   Twitch: content classification for a mature-rated game.

## Commands (Default scheme)
| chat | controller | kind |
|---|---|---|
| up / down / left / right | left stick 1 s / 0.6 s | brief move; steers in cars |
| goup / godown / goleft / goright | left stick | toggle (new direction replaces) |
| sprint | left stick up + LS | toggle: run (GTA VI runs on a left-stick click) |
| a / b | RT / LT | shoot / aim toggle (lock-on) |
| jump / crouch / cover / melee | A / B / RB / X | tap |
| enter / holster | Y / LB | vehicle in/out, interact / draw-holster |
| drive / reverse | RT / LT | toggle accelerate / brake-reverse |
| handbrake | A 0.6 s | in vehicles |
| lookleft / lookright / lookup / lookdown / lookback | right stick | brief camera turns |
| stop | | release everything toggled |
Not mapped on purpose: View (map), Menu (pause), D-pad (phone, radio), hold LB (weapon wheel).
`b` and `reverse` share LT, and `a` and `drive` share RT: toggling one turns the shared trigger off.

## Tuning
- Anarchy runs every command in order, and moves last up to a second, so `[anarchy].max_queue`
  is 10 to keep the backlog short. Democracy rounds are 5 s (Pokémon's 20 s is too slow).
- Stick strengths and seconds live in the command table; camera turns are the likeliest to
  need tuning against GTA's camera sensitivity.
- AI mode works unchanged: the prompt lists each command with its `description`, and
  `ai_notes` explains toggles. The AI can't see the screen, so explicit commands work best.

## Unverified (only checkable on the owner's PC)
- Whether the Xbox app needs focus to read it (it does accept the virtual controller, after a
  restart; checked in Windows with `joy.cpl`, which shows the pad's buttons and axes moving).
- The button map, taken from published Default-scheme guides; handbrake on A and LS-click
  running are the least certain.
- Remote Play adds roughly 50–100 ms on top of Twitch's delay.
- ViGEmBus is retired upstream (no updates) but still installs and works; a future Windows
  update could break it.
