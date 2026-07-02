# Sound Design (spec §8) — scaffolding

Full retro-computer soundscape: boot chimes, ambient hum, error buzzes, on top
of visual/keypress feedback. **v1 status: wired, assets are placeholders.**

- `foundationhub-sound` — the per-session sound daemon. Started by `foundationhub-session`
  (the login shell) if present. Plays ambient hum on loop and responds to event
  cues (warning buzz, select blip) written to a small control fifo.
- `assets/` — `.wav` cues. Currently silent placeholders / `.gitkeep`; drop real
  audio here and `install/06-theme-sound.sh` copies them to
  `/usr/share/foundationhub/sounds/`.

The dedicated sound + visual pass is spec §11.10 — after the subsystems are
stable. This directory just guarantees the hooks exist so that pass is a
content drop, not a rewire.

## Event cues (planned)

| Cue file            | Trigger |
|---------------------|---------|
| `hum.wav`           | ambient loop while the Hub is up |
| `boot-chime.wav`    | session start |
| `select.wav`        | menu Enter |
| `back.wav`          | Esc/Backspace |
| `warn.wav`          | Frank status-bar warning |
| `alert.wav`         | Frank full-screen serious banner |
| `lock.wav`          | lockout entered |
