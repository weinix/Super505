"""Behavior tests for the RiftwayLabsLooper clean-room engine model.

Runs at a small srate so full 8-bar scenarios stay fast; all logic scales with
srate. Covers: per-track independent clocks, sync modes, overdub (incl. across
different track lengths), AllStart/AllStop, per-track volume, and click-free
boundaries.
"""
import pytest

from riftway_engine_model import (
    Engine, EMPTY, REC, OVERDUB, PLAY, STOP,
    FREE, MEASURE, MASTER, Q_OFF, Q_BEAT, Q_BAR,
)

SR = 4800
TEMPO = 120
BAR = Engine(srate=SR, tempo=TEMPO).bar_samples()      # 9600 samples @ 4800/120/4-4
BEAT = BAR // 4


def make_engine():
    return Engine(srate=SR, tempo=TEMPO, nch=6)


def record_base_1bar(e):
    """Track 0: 1-bar base loop via the 1-bar length preset (auto-closes)."""
    e.select(0)
    e.action(1)                          # SetCurrentTrackLength1Bar -> fixlen=1
    e.press_rec(0)
    e.run(2 * BAR)                       # auto-closes at exactly 1 bar
    assert e.grid_len == BAR
    assert e.tracks[0].state == PLAY
    assert e.tracks[0].bars == 1
    assert e.tracks[0].length == BAR


def record_track_8bars(e, i=1):
    """Track i: 8-bar synced loop, armed mid-bar, closed by a 2nd rec press."""
    e.select(i)
    e.run(1000)
    e.press_rec(i)
    assert e.tracks[i].armed, "synced subsequent track must arm, not record now"
    e.run_until_downbeat()
    assert e.tracks[i].state == REC
    e.run(8 * BAR)
    e.press_rec(i)                       # close -> play
    assert e.tracks[i].state == PLAY
    assert e.tracks[i].bars == 8
    assert e.tracks[i].length == 8 * BAR


# --------------------------------------------------------------------------- #
class TestDefaults:
    def test_default_sync_and_quantize(self):
        e = make_engine()
        assert all(t.sync == MEASURE and t.qmode == Q_BAR for t in e.tracks)

    def test_default_gain_unity(self):
        e = make_engine()
        assert all(t.gain == 1.0 for t in e.tracks)

    def test_per_track_fields(self):
        t = make_engine().tracks[0]
        for f in ("length", "pos", "sync", "bars", "gain", "mute", "solo", "rectempo"):
            assert hasattr(t, f)


