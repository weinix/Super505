# 06 — Build Progress & Design Notes

Session log through **2026-06-21**, built on the `bmini` dev machine. This doc is
the cold-resume reference: what's built, what works, the gotchas we hit, and the
open design questions to discuss next session.

Supersedes the "build paused" status in the README / docs 01–05 — **the build is
underway and the core looper works end-to-end.**

---

## 1. Status: core looper works live

Verified on `bmini` (Reaper 7.72, PipeWire/JACK, Launchpad Pro MK3 on `hw:3,0,0`):

- 5 loop columns driven from the Launchpad pads
- Record / overdub / play, stop, **per-track clear**
- RC-505-style **LED feedback** (rec=red, overdub=amber, play=green,
  stopped-with-content=dim/blue, empty=off; count-in=amber flash)
- Static function-row colors (stop=green, clear=amber, reverse=blue, select=white,
  utility=dim)
- Full **audio path**: source → Super505 loops → mixdown → master
- **Count-in** feature (clicks N beats at project tempo, then records)
- **Low latency** (~5 ms)

**Not yet done:** saved `.rpp` project template, utility-row → Reaper actions,
per-track volume/mute, multi-instrument routing build-out, git push (commit is
local), UR22C integration.

---

## 2. What got built (all additive; factory `super8` untouched)

| Artifact | Location (live) | Repo copy | Purpose |
|---|---|---|---|
| **`super505`** JSFX | `~/.config/REAPER/Effects/loopsamplers/super505` | `reaper/effects/super505` | Forked looper engine (see §3) |
| **`super505_mixdown`** JSFX | `…/loopsamplers/super505_mixdown` | `reaper/effects/super505_mixdown` | Folds loop output ch1–8 → stereo 1/2 (8 in/out pins) |
| `lp_programmer.sh` | — | `tools/lp_programmer.sh` | Launchpad bring-up/reset via `amidi` (programmer/live mode, paint, palette ramp) |
| `route_guitar.sh` | — | `tools/route_guitar.sh` | Wire E-SP1 guitar → Reaper inputs over PipeWire (run after reboot/replug) |
| low-latency conf | `~/.config/pipewire/pipewire.conf.d/99-super505-lowlatency.conf` | `reaper/99-super505-lowlatency.conf` | PipeWire quantum 256 (~5 ms) |

Git: committed locally as `e50866e` on `main`; **not pushed** (push needs the
remote switched HTTPS→SSH and user approval — SSH auth works as `weinix`).

---

## 3. super505 JSFX — changes vs factory super8

1. **Note remap** to Launchpad Programmer-mode pads (channel 1):
   note1 Rec/OD/Play = 81–85, note2 Stop = 71–75, note3 Select = 31–35,
   note4 Reverse = 41–45, **note5 Clear = 61–65** (new). Channels 6–8 = off.
2. **Per-track Clear** — new `st_note5` + `chan_clear()` (`st_num` 14→15); erases
   only that channel's buffer, leaves `g_length` / other channels intact.
3. **LED engine** (`@block`), self-healing: send "enter Programmer mode" sysex once
   via `midisend_buf`, then re-assert static pads every ~0.5 s; Rec/Play pads
   reflect state send-on-change. Palette = editable `C_*` constants
   (red5/amber9/green21/blue45/white3/dim1).
4. **Dropped** super8's blind MIDI pass-through echo (so the track MIDI output is
   reserved for LED data).
5. **Count-in** (new) — slider5 `g_countin` + a clickable **`count-in: N`** button
   in the top bar (cycles 0–8). Pressing Rec on an *empty* column with count-in > 0
   clicks N beats at project tempo (pad flashes amber), then starts recording on
   the downbeat via `setstate_for_rec`. A second press cancels. Off by default.
6. GUI title → "Super505".

---

## 4. Audio routing architecture (the per-channel model)

Super8/505 records/plays **each loop on its own channel** (loop N ↔ channel N).
This is the crux of everything:

