# 01 — Environment Findings

Inspection performed 2026-06-10 on the Arch Linux Reaper workstation.
Everything below is observed fact, not assumption.

## Reaper

- Binary: `/usr/bin/reaper`
- Version: **7.72** (`~/.config/REAPER/reaper-install-rev.txt` → `7.72`)
- Resource dir: `~/.config/REAPER`
- Reaper was **not running** during inspection.

## Audio backend

- System audio stack: **PipeWire** (`pipewire`, `pipewire-pulse`, `wireplumber` all running).
- `pw-jack`, `pw-cli`, `qjackctl` present; **no standalone `jackd`** (PipeWire provides JACK).
- `reaper.ini` audio keys are the Linux/ALSA-style block:
  - `linux_audio_srate=44100`, `linux_audio_bsize=512`, `linux_audio_bufs=3`,
    `linux_audio_nch_in=2`, `linux_audio_nch_out=2`, `linux_audio_bits=32`
  - `jack_launchcmd=` (empty)
- **MIDI device naming is ambiguous between backends** — Reaper keeps two caches:
  - `reaper-midihw-alsa.ini` → ALSA names like `hw:MK3`, `hw:MK3,0,1`
  - `reaper-midihw-linux.ini` → JACK/Midi-Bridge names like
    `Midi-Bridge:Launchpad Pro MK3: LPProMK3 MIDI`
  - DrivenByMoss is configured against the **JACK/Midi-Bridge** names, which
    suggests Reaper currently runs with **JACK MIDI (via PipeWire)**.
  - **Action item at resume:** confirm the active backend in
    Reaper → Preferences → Audio → Device, and use the matching port-name form.

## Audio interface

- **Steinberg UR22C** (ALSA card 4), with two hardware MIDI ports
  (`Steinberg UR22C MIDI 1/2`). This is the guitar/mic input path.

## Launchpad Pro MK3 (the controller)

- **Currently NOT connected** (`lsusb` shows no Novation/Launchpad device).
- Previously configured (DrivenByMoss config timestamped 2026-05-27).
- When connected it exposes **three USB-MIDI ports**. Known names from caches:
  - JACK: `Midi-Bridge:Launchpad Pro MK3: LPProMK3 MIDI` (capture & playback)
  - JACK: `Midi-Bridge:Launchpad Pro MK3: LPProMK3 DIN`
  - JACK: `Midi-Bridge:Launchpad Pro MK3: LPProMK3 DAW`
  - ALSA: `hw:MK3` (port 0,0 = "MIDI"), `hw:MK3,0,1` (port 0,1 = "DAW")
- For a custom RC-505 surface we want the **`LPProMK3 MIDI`** port in
  **Programmer mode** (pads send/receive raw notes; velocity sets LED color).
  See [04-launchpad-promk3-reference.md](04-launchpad-promk3-reference.md).

## Installed Reaper extensions / scripting

`~/.config/REAPER/UserPlugins/` contains only:
- `reaper_drivenbymoss.so` + `drivenbymoss-libs/` + `java-runtime/` (DrivenByMoss)

**Not installed:** SWS, `js_ReaScriptAPI`, ReaImGui, ReaPack.

**Implication:** stock ReaScript (`reaper.StuffMIDIMessage`) can only send 3-byte
messages to the *virtual MIDI keyboard / control* path — it cannot reliably push
arbitrary notes or sysex to a *hardware output* like the Launchpad. Driving LEDs
from a Lua script would require installing `js_ReaScriptAPI`. **We therefore plan
to generate LED feedback from the forked Super505 JSFX instead** (JSFX `midisend`
goes out the track's hardware MIDI output with zero extra dependencies).

## DrivenByMoss — the coexistence conflict

- `~/.config/REAPER/DrivenByMoss4Reaper.config`:
  `CONTROLLER_INSTANCE0=...novation.launchpad.LaunchpadProMk3ControllerInstance`
- `~/.config/REAPER/DrivenByMoss4Reaper-Launchpad-Pro-Mk3.config`:
  - `MIDI_INPUT0 = Midi-Bridge:Launchpad Pro MK3: LPProMK3 MIDI (capture)`
  - `MIDI_OUTPUT0 = Midi-Bridge:Launchpad Pro MK3: LPProMK3 MIDI (playback)`
- DrivenByMoss is a **global control surface** (Reaper-wide, not per-project). It
  grabs the `LPProMK3 MIDI` port and drives the Launchpad in its own modes.
- **Super505 needs that same port.** A MIDI port can only be owned by one
  consumer. They cannot run simultaneously on the same port → pending decision in
  [05-open-decisions.md](05-open-decisions.md).

## Other connected MIDI gear (for context, from caches)

- Keystation 49 MK3, Impact GX49, Behringer X18/XR18, a "Digital Keyboard",
  VirMIDI virtual ports, BLE MIDI. None are needed for Super505.

## Relevant Reaper directories (for deliverables)

- JSFX effects: `~/.config/REAPER/Effects/` (Super8 at `Effects/loopsamplers/super8`)
- Project templates: `~/.config/REAPER/ProjectTemplates/`
- Track templates: `~/.config/REAPER/TrackTemplates/`
- Scripts: `~/.config/REAPER/Scripts/` (only factory `Cockos/` present)
- Key/MIDI bindings: `~/.config/REAPER/reaper-kb.ini`
