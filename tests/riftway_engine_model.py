"""RiftwayLabsLooper — clean-room engine reference model (spec of record).

INDEPENDENT, sample-accurate reference implementation of the RiftwayLabsLooper
engine, written from the RiftwayLabs feature requirements and RC-505 looper
behavior — NOT derived from Cockos Super8. It defines the intended behavior; the
JSFX engine (P2) is implemented to match it.

Architecture (the "better" design):
  * PER-TRACK INDEPENDENT CLOCKS. Every track owns
    {buf, length, pos, state, sync, bars, gain, mute, solo, envelopes} and
    advances its own `pos` by 1 per sample, wrapping at `length`. The per-sample
    record write is a plain monotonic counter — NO global-grid math in the hot
    path. A light shared grid (grid_len / grid_pos / grid_cycle) is consulted
    ONLY at discrete events: establishing the base measure, firing a quantized
    record start, and setting phase at record-close / AllStart. Synced tracks stay
    phase-locked *by construction* (length = k * grid_len, same advance rate).
  * STAGED per-sample pipeline: advance grid -> per track {record|overdub|read}
    -> playback fade * gain -> mute/solo gate -> mix.
  * CLICK-FREE boundaries: equal-power fades at every state edge + a loop-join
    crossfade applied when a loop closes.
  * PER-TRACK VOLUME (`gain`), applied to playback only (never to recorded input).

Sample-accurate: feed input via process(x)/run(n,x) and read mixed output;
timing/alignment assertions read track.pos / track.length / track.wraps. Tests use
a small srate so 8-bar scenarios run fast; all logic scales with srate.
"""
import math

# track state machine
EMPTY, REC, OVERDUB, PLAY, STOP = 0, 1, 2, 3, 4
STATE_NAMES = {EMPTY: "EMPTY", REC: "REC", OVERDUB: "OVERDUB", PLAY: "PLAY", STOP: "STOP"}
# sync policy
FREE, MEASURE, MASTER = 0, 1, 2
# quantize policy
Q_OFF, Q_BEAT, Q_BAR = 0, 1, 2

# fade / crossfade durations (seconds), scaled by srate
REC_FADE_IN_S = 0.002
REC_FADE_OUT_S = 0.004
PLAY_FADE_S = 0.005
LOOP_XFADE_S = 0.005


def _slope(srate, seconds):
    return 1.0 / max(int(srate * seconds), 1)


def _eqpow(env):
    """equal-power fade curve: env[0,1] -> gain[0,1] (click-free)."""
    return math.sin(max(0.0, min(1.0, env)) * math.pi * 0.5)


def _approach(v, target, up, down):
    """move v toward target by up/down slope, no overshoot, clamp [0,1]."""
    if target > v:
        return min(v + up, target, 1.0)
    if target < v:
        return max(v - down, target, 0.0)
    return v


class Track:
    def __init__(self, maxlen):
        self.maxlen = maxlen
        self.buf = [0.0] * maxlen
        self.state = EMPTY
        self.length = 0          # loop length in samples (0 = empty/unset)
        self.pos = 0             # play/overdub position in [0, length)
        self.sync = MEASURE      # default MEASURE_SYNC
        self.bars = 0            # synced length in bars (0 = free/unset)
        self.fixlen = 0          # preset length in bars (0 = measure freely)
        self.qmode = Q_BAR       # default quantize-to-bar
        self.gain = 1.0          # per-track playback volume
        self.mute = False
        self.solo = False
        self.anchor = 0          # grid cycle captured at record start (phase ref)
        self.rectempo = 0.0
        self.rec_env = 0.0       # record punch fade [0,1]
        self.play_env = 0.0      # playback fade [0,1]
        self._rec_target = 0.0
        self._play_target = 0.0
        self.meas = 0            # 0 none, 1 synced-measuring, 2 free-measuring
        self.meas_count = 0      # monotonic sample counter while recording
        self.armed = False
        self.wraps = 0           # test instrumentation

    def has_content(self):
        return self.length > 0 or self.state in (REC, OVERDUB)


