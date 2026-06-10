# 03 — Architecture Proposal

The plan to build once the Launchpad is connected and the open decisions
([05-open-decisions.md](05-open-decisions.md)) are confirmed. Nothing here has
been implemented yet.

## Design principle

The **Super505 JSFX is the single source of truth** for loop state, so it is also
the natural place to generate LED feedback. This avoids a fragile ReaScript
polling loop and needs **zero extra Reaper extensions** (none are installed).

## Signal & MIDI routing

```
                 guitar / mic
                      │
              [ Steinberg UR22C in ]
                      │  audio
                      ▼
        ┌─────────────────────────────┐
        │  Track: "Super505 Looper"   │
        │   • input FX (optional)     │
        │   • Super505 JSFX (engine)  │
        └─────────────────────────────┘
              │ audio out        ▲ MIDI in (pad presses, ch1)
              ▼                  │
          [ Master ]      [ Launchpad LPProMK3 MIDI input ]
              │                  ▲
              ▼                  │ MIDI out = LED data (Note-On ch1 = color)
        speakers/phones   [ Track HW MIDI output → LPProMK3 MIDI ]
                                 │
                                 └──> physically the same Launchpad device
```

Key points:
- The Launchpad's `LPProMK3 MIDI` **input** → looper track input (channel 1).
- The looper track's **hardware MIDI output** → `LPProMK3 MIDI` so the JSFX's
  LED Note-Ons reach the pads.
- The Launchpad port is **also enabled for "control"** in Reaper MIDI prefs so the
  **utility-row** pad notes can fire Reaper actions (undo/save/etc.) via MIDI-learn,
  independent of the track. (A device can be both a control input and a track input.)
- Super505 **drops Super8's pass-through echo** so only deliberate LED data leaves
  the track MIDI output.

## What gets built (resume order)

### 1. Super505 JSFX (fork of Super8) — *additive*
- Copy `~/.config/REAPER/Effects/loopsamplers/super8` →
  `~/.config/REAPER/Effects/loopsamplers/super505` (back up nothing destructive;
  original stays). New `desc:` so it shows as a distinct plugin.
- **Note remap** to Launchpad Programmer-mode pads (see
  [04-launchpad-promk3-reference.md](04-launchpad-promk3-reference.md)):
  - note1 (Rec/OD/Play) tracks 1–5 → 81–85
  - note2 (Stop)        tracks 1–5 → 71–75
  - note3 (Select)      tracks 1–5 → 31–35
  - note4 (Reverse)     tracks 1–5 → 41–45
- **Add per-channel Clear** command + clear-note per track (61–65).
- **LED engine** in `@block`/`@gfx`: for channels 1–5 compute desired color from
  `st_state` + `st_dirty` + `g_firstrec` and emit Note-On to the matching pad:
  - empty → off, rec → red, overdub (rec+dirty) → amber, play → green,
    stopped-with-content → dim, first-pass `g_firstrec` → red **flashing** (ch2).
  - Only send on change (track last-sent color per pad) to avoid MIDI flooding.
- **On init**: send Programmer-mode sysex; paint utility/static pads.
- (Post-MVP) optional per-channel mute & volume.

### 2. Reaper project template — *additive*
- New `ProjectTemplates/Super505.RPP` (and a copy in this repo).
- Tracks: **Audio In** (UR22C, record-armed, input monitoring, low latency) →
  **Super505 Looper** (JSFX + routing above) → optional **FX chain** →
  optional **master limiter**.
- Click routed so it can go to headphones only (separate hardware out) if desired.
- Launchpad MIDI input enabled; looper track HW MIDI out set to Launchpad.

### 3. Launchpad ⇄ action mapping
- **Track rows (1–6):** handled entirely by the JSFX note map — pads talk straight
  to Super505. No Reaper action binding needed.
- **Utility row (Row 8, pads 11–18):** bound to Reaper actions via MIDI-learn
  (stored in `reaper-kb.ini`, backed up first):
  - All Start/Stop → could also be the JSFX `play all`; or a Reaper transport action
  - Undo / Redo → `Edit: Undo` / `Edit: Redo`
  - Tap Tempo → `Tap tempo`
  - Metronome → `Options: Toggle metronome`
  - Save → `File: Save project`
  - Panic → `MIDI: reset all` + stop, or the JSFX clear-all/stop-all
- **Row 7 (Track FX on/off):** deferred to post-MVP (per-track FX-bypass targeting
  via raw MIDI-learn is awkward without js_ReaScriptAPI).

### 4. LED for utility/static pads
- Painted by the Super505 JSFX on init (static colors), so the utility row has
  clear, consistent colors with no extra moving parts.

### 5. Optional helper scripts
- A tiny standalone script (`tools/lp_programmer.sh` using `amidi`) to manually
  toggle Programmer mode and test pad colors during bring-up — independent of Reaper.

## MVP scope (target for first working session)

✅ 5 loop tracks from Launchpad · Record/Overdub/Play · Stop · **per-track Clear**
(pending decision) · All Start/Stop · Undo/Redo · LED feedback · save/load template.

**Deferred (task 8):** reverse polish, true mute, per-track volume/faders, per-track
FX, phrase-memory scenes, backing-track clips, Godin MIDI-guitar routing.

## Risks / things to validate live

- Exact Launchpad palette indices (colors).
- Programmer-mode sysex round-trip from inside a JSFX (`midisend_str`).
- LED update rate / no MIDI flooding (send-on-change required).
- DrivenByMoss vs Super505 port ownership (decision pending).
- Whether Reaper is on ALSA or JACK MIDI today (affects port names).
- Latency/monitoring config on the UR22C under PipeWire.
