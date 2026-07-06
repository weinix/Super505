# 05 — Open Decisions (resume blockers)

Two decisions are still open. Both were raised 2026-06-10; you chose to pause and
document until the Launchpad is connected. Capture your answers here when we resume.

## Decision 1 — DrivenByMoss vs RiftwayLabsLooper on the `LPProMK3 MIDI` port

DrivenByMoss currently owns `LPProMK3 MIDI` as a **global** Reaper control surface.
RiftwayLabsLooper needs that same port; one MIDI port = one consumer. Options:

- **(Recommended) Toggle DBM off for RiftwayLabsLooper.** Disable the DrivenByMoss
  Launchpad Pro Mk3 surface (Reaper → Preferences → Control/OSC/web) while using
  RiftwayLabsLooper; re-enable for normal DBM use. Fully reversible, nothing deleted.
- **Use the separate DAW port.** Keep DBM on MIDI, run RiftwayLabsLooper on `LPProMK3 DAW`.
  Avoids the toggle but the DAW port behaves differently in Programmer mode and is
  less reliable; may still conflict.
- **DBM rarely used.** Leave the DBM surface disabled by default and make RiftwayLabsLooper
  the primary Launchpad setup.

**Your answer:** _pending — to confirm when Launchpad is connected._

## Decision 2 — Per-track Clear

Super8 only has a global "kill all" (no per-track clear). RC-505 MVP wants per-track
Clear on Row 3.

- **(Recommended) Add real per-track clear** to the RiftwayLabsLooper JSFX (each Row-3 pad
  erases only its track). More JSFX work, matches the spec.
- **MVP: Clear All only.** Map one pad to Super8's existing global "kill" now, add
  true per-track clear later.

**Your answer:** **RESOLVED — real per-track clear implemented** (`st_note5` +
`chan_clear()` in RiftwayLabsLooper).

---

## Status update (2026-06-21)

Both decisions above are resolved: **Decision 1 is moot** (DrivenByMoss is
uninstalled on the `bmini` dev machine — no port conflict), and **Decision 2 = real
per-track clear** (built).

> **2026-06-27 update — Decision 1 is NOT moot on the `sun` machine.** This machine
> has DrivenByMoss installed and active (`csurf_1=DrivenByMoss4Reaper`); it claims the
> Launchpad and silently eats every pad press, so RiftwayLabsLooper gets no MIDI. Resolution
> taken = **(Recommended) toggle DBM off**: Prefs → Control/OSC/web → Remove
> `DrivenByMoss4Reaper` (reversible). See `docs/07` §"Manual steps" item 2. The core looper is working — see
[06-build-progress-and-design.md](06-build-progress-and-design.md). The new open
**design** question is per-channel loop length (§7 of doc 06): accept the
`div`-subdivision model vs. pursue truly independent lengths.

---

## Resume checklist

- [ ] Launchpad plugged in and enumerating (`lsusb`, `aconnect -l`, `amidi -l`)
- [ ] Confirm Reaper MIDI backend (ALSA vs JACK) and exact port name
- [ ] Decision 1 answered
- [ ] Decision 2 answered
- [ ] Proceed with build order in [03-architecture-proposal.md](03-architecture-proposal.md)
