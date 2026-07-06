#!/usr/bin/env bash
# lp_programmer.sh — Launchpad Pro MK3 bring-up helper for RiftwayLabsLooper.
#
# Talks to the Launchpad's "LPProMK3 MIDI" port via ALSA raw MIDI (amidi),
# independent of Reaper. Auto-detects the port by name (card numbers differ
# per machine). Use during bring-up to enter Programmer mode, lock LED palette
# indices, and confirm pad note numbers — before any Reaper/JSFX work.
#
# Requires: alsa-utils (amidi). The Launchpad must be connected and NOT owned
# by a running Reaper/DAW (close Reaper first).
#
# Usage:
#   tools/lp_programmer.sh port              # show detected ALSA port
#   tools/lp_programmer.sh prog              # enter Programmer mode
#   tools/lp_programmer.sh live              # return to standard/Live mode
#   tools/lp_programmer.sh off               # turn all 64 pads off
#   tools/lp_programmer.sh pad NOTE VEL [CH] # light one pad (decimals; CH 1=static 2=flash 3=pulse)
#   tools/lp_programmer.sh layout            # paint the RiftwayLabsLooper row layout (verify pad numbers)
#   tools/lp_programmer.sh ramp [START]      # palette explorer: pads 11..88 = indices START..START+63
set -euo pipefail

PORT_NAME="LPProMK3 MIDI"

detect_port() {
  local p
  p=$(amidi -l 2>/dev/null | awk -v n="$PORT_NAME" 'index($0,n){print $2; exit}')
  if [[ -z "$p" ]]; then
    echo "error: '$PORT_NAME' port not found. Is the Launchpad connected? (amidi -l)" >&2
    exit 1
  fi
  printf '%s' "$p"
}

# send space-separated hex bytes
send() { amidi -p "$(detect_port)" -S "$*"; }

# note-on: decimal note + velocity, optional channel (1/2/3 -> status 90/91/92)
note_on() {
  local note=$1 vel=$2 ch=${3:-1}
  local status=$((0x90 + ch - 1))
  printf -v hex '%02X %02X %02X' "$status" "$note" "$vel"
  send "$hex"
}

enter_programmer() { send "F0 00 20 29 02 0E 0E 01 F7"; }
enter_live()       { send "F0 00 20 29 02 0E 0E 00 F7"; }

# all 64 grid pads (rows 1..8, cols 1..8) -> note = row*10+col
grid_pads() { for r in 1 2 3 4 5 6 7 8; do for c in 1 2 3 4 5 6 7 8; do echo $((r*10+c)); done; done; }

all_off() { enter_programmer; for n in $(grid_pads); do note_on "$n" 0 1; done; }

# Provisional RiftwayLabsLooper palette indices (confirm/adjust visually with `ramp`)
C_RED=5; C_AMBER=9; C_GREEN=21; C_DIM=45; C_WHITE=3; C_UTIL=1

paint_layout() {
  enter_programmer
  for n in 81 82 83 84 85; do note_on "$n" $C_RED   1; done  # Rec/Overdub/Play
  for n in 71 72 73 74 75; do note_on "$n" $C_GREEN 1; done  # Stop
  for n in 61 62 63 64 65; do note_on "$n" $C_AMBER 1; done  # Clear (per-track)
  for n in 41 42 43 44 45; do note_on "$n" $C_DIM   1; done  # Reverse
  for n in 31 32 33 34 35; do note_on "$n" $C_WHITE 1; done  # Select/Monitor
  for n in 11 12 13 14 15 16 17 18; do note_on "$n" $C_UTIL 1; done  # Utility row
}

# light pads 11..88 with velocity = sequential palette index, to read off colors
paint_ramp() {
  local idx=${1:-0}
  enter_programmer
  for n in $(grid_pads); do
    note_on "$n" $((idx & 127)) 1
    idx=$((idx+1))
  done
}

cmd=${1:-}
case "$cmd" in
  port)   detect_port; echo ;;
  prog|programmer) enter_programmer; echo "Programmer mode ON" ;;
  live)   enter_live; echo "Live mode (standard) ON" ;;
  off|clear) all_off; echo "all pads off" ;;
  pad)    note_on "$2" "$3" "${4:-1}"; echo "lit pad $2 vel $3 ch ${4:-1}" ;;
  layout) paint_layout; echo "painted RiftwayLabsLooper layout (run 'live' or 'off' to restore)" ;;
  ramp)   paint_ramp "${2:-0}"; echo "painted palette ramp from ${2:-0} (each pad's color = its index)" ;;
  *)
    grep '^#' "$0" | sed '1d;s/^# \{0,1\}//'
    exit 1 ;;
esac
