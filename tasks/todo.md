# Super505 — Build Plan (resume)

Status: **plan written, awaiting approval to build.** Nothing in `~/.config/REAPER`
has been modified yet.

## Context deltas since the 2026-06-10 design (verified live 2026-06-20)

- **Launchpad Pro MK3 is now connected.** USB `1235:0123`. ALSA ports:
  `hw:3,0,0` = LPProMK3 MIDI (our surface), `hw:3,0,1` = DIN, `hw:3,0,2` = DAW.
  (Doc 01/04 assumed the `hw:MK3` alias — real name is `hw:3,0,0`.)
- **DrivenByMoss is gone.** `UserPlugins/` is empty, no `DrivenByMoss*` configs.
  → **Decision 1 (port conflict) is moot.** Super505 owns `LPProMK3 MIDI` freely.
- **Decision 2 answered: real per-track clear** (user choice 2026-06-20).
- No Reaper extensions installed (no SWS/js_ReaScriptAPI/ReaImGui/ReaPack) →
  LED feedback comes from the JSFX, as designed.
- Reaper 7.72, not currently running. Super8 present; super505 not forked yet.

### Dev on `bmini` (no UR22C) — 2026-06-20

Working on `bmini`: has Reaper 7.72, super8 JSFX, and the Launchpad (`hw:3,0,0`),
but **no UR22C** (audio input only). Everything is buildable except the template's
final input-device assignment and end-to-end *audio*-recording verification, which
wait for the UR22C. LED + state-machine logic is verifiable with the Launchpad alone.
Template will use a **parameterized/placeholder audio input**, repointed to the
UR22C later. Keep artifacts **device-name based**, not card-index based (card
numbers differ per machine).

## Note / pad map (Launchpad Programmer mode, channel 1)

| Function            | Pads (track 1..5) | JSFX field |
|---------------------|-------------------|------------|
| Rec/Overdub/Play    | 81 82 83 84 85    | note1      |
| Stop                | 71 72 73 74 75    | note2      |
| Clear (per-track)   | 61 62 63 64 65    | note5 *(new)* |
| Reverse             | 41 42 43 44 45    | note4      |
| Select/Monitor      | 31 32 33 34 35    | note3      |
| Utility row         | 11..18            | Reaper MIDI-learn |

LED out (to same pads): Note-On ch1=static, ch2=flashing, ch3=pulsing; velocity=palette index.
Colors: empty=off(0), rec=red, overdub=amber, play=green, stopped-w/content=dim, first-pass=red flashing(ch2). Exact indices locked during bring-up.

---

## Tasks

### 0. Bring-up / de-risk (no Reaper files touched)
- [x] `tools/lp_programmer.sh` (amidi, auto-detects `hw:3,0,0`): Programmer mode + paint layout — **layout confirmed by user 2026-06-20**.
- [ ] Confirm Reaper MIDI backend in use (ALSA vs JACK) and the matching port name form.
- [~] Palette indices: provisional standard LP Pro MK3 values baked as editable `C_*` constants; `ramp` available to fine-tune live.

### 1. Fork super505 JSFX (additive; super8 untouched) — CODE COMPLETE, pending live compile-check
- [x] Copy `Effects/loopsamplers/super8` → `Effects/loopsamplers/super505`; new `desc:`.
- [x] **Note remap**: init loop now assigns note1=81–85, note2=71–75, note3=31–35, note4=41–45, note5=61–65 (tracks 1–5; channels 6–8 off/128).
- [x] **Per-track clear**: added `st_note5` + `st_num`=15, set in `init`, handled in `onmsg` → new `chan_clear()` erasing only that channel's buffer, leaving `g_length`/other tracks intact. (note5 not serialized — always re-init to 61–65 defaults, which is what we want.)
- [x] **Drop pass-through echo**: both `midirecv ? midisend` echoes replaced with `midirecv` only.
- [x] **LED engine** in `@block`: Rec/Play pad (81–85) reflects state via send-on-change `mem_led_last[]`.
- [x] **Programmer-mode entry + static pads**: sysex via `midisend_buf` on first @block + static paint of stop/clear/reverse/select/utility rows.
- [x] **Loaded in Reaper — compiles clean; note remap confirmed (GUI shows pads 81/71/31…, ch6-8 off).**
- [x] **LED feedback verified live**: static rows paint correct colors (stop=green, clear=amber, reverse=blue, select=white; Rec/Play off when empty). Self-healing repaint works.
- [x] **Functional test: record/replay verified on all 5 columns** (after audio routing fixes below). Dynamic Rec/Play LEDs cycle live.
- [~] Per-track clear: implemented; quick confirm still pending.

