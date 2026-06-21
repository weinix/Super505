# Super505

Reproduce a Boss **RC-505** loop-station workflow inside **Reaper on Linux**, driven
by a **Novation Launchpad Pro MK3**, using the **Super8** JSFX looper as the engine.

> **Status: CORE LOOPER WORKING (build underway).**
> The `super505` JSFX fork drives 5 loop columns from the Launchpad with LED
> feedback, per-track clear, a count-in, and a full audio path (source → loops →
> stereo mixdown). See **[docs/06-build-progress-and-design.md](docs/06-build-progress-and-design.md)**
> for current state, runtime gotchas, and the open design questions (esp.
> per-channel loop length). Docs 01–05 below capture the original inspection/design.

---

## What this project is

A live-performance setup that makes Reaper behave like an RC-505:

- 5 loop tracks, columns 1–5 on the Launchpad
- Record → Overdub → Play, Stop, Clear per track
- All Start/Stop, Undo/Redo, Tap Tempo, Metronome, Save, Panic
- RC-505-style LED feedback: red = recording, amber = overdub, green = playing,
  dim = stopped-with-content, off = empty, blinking = waiting for quantized start

The looping engine is the factory **Super8** JSFX. We do **not** rebuild a looper
from scratch. Where Super8 falls short (no LED output, no per-track clear, no
exposed state) we will use a **forked copy named `super505`** — purely additive,
the original `super8` is never touched.

---

## Current findings (read these first)

| Doc | Contents |
|-----|----------|
| [docs/01-environment-findings.md](docs/01-environment-findings.md) | System inspection: Reaper version, audio backend, MIDI ports, Launchpad device names, installed extensions, DrivenByMoss conflict |
| [docs/02-super8-analysis.md](docs/02-super8-analysis.md) | Full Super8 JSFX teardown: MIDI map, state machine, actions, exposed params, limitations |
| [docs/03-architecture-proposal.md](docs/03-architecture-proposal.md) | Proposed Super505 design, signal/MIDI routing, what gets built, MVP scope |
| [docs/04-launchpad-promk3-reference.md](docs/04-launchpad-promk3-reference.md) | Launchpad Pro MK3 Programmer-mode reference: ports, pad note grid, LED colors, sysex |
| [docs/05-open-decisions.md](docs/05-open-decisions.md) | The 2 decisions still pending your input |

---

## The headline facts

1. **Super8 sends no LED feedback** and **exposes no per-channel state** to Reaper
   (no `gmem`; only `Sync` and `Click count` sliders). It only echoes incoming MIDI.
2. **No `js_ReaScriptAPI` / SWS / ReaImGui installed** — so a plain Lua script
   cannot reliably push LED/sysex to the Launchpad. → LED feedback must come from
   a forked **Super505 JSFX** that emits MIDI-out to the device.
3. **DrivenByMoss already owns the `LPProMK3 MIDI` port** as a global control
   surface. It and Super505 cannot share that port — see
   [docs/05-open-decisions.md](docs/05-open-decisions.md).
4. **Super8 has no per-track Clear** — only a global "kill all". Per-track clear
   (an MVP item) requires a small JSFX addition.

---

## How we resume (when the Launchpad is plugged in)

1. Plug in the Launchpad; confirm it enumerates (`lsusb | grep -i novation`,
   `aconnect -l`).
2. Confirm the two pending decisions in [docs/05-open-decisions.md](docs/05-open-decisions.md).
3. Build order (from [docs/03-architecture-proposal.md](docs/03-architecture-proposal.md)):
   1. Back up `super8`, fork to `super505` JSFX (LED out + per-track clear + note remap).
   2. Create the Reaper project template (input track, looper track, routing).
   3. Map Launchpad pads → Super505 actions and utility pads → Reaper actions.
   4. Wire LED feedback and Programmer-mode entry.
   5. Run the test checklist.

---

## Conventions / safety rules for this project

- **Additive only.** New files: `super505` JSFX, new project template, new scripts.
- **Back up before touching** any existing Reaper file (`.bak` copy first).
- Original `super8` is never modified.
- Linux paths only. Reaper resource dir: `~/.config/REAPER`.
