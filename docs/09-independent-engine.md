# 09 — Independent Engine (clean-room rewrite): architecture & spec

Status: **P1 complete** — behavioral spec + sample-accurate reference model
(`tests/riftway_engine_model.py`) + tests (`tests/test_engine.py`, 25 passing).
The live JSFX engine is untouched. P2 (fresh JSFX implementation) follows only
after this spec is reviewed.

## Why

The current `reaper/effects/RiftwayLabsLooper` engine is derived from Cockos
**Super8 (LGPL)**; the product cannot shed the LGPL until the inherited DSP core
is replaced by an independent implementation. Goal: an engine that (a) owes
nothing to Super8's code expression and (b) is genuinely better. Decisions
(2026-07-06): re-architect (not copy), stay in JSFX/EEL2, pragmatic independent
creation.

## Independent-creation process note (the "clean-room" record)

- This engine is specified by **`tests/riftway_engine_model.py`**, written from the
  **RiftwayLabs feature requirements + RC-505 looper behavior + the JSFX/EEL2 &
  REAPER platform contract** — NOT by transcribing Super8's source. It is a fresh
  architecture (per-track clocks) with its own naming, structure, and decomposition.
- Copyright protects Super8's specific *expression*, not the *idea* of a looper or
  its algorithms. The reference model and the P2 JSFX are an independent
  implementation of the same functionality, not a derivative work.
- Reused code is only **RiftwayLabs-original** (LED engine, arm bridge, action
  dispatcher, per-track clear/mute/solo, count-in) — already ours.
- Platform glue that is not creative expression (CC/PC MIDI normalization, the
  `<? ?>` per-channel codegen idiom, calling `spl`/`midisend`/`gmem`/`gfx_*`/
  `export_buffer_to_project`) is reimplemented fresh as standard technique.
- Keep this note + the model/tests as evidence of independent creation.
- **Not legal advice** — a one-time IP-lawyer review is warranted before selling.

## Architecture

**Per-track independent clocks.** Every track owns
`{buf, length, pos, state, sync, bars, fixlen, qmode, gain, mute, solo,
envelopes, anchor, rectempo}` and advances its **own** `pos` by 1 per sample,
wrapping at `length`. There is **no global-grid math in the per-sample hot path** —
the record write index is a plain monotonic counter. A light shared grid
(`grid_len`, `grid_pos`, `grid_cycle`) is consulted ONLY at discrete events:
establishing the base measure, firing a quantized record start, and computing
phase at record-close / AllStart. Synced tracks stay phase-locked **by
construction**: `length` is an integer multiple of `grid_len` and all tracks
advance at the same sample rate, so alignment holds without per-sample re-derivation.

**Staged per-sample pipeline** (replaces Super8's hybrid `process`):
```
advance grid (events only)
for each track:
  update rec/play envelopes (equal-power, click-free)
  REC:     buf[meas_count++] = in * recgain            # monotonic, clock-independent
  OVERDUB: buf[pos] += in * recgain ; read = buf[pos]  # accumulate onto own loop
  PLAY:    read = buf[pos]
  read *= playgain(fade) * gain                         # per-track VOLUME
  read *= mute/solo gate
  out += read ; pos++ ; wrap at length
```

**State machine:** `EMPTY → REC → (PLAY|OVERDUB) → STOP`; `STOP → PLAY` restarts at
0; `any → clear → EMPTY`. Rec pad cycles EMPTY→REC→(close)PLAY→OVERDUB→PLAY.

**Length policy per track (the marquee feature).**
- **FREE:** records immediately; `length` = exact recorded samples (beat-snapped if
  `qmode=BEAT` and a grid exists); owns its clock; `STOP→PLAY` restarts at 0.
- **MEASURE (default):** the first synced recording defines the **base measure**
  (`grid_len`); later MEASURE tracks **arm** and start on the next grid downbeat,
  close snapped to whole bars (or the exact `fixlen` preset), and phase-lock to
  their own start (`anchor` = start cycle).
- **MASTER:** like MEASURE but phase-locked to global bar 1 (`anchor = 0`).
- `fixlen` (1/2/4/8-bar presets) auto-closes recording at exactly N bars; the base
  track auto-closes at N bars of the captured tempo.

**Fades / click-free boundaries.**
- **Equal-power** (`sin(env·π/2)`) fades on rec-in/out and play-in/out (state edges).
- **Linear** crossfade at the loop join on record-close (`a·head + (1−a)·tail`) —
  linear, not equal-power, because a loop's head/tail are the *same* correlated
  recording, so equal-power would overshoot (√2 bump); linear preserves level.

**Per-track volume.** `gain` (default 1.0) scales **playback only** — it never
affects what is recorded or overdubbed. Mute/solo are separate output gates.

**Buffer model & memory budget.** One fixed buffer per track, sized to an equal
static slice of JSFX memory: `max_len = (maxmem_slots − overhead) / nch` samples
(1 double slot = 1 sample). JSFX `maxmem` MB → `maxmem × 131072` slots. At the
256 MB default with `nch=6`: ≈ **5.59 M samples/track ≈ 116 s @ 48 kHz per loop**.
Equal static slices are chosen for determinism and EEL2's flat-memory reality (no
malloc); users trade length vs. channel count via the `maxmem` config (64 MB–1 GB).
Recording is capped at `max_len` (it stops/ignores input beyond the slice).

## Overdub with different track lengths (exact behavior)

Overdub is **per-track and length-local**: pressing rec on a PLAYING track →
OVERDUB, which does `buf[pos] += in·recgain` at that track's own `pos`, wrapping at
that track's own `length`. Consequences:
- Overdub **never changes `length`** (only first-pass REC defines length).
- A **short** loop overdubbed for longer than its length **layers repeatedly**: a
  1-bar loop overdubbed for 2 bars adds the input onto the *same* buffer positions
  twice (each position accumulates both passes).
- A **long** loop overdubbed for less than its length fills only the covered span
  **once**, starting at wherever its playhead was; the rest is untouched.
- Overdubs **stack additively** (no auto-normalization — RC-505/looper convention);
  per-track `gain` and the mixer manage levels. Punch-in/out use the rec envelope
  so a layer never clicks at its start/end.
- Tracks of different lengths overdub **independently** — each accumulates onto its
  own buffer at its own position; they never cross-contaminate.

## Reused RiftwayLabs assets (bind to new fields in P2)
LED engine (`state`/`pos`/`length`), arm bridge + gmem want-mask, `rl_action`
dispatcher (**FCB1010 actions land here**), per-track clear/mute/solo, count-in.

## Verification
`cd tests && pytest` — `test_engine.py` (25) + `test_track_lengths.py` (20, the
legacy engine) all green. New tests cover independent clocks, sync modes,
quantize, length presets, AllStart/AllStop, per-track volume, click-free
boundaries, and overdub across different track lengths.
