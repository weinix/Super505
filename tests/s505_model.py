"""Sample-accurate Python reference model of the Super505 loop-sync engine.

This mirrors the arithmetic of reaper/effects/super505 (the JSFX) function by
function so the independent-track-length model can be tested headlessly.
Audio content is not modeled -- only state, positions and lengths, which is
what the loop-sync feature is about. Each method notes the JSFX code it
mirrors; if you change the JSFX engine, change this model to match.

Known intentional simplifications (irrelevant to loop arithmetic):
  - no fades / record-gate / latch queue / count-in / linked channels
  - "dirty" is a boolean-ish flag, not a high-water sample count
  - g_pos does not advance while no grid exists (JSFX pins it to 0 by
    wrapping every sample; observable behavior is identical)
"""

# sync modes (st_sync)
FREE, MEASURE_SYNC, MASTER_SYNC = 0, 1, 2
# quantize modes (st_qmode)
Q_OFF, Q_BEAT, Q_BAR = 0, 1, 2

BLOCK = 256  # samplesblock used for @block-level logic (idle reset)


class Track:
    """Per-channel state record (mem_stlist entry + channel instance vars)."""

    def __init__(self):
        self.state = 0          # st_state: 0=stop 1=play 2=rec
        self.dirty = 0          # st_dirty (boolean-ish)
        self.mult = 0           # st_mult: bars this loop spans (0=free/unset)
        self.anchor = 0         # st_anchor: g_cycle at record-start downbeat
        self.sync = MEASURE_SYNC  # st_sync
        self.qmode = Q_BAR      # st_qmode
        self.fixlen = 0         # st_fixlen: preset length in bars
        self.slen = 0           # st_len: loop length in samples
        self.ppos = 0           # st_ppos: current position in own loop
        self.rectempo = 0       # st_rectempo
        # channel instance vars
        self.meas_state = 0     # 0=idle 1=synced measuring 2=free measuring
        self.meas_samples = 0
        self.fppos = 0          # free-loop playback position
        # test instrumentation (not in JSFX)
        self.l_pos = None       # last computed read position
        self.wraps = 0          # count of l_pos returning to 0 while playing

    def length_samples(self, g_length):
        """mirrors track_len() in the JSFX"""
        if self.mult > 0:
            return self.mult * g_length
        if self.slen > 0:
            return self.slen
        return g_length


