# 04 — Launchpad Pro MK3 Reference (for RiftwayLabsLooper)

Reference notes for driving the controller. **To be verified live** once the
device is connected — values below follow Novation's published Programmer
Reference for the Launchpad Pro MK3.

## Ports (Linux)

The device enumerates 3 USB-MIDI ports. Use these names (JACK/Midi-Bridge form;
ALSA equivalents in parentheses):

| Port | JACK name | ALSA | Use |
|------|-----------|------|-----|
| MIDI | `Midi-Bridge:Launchpad Pro MK3: LPProMK3 MIDI` | `hw:MK3` (0,0) | **RiftwayLabsLooper surface** (Programmer mode) |
| DIN  | `Midi-Bridge:Launchpad Pro MK3: LPProMK3 DIN`  | — | physical DIN out, unused |
| DAW  | `Midi-Bridge:Launchpad Pro MK3: LPProMK3 DAW`  | `hw:MK3,0,1` | DAW integration / DrivenByMoss session, unused by RiftwayLabsLooper |

## Programmer mode

In **Programmer mode** every pad and button sends/receives a fixed Note number,
and an incoming Note-On sets that pad's LED by **velocity = color palette index**.
This is what makes self-contained LED feedback possible from the RiftwayLabsLooper JSFX.

- **Enter Programmer mode (sysex):**
  `F0 00 20 29 02 0E 0E 01 F7`
- **Return to standard/Live mode (sysex):**
  `F0 00 20 29 02 0E 0E 00 F7`

RiftwayLabsLooper plan: the JSFX sends the "enter Programmer mode" sysex on init.

## Pad note grid (Programmer mode)

Pads are numbered **row*10 + column**, bottom-left = `11`, top-right = `88`.
Bottom row = 11–18, next row up = 21–28, … top row = 81–88. The outer ring
(logo, scene launch, CC buttons) uses other numbers in the 1–99 range.

### Confirmed transport button CCs (live, Programmer mode)

Snooped via `tools/print_launchpad_key.sh` (2026-07-07). Outer-ring buttons send
**Control Change** on ch 1, value 127 on press / 0 on release:

| Function (RiftwayLabsLooper NG) | Physical button | CC |
|---------------------------------|-----------------|----|
| **Play-all** (AllStart/AllStop toggle) | user's play button | **20** |
| **Clear-all** (kill + grid reset)      | user's clear button | **19** |

Wired as the `g_play_cc` / `g_clear_cc` slider defaults in `RiftwayLabsLooper_ng`.
The engine acts on press only (non-zero value).

## FCB1010 foot controller map (live, into UR22C MIDI IN) — VERIFIED 2026-07-08

Snooped via `tools/print_launchpad_key.sh UR22C`, wired into the NG engine and
**verified working live in REAPER** (2026-07-08). Footswitches send
**Program Change** on ch 1; expression pedals send **Control Change**. The foot
controller does only the hands-busy, time-critical actions on the **selected**
track (per the locked LED design, col 8 = selected) plus global transport —
selection/mute/solo/length-sync presets stay on the Launchpad.

| Switch | Sends | Function | Acts on |
|--------|-------|----------|---------|
| **FS1** | PC 0 | **Record → Play → Overdub** cycle (empty→rec, rec→play, play→overdub, overdub→play, stopped→play) | selected track |
| **FS2** | PC 1 | **Stop / Play** toggle | selected track |
| **FS3** | PC 2 | **Clear** | selected track |
| **FS4** | PC 3 | **Select next track** (wrap 1→6→1; none→T1) | — |
| **FS5** | PC 4 | **Play-all / Stop-all** (= LP Play, CC 20) | all |
| **FS10** | PC 9 | **Clear-all** (= LP Clear, CC 19) — parked far right | all |
| FS6–9 | PC 5–8 | *unmapped* (room to grow) | — |
| **Exp A** | CC 27 | **Selected-track volume** (0..1) | selected track |
| **Exp B** | CC 7 | **Master / output volume** (0..1) | all |

