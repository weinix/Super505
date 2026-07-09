# 08 — MIDI Recovery Checklist (dark Launchpad / dead pads / silent FCB1010)

When the Launchpad grid goes dark or controllers stop reaching the looper,
work this list **top to bottom** — each layer is proven before moving up, so
you never guess. Root causes seen live (2026-07-08): device re-enumeration
after replug drops the PipeWire links, REAPER's track MIDI input resets, and
(fixed since) the engine's LED cache suppressed repaints.

**TL;DR for the common case (replugged the Launchpad, grid dark):**

```bash
./tools/launchpad_reset.sh        # fixes OS layer: Programmer mode + links
# then in REAPER: FX "Action trigger" -> LedRepaint  (or reload the FX)
# still dark? -> §4 REAPER settings (track MIDI input is the usual suspect)
```

---

## 1. Hardware / device layer

| Check | How | Good result |
|-------|-----|-------------|
| Launchpad enumerated | `aseqdump -l` | a `LPProMK3 MIDI` port (card number CHANGES per replug — never hard-code) |
| UR22C (FCB1010 DIN in) enumerated | `aseqdump -l` | `Steinberg UR22C MIDI 1` |
| Stuck in Note/Sequencer mode (colorful chromatic diamond) | look at the pad | not bootloader — it just needs the Programmer sysex (§2) |
| Real bootloader (rare) | pad shows bootloader UI | unplug 5 s, replug touching nothing; last resort: Novation Components firmware repair |
| FCB1010 silent | cable FCB **MIDI OUT → UR22C MIDI IN**; power on | `print_launchpad_key.sh UR22C` shows PC 0–9 per footswitch |
| FCB1010 was working, went silent | **unplug/replug the UR22C** (its DIN input flakes; happened twice on 2026-07-08) | snoop shows PC again; then re-verify §2 links — the replug re-enumerates |
| USB flakiness | replug / different port | fresh clean enumeration in `aseqdump -l` |

## 2. OS / PipeWire layer — `./tools/launchpad_reset.sh`

The script is idempotent; run it after ANY replug or when in doubt. It:

1. finds the Launchpad seq port dynamically,
2. sends the **Programmer-mode sysex** via the sequencer path
   (`aplaymidi` — raw `amidi` always says "busy" here because PipeWire owns
   the raw device; do not fight it),
3. re-links `REAPER:MIDI Output → Launchpad` (LED path) and
   `Launchpad → REAPER:MIDI Input` (pad path) if the replug dropped them.

```bash
./tools/launchpad_reset.sh          # normal recovery
./tools/launchpad_reset.sh --test   # + light top-left pad GREEN: proves the
                                    #   computer->Launchpad path without REAPER
```

Manual inspection when the script isn't enough:

```bash
pw-link -l -I | grep -iE 'REAPER:MIDI|Launchpad'   # see the actual wires
pw-link <out-id> <in-id>                           # add a missing wire by ID
```

A patchbay GUI (`qpwgraph`) makes "everything enabled but nothing flows"
visible at a glance — REAPER's prefs can look fine while the wire is gone.

Also check nothing else is holding the device:

```bash
aconnect -l | grep -i webmidi   # a Firefox tab running Novation Components!
```

Close that browser tab — it fights REAPER for the Launchpad.

## 3. Prove each direction independently (no guessing)

| Direction | Command | Good result |
|-----------|---------|-------------|
| Computer → Launchpad | `./tools/launchpad_reset.sh --test` | top-left pad turns green |
| Launchpad → computer | `./tools/print_launchpad_key.sh "LPProMK3 MIDI"` then press pads | Note on/off lines print |
| FCB1010 → computer | `./tools/print_launchpad_key.sh UR22C` then step on switches | `Program change ... 0..9` |

`aseqdump` snoops **alongside** REAPER (seq layer is multi-subscriber), so
these tests are safe with REAPER running. If both directions pass here but
REAPER sees nothing, the problem is 100 % inside REAPER → §4.

## 4. REAPER settings (a restart / re-enumeration resets these)

Work in this order:

1. **Preferences → Audio → MIDI Devices**
   - Launchpad **input** row: *enabled*. Launchpad **output** row: *enabled*.
   - UR22C **input** row (FCB1010): *enabled*.
   - Duplicate entries with one `<offline>` ghost → enable the live one.