**Audio path solved live (was the per-channel input/output gotcha):**
- Super505 records/plays **each loop on its own channel** (loop N ↔ channel N).
- INPUT: "Mic In" track (Yeti) → 3 stereo sends to the 8-ch Super505 track at dest **1/2, 3/4, 5/6** → feeds loop channels 1–5.
- OUTPUT: new **`super505_mixdown`** JSFX (8 in/out pins, sums ch1-8 → stereo 1/2) inserted **after** super505 → all loops reach the master.
- New JSFX added mid-session isn't indexed until Add-FX browser reopens (or Reaper restart).

**Live setup notes (bmini, verified):**
- Reaper MIDI backend = JACK/Midi-Bridge. Routing confirmed via `pw-link`: `REAPER:MIDI Output 2 → LPProMK3 MIDI (playback)` (LEDs out), `LPProMK3 MIDI (capture) → REAPER:MIDI Input 2` (pads in).
- **FX only runs `@block` when the track is processing** → the looper track MUST be record-armed + input-monitoring ON (or transport playing) for LEDs/looping to work.
- Reloading the JSFX after an external edit = remove/re-add FX (title animates "Super505" = new code live).
- Audio input available here = **Blue Yeti mic** (no UR22C needed for a real loop test).

### 2. Reaper project template (additive)
- [ ] `ProjectTemplates/Super505.RPP` + copy into this repo (`reaper/Super505.RPP`).
- [ ] Tracks: **Audio In** (UR22C, rec-armed, input monitor, low latency) → **Super505 Looper** (super505 JSFX) → optional FX → optional master limiter.
- [ ] Routing: Launchpad `LPProMK3 MIDI` input → looper track input (ch1); looper track **HW MIDI output → LPProMK3 MIDI** so LED Note-Ons reach the pads.
- [ ] Click routable to a separate HW out (headphones) if desired.

### 3. Utility-row → Reaper action mapping
- [ ] Back up `reaper-kb.ini` first.
- [ ] MIDI-learn utility pads (11–18): All Start/Stop, Undo, Redo, Tap Tempo, Metronome toggle, Save, Panic. (Row 7 track-FX deferred — awkward without js_ReaScriptAPI.)

### 4. Test checklist (live)
- [ ] Rec→Overdub→Play→Stop→Clear per track; All Start/Stop; Undo/Redo.
- [ ] LEDs match state on all transitions incl. first-pass blink; no MIDI flooding.
- [ ] Save/load template round-trips routing + MIDI assignments.

### 5. Docs
- [ ] Update `docs/05-open-decisions.md` (both decisions resolved) and README status.

### Live session add-ons (bmini, 2026-06-20)
- [x] **Audio output fold**: `super505_mixdown` JSFX (repo: `reaper/effects/`) sums loop ch1-8 → stereo; all 5 columns audible.
- [x] **Guitar input**: enya **E-SP1** USB interface routed to Reaper inputs via PipeWire (`tools/route_guitar.sh`, run after reboot/replug). Yeti still available (`--keep`). Track records "Reaper input 1/2" so the template is input-source-agnostic (guitar / Yeti / future UR22C).
- [x] **Latency**: PipeWire quantum 1024→**256** (~5 ms). Persistent drop-in `~/.config/pipewire/pipewire.conf.d/99-super505-lowlatency.conf` (repo copy in `reaper/`). Revert: delete file / `force-quantum 0`.
- [ ] **Save Reaper project + "Super505" project template; copy `.rpp` into repo; git commit checkpoint.** ← next
- [ ] Confirm per-track Clear; then utility-row Reaper actions.