Wired in `RiftwayLabsLooper_ng`: PC dispatched in `onmsg` (normalized `raw+258`);
expression CCs handled inline in `@block` (need the value + must act at value 0),
assignable via the `g_volsel_cc` / `g_volmaster_cc` sliders. Fresh session: press
FS4 (or a Launchpad col-8 pad) first so FS1 has a selected track to record.

```
 81 82 83 84 85 86 87 88     <- top pad row
 71 72 73 74 75 76 77 78
 61 62 63 64 65 66 67 68
 51 52 53 54 55 56 57 58
 41 42 43 44 45 46 47 48
 31 32 33 34 35 36 37 38
 21 22 23 24 25 26 27 28
 11 12 13 14 15 16 17 18     <- bottom pad row
```

### Provisional RiftwayLabsLooper row assignment

The spec asks for action rows. Mapping the user's "Row 1 = top" layout onto pad
numbers (top row 81–88 down to bottom 11–18), **columns 1–5 = tracks 1–5**:

| Spec row | Function | Pad notes (track 1..5) |
|---------:|----------|------------------------|
| Row 1 | Rec/Overdub/Play | 81 82 83 84 85 |
| Row 2 | Stop             | 71 72 73 74 75 |
| Row 3 | Clear            | 61 62 63 64 65 |
| Row 4 | Mute             | 51 52 53 54 55 |
| Row 5 | Reverse          | 41 42 43 44 45 |
| Row 6 | Select/Monitor   | 31 32 33 34 35 |
| Row 7 | Track FX on/off  | 21 22 23 24 25 |
| Row 8 | Utility          | 11 12 13 14 15 16 17 18 |

Columns 6–8 (x6/x7/x8) are free for scenes/phrase memory later.
**These note numbers feed directly into the RiftwayLabsLooper JSFX note map**, replacing
the Super8 defaults from [02-super8-analysis.md](02-super8-analysis.md).

> Note: pads send Note-On on **channel 1**, which is exactly what Super8/RiftwayLabsLooper
> requires. Good fit.

## LOCKED LED design (RiftwayLabsLooper NG)

Grid rows 8..3 (top→down) = Tracks 1..6. Per-track columns:

| Col | Meaning | States |
|-----|---------|--------|
| **1** | track STATE (only) | off=empty · **flashing red**=armed · **solid red**=rec · **yellow**=overdub · **green**=play · **dim green**=stopped-w/loop |
| **6** | solo | **yellow**=solo · off |
| **7** | mute | **red**=muted · off |
| **8** | SELECTED track (only) | **blue**=selected · off — shown even when the track is empty (FCB1010 acts on the selected track) |

Column 1 shows state only; column 8 shows selection only — never overloaded.
Velocities: red=5, yellow=13, green=21, dim green=19, blue=45; flashing via
Note-On channel 2 (0x91), static via channel 1 (0x90). All verified live 2026-07-08.

## LED colors (velocity palette, channel 1 = static)

Programmer mode: **Note-On ch1** = static color, **ch2** = flashing,
**ch3** = pulsing. Velocity is the palette index (0–127). Common indices
(to confirm live):

| Meaning (RC-505) | Color | Approx velocity |
|------------------|-------|----------------:|
| Empty | off | 0 |
| Recording | red (bright) | 5 |
| Overdub | amber / orange | 9 or 84 |
| Playing | green (bright) | 21 |
| Stopped w/ content | dim green / blue | 19 / 45 |
| Waiting for quantized start | red **flashing** (ch2) | 5 |

The full 128-entry palette is in Novation's Programmer Reference; we'll lock exact
indices during live bring-up.

## Verification commands (when connected)

```bash
lsusb | grep -i novation
aconnect -l                 # ALSA client/port list
amidi -l                    # ALSA raw MIDI ports
# Enter programmer mode + light pad 81 red, via ALSA raw (port from `amidi -l`):
amidi -p hw:MK3 -S 'F0 00 20 29 02 0E 0E 01 F7'
amidi -p hw:MK3 -S '90 51 05'   # note 0x51=81dec? -> use decimal-correct hex
```

(We'll finalize exact hex when the device is present.)