2. **Looper track — MIDI input: DEVICE-SCOPED, never "All MIDI inputs"**:
   - "All MIDI inputs" merges EVERY controller into the looper — a music
     keyboard's notes collide with the pad note map (live example: GX49 key
     F2 = note 41 = track 5's REC pad). The JSFX cannot tell devices apart,
     so scoping must happen here.
   - Looper track input = **MIDI → Launchpad Pro MK3 LPProMK3 MIDI → All
     channels** (the Launchpad ONLY).
   - The FCB1010 arrives via a dedicated **feeder track** `FCB→looper`:
     input = **UR22C MIDI 1**, record-armed + monitoring ON, no FX, with a
     **MIDI-only send** to the looper (audio None, MIDI All→All).
   - Looper track is **record-armed** with **input monitoring ON** — the
     JSFX only receives MIDI that is monitored through the track.
2b. **Looper track — receives must be AUDIO-ONLY** (double-trigger trap):
   - REAPER sends default to audio + **MIDI (All→All)**. Source tracks are
     armed+monitored by the arm bridge, so their sends forward every pad /
     footswitch press into the looper FX **again**, on top of the track's own
     All-MIDI input → every press arrives twice.
   - Symptom: REC on an empty track lands instantly on **PLAY (green, tiny
     len)** — the duplicate closes the record; mute pads look dead (toggle
     twice). Model check: double press from EMPTY → PLAY len≈1.
   - Fix: looper track Route/IO → each entry under **Receives** → set the
     **MIDI dropdown to None** (keep audio).
3. **Looper track — MIDI hardware output** (the LED path):
   - Track Route/IO dialog → **MIDI Hardware Output → Launchpad Pro MK3
     LPProMK3 MIDI** (not `<no output>`).
4. **FX present and current**: `RiftwayLabsLooper_ng` loaded (project pins the
   `…_ng.disabled` filename — deploys must copy to BOTH names).

## 5. Engine layer (JSFX)

- **LedRepaint**: FX slider "Action trigger" → **LedRepaint** re-sends the
  Programmer sysex and repaints every pad. Engines deployed ≥ 2026-07-08 also
  do this automatically on every FX (re)load — the old LED-cache bug
  (reload blanked the pads but skipped the repaint) is fixed.
- **"last MIDI" monitor** (FX GUI bottom line): press a pad/footswitch — the
  `st/d1/d2` line must change. It updates only for channel-voice presses
  (notes, CC, PC — clock/active-sense filtered). FCB1010 footswitches show as
  `st=C0 d1=<0..9> d2=0` (engines deployed ≥ 2026-07-08 — older builds
  dropped PC from the monitor because PC has no 2nd data byte, even though
  dispatch worked). If it moves but LEDs stay dark, only the LED path (§4.3)
  is broken; if it never moves, input path (§4.1–4.2).
- Arm bridge (`RiftwayLabsLooper_arm_bridge.lua`) self-heals looper-FX
  discovery; it does NOT manage MIDI devices — that's this checklist.

## 6. Diagnosis map (symptom → layer)

| Symptom | Start at |
|---------|----------|
| Grid dark, pads do nothing | §2 script, then §4 |
| Grid dark, but "last MIDI" moves on press | §4.3 (track MIDI hardware output) |
| Grid lit, pads do nothing | §4.1–4.2 (input enable / track input) |
| REC lands on PLAY (green) instantly; mute pads look dead | every press delivered TWICE → §4.2b (receives carrying MIDI) |
| Playing a music keyboard triggers looper pads (e.g. GX49 F2 → T5 REC) | looper input is "All MIDI inputs" → §4.2 (device-scoped input + FCB feeder) |
| `--test` pad won't light | §1–§2 (device / links / mode) |
| Snoop shows presses, REAPER doesn't | §4 |
| FCB1010 dead but Launchpad fine | replug UR22C (§1), then §3 FCB row, then §4.1 UR22C input + §4.2 All-MIDI-inputs |
| Snoop is silent AND REAPER ports missing from graph | REAPER isn't running (a device replug can take it down) — start it; links auto-restore |
| Everything checks out, still wrong | close Novation Components (web tab!), then §2 manual `pw-link` |

## Notes / gotchas (learned the hard way)

- **Never hard-code ALSA card numbers** — the Launchpad moved cards across
  replugs in one session. Tools must discover ports by name.
- **`amidi` (raw) is unusable on this machine** — PipeWire owns raw MIDI;
  use seq-layer tools (`aseqdump`, `aplaymidi`, `pw-link`).
- **`fuser` on `/dev/snd/midiC*` proves nothing** — PipeWire holds devices
  via `/dev/snd/seq`, invisible to per-device `fuser`.
- REAPER's prefs can show a device *enabled* while its PipeWire wire is
  missing — the graph, not the checkbox, is the truth (§2).
- A REAPER **restart** re-enumerates MIDI devices: expect §4 items (track
  input especially) to need re-checking afterwards.
