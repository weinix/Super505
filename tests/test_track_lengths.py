"""V1 independent-track-length tests for the RiftwayLabsLooper loop-sync engine.

Scenario from the spec, at 120 BPM (48 kHz, 4/4 -> 1 bar = 96000 samples):
  - Track 1 records a 1-bar loop and immediately loops every bar.
  - Track 2 records 8 bars while track 1 keeps looping, then loops every 8 bars.
  - Track 1 loops 8x while track 2 loops 1x; both re-align at bar 1 after 8 bars.
  - AllStop/AllStart preserves each track's own loop length.

These run against tests/riftwaylabs_looper_model.py, a sample-accurate mirror of the JSFX
engine arithmetic in reaper/effects/RiftwayLabsLooper.
"""
import pytest

from riftwaylabs_looper_model import Engine, FREE, MEASURE_SYNC, MASTER_SYNC, Q_BEAT

SR = 48000
BAR = 96000          # 1 bar @ 120 BPM, 4/4, 48 kHz
BEAT = BAR // 4


def make_engine():
    return Engine(srate=SR, tempo=120)


def record_base_1bar(e):
    """Track 1: 1-bar drum loop via the SetCurrentTrackLength1Bar preset."""
    e.select(0)
    e.action(1)                    # SetCurrentTrackLength1Bar
    e.press_rec(0)
    e.run(2 * BAR)                 # recording auto-closes at exactly 1 bar
    assert e.g_length == BAR, "base measure must close at exactly 1 bar"
    assert e.tracks[0].state == 1
    assert e.tracks[0].mult == 1
    assert e.tracks[0].slen == BAR


def record_track2_8bars(e):
    """Track 2: 8-bar guitar loop, armed mid-bar, closed by a 2nd rec press."""
    e.run(1000)                    # somewhere mid-bar
    e.press_rec(1)
    assert e.arm_mask & 2, "track 2 must arm, not record immediately"
    e.run_until_downbeat()
    assert e.tracks[1].state == 2 and e.tracks[1].meas_state == 1, \
        "armed track must start recording at the downbeat"
    e.run(8 * BAR)                 # record exactly 8 bars
    e.press_rec(1)                 # close -> play
    t2 = e.tracks[1]
    assert t2.state == 1
    assert t2.mult == 8
    assert t2.slen == 8 * BAR


class TestDefaults:
    def test_default_sync_mode_is_measure_sync(self):
        e = make_engine()
        assert all(t.sync == MEASURE_SYNC for t in e.tracks)

    def test_per_track_state_fields_exist(self):
        e = make_engine()
        t = e.tracks[0]
        # loop length (samples + bars), position, record tempo, sync, quantize
        for field in ("slen", "mult", "ppos", "rectempo", "sync", "qmode"):
            assert hasattr(t, field)


