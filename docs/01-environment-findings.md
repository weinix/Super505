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

## Alternative guitar input: Enya XMARI / E-SP1 smart guitar (USB audio)

A second, all-in-one way to get a guitar signal into Reaper without the UR22C:
the **Enya Music XMARI**, a carbon-fiber S-style **smart guitar** whose onboard
**E-SP1 system** includes a **USB-C audio interface**. Because the guitar *is* the
audio interface, it removes a whole hardware link from the dev/test loop — plug
one USB-C cable into the workstation and you have a guitar source for exercising
the Super505 looper. No DI box, no amp, no separate interface.

### What it is (verified)

- **Instrument:** 39" S-style smart electric guitar, integrated carbon-fiber
  composite body, maple neck, 22 frets. Effectively an "amp/interface in a guitar."
- **E-SP1 = the onboard smart system** (proprietary DSP chip + OS), *not* the
  guitar model name. It provides amp/effects modeling with **4 presets**
  (Clean, Overdrive, Distortion, Lead Hi-Gain), tuner, EQ, reverb/delay, all
  editable in the **ENYA MUSIC** mobile app. Some Enya docs also use "E-SP1" as a
  product label, so the name is overloaded — treat "XMARI" as the guitar.
- **Connectivity:** **USB-C** marketed as *"OTG Recording & Charging"* — Enya
  explicitly pitches it as plugging into a DAW for home recording. Also has a
  **3.5 mm headphone jack** for silent on-device monitoring, and **Bluetooth 5.2**
  (app + backing-track playback).
- **Power:** internal **3.7 V / 2600 mAh** rechargeable Li-ion, charged over USB-C.
  (Whether it runs bus-powered with a dead battery is undocumented.)
- **Effects are applied on the guitar.** What the DSP outputs is the *selected
  preset tone*; for looping this means you typically capture the processed sound
  and do **not** need amp-sim plugins in Reaper.

### What we could NOT verify (must field-test before relying on it)

Enya publishes only marketing-level info. None of the following is documented
anywhere, so **do not quote these as facts** — confirm by plugging the guitar in:

- **USB Audio Class** (UAC1/UAC2) — i.e. whether it's truly driver-free /
  class-compliant. The Android-OTG-recording framing *strongly suggests* it
  enumerates as a standard USB audio gadget, but this is an inference, not a fact.
- **Sample rate, bit depth, channel count** (mono guitar vs. stereo stream).
- **Whether USB exposes a playback/output endpoint** (DAW monitoring back through
  the guitar) — on-device monitoring is via the 3.5 mm jack, so it may be
  capture-only over USB.
- **Clean DI vs. processed-only** routing over USB (is a dry signal capturable?).
- **Latency** figures.
- **Any Linux/ALSA/PipeWire behavior** — there are zero Linux reports for this
  device. Expected to be plug-and-play UAC class, but **untested here**.

### Verify on Linux (do this when the guitar is plugged in)

```sh
# Does it enumerate as a USB device + ALSA card?
lsusb | grep -i enya            # or look for an unknown audio gadget
cat /proc/asound/cards          # new card = the XMARI capture device
arecord -l                      # confirm a capture device + list its name
arecord -L                      # exact ALSA device string for Reaper
pw-cli ls Node | grep -i -A2 enya   # PipeWire view (this box runs PipeWire)
```

Record the **actual** card name, supported rates, and channel count from the
output above and fold them back into this doc's spec table — that field test is
the only authoritative source for the unverified items above.

### Configure in Reaper

1. Plug the XMARI in via USB-C; power it on (master knob). Confirm it enumerates
   with the commands above.
2. Reaper → **Preferences → Audio → Device**. This workstation runs PipeWire, so
   either:
   - **ALSA backend:** pick the XMARI directly as the **input device**. Output
     stays on the UR22C / system DAC (the XMARI may be capture-only over USB), or
   - **JACK backend (PipeWire):** launch Reaper under `pw-jack` and patch the
     XMARI's capture node to Reaper in `qpwgraph`/`qjackctl`, output on the UR22C.
   - Set a small block size (e.g. 128–256) and check for x-runs; the
     all-in-USB-guitar path's latency is unknown, so measure it.
3. On the Super505 input track, set the **record input** to the XMARI's channel(s).
   If it presents as **stereo**, record stereo; if **mono**, use a single channel.
4. Because the E-SP1 DSP already shapes the tone, **leave amp-sim plugins off** the
   input track — pick the guitar's preset (Clean for a flat looping source) instead.
5. Arm + monitor and play a test loop through Super505 to confirm signal, level,
   and acceptable latency before relying on it for a session.

> **Status:** documented from Enya's public materials + research; **not yet
> tested against this Linux box.** The UR22C remains the known-good input path
> until the XMARI is field-verified.

**Sources:** [enya-music.com/products/xmari](https://www.enya-music.com/products/xmari),
[enyamusicglobal.com/products/xmari](https://enyamusicglobal.com/products/xmari),
[Enya GearGuide review](https://enyamusicglobal.com/blogs/gearguide101/4),
[user-manual portal](https://www.enya-music.com/pages/user-manual).

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
