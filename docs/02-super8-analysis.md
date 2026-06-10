# 02 — Super8 JSFX Analysis

Source: `~/.config/REAPER/Effects/loopsamplers/super8` (factory Cockos JSFX, 1658 lines).
This is the authoritative teardown the Super505 fork is based on.

## 1. Pins / I/O

- `config: nch "Channels"` default **8** (configurable 1/2/4/8/12/16/24/32/48).
- Inputs: `nch` audio inputs (1 per channel).
- Outputs: `nch` audio outputs + 2 extra:
  - `out_pin: monitor output` (selected-channel monitor)
  - `out_pin: click output` (metronome)
- For Super505 we use channels **1–5** (5 RC-505 tracks); channels 6–8 unused.

## 2. MIDI input model

Super8 reads MIDI in `@sample` via `midirecv` and reacts to:

- **Note-On, channel 1 only** (`0x90`), velocity > 0.
- **CC (`0xb0`)** is internally remapped to `note + 129`.
- **Program Change (`0xc0`)** remapped to `note + 129*2`.
- So a "MIDI assignment" value 0–127 = note, 129–256 = CC, 258+ = PC.
  `128`, and `129*3`+ = **OFF / unassigned**.
- **Channel is fixed to 1.** Messages on other channels are ignored (they only
  match the raw status byte `0x90`/`0xb0`/`0xc0`). The Launchpad must therefore
  send on **MIDI channel 1**.

MIDI assignments are user-remappable in the JSFX UI (right-click a value tweaker
to cycle note/CC/PC/off; ctrl+right-click to learn the last received event).

## 3. Per-channel state machine

Per channel `st_state` (`mem_stlist[... + st_state]`):

| Value | Meaning |
|-------|---------|
| 0 | stopped / empty (off) |
| 1 | playing |
| 2 | recording (and overdubbing) |

`st_dirty > 0` ⇒ the channel buffer holds recorded audio (loop exists).
`g_firstrec != 0` ⇒ first-pass recording, i.e. **loop length not set yet**
(this is the "still defining the loop" window — useful for the *blinking* LED).
`g_length` = current global loop length in samples (all channels share it).

### Transitions (per channel, from `onmsg`)

- **note1** (rec/play cycle):
  - state 0 → **2** (start recording)
  - state 2 with length set → **1** (recording done → play)
  - state 2 first-pass → set length, continue (overdub)
  - This single button is RC-505 **Record → Overdub → Play**.
- **note2** (stop/play toggle):
  - state 2, or (state 0 with content) → **1** (play)
  - else → **0** (stop)
- **note3**: toggle "selected for monitoring" (`g_chan_selected`).
- **note4**: reverse the loop (`reverse()`).

Linked channel pairs (stereo) follow each other via `get_linked_rec`.

## 4. Default MIDI note map (channel 1)

Computed from the init loop (`ch%d.init`, starting note `a=36`, stride +2 except
+3 after channels 2/5/7). `note3` and `note4` default **OFF (128)**.

| Channel | note1 (Rec/Play) | note2 (Stop/Play) | note3 (Select) | note4 (Reverse) |
|--------:|:----------------:|:-----------------:|:--------------:|:---------------:|
| 1 | 36 | 37 | off | off |
| 2 | 38 | 39 | off | off |
| 3 | 42 | 43 | off | off |
| 4 | 44 | 45 | off | off |
| 5 | 46 | 47 | off | off |
| 6 | 50 | 51 | off | off |
| 7 | 52 | 53 | off | off |
| 8 | 56 | 57 | off | off |

(The gaps — 40,41,48,49,54,55 — match a drum-pad layout for the unassigned
select/reverse notes.) **Super505 will reassign all of these** to Launchpad
Programmer-mode pad notes.

## 5. Global / utility actions

Stored in `mem_gen_cfg`, all default **OFF (128)** unless noted — i.e. you must
assign a note/CC to use them:

| Name | Internal | Effect |
|------|----------|--------|
| `play all` | `cfgp_playall` | Play every channel with content, or stop all if all already playing — **All Start/Stop** |
| `rec/play selected` | `cfgp_playsel` | Cycle the selected channel stop/rec/play |
| `kill` | `cfgp_reset` | **Clear ALL** channels (full reset) |
| `halve` | `cfgp_halve` | Halve loop length |
| `double` | `cfgp_double` | Double loop length (repeat content) |
| `double no rep` | `cfgp_double_norep` | Double, no repeat |
| `x-fade shortened` | `cfgp_xfade` | Crossfade loop boundary |
| `add to project` | `cfgp_export` | Render active channels to project tracks |

Non-MIDI config: `gate` (start-rec gate dB), `fade` (xfade ms), `clickcnt`
(loop length in clicks), `vclick`, `offs`/`length` (freeform trim), `latch`
(defer commands to next loop boundary), `link` (stereo pairing), `div` (subdivide).

## 6. Sync modes (`slider1` / `cfgp_sync`)

- **0 = off** — classic freeform; loop length = first recording length.
- **1 = project** — loop length locked to project tempo × click count; syncs to
  playback position when transport runs.
- **2 = playback** — full transport sync.

`slider4` = **Click count / length** (loop length in clicks / metronome divisions).

These two sliders are the **only state Reaper can read/write** on Super8.

## 7. Hard limitations (why we fork to Super505)

1. **No LED / MIDI feedback output.** It only echoes received MIDI
   (`midirecv ? midisend`). There is no way to reflect loop state on a controller.
2. **No exposed per-channel state.** No `gmem`, no extra sliders — Reaper/ReaScript
   can't see which channel is recording/playing/empty.
3. **No per-channel Clear.** Only global `kill` (clear all). RC-505 per-track
   Clear does not exist.
4. **No per-channel mute/volume that preserves loop position.** "Stop" halts the
   channel; there's no silent-but-running mute like the RC-505.
5. **Channel-1-only MIDI**, fixed status bytes — controller must conform.
6. **Pass-through echo** of incoming MIDI conflicts with repurposing the MIDI
   output for LED control (it would re-light pads with press velocities).

## 8. What Super505 (fork) will change — summary

Additive copy `super505`, original `super8` untouched:

- **Remap notes** to Launchpad Pro MK3 Programmer-mode pad numbers for 5 tracks.
- **Add per-channel Clear** command (new note per channel).
- **Add LED feedback**: in `@block`, emit Note-On to the Launchpad reflecting each
  channel's state (red rec / amber overdub / green play / dim stopped-with-content
  / off empty / blink while `g_firstrec`).
- **Send Programmer-mode entry sysex** on init; light utility pads static.
- **Drop the blind pass-through echo** (replace with deliberate LED output).
- (Post-MVP) optional per-channel mute/volume.

Details and routing in [03-architecture-proposal.md](03-architecture-proposal.md).
