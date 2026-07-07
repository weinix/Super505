#!/usr/bin/env bash
# print_launchpad_key.sh — print the MIDI code each Launchpad Pro MK3 button
# sends, in PROGRAMMER MODE (the same mode the RiftwayLabsLooper JSFX puts it in),
# so the numbers match exactly what the engine's onmsg() receives.
#
# Usage:  ./tools/print_launchpad_key.sh
#   Press a button -> read the decoded line. Ctrl-C to stop.
#     "Control change  ch 0  <cc> <val>"  -> a CC BUTTON  (use for play_cc / clear_cc)
#     "Note on         ch 0  <note> <vel>"-> a GRID PAD
#
# Notes:
#   * Uses ALSA seq (aseqdump), which supports multiple subscribers, so this can
#     snoop while REAPER is also connected — it does NOT steal the device.
#   * Requires alsa-utils (amidi, aseqdump).
set -uo pipefail

NAME_MATCH='LPProMK3 MIDI'                       # the port buttons come out of
SYSEX_PROG='F0 00 20 29 02 0E 0E 01 F7'          # LP Pro MK3 -> Programmer mode

command -v aseqdump >/dev/null || { echo "ERROR: aseqdump not found (install alsa-utils)"; exit 1; }

# --- locate the Launchpad MIDI port (seq for reading, raw for the mode sysex) ---
seq_port=$(aseqdump -l 2>/dev/null | awk -v n="$NAME_MATCH" 'index($0,n){print $1; exit}')
raw_port=$(amidi   -l 2>/dev/null | awk -v n="$NAME_MATCH" 'index($0,n){print $2; exit}')

if [ -z "${seq_port}" ]; then
  echo "ERROR: Launchpad '$NAME_MATCH' port not found."
  echo "Plugged in? Current ports:"; aseqdump -l 2>/dev/null | grep -i launchpad || echo "  (none)"
  exit 1
fi

# --- best-effort: force Programmer mode so codes match the engine ---
# If REAPER holds the raw device this fails harmlessly (REAPER's JSFX already
# keeps it in Programmer mode).
if [ -n "${raw_port}" ]; then
  if amidi -p "${raw_port}" -S "${SYSEX_PROG}" 2>/dev/null; then
    echo "Set Programmer mode on ${raw_port}."
  else
    echo "Note: could not send mode sysex to ${raw_port} (in use by REAPER?)."
    echo "      That's fine IF the RiftwayLabsLooper JSFX is loaded — it already"
    echo "      keeps the pad in Programmer mode. Otherwise close REAPER and rerun."
  fi
fi

cat <<EOF

Listening on seq ${seq_port} ($NAME_MATCH). Press Launchpad buttons:
  Control change  -> the number after 'ch 0' is the CC   (play_cc / clear_cc)
  Note on         -> the number after 'ch 0' is the grid pad note
Ctrl-C to stop.
------------------------------------------------------------------------
EOF

# filter the MIDI-clock / sensing / subscription spam so button presses stand out
aseqdump -p "${seq_port}" \
  | grep --line-buffered -viE 'clock|active sensing|sensing|subscribed|^ *Source'