- **Input** — feed each loop channel its source via **sends** into the Super505
  track (which is set to **8 track channels**):
  - *Single-source* (current guitar test): one "Mic In" track → 3 stereo sends to
    dest **1/2, 3/4, 5/6** → all 5 columns record the same source.
  - *Multi-instrument* (planned, §6): each source track → **one** channel.
- **Output** — `super505_mixdown` (inserted **after** super505) sums ch1–8 → stereo,
  so every loop reaches the master.
- **Monitoring** — keep **Super505 channel monitoring OFF** (right-click the channel
  speaker icons) and monitor live sound via the **source tracks**. Otherwise the
  live signal is heard twice (source-track monitor + Super505 monitor) ≈ +6 dB,
  making live louder than replay.

Signal in one line:
```
source(s) → send(s) → Super505 [loops, per channel] → super505_mixdown [→stereo] → master
Launchpad ⇄ Super505  (pad presses in / LED note-ons out, both on LPProMK3 MIDI)
```

---

## 5. Environment & key runtime gotchas (cost real debugging time)

Hardware on `bmini`: Launchpad Pro MK3 (`hw:3,0,0`, **JACK/Midi-Bridge** backend);
audio inputs = **Yeti mic**, **enya E-SP1 guitar** (USB), onboard line-in (card 1);
**MT Power Drum Kit** installed (VST3 + `PowerDrum`/`powerdrum_locker` track
templates + Drum Locker groove browser). **No UR22C yet**, **no DrivenByMoss**, no
Reaper extensions.

Gotchas:
- A JSFX runs `@block`/`@sample` **only while its track is processing** → the
  looper track must be **record-armed + input-monitoring ON** (or transport playing).
  Otherwise no MIDI/LEDs go out and the Launchpad shows its own idle animation.
- **Reload after editing a `.jsfx`** = remove/re-add the FX (the "Super505" title and
  the new top-bar button confirm new code is live). Reaper indexes JSFX at startup;
  a brand-new JS file may need the Add-FX browser reopened (or a restart).
- **LED note-ons in the same block as the programmer-mode sysex get dropped** (device
  clears the grid switching modes) → hence the staged/self-healing repaint.
- **Launchpad stays in Programmer mode** after Reaper closes/crashes (JSFX has no
  shutdown hook) → reset with `tools/lp_programmer.sh live` (when the port is free)
  or a USB re-plug. After a re-plug, Reaper may drop the device — re-enable it in
  Prefs → MIDI Devices and re-set the track MIDI HW output.
- **PipeWire/JACK can segfault** in its own audio thread (we hit one) — unrelated to
  the JSFX. **Save the project often.**
- **PipeWire links aren't persistent** across reboot/replug (`route_guitar.sh` re-runs
  them); the low-latency quantum config applies on next PipeWire/boot restart.

---

## 6. Design direction: multi-instrument rig (to discuss)

Goal: dedicated instrument per loop column, build a groove-based arrangement.
```
Drum (MT Power Drum Kit + Drum Locker groove) ──► Super505 ch1 ──► column 1
Guitar 1 (E-SP1)                               ──► ch2        ──► column 2
Guitar 2 (input TBD)                           ──► ch3        ──► column 3
Mic (Yeti)                                     ──► ch4        ──► column 4
```
Decisions already made by the user:
- **Drum = recorded one pass into column 1** (not just live backing).
- Per-channel routing (above), tempo-synced workflow preferred.

---

## 7. Independent track lengths — IMPLEMENTED (v1, 2026-07-05)

User wants: **drum = 1 bar, chords = 8 bars, solo on top** — i.e. each part loops at
its own length. This is now a core v1 feature (RC-505 style), built additively on
the factory engine rather than the invasive rewrite feared earlier.

**Model.** The first *synced* recording defines the **base measure** (`g_length`
= 1 bar); a master `g_cycle` counts bars. Each track owns (state record):

| field | meaning |
|---|---|
| `st_len` | loop length in **samples** (authoritative for FREE tracks) |
| `st_mult` | loop length in **bars** (multiple of the base; 0 = free/unset) |
| `st_ppos` | current playback position inside its own loop (drives its LED) |
| `st_rectempo` | project tempo captured at record start |
| `st_sync` | `FREE` / `MEASURE_SYNC` (default) / `MASTER_SYNC` |
| `st_qmode` | quantize start/stop/rec-close: off / beat / bar (default bar) |
| `st_fixlen` | preset bar count — recording auto-closes at exactly N bars |
| `st_anchor` | `g_cycle` at record start (phase anchor for the loop window) |