class Engine:
    def __init__(self, srate=4800, tempo=120, nch=6, ts_num=4, ts_den=4,
                 maxlen=None, project_synced=False):
        self.srate = srate
        self.tempo = tempo
        self.ts_num = ts_num
        self.ts_den = ts_den
        self.project_synced = project_synced
        self.now = 0
        cap = maxlen if maxlen is not None else self.bar_samples() * 64
        self.maxlen = cap
        self.tracks = [Track(cap) for _ in range(nch)]
        self.selected = -1
        self.grid_len = 0        # base measure in samples (0 until established)
        self.grid_pos = 0
        self.grid_cycle = 0
        self._s_rec_in = _slope(srate, REC_FADE_IN_S)
        self._s_rec_out = _slope(srate, REC_FADE_OUT_S)
        self._s_play = _slope(srate, PLAY_FADE_S)
        self.xfade = max(int(srate * LOOP_XFADE_S), 1)

    # ---- grid helpers -----------------------------------------------------
    def bar_samples(self):
        return int(round(self.srate * self.ts_num * (4.0 / self.ts_den) * 60.0 / self.tempo))

    def beat_samples(self):
        return max(int(round(self.srate * (4.0 / self.ts_den) * 60.0 / self.tempo)), 1)

    def _grid_running(self):
        return self.grid_len > 0 and any(
            t.state in (REC, OVERDUB, PLAY) or t.armed for t in self.tracks)

    # ---- selection / mixer ------------------------------------------------
    def select(self, i):
        self.selected = i

    def set_gain(self, i, g):
        self.tracks[i].gain = g

    def toggle_mute(self, i):
        self.tracks[i].mute = not self.tracks[i].mute

    def toggle_solo(self, i):
        self.tracks[i].solo = not self.tracks[i].solo

    # ---- record / play transitions ---------------------------------------
    def press_rec(self, i):
        """rec pad: EMPTY->REC, REC->PLAY(close), PLAY->OVERDUB, OVERDUB->PLAY, STOP->PLAY."""
        t = self.tracks[i]
        if t.armed:
            t.armed = False
            return
        if t.state == EMPTY:
            self._begin_record(i)
        elif t.state == REC:
            self._close_record(i)
        elif t.state == PLAY:
            self._begin_overdub(i)
        elif t.state == OVERDUB:
            self._end_overdub(i)
        elif t.state == STOP:
            self._start_play(i)
        self.selected = i

    def press_stop(self, i):
        t = self.tracks[i]
        if t.armed:
            t.armed = False
            return
        if t.state == REC:
            self._close_record(i)
        elif t.state == OVERDUB:
            self._end_overdub(i)
        elif t.state == PLAY:
            self._stop(i)
        elif t.state == STOP and t.length > 0:
            self._start_play(i)
        self.selected = i

    def press_clear(self, i):
        t = self.tracks[i]
        for k in range(t.length):
            t.buf[k] = 0.0
        t.state = EMPTY
        t.length = t.pos = t.bars = t.anchor = 0
        t.meas = t.meas_count = 0
        t.armed = False
        t.rec_env = t.play_env = t._rec_target = t._play_target = 0.0

    def _begin_record(self, i):
        t = self.tracks[i]
        t.rectempo = self.tempo
        t.rec_env = 0.0
        t._rec_target = 1.0
        t.meas_count = 0
        grid_exists = self.grid_len > 0
        if t.sync == FREE:
            t.state = REC
            t.meas = 2                           # free: measure own length off-grid
        elif not grid_exists:
            t.state = REC
            t.meas = 1                           # base track: defines the grid
            t.anchor = 0
            self.grid_pos = self.grid_cycle = 0
        elif t.qmode == Q_OFF:
            t.state = REC
            t.meas = 2                           # unquantized: record now, own length
        else:
            t.armed = True                       # quantized: wait for downbeat

    def _fire_armed(self, i):
        t = self.tracks[i]
        t.armed = False
        t.state = REC
        t.rectempo = self.tempo
        t.anchor = self.grid_cycle
        t.meas_count = 0
        t.rec_env = 0.0
        t._rec_target = 1.0
        t.meas = 1 if t.qmode == Q_BAR else 2

    def _close_record(self, i):
        t = self.tracks[i]
        if t.meas == 1 and self.grid_len == 0:
            # BASE track: its recording defines the base measure
            bars = max(int(t.fixlen), 1)
            self.grid_len = max(round(t.meas_count / bars), 1)
            t.bars = bars
            t.anchor = 0
            length = t.bars * self.grid_len
        elif t.meas == 1:
            # subsequent synced track: snap to whole base measures (or exact fixlen)
            t.bars = max(int(t.fixlen), 1) if t.fixlen > 0 else \
                max(round(t.meas_count / max(self.grid_len, 1)), 1)
            length = t.bars * self.grid_len
            if t.sync == MASTER:
                t.anchor = 0
        else:
            # free / beat-quantized: keep exact recorded length (beat-snapped)
            length = t.meas_count
            if t.qmode == Q_BEAT and self.grid_len > 0:
                bl = self.beat_samples()
                length = max(round(length / bl), 1) * bl
            t.bars = 0
        length = min(max(length, 1), t.maxlen)
        for k in range(t.meas_count, length):    # zero any rounded-up tail
            t.buf[k] = 0.0
        t.length = length
        self._apply_loop_xfade(t)
        t.pos = self._grid_phase(t) if t.bars > 0 else 0
        t.meas = 0
        t.state = PLAY
        t._rec_target = 0.0
        t._play_target = 1.0

    def _grid_phase(self, t):
        if t.bars <= 0 or self.grid_len == 0:
            return 0
        ph = (self.grid_cycle - t.anchor) % t.bars
        return (ph * self.grid_len + self.grid_pos) % t.length

    def _begin_overdub(self, i):
        t = self.tracks[i]
        t.state = OVERDUB
        t.rec_env = 0.0
        t._rec_target = 1.0
        t._play_target = 1.0

    def _end_overdub(self, i):
        t = self.tracks[i]
        t.state = PLAY
        t._rec_target = 0.0
        t._play_target = 1.0

    def _start_play(self, i):
        t = self.tracks[i]
        t.state = PLAY
        t.pos = 0 if t.sync == FREE else self._grid_phase(t)
        t._play_target = 1.0
        t._rec_target = 0.0

    def _stop(self, i):
        t = self.tracks[i]
        t.state = STOP
        t._play_target = 0.0
        t._rec_target = 0.0

    def _apply_loop_xfade(self, t):
        """LINEAR crossfade of loop end into start so the wrap is click-free.
        Linear (not equal-power) because a loop's head/tail come from the same
        continuous recording and are correlated — a*x + (1-a)*x = x preserves
        level, whereas an equal-power blend of correlated samples overshoots."""
        L = t.length
        n = min(self.xfade, L // 2) if L > 1 else 0
        for k in range(n):
            a = k / n                          # 0 at the wrap -> 1 into the head
            t.buf[k] = t.buf[k] * a + t.buf[L - n + k] * (1.0 - a)

    # ---- global transport -------------------------------------------------
    def all_stop(self):
        for i, t in enumerate(self.tracks):
            if t.state == REC:
                self._close_record(i)
            elif t.state == OVERDUB:
                self._end_overdub(i)
            if t.state in (PLAY, OVERDUB):
                self._stop(i)
            t.armed = False

    def all_start(self):
        """restart the whole arrangement from bar 1, all tracks aligned."""
        self.grid_pos = self.grid_cycle = 0
        for t in self.tracks:
            if t.length > 0:
                t.state = PLAY
                t.pos = 0
                if t.sync != FREE:
                    t.anchor = 0
                t._play_target = 1.0
                t._rec_target = 0.0

    # ---- action dispatcher (ids mirror the JSFX rl_action) ---------------
    def action(self, aid):
        if aid in (1, 2, 3, 4):
            self._set_len_bars({1: 1, 2: 2, 3: 4, 4: 8}[aid])
        elif aid in (5, 6, 7):
            self._set_sync(aid - 5)
        elif aid == 8 and self.selected >= 0:
            self._set_sync((self.tracks[self.selected].sync + 1) % 3)

    def _set_len_bars(self, n):
        if self.selected < 0:
            return
        t = self.tracks[self.selected]
        t.fixlen = n
        if t.state != REC and t.length > 0 and t.bars > 0 and self.grid_len > 0 and n != t.bars:
            oldlen = t.bars * self.grid_len
            newlen = min(n * self.grid_len, t.maxlen)
            if newlen > oldlen:
                for k in range(oldlen, newlen):
                    t.buf[k] = t.buf[k % oldlen]
            t.bars = max(newlen // max(self.grid_len, 1), 1)
            t.length = t.bars * self.grid_len

    def _set_sync(self, m):
        if self.selected < 0:
            return
        t = self.tracks[self.selected]
        if m == t.sync:
            return
        if m == MASTER and t.bars > 0:
            t.anchor = 0
        elif m == FREE and t.bars > 0 and self.grid_len > 0:
            t.length = t.bars * self.grid_len
            t.pos = self._grid_phase(t)
            t.bars = 0
            t.anchor = 0
        t.sync = m

    # ---- per-sample engine ------------------------------------------------
    def _advance_grid(self):
        if not self._grid_running():
            if not any(t.state in (REC, OVERDUB, PLAY) or t.armed for t in self.tracks):
                self.grid_pos = self.grid_cycle = 0
            return
        self.grid_pos += 1
        if self.grid_pos >= self.grid_len:
            self.grid_pos = 0
            self.grid_cycle += 1
            for i, t in enumerate(self.tracks):
                if t.armed and t.qmode == Q_BAR:
                    self._fire_armed(i)
        bl = self.beat_samples()
        if self.grid_pos % bl == 0:
            for i, t in enumerate(self.tracks):
                if t.armed and t.qmode == Q_BEAT:
                    self._fire_armed(i)

    def process(self, x=0.0):
        self._advance_grid()
        any_solo = any(t.solo and t.has_content() for t in self.tracks)
        out = 0.0
        for i, t in enumerate(self.tracks):
            out += self._track_process(i, t, x, any_solo)
        self.now += 1
        return out

    def _track_process(self, i, t, x, any_solo):
        if t.state == EMPTY and not t.armed:
            return 0.0
        t.rec_env = _approach(t.rec_env, t._rec_target, self._s_rec_in, self._s_rec_out)
        t.play_env = _approach(t.play_env, t._play_target, self._s_play, self._s_play)
        rec_g = _eqpow(t.rec_env)
        play_g = _eqpow(t.play_env)
        contrib = 0.0

        if t.state == REC:
            wi = t.meas_count                       # monotonic write, clock-independent
            if wi < t.maxlen:
                t.buf[wi] = x * rec_g
            t.meas_count += 1
            # fixed-length preset -> auto-close
            if t.fixlen > 0:
                bar = self.grid_len if (t.meas == 1 and self.grid_len > 0) else self.bar_samples()
                if t.meas_count >= t.fixlen * bar:
                    self._close_record(i)
        elif t.state == OVERDUB:
            if t.length > 0:
                t.buf[t.pos] = t.buf[t.pos] + x * rec_g   # accumulate onto own loop
                contrib = t.buf[t.pos] * play_g * t.gain
                self._advance_pos(t)
        elif t.state == PLAY:
            if t.length > 0:
                contrib = t.buf[t.pos] * play_g * t.gain
                self._advance_pos(t)
        elif t.state == STOP:
            if t.length > 0 and t.play_env > 0.0001:
                contrib = t.buf[t.pos] * play_g * t.gain
                self._advance_pos(t)

        if any_solo:
            gate = 1.0 if t.solo else 0.0
        else:
            gate = 0.0 if t.mute else 1.0
        return contrib * gate

    def _advance_pos(self, t):
        prev = t.pos
        t.pos += 1
        if t.pos >= t.length:
            t.pos = 0
        if t.state == PLAY and prev != 0 and t.pos == 0:
            t.wraps += 1

    # ---- test helpers -----------------------------------------------------
    def run(self, n, x=0.0):
        return [self.process(x) for _ in range(int(n))]

    def run_signal(self, samples):
        return [self.process(x) for x in samples]

    def run_until_downbeat(self, limit=None):
        """advance to the NEXT grid downbeat (a bar wrap). If already sitting on a
        downbeat, advance past it — armed tracks fire on the wrap, so returning at
        the current downbeat would skip the fire."""
        limit = limit if limit is not None else self.grid_len + 2
        start_cycle = self.grid_cycle
        for _ in range(int(limit)):
            self.process(0.0)
            if self.grid_len > 0 and self.grid_pos == 0 and self.grid_cycle > start_cycle:
                return
        raise AssertionError("no downbeat reached")
