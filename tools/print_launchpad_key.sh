#!/usr/bin/env bash
# print_launchpad_key.sh — show the MIDI messages ANY device sends (decoded),
# so you can read the exact codes to bind (CC / Program Change / Note).
#
# Works with any MIDI input: Launchpad, FCB1010 (via a USB-MIDI interface's DIN
# IN, e.g. the UR22C), keyboards, etc. When the target is a Launchpad it is put
# into Programmer mode first so the codes match what the JSFX engine receives.
#
# Usage:
#   ./tools/print_launchpad_key.sh                 # list ports; listen on the first hardware one
#   ./tools/print_launchpad_key.sh <name|addr>     # listen on a port matching a name substr or seq addr
# Examples:
#   ./tools/print_launchpad_key.sh UR22C           # FCB1010 plugged into the UR22C MIDI IN
#   ./tools/print_launchpad_key.sh "LPProMK3 MIDI" # Launchpad
#   ./tools/print_launchpad_key.sh 36:0            # explicit ALSA seq address
#
# Reading the output (press a control, watch its line):
#   "Control change  ... <cc> <val>"   -> CC button/pedal   (val 127 press / 0 release)
#   "Program change  ... <prog>"       -> FCB1010 footswitch preset (common default)
#   "Note on         ... <note> <vel>" -> a pad / key
#   ALSA seq allows multiple subscribers, so this snoops alongside REAPER.
set -uo pipefail

command -v aseqdump >/dev/null || { echo "ERROR: aseqdump not found (install alsa-utils)"; exit 1; }

FILTER="${1:-}"

# candidate input ports = seq ports minus System + Midi Through
mapfile -t LINES < <(aseqdump -l 2>/dev/null | sed '1d' | grep -viE 'System|Midi Through' | grep -E '^[[:space:]]*[0-9]+:[0-9]+')

[ "${#LINES[@]}" -gt 0 ] || { echo "ERROR: no MIDI input ports found (is the device plugged in?)"; exit 1; }

echo "Available MIDI input ports:"
for l in "${LINES[@]}"; do echo "  $l"; done
echo

# pick the port
CHOICE=""
if [ -n "$FILTER" ]; then
  for l in "${LINES[@]}"; do
    if printf '%s' "$l" | grep -qiF "$FILTER"; then CHOICE="$l"; break; fi
  done
  [ -n "$CHOICE" ] || { echo "ERROR: no input port matches '$FILTER' (see list above)"; exit 1; }
else
  CHOICE="${LINES[0]}"
  echo "No filter given -> using the first port. Pass a name (e.g. 'UR22C') to target another."
fi

ADDR=$(printf '%s' "$CHOICE" | awk '{print $1}')
DESC=$(printf '%s' "$CHOICE" | sed -E 's/^[[:space:]]*[0-9]+:[0-9]+[[:space:]]+//')

# Launchpad only: force Programmer mode so its codes match the engine
if printf '%s' "$CHOICE" | grep -qiE 'launchpad|LPProMK3'; then
  RAW=$(amidi -l 2>/dev/null | awk '/LPProMK3 MIDI/{print $2; exit}')
  if [ -n "${RAW:-}" ] && amidi -p "$RAW" -S 'F0 00 20 29 02 0E 0E 01 F7' 2>/dev/null; then
    echo "Set Launchpad Programmer mode on ${RAW}."
  fi
fi

cat <<EOF

Listening on ${ADDR}  (${DESC}). Press controls; Ctrl-C to stop.
  Control change -> the number after 'ch N' is the CC   (val 127 press / 0 release)
  Program change -> the number is the PC/preset          (FCB1010 default)
  Note on        -> the number is the pad/key note
------------------------------------------------------------------------
EOF

# filter the MIDI-clock / sensing / subscription spam so presses stand out
aseqdump -p "$ADDR" \
  | grep --line-buffered -viE 'clock|active sensing|sensing|subscribed|^ *Source'