class TestScenario120Bpm:
    """The required spec scenario."""

    def test_track1_loops_8x_while_track2_loops_once(self):
        e = make_engine()
        record_base_1bar(e)
        record_track2_8bars(e)

        t1, t2 = e.tracks[0], e.tracks[1]
        # the moment after close is a shared downbeat: both at position 0
        assert e.g_pos == 0
        e.run(1)
        assert t1.l_pos == 0 and t2.l_pos == 0

        t1.wraps = t2.wraps = 0
        e.run(8 * BAR)             # exactly 8 bars
        assert t1.wraps == 8, "1-bar track must loop 8 times in 8 bars"
        assert t2.wraps == 1, "8-bar track must loop once in 8 bars"
        # both align again at bar 1 after 8 bars
        assert t1.l_pos == 0 and t2.l_pos == 0

    def test_tracks_stay_bar_aligned_throughout(self):
        e = make_engine()
        record_base_1bar(e)
        record_track2_8bars(e)
        t1, t2 = e.tracks[0], e.tracks[1]
        for _ in range(16):        # check every half bar for 8 bars
            e.run(BAR // 2)
            # both tracks' positions refer to the same processed sample, so
            # within-bar offsets must match exactly
            assert t1.l_pos % BAR == t2.l_pos % BAR, \
                "8-bar loop must stay locked to the shared bar grid"

    def test_allstop_allstart_preserves_each_tracks_length(self):
        e = make_engine()
        record_base_1bar(e)
        record_track2_8bars(e)
        t1, t2 = e.tracks[0], e.tracks[1]

        e.all_start_stop()         # AllStop
        assert t1.state == 0 and t2.state == 0
        e.run(10 * 256)            # idle blocks pass; master transport resets
        assert t1.mult == 1 and t1.slen == BAR
        assert t2.mult == 8 and t2.slen == 8 * BAR

        e.all_start_stop()         # AllStart
        assert t1.state == 1 and t2.state == 1
        e.run(1)
        assert t1.l_pos == 0 and t2.l_pos == 0, \
            "AllStart must restart both tracks aligned at bar 1"

        t1.wraps = t2.wraps = 0
        e.run(8 * BAR)
        assert t1.wraps == 8 and t2.wraps == 1
        assert t1.l_pos == 0 and t2.l_pos == 0

    def test_sloppy_manual_close_snaps_to_whole_bars(self):
        """A close pressed slightly off the boundary still yields 8 bars."""
        e = make_engine()
        record_base_1bar(e)
        e.run(1000)
        e.press_rec(1)
        e.run_until_downbeat()
        e.run(8 * BAR - 700)       # press 700 samples early
        e.press_rec(1)
        assert e.tracks[1].mult == 8
        assert e.tracks[1].slen == 8 * BAR


class TestFixedLengthPresets:
    def test_synced_track_autocloses_at_preset_bars(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(1)
        e.action(2)                # SetCurrentTrackLength2Bars
        e.run(500)
        e.press_rec(1)             # arms
        e.run_until_downbeat()
        e.run(2 * BAR + 10)        # no second press needed
        t = e.tracks[1]
        assert t.state == 1 and t.mult == 2 and t.slen == 2 * BAR

    def test_existing_loop_resnaps_to_preset(self):
        e = make_engine()
        record_base_1bar(e)
        record_track2_8bars(e)
        e.select(1)
        e.action(3)                # SetCurrentTrackLength4Bars -> shrink 8 -> 4
        t = e.tracks[1]
        assert t.mult == 4 and t.slen == 4 * BAR

    def test_all_length_actions(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(0)
        for aid, bars in ((1, 1), (2, 2), (3, 4), (4, 8)):
            e.action(aid)
            assert e.tracks[0].mult == bars
            assert e.tracks[0].slen == bars * BAR


class TestSyncModes:
    def test_free_track_owns_unsnapped_length(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(2)
        e.action(5)                # SetCurrentTrackSyncModeFree
        e.press_rec(2)             # immediate start, no arming
        t = e.tracks[2]
        assert t.state == 2 and t.meas_state == 2
        e.run(100000)              # NOT a bar multiple
        e.press_rec(2)
        assert t.state == 1
        assert t.mult == 0 and t.slen == 100000, \
            "FREE loop keeps its exact recorded length"
        e.run(1)                   # settle onto the loop start after the close
        t.wraps = 0
        e.run(3 * 100000)
        assert t.wraps == 3        # loops on its own period

    def test_free_track_does_not_disturb_grid_tracks(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(2)
        e.action(5)
        e.press_rec(2)
        e.run(100000)
        e.press_rec(2)
        assert e.g_length == BAR   # grid untouched
        t1 = e.tracks[0]
        e.run(1)
        start = e.now
        t1.wraps = 0
        e.run(8 * BAR)
        assert t1.wraps == 8       # grid tracks unaffected

    def test_master_sync_locks_window_to_bar1(self):
        e = make_engine()
        record_base_1bar(e)
        e.select(1)
        e.action(7)                # SetCurrentTrackSyncModeMaster
        e.run(1000)
        e.press_rec(1)
        e.run_until_downbeat()
        e.run(2 * BAR)
        e.press_rec(1)
        t = e.tracks[1]
        assert t.mult == 2
        assert t.anchor == 0, "MASTER_SYNC loop window locks to the global grid"

    def test_toggle_cycles_sync_modes(self):
        e = make_engine()
        e.select(3)
        t = e.tracks[3]
        assert t.sync == MEASURE_SYNC
        e.action(8)
        assert t.sync == MASTER_SYNC
        e.action(8)
        assert t.sync == FREE
        e.action(8)
        assert t.sync == MEASURE_SYNC

    def test_set_sync_actions(self):
        e = make_engine()
        e.select(4)
        for aid, mode in ((5, FREE), (7, MASTER_SYNC), (6, MEASURE_SYNC)):
            e.action(aid)
            assert e.tracks[4].sync == mode


class TestQuantize:
    def test_beat_quantized_start_and_close(self):
        e = make_engine()
        record_base_1bar(e)
        t = e.tracks[3]
        t.qmode = Q_BEAT
        e.run(100)                 # just past a beat boundary
        e.press_rec(3)
        assert e.arm_mask & (1 << 3)
        e.run(BEAT)                # fires at the NEXT beat, not the next bar
        assert t.state == 2 and t.meas_state == 2
        e.run(3 * BEAT - 500)      # ~3 beats, slightly short
        e.press_rec(3)
        assert t.slen == 3 * BEAT, "beat quantize snaps length to whole beats"

    def test_quantize_off_records_immediately(self):
        e = make_engine()
        record_base_1bar(e)
        t = e.tracks[3]
        t.qmode = 0                # Q_OFF
        e.run(12345)
        e.press_rec(3)
        assert t.state == 2 and t.meas_state == 2, \
            "quantize-off records immediately mid-bar"


class TestArmBridgeMask:
    """gmem[1] protocol for RiftwayLabsLooper_arm_bridge.lua: a channel's bit is set
    exactly while it wants live input (armed / recording / overdubbing)."""

    def test_mask_follows_the_record_lifecycle(self):
        e = make_engine()
        assert e.want_input_mask() == 0
        e.select(0)
        e.action(1)                # 1-bar preset
        e.press_rec(0)
        assert e.want_input_mask() == 0b1, "recording base track wants input"
        e.run(2 * BAR)             # auto-closes at 1 bar -> playing
        assert e.want_input_mask() == 0

        e.run(100)
        e.press_rec(1)             # arms track 2
        assert e.want_input_mask() == 0b10, "ARMED channel wants input early"
        e.run_until_downbeat()     # fires -> recording
        assert e.want_input_mask() == 0b10
        e.run(8 * BAR)
        e.press_rec(1)             # close -> play
        assert e.want_input_mask() == 0

    def test_overdub_wants_input_again(self):
        e = make_engine()
        record_base_1bar(e)
        e.press_rec(0)             # play -> overdub
        assert e.want_input_mask() == 0b1
        e.press_rec(0)             # overdub -> play
        assert e.want_input_mask() == 0


class TestArmCancelAndClear:
    def test_press_on_armed_channel_cancels(self):
        e = make_engine()
        record_base_1bar(e)
        e.run(10)
        e.press_rec(1)
        assert e.arm_mask & 2
        e.press_rec(1)             # second press cancels the arm
        assert not (e.arm_mask & 2)
        assert e.tracks[1].state == 0

    def test_clear_forgets_length_but_keeps_settings(self):
        e = make_engine()
        record_base_1bar(e)
        record_track2_8bars(e)
        e.select(1)
        e.action(7)                # MASTER_SYNC setting
        e.clear(1)
        t = e.tracks[1]
        assert t.slen == 0 and t.mult == 0 and t.dirty == 0
        assert t.sync == MASTER_SYNC, "sync mode is a setting; survives clear"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