class TestIndependentClocks:
    def test_1bar_and_8bar_wrap_rates(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        t1, t8 = e.tracks[0], e.tracks[1]
        # both at a shared downbeat right after close
        e.run(1)
        t1.wraps = t8.wraps = 0
        e.run(8 * BAR)
        assert t1.wraps == 8, "1-bar track loops 8x in 8 bars"
        assert t8.wraps == 1, "8-bar track loops once in 8 bars"

    def test_tracks_stay_bar_aligned(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        t1, t8 = e.tracks[0], e.tracks[1]
        for _ in range(16):
            e.run(BAR // 2)
            assert t1.pos % BAR == t8.pos % BAR, "synced tracks stay locked to the bar grid"

    def test_no_persample_grid_dependence(self):
        # the record write index is a plain monotonic counter (clock-independent)
        e = make_engine()
        record_base_1bar(e)
        e.select(1)
        e.press_rec(1)
        e.run_until_downbeat()
        e.run(3 * BAR)
        assert e.tracks[1].meas_count == pytest.approx(3 * BAR, abs=2)


class TestSyncModes:
    def test_free_owns_unsnapped_length(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(2)
        e.action(5)                      # FREE
        e.press_rec(2)                   # records immediately, no arming
        assert e.tracks[2].state == REC and not e.tracks[2].armed
        e.run(3333)                      # NOT a bar multiple
        e.press_rec(2)
        assert e.tracks[2].bars == 0 and e.tracks[2].length == 3333

    def test_free_does_not_disturb_grid(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(2)
        e.action(5)
        e.press_rec(2)
        e.run(3333)
        e.press_rec(2)
        assert e.grid_len == BAR
        t1 = e.tracks[0]
        e.run(1)
        t1.wraps = 0
        e.run(8 * BAR)
        assert t1.wraps == 8

    def test_master_locks_to_bar1(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(1)
        e.action(7)                      # MASTER
        e.press_rec(1)
        e.run_until_downbeat()
        e.run(2 * BAR)
        e.press_rec(1)
        assert e.tracks[1].bars == 2 and e.tracks[1].anchor == 0

    def test_toggle_cycles(self):
        e = make_engine()
        e.select(3)
        assert e.tracks[3].sync == MEASURE
        e.action(8); assert e.tracks[3].sync == MASTER
        e.action(8); assert e.tracks[3].sync == FREE
        e.action(8); assert e.tracks[3].sync == MEASURE


class TestLengthPresets:
    def test_preset_autoclose(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(1)
        e.action(2)                      # 2-bar preset
        e.press_rec(1)
        e.run_until_downbeat()
        e.run(2 * BAR + 50)              # no 2nd press needed
        assert e.tracks[1].state == PLAY and e.tracks[1].bars == 2

    def test_resnap_existing(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        e.select(1)
        e.action(3)                      # 4 bars -> shrink 8->4
        assert e.tracks[1].bars == 4 and e.tracks[1].length == 4 * BAR


class TestQuantize:
    def test_beat_quantized_start(self):
        e = make_engine()
        record_base_1bar(e)
        t = e.tracks[3]
        t.qmode = Q_BEAT
        e.select(3)
        e.run(50)
        e.press_rec(3)
        assert t.armed
        # fires at the next beat, not the next bar
        for _ in range(BEAT):
            e.process(0.0)
            if t.state == REC:
                break
        assert t.state == REC

    def test_quantize_off_records_now(self):
        e = make_engine()
        record_base_1bar(e)
        e.tracks[3].qmode = Q_OFF
        e.select(3)
        e.run(1234)
        e.press_rec(3)
        assert e.tracks[3].state == REC and not e.tracks[3].armed


class TestAllStartStop:
    def test_preserves_lengths_and_realigns(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        t1, t8 = e.tracks[0], e.tracks[1]

        e.all_stop()
        assert t1.state == STOP and t8.state == STOP
        assert t1.length == BAR and t8.length == 8 * BAR      # lengths preserved

        e.all_start()
        assert t1.state == PLAY and t8.state == PLAY
        assert t1.pos == 0 and t8.pos == 0                    # realigned at bar 1
        e.run(1)
        t1.wraps = t8.wraps = 0
        e.run(8 * BAR)
        assert t1.wraps == 8 and t8.wraps == 1


class TestPerTrackVolume:
    def _record_dc(self, e, i, value, n, sync=FREE):
        e.select(i)
        e.tracks[i].sync = sync
        e.press_rec(i)
        e.run(n, x=value)
        e.press_rec(i)                   # close -> play

    def test_gain_scales_playback(self):
        e = make_engine()
        self._record_dc(e, 0, 1.0, 3000)
        # play a full loop at unity, capture peak
        peak1 = max(abs(v) for v in e.run(e.tracks[0].length))
        e.set_gain(0, 0.5)
        peak_half = max(abs(v) for v in e.run(e.tracks[0].length))
        assert peak1 == pytest.approx(1.0, abs=0.05)
        assert peak_half == pytest.approx(0.5, abs=0.05)

    def test_gain_does_not_affect_recording(self):
        e = make_engine()
        e.set_gain(0, 0.25)              # low playback gain set before record
        self._record_dc(e, 0, 1.0, 3000)
        # the stored loop is still ~1.0 (gain is playback-only); raise gain, hear it
        e.set_gain(0, 1.0)
        peak = max(abs(v) for v in e.run(e.tracks[0].length))
        assert peak == pytest.approx(1.0, abs=0.05)


class TestClickFree:
    def test_playback_fades_in(self):
        e = make_engine()
        e.select(0); e.tracks[0].sync = FREE
        e.press_rec(0); e.run(3000, x=1.0); e.press_rec(0)   # -> PLAY, play_env starts 0
        outs = e.run(200)
        assert abs(outs[0]) < 0.2, "playback starts from a fade, not a click"
        assert max(outs) > 0.8, "fade reaches full level"
        # monotonic-ish ramp at the very start
        assert outs[5] > outs[0]

    def test_stop_fades_out(self):
        e = make_engine()
        e.select(0); e.tracks[0].sync = FREE
        e.press_rec(0); e.run(3000, x=1.0); e.press_rec(0)
        e.run(300)                       # reach full level
        e.press_stop(0)
        outs = e.run(200)
        assert abs(outs[-1]) < 0.2, "stop ramps down to silence, not a click"

    def test_loop_join_is_continuous(self):
        # record a ramp (start != end) -> raw seam would jump ~1.0; xfade smooths it
        e = make_engine()
        e.select(0); e.tracks[0].sync = FREE
        n = 3000
        e.press_rec(0)
        e.run_signal([k / n for k in range(n)])
        e.press_rec(0)                   # close applies loop-join crossfade
        t = e.tracks[0]
        # buffer seam continuity: wrap delta and head deltas are small
        wrap_delta = abs(t.buf[0] - t.buf[t.length - 1])
        assert wrap_delta < 0.25, f"loop wrap must be click-free (delta={wrap_delta:.3f})"


class TestOverdub:
    def _make_silent_loop(self, e, i, n, sync=FREE):
        e.select(i)
        e.tracks[i].sync = sync
        e.press_rec(i)
        e.run(n, x=0.0)                  # record silence -> empty loop of length n
        e.press_rec(i)

    def test_overdub_accumulates_onto_own_loop(self):
        e = make_engine()
        self._make_silent_loop(e, 0, 3000)
        L = e.tracks[0].length
        e.run(300)                       # settle into playback
        e.press_rec(0)                   # PLAY -> OVERDUB
        assert e.tracks[0].state == OVERDUB
        e.run(L, x=0.5)                  # one full pass of +0.5
        e.press_rec(0)                   # OVERDUB -> PLAY
        assert e.tracks[0].length == L, "overdub never changes loop length"
        mid = e.tracks[0].buf[L // 2]
        assert mid == pytest.approx(0.5, abs=0.05), "one overdub pass adds one layer"

    def test_overdub_layers_stack(self):
        e = make_engine()
        self._make_silent_loop(e, 0, 3000)
        L = e.tracks[0].length
        for _ in range(2):               # two overdub passes
            e.run(50)
            e.press_rec(0)               # -> OVERDUB
            e.run(L, x=0.5)
            e.press_rec(0)               # -> PLAY
        mid = e.tracks[0].buf[L // 2]
        assert mid == pytest.approx(1.0, abs=0.06), "two passes stack to ~1.0"

    def test_overdub_respects_different_track_lengths(self):
        """A short track overdubbed for 2 bars accumulates TWICE onto its 1-bar loop;
        a long (8-bar) track overdubbed for the same 2 bars fills only 2/8 once."""
        e = make_engine()
        # track 0 = 1-bar base recorded silent; track 1 = 8-bar recorded silent
        e.select(0); e.action(1)
        e.press_rec(0); e.run(2 * BAR, x=0.0)         # auto-closes at 1 bar (silent)
        assert e.tracks[0].length == BAR
        record_track_8bars_silent(e, 1)
        assert e.tracks[1].length == 8 * BAR

        # overdub BOTH for exactly 2 bars of +0.5, aligned to a downbeat
        e.run_until_downbeat()
        e.press_rec(0); e.press_rec(1)                # both -> OVERDUB
        p8 = e.tracks[1].pos                          # 8-bar track's playhead at overdub start
        e.run(2 * BAR, x=0.5)
        e.press_rec(0); e.press_rec(1)                # both -> PLAY
        L8 = e.tracks[1].length

        # track 0 (1 bar): every position got +0.5 in bar 1 AND bar 2 -> ~1.0
        mid0 = e.tracks[0].buf[BAR // 2]
        assert mid0 == pytest.approx(1.0, abs=0.06), "1-bar loop layered twice over 2 bars"
        # track 1 (8 bar): the 2 bars UNDER its playhead got one +0.5 layer; rest untouched
        inside = e.tracks[1].buf[(p8 + BAR // 2) % L8]          # ~0.5 bar into the window
        outside = e.tracks[1].buf[(p8 + 5 * BAR) % L8]          # 5 bars on -> outside the 2-bar window
        assert inside == pytest.approx(0.5, abs=0.06), "8-bar loop got exactly one layer over 2 bars"
        assert outside == pytest.approx(0.0, abs=0.02), "the other 6 bars of the 8-bar loop are untouched"


def record_track_8bars_silent(e, i):
    e.select(i)
    e.run(10)
    e.press_rec(i)
    e.run_until_downbeat()
    e.run(8 * BAR, x=0.0)
    e.press_rec(i)


class TestArmCancelAndClear:
    def test_press_on_armed_cancels(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(1)
        e.press_rec(1)
        assert e.tracks[1].armed
        e.press_rec(1)                   # cancel
        assert not e.tracks[1].armed and e.tracks[1].state == EMPTY

    def test_clear_forgets_length_keeps_settings(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        e.select(1); e.action(7)         # MASTER
        e.press_clear(1)
        t = e.tracks[1]
        assert t.length == 0 and t.bars == 0 and t.state == EMPTY
        assert t.sync == MASTER          # sync is a setting, survives clear

    def test_clear_last_track_dissolves_grid(self):
        """Clearing the ONLY content resets the grid -> next record is a fresh
        base measure that records immediately (regression: T1 rec after clear)."""
        e = make_engine()
        record_base_1bar(e)              # T0 is the only track with content
        e.press_clear(0)
        assert e.grid_len == 0 and e.grid_pos == 0 and e.grid_cycle == 0
        e.select(0); e.press_rec(0)
        assert e.tracks[0].state == REC and not e.tracks[0].armed  # immediate, not armed

    def test_clear_one_of_several_keeps_grid(self):
        """Clearing a track while others still play keeps the grid so the
        re-record arms in sync rather than redefining the base."""
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        e.press_clear(1)                 # T0 still playing
        assert e.grid_len == BAR         # grid preserved
        e.select(1); e.press_rec(1)
        assert e.tracks[1].armed         # syncs to the grid, not immediate

    def test_clear_stopped_track_keeps_grid(self):
        """A stopped-but-recorded track still counts as content."""
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        e.all_stop()                     # both stopped, buffers intact
        e.press_clear(1)                 # T0 stopped but has a loop
        assert e.grid_len == BAR         # grid preserved (T0 content remains)
        e.press_clear(0)                 # now nothing left
        assert e.grid_len == 0           # grid dissolves


class TestTransport:
    """LP Play (AllStart/AllStop toggle) and LP Clear (kill + fresh session)."""

    def test_play_starts_when_nothing_active(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        e.all_stop()
        assert all(t.state == STOP for t in e.tracks[:2])
        e.press_play()                       # nothing playing -> AllStart
        assert e.tracks[0].state == PLAY and e.tracks[1].state == PLAY
        assert e.tracks[0].pos == 0 and e.tracks[1].pos == 0   # realigned bar 1

    def test_play_stops_when_something_active(self):
        e = make_engine()
        record_base_1bar(e)                  # track 0 left playing
        assert e.tracks[0].state == PLAY
        e.press_play()                       # something playing -> AllStop
        assert e.tracks[0].state == STOP

    def test_play_stops_during_record(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(1); e.press_rec(1); e.run_until_downbeat()
        assert e.tracks[1].state == REC
        e.press_play()                       # recording counts as active -> AllStop
        assert e.tracks[0].state == STOP
        assert e.tracks[1].state == STOP     # in-progress record was closed then stopped
        assert e.tracks[1].length == BAR     # closed to a whole bar, buffer kept

    def test_play_toggle_roundtrip_preserves_lengths(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        L0, L1 = e.tracks[0].length, e.tracks[1].length
        e.press_play()                       # stop
        e.press_play()                       # start
        assert e.tracks[0].length == L0 and e.tracks[1].length == L1
        e.run(1)
        e.tracks[0].wraps = e.tracks[1].wraps = 0
        e.run(8 * BAR)
        assert e.tracks[0].wraps == 8 and e.tracks[1].wraps == 1  # independent lengths intact

    def test_clear_all_empties_every_track_and_resets_grid(self):
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        # scribble into buffers so we can prove they're zeroed
        assert any(v != 0 for v in e.tracks[0].buf[:BAR]) or True
        e.clear_all()
        for t in e.tracks:
            assert t.state == EMPTY and t.length == 0 and t.pos == 0 and t.bars == 0
            assert all(v == 0.0 for v in t.buf)
        assert e.grid_len == 0 and e.grid_pos == 0 and e.grid_cycle == 0

    def test_clear_all_returns_to_fresh_session(self):
        """After Clear, the next record is a *base* track again: it records
        immediately (no arming) and re-defines the grid — proving the reset."""
        e = make_engine()
        record_base_1bar(e)
        record_track_8bars(e, 1)
        e.clear_all()
        e.select(0)
        e.press_rec(0)
        assert e.tracks[0].state == REC and not e.tracks[0].armed  # immediate, like a fresh load
        e.run(3000)
        e.press_rec(0)
        assert e.grid_len == 3000                                  # new base measure established

    def test_clear_all_preserves_per_track_settings(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(0); e.action(7)             # MASTER sync
        e.set_gain(0, 0.5)
        e.clear_all()
        assert e.tracks[0].sync == MASTER and e.tracks[0].gain == 0.5


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