- **MEASURE_SYNC** (default): rec press on a later track *arms* it (red flash);
  recording starts at the next base downbeat, closes snapped to a whole multiple
  of the base, playback phase-locked via `(g_cycle - anchor) % mult`.
  1-bar drums + 8-bar guitar stay bar-aligned and re-meet every 8 bars.
- **MASTER_SYNC**: same, but the loop window locks to the *global* bar-1 grid
  (`anchor = 0`).
- **FREE**: records immediately, keeps its exact sample length, runs its own
  position counter — never touches the grid.
- AllStart/AllStop preserve every track's own length; on AllStart all synced
  tracks restart aligned at bar 1.
- The base track can pre-set its length (e.g. 1 bar) via `st_fixlen`, closing at
  N bars of the tempo captured at record start.

**Actions** (dispatcher; Launchpad **row 2** pads 21–28, or the "Action trigger"
slider for MIDI-learn/automation): `SetCurrentTrackLength{1,2,4,8}Bars`,
`SetCurrentTrackSyncMode{Free,Measure,Master}`, `ToggleCurrentTrackSyncMode`.
They act on the *selected* track (col-8 select pad). Row-2 LEDs show the selected
track's bar count (green) and sync mode (amber).

**Tests**: `tests/test_track_lengths.py` runs the spec scenario (120 BPM: 1-bar
track loops 8× while the 8-bar track loops once; re-alignment; AllStop/AllStart
length preservation) against `tests/s505_model.py`, a sample-accurate Python
mirror of the engine arithmetic. Keep model and JSFX in sync when editing the
engine.

**Known limits (v1)**: global halve/double still operate on the base measure only
(mult tracks don't rescale); FREE→MEASURE with existing content applies to the
next recording; beat-quantized tracks use the free-position engine internally.

**Arm bridge (2026-07-05).** REAPER only passes live input through record-armed,
monitored tracks — unarmed source tracks made looper rows record silence. The JSFX
now publishes a per-channel "wants live input" bitmask (armed / recording /
count-in) to gmem namespace `Super505` (`[0]` heartbeat, `[1]` mask, `[2]` nchan);
`reaper/scripts/super505_arm_bridge.lua` (auto-started by `Scripts/__startup.lua`)
watches it and record-arms whichever tracks *send into* that looper channel — the
mapping follows the project routing, not track order. One-way: the bridge never
disarms (disarming would cut live monitoring through the looper). If a flagged
channel has no feeding send, it prints a console warning naming the missing send.

---

## 8. Other open items / candidate next features

- **Per-track volume + mute** — deferred in the original plan; now valuable for
  balancing 4 instruments. Natural next super505 feature (super8 has per-channel
  monitor/output to build on).
- **Save the `.rpp` project template** (multi-instrument routing + sync + count-in)
  and add it to the repo — we kept losing the session to crashes; do this early.
- **Utility row → Reaper actions** (Undo/Redo/Tap Tempo/Metronome/Save/All
  Start-Stop/Panic) via MIDI-learn (back up `reaper-kb.ini` first).
- **Guitar 2 input** hardware choice (onboard line-in vs UR22C vs another interface).
- **UR22C** swap-in when it arrives (one input-device change; template is
  input-source-agnostic since tracks record "Reaper input N").
- **Push** the local commit (HTTPS→SSH).
- Count-in polish (accent the final "go" beat), LED palette fine-tuning.

---

## 9. How to resume next session

1. Read this doc + `tasks/todo.md`.
2. Launch Reaper; if the Launchpad is stuck, `tools/lp_programmer.sh live` or replug.
3. If using the guitar, `tools/route_guitar.sh`.
4. Looper track must be armed + monitored for LEDs/looping to run.
5. Pick up the **§7 loop-length design discussion** and the **multi-instrument
   template** build-out.
