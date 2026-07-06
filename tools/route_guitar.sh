#!/usr/bin/env bash
# route_guitar.sh — connect the enya E-SP1 guitar USB interface to Reaper's
# audio inputs over PipeWire/JACK. Run after a reboot or USB re-plug, because
# pw-link connections are not persistent (PipeWire defaults back to the Yeti).
#
# Routes the guitar's capture_FL to BOTH Reaper inputs so a mono guitar still
# feeds all 5 RiftwayLabsLooper loop channels. Reaper must be running.
#
# Usage:  tools/route_guitar.sh         # connect guitar, drop the Yeti
#         tools/route_guitar.sh --keep  # connect guitar, leave Yeti connected too
set -euo pipefail

gfl=$(pw-link -I -o 2>/dev/null | awk '/enya.*E-SP1.*capture_FL/{print $1; exit}')
in1=$(pw-link -I -i 2>/dev/null | awk '/REAPER:in1/{print $1; exit}')
in2=$(pw-link -I -i 2>/dev/null | awk '/REAPER:in2/{print $1; exit}')

[ -z "${gfl:-}" ] && { echo "guitar capture port not found — is the E-SP1 plugged in?" >&2; exit 1; }
[ -z "${in1:-}" ] && { echo "REAPER inputs not found — is Reaper running?" >&2; exit 1; }

pw-link "$gfl" "$in1" 2>/dev/null || true
pw-link "$gfl" "$in2" 2>/dev/null || true

if [ "${1:-}" != "--keep" ]; then
  yfl=$(pw-link -I -o 2>/dev/null | awk '/Yeti.*capture_FL/{print $1; exit}')
  yfr=$(pw-link -I -o 2>/dev/null | awk '/Yeti.*capture_FR/{print $1; exit}')
  [ -n "${yfl:-}" ] && pw-link -d "$yfl" "$in1" 2>/dev/null || true
  [ -n "${yfr:-}" ] && pw-link -d "$yfr" "$in2" 2>/dev/null || true
fi

echo "guitar routed -> REAPER inputs:"
pw-link -l 2>/dev/null | grep -iB1 'REAPER:in' | grep -iE 'enya|E-SP1|Yeti|REAPER:in'