class Engine:
    def __init__(self, srate=48000, tempo=120, nch=5, maxlen=10**9,
                 ts_num=4, ts_den=4, clickcnt=0):
        self.srate = srate
        self.tempo = tempo
        self.ts_num = ts_num
        self.ts_den = ts_den
        self.clickcnt = clickcnt  # cfgp_clickcnt (0 -> 4 beats/bar)
        self.maxlen = maxlen
        self.tracks = [Track() for _ in range(nch)]
        self.g_pos = 0
        self.g_length = 0
        self.g_cycle = 0
        self.g_firstrec = 0     # 1+idx while the base track records
        self.arm_mask = 0
        self.active_mask = 0
        self.selected = -1      # g_chan_selected
        self.inactive_blockcnt = 0
        self._sample_in_block = 0
        self.now = 0            # absolute sample counter (test convenience)

    # ---- helpers -----------------------------------------------------------

    @property
    def beatlen(self):
        """mirrors g_beatlen computed in @block"""
        bpb = self.clickcnt if self.clickcnt > 0 else 4
        return max(self.g_length // bpb, 1) if self.g_length > 0 else 0

    def barlen(self, tempo):
        """bar length in samples at a given tempo (base-track fixlen close)"""
        return int(self.srate * self.ts_num * 240 / (max(tempo, 1) * self.ts_den))

    # ---- setstate() --------------------------------------------------------

    def setstate(self, i, st):
        t = self.tracks[i]
        # finalize loop length when leaving the record state
        if st != 2:
            if t.meas_state == 1:
                if t.fixlen > 0:
                    t.mult = max(int(t.fixlen), 1)
                else:
                    t.mult = max(int(t.meas_samples / max(self.g_length, 1) + 0.5), 1)
                t.anchor = 0 if t.sync == MASTER_SYNC else t.anchor % max(t.mult, 1)
                t.slen = t.mult * self.g_length
                t.meas_state = 0
            elif t.meas_state == 2:
                l = t.meas_samples
                if t.qmode == Q_BEAT and self.beatlen > 0:
                    l = max(int(l / self.beatlen + 0.5), 1) * self.beatlen
                l = max(min(l, self.maxlen - 1), 1)
                t.slen = l
                t.mult = 0
                t.anchor = 0
                t.fppos = 0
                t.meas_state = 0
            elif self.g_firstrec == 1 + i:
                t.mult = 1
                t.anchor = 0
                t.slen = self.g_length

        if t.state:
            if st == 0:
                self.active_mask &= ~(1 << i)
            elif self.g_length > 0:
                if self.g_firstrec == 1 + i:   # base length just closed
                    t.mult = 1
                    t.anchor = 0
                    t.slen = self.g_length
                self.g_firstrec = 0
        else:
            if st > 0:
                if t.mult == 0 and t.slen > 0:
                    t.fppos = 0                # FREE loop restarts from the top
                if st == 2 and t.dirty > 0:
                    t.dirty = 0                # fresh record wipes old content
                self.active_mask |= (1 << i)
                if st == 2 and t.meas_state == 0:
                    if t.sync != FREE:
                        if self.g_length == 0 and self.g_firstrec == 0:
                            self.g_pos = 0
                            self.g_cycle = 0
                            self.g_firstrec = 1 + i
                            t.rectempo = self.tempo
                        elif self.g_length > 0 and self.active_mask == (1 << i):
                            t.meas_state = 1
                            t.meas_samples = 0
                            t.anchor = self.g_cycle
                            t.rectempo = self.tempo
                    elif t.slen <= 0:
                        t.meas_state = 2
                        t.meas_samples = 0
                        t.rectempo = self.tempo

        t.state = st
        t.dirty = max(t.dirty, 1 if st == 2 else 0)

    # ---- onmsg() note handling --------------------------------------------

    def press_rec(self, i):
        """note1: rec / set-length / overdub-toggle"""
        t = self.tracks[i]
        newstate = 1 if (t.state == 2 and self.g_firstrec == 0) else 2
        self._apply_newstate(i, newstate)

    def press_stop(self, i):
        """note2: play/stop toggle"""
        t = self.tracks[i]
        newstate = 1 if (t.state == 2 or (t.state == 0 and (self.g_length or t.slen))) else 0
        self._apply_newstate(i, newstate)

    def select(self, i):
        self.selected = i

    def clear(self, i):
        """note5 -> chan_clear()"""
        t = self.tracks[i]
        self.setstate(i, 0)
        t.dirty = 0
        t.mult = 0
        t.anchor = 0
        t.slen = 0
        t.ppos = 0
        t.meas_state = 0
        t.meas_samples = 0
        t.fppos = 0
        self.arm_mask &= ~(1 << i)
        if self.g_firstrec == 1 + i:
            self.g_firstrec = 0

    def _apply_newstate(self, i, newstate):
        t = self.tracks[i]
        if self.arm_mask & (1 << i):           # press on an armed channel cancels
            self.arm_mask &= ~(1 << i)
            return
        if (newstate == 2 and t.state == 0 and t.dirty == 0 and self.g_length > 0
                and self.g_firstrec == 0 and self.active_mask != 0):
            if t.sync == FREE or t.qmode == Q_OFF:
                self.setstate(i, 2)
                t.meas_state = 2
                t.meas_samples = 0
                t.rectempo = self.tempo
            else:
                self.arm_mask |= (1 << i)      # quantized record start
            self.selected = i
            return
        self.setstate(i, newstate)
        self.selected = i

    def all_start_stop(self):
        """mirrors play_or_stop_all()"""
        want = 1 if any(t.state != 1 and t.dirty > 0 for t in self.tracks) else 0
        for i in reversed(range(len(self.tracks))):
            t = self.tracks[i]
            if t.state != want and (t.dirty > 0 or t.state):
                self.setstate(i, want)

    # ---- action dispatcher -------------------------------------------------

    ACTION_NAMES = {
        1: "SetCurrentTrackLength1Bar",
        2: "SetCurrentTrackLength2Bars",
        3: "SetCurrentTrackLength4Bars",
        4: "SetCurrentTrackLength8Bars",
        5: "SetCurrentTrackSyncModeFree",
        6: "SetCurrentTrackSyncModeMeasure",
        7: "SetCurrentTrackSyncModeMaster",
        8: "ToggleCurrentTrackSyncMode",
    }

    def action(self, aid):
        """mirrors s505_action()"""
        if aid in (1, 2, 3, 4):
            self._set_len_bars({1: 1, 2: 2, 3: 4, 4: 8}[aid])
        elif aid in (5, 6, 7):
            self._set_sync(aid - 5)
        elif aid == 8 and self.selected >= 0:
            self._set_sync((self.tracks[self.selected].sync + 1) % 3)

    def _set_len_bars(self, n):
        """mirrors s505_set_len_bars()"""
        if self.selected < 0:
            return
        t = self.tracks[self.selected]
        t.fixlen = n
        if (t.state != 2 and t.dirty > 0 and t.mult > 0 and self.g_length > 0
                and n != t.mult):
            newlen = min(n * self.g_length, self.maxlen - 1)
            t.mult = max(newlen // max(self.g_length, 1), 1)
            t.slen = t.mult * self.g_length
            t.anchor = 0 if t.sync == MASTER_SYNC else t.anchor % t.mult

    def _set_sync(self, m):
        """mirrors s505_set_sync()"""
        if self.selected < 0:
            return
        t = self.tracks[self.selected]
        if m == t.sync:
            return
        if m == MASTER_SYNC and t.mult > 0:
            t.anchor = 0
        elif m == FREE and t.mult > 0 and self.g_length > 0:
            t.slen = t.mult * self.g_length
            ph = (self.g_cycle - t.anchor) % t.mult
            t.fppos = ph * self.g_length + self.g_pos
            t.mult = 0
            t.anchor = 0
        t.sync = m

    # ---- @sample / @block --------------------------------------------------

    def _sample(self):
        # pre-wrap (external length changes)
        if self.g_length > 0 and self.g_pos >= self.g_length and self.g_firstrec == 0:
            self.g_pos = 0
            self.g_cycle += 1

        # per-channel process(): compute this track's own read/write position
        for i, t in enumerate(self.tracks):
            prev = t.l_pos
            if t.meas_state == 1:
                wr = (self.g_cycle - t.anchor) * self.g_length + self.g_pos
                t.l_pos = min(wr, self.maxlen - 1)
                t.meas_samples += 1
                if (t.fixlen > 0 and self.g_length > 0
                        and t.meas_samples >= t.fixlen * self.g_length):
                    self.setstate(i, 1)        # fixed-length auto-close
            elif t.meas_state == 2:
                t.l_pos = min(t.meas_samples, self.maxlen - 1)
                t.meas_samples += 1
            elif t.mult == 0 and t.slen > 0:
                t.l_pos = t.fppos              # FREE loop: own position counter
                t.fppos += 1
                if t.fppos >= t.slen:
                    t.fppos = 0
            else:
                if t.mult > 1 and self.g_firstrec == 0:
                    lp = ((self.g_cycle - t.anchor) % t.mult) * self.g_length + self.g_pos
                    if lp < 0:
                        lp += t.mult * self.g_length
                    t.l_pos = lp
                else:
                    t.l_pos = self.g_pos
            t.ppos = t.l_pos
            if t.state == 1 and prev is not None and t.l_pos == 0 and prev != 0:
                t.wraps += 1

        # transport advance
        if self.g_firstrec:
            self.g_pos += 1
            if self.g_pos >= self.maxlen:
                fr = self.tracks[self.g_firstrec - 1]
                fr.mult = 1
                fr.anchor = 0
                fr.slen = self.g_length
                self.g_firstrec = 0
                self.g_pos = 0
                self.g_cycle = 0
            else:
                self.g_length = self.g_pos
                fr = self.tracks[self.g_firstrec - 1]
                if (fr.fixlen > 0 and
                        self.g_length >= fr.fixlen * self.barlen(fr.rectempo)):
                    self.setstate(self.g_firstrec - 1, 1)  # base fixlen auto-close
        elif self.g_length > 0:
            self.g_pos += 1
            if self.g_pos >= self.g_length:
                self.g_pos = 0
                self.g_cycle += 1
                # bar-quantized armed channels start at the downbeat
                for i, t in enumerate(self.tracks):
                    if self.arm_mask & (1 << i) and t.qmode != Q_BEAT:
                        self.arm_mask &= ~(1 << i)
                        t.anchor = self.g_cycle
                        t.rectempo = self.tempo
                        self.setstate(i, 2)
                        t.meas_state = 1
                        t.meas_samples = 0
            # beat-quantized armed channels start at any beat boundary
            if self.arm_mask and self.beatlen > 0 and self.g_pos % self.beatlen == 0:
                for i, t in enumerate(self.tracks):
                    if self.arm_mask & (1 << i) and t.qmode == Q_BEAT:
                        self.arm_mask &= ~(1 << i)
                        t.rectempo = self.tempo
                        self.setstate(i, 2)
                        t.meas_state = 2
                        t.meas_samples = 0

        self.now += 1

    def _block(self):
        """mirrors the @block idle reset"""
        if self.active_mask == 0:
            if self.inactive_blockcnt < 2:
                self.inactive_blockcnt += 1
            else:
                self.g_pos = 0
                self.g_cycle = 0
                self.arm_mask = 0
                for t in self.tracks:
                    t.anchor = 0
        else:
            self.inactive_blockcnt = 0

    def run(self, nsamples):
        for _ in range(nsamples):
            self._sample()
            self._sample_in_block += 1
            if self._sample_in_block >= BLOCK:
                self._sample_in_block = 0
                self._block()

    def run_until_downbeat(self, max_samples=None):
        """advance to the next sample where g_pos == 0 (a bar boundary)"""
        limit = max_samples if max_samples is not None else self.g_length + 1
        for _ in range(int(limit)):
            if self.g_pos == 0:
                return
            self.run(1)
        raise AssertionError("no downbeat reached")
