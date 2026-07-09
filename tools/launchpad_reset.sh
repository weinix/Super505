#!/usr/bin/env bash
# launchpad_reset.sh — recover the Launchpad Pro MK3 after a replug/re-enumeration.
#
# What goes wrong: unplugging the Launchpad recreates its PipeWire node, which
# silently drops the REAPER<->Launchpad MIDI links (REAPER's prefs still look
# fine). The pad also boots into standalone Note mode instead of Programmer mode.
# Result: dark grid, dead pads.
#
# What this does (idempotent, safe to run any time):
#   1. Finds the Launchpad's ALSA seq port (never hard-codes the card number).
#   2. Sends the Programmer-mode sysex via the sequencer path (aplaymidi).
#      (Raw `amidi` fails with "busy" here — PipeWire owns the raw device.)
#   3. Re-links REAPER:MIDI Output -> Launchpad (LED path) and
#      Launchpad -> REAPER:MIDI Input (pad path) with pw-link, if missing.
#   4. Reminds you of the one in-REAPER step: LedRepaint (or FX reload).
#
# Usage: ./tools/launchpad_reset.sh          # full reset (mode + links)
#        ./tools/launchpad_reset.sh --test   # also light the top-left pad green,
#                                            # proving the computer->Launchpad path
#                                            # without REAPER in the loop
set -uo pipefail
DO_TEST=0; [ "${1:-}" = "--test" ] && DO_TEST=1

for c in aseqdump aplaymidi pw-link; do
  command -v "$c" >/dev/null || { echo "ERROR: $c not found"; exit 1; }
done

# --- 1. locate the Launchpad seq port (MIDI port, not DIN/DAW) ---------------
ADDR=$(aseqdump -l 2>/dev/null | awk '/LPProMK3 MIDI/{print $1; exit}')
[ -n "${ADDR:-}" ] || { echo "ERROR: Launchpad Pro MK3 not found (plugged in?)"; exit 1; }
echo "Launchpad seq port: $ADDR"

# --- 2. Programmer-mode sysex via the sequencer (PipeWire owns raw midi) -----
# Tiny prebuilt SMF containing only: F0 00 20 29 02 0E 0E 01 F7
SMF=$(mktemp --suffix=.mid)
printf '\x4D\x54\x68\x64\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60\x4D\x54\x72\x6B\x00\x00\x00\x0F\x00\xF0\x08\x00\x20\x29\x02\x0E\x0E\x01\xF7\x00\xFF\x2F\x00' > "$SMF"
if aplaymidi -p "$ADDR" "$SMF"; then
  echo "Programmer-mode sysex sent (grid blanks until the FX repaints it)."
else
  echo "WARNING: could not send Programmer sysex to $ADDR"
fi
rm -f "$SMF"

# --- 2b. optional path test: light the top-left pad (81) green ---------------
if [ "$DO_TEST" = 1 ]; then
  SMF=$(mktemp --suffix=.mid)
  # SMF: note-on ch1 note 81 vel 21 (green), end-of-track (no note-off -> LED stays)
  printf '\x4D\x54\x68\x64\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60\x4D\x54\x72\x6B\x00\x00\x00\x08\x00\x90\x51\x15\x60\xFF\x2F\x00' > "$SMF"
  aplaymidi -p "$ADDR" "$SMF" \
    && echo "TEST: top-left pad should be GREEN (computer->Launchpad path OK; LedRepaint will overwrite it)" \
    || echo "TEST FAILED: could not send the test LED"
  rm -f "$SMF"
fi

# --- 3. restore REAPER <-> Launchpad links in the PipeWire graph -------------
if ! pgrep -x reaper >/dev/null; then
  echo "REAPER is not running -> skipping pw-link (start REAPER, run this again)."
  exit 0
fi

# port names contain spaces/colons -> resolve numeric IDs and link by ID.
LP_PLAY=$(pw-link -i -I 2>/dev/null | awk '/Launchpad Pro MK3: LPProMK3 MIDI/{print $1; exit}')
LP_CAPT=$(pw-link -o -I 2>/dev/null | awk '/Launchpad Pro MK3: LPProMK3 MIDI/{print $1; exit}')
R_OUT=$(pw-link -o -I 2>/dev/null | awk '/REAPER:MIDI Output/{print $1; exit}')
[ -n "${LP_PLAY:-}" ] && [ -n "${LP_CAPT:-}" ] || { echo "ERROR: Launchpad MIDI ports not in the PipeWire graph"; exit 1; }

link() {  # link <src-id> <dst-id> <label> — idempotent
  local out
  if out=$(pw-link "$1" "$2" 2>&1); then
    echo "Linked $3: $1 -> $2"
  elif grep -q "File exists" <<<"$out"; then
    echo "$3 already linked: $1 -> $2"
  else
    echo "WARNING: $3 link failed ($1 -> $2): $out"
  fi
}

# LED path: REAPER MIDI Output -> Launchpad playback
if [ -n "${R_OUT:-}" ]; then
  link "$R_OUT" "$LP_PLAY" "LED path (REAPER -> Launchpad)"
else
  echo "WARNING: no 'REAPER:MIDI Output' port (enable the Launchpad output in REAPER MIDI prefs)"
fi

# Pad path: Launchpad capture -> the FREE REAPER MIDI Input. Other devices
# (GX49/UR22C) keep their links across a Launchpad replug, so the Launchpad's
# slot is exactly the REAPER input with nothing feeding it.
if pw-link -l -I 2>/dev/null | awk -v c="$LP_CAPT" '
    $2 ~ /^\|/ { if (inblk && $2=="|->" && $0 ~ /REAPER:MIDI Input/) found=1; next }
    { inblk = ($1==c) }
    END {exit !found}'; then
  echo "Pad path already linked: Launchpad ($LP_CAPT) -> REAPER input"
else
  FED=$(pw-link -l -I 2>/dev/null | awk '$2=="|->" && $0 ~ /REAPER:MIDI Input/ {print $3}' | sort -u)
  R_IN=""
  while read -r id _rest; do
    grep -qx "$id" <<<"$FED" || { R_IN=$id; break; }
  done < <(pw-link -i -I 2>/dev/null | awk '/REAPER:MIDI Input/{print $1}')
  if [ -n "$R_IN" ]; then
    link "$LP_CAPT" "$R_IN" "Pad path (Launchpad -> REAPER)"
  else
    echo "WARNING: no free REAPER:MIDI Input found for the Launchpad"
  fi
fi

cat <<'EOF'

Done. If the grid is still dark, make the FX repaint once (engines deployed
before 2026-07-08 don't auto-repaint): in RiftwayLabsLooper_ng set slider
"Action trigger" -> LedRepaint, or remove+re-add the FX.
EOF