## Deferred (post-MVP)
Reverse polish, true silent mute, per-track volume/faders, per-track FX (Row 7),
phrase-memory scenes, backing-track clips, Godin MIDI-guitar routing.

## Safety rules (project conventions)
Additive only. Back up any existing Reaper file (`.bak`) before touching. super8 never modified. Linux paths only.

## Risks to validate live
sysex/`midisend_str` from JSFX; LED update rate; exact palette indices; Reaper ALSA-vs-JACK port name; UR22C latency under PipeWire.

## Review / session checkpoint (2026-06-21)

Core looper works end-to-end (5 columns, rec/overdub/play/stop/clear, LEDs, audio
in→loops→mixdown→master, count-in, low latency). Full status, architecture, runtime
gotchas, and the open design questions are documented in
**`docs/06-build-progress-and-design.md`** — the cold-resume reference.

**Main thing to discuss next session:** the loop-length model (per-channel `div`
subdivisions of a shared master length vs. truly independent lengths) — doc 06 §7.
Then: multi-instrument template (drum/gtr1/gtr2/mic → ch1–4), per-track volume/mute,
save `.rpp` template, utility row, git push (HTTPS→SSH).

## v1 independent track lengths (2026-07-05) — CODE COMPLETE, pending live verify

Implemented per doc 06 §7 (now the design record). Summary:
- [x] Per-track `st_len`/`st_mult`/`st_ppos`/`st_rectempo`/`st_sync`/`st_qmode`/`st_fixlen`.
- [x] Sync modes FREE / MEASURE_SYNC (default) / MASTER_SYNC; quantize off/beat/bar (default bar).
- [x] Action dispatcher: `SetCurrentTrackLength{1,2,4,8}Bars`, `SetCurrentTrackSyncMode{Free,Measure,Master}`,
      `ToggleCurrentTrackSyncMode` — Launchpad row 2 (notes 21–28) + "Action trigger" slider.
- [x] Launchpad col-8 status shows each track's OWN loop position (`st_ppos`); row-2 LEDs
      show selected track's bars (green) + sync mode (amber).
- [x] AllStart/AllStop preserve per-track lengths; kill/clear forget lengths but keep settings.
- [x] Serialization: sync/qmode/fixlen persist per track (back-compat guarded).
- [x] Tests: `cd tests && pytest` — 18 passing (sample-accurate engine model, 120 BPM spec scenario).
- [x] Deployed to `~/.config/REAPER/Effects/loopsamplers/super505`
      (backup: `super505.pre-v1len.bak`).
- [x] **Live verify**: 1-bar drum + 8-bar guitar independent lengths confirmed working (2026-07-05).
- [ ] Live verify remaining: FREE mode, row-2 action pads, MASTER_SYNC, AllStart/AllStop.

## Arm bridge (2026-07-05) — CODE COMPLETE, pending live verify

Pressing rec on looper rows 1-5 auto record-arms the REAPER track(s) feeding that
looper channel (fixes "rows 3-5 record silence because source tracks weren't armed").
- [x] JSFX publishes to gmem namespace `Super505`: [0]=heartbeat, [1]=want-input
      bitmask (armed / recording / count-in channels), [2]=nchan.
- [x] `reaper/scripts/super505_arm_bridge.lua`: defer loop, on a rising mask bit
      finds the track(s) whose receive on the looper covers that channel (mapping
      follows the SENDS, not track order) and sets I_RECARM + I_RECMON. One-way:
      never auto-disarms. Warns in the console if a channel has no feeding send.
- [x] `reaper/scripts/__startup.lua` auto-starts the bridge at REAPER launch.
- [x] Deployed: JSFX + both scripts to `~/.config/REAPER` (Scripts/, Effects/).
- [x] Model tests for the gmem mask protocol (20 passing total).
- [ ] **Live verify**: restart REAPER (or Actions -> run `super505_arm_bridge.lua`
      once) + re-add the FX; press rec on row 3/4 -> Vocal/Bass tracks arm.
      NOTE: sends must exist (Bass Guitar still needs a send -> looper ch, see
      routing fix); the bridge prints a console warning if a send is missing.
