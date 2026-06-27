#!/usr/bin/env bash
# reaper_ur22c_pin.sh — force Reaper's audio I/O onto the Steinberg UR22C,
# independent of PipeWire's default device.
#
# Why: Reaper (JACK backend via pipewire-jack) auto-connects its ports
# (REAPER:in1/in2, out1/out2) to whatever the *default* source/sink is. We keep
# the default SOURCE = Yeti (so other apps capture from the Yeti) but want Reaper
# itself to record from the UR22C. This re-pins Reaper to the UR22C and removes
# any Yeti->Reaper input links the default-source auto-connect created.
# Output already follows the default sink (UR22C), but we pin it too for safety.
#
# Port names come from the UR22C "Pro Audio" profile and are stable across
# reboots (keyed on the USB device), so we match them by pattern.
#
# Modes:
#   reaper_ur22c_pin.sh once    # reconcile a single time
#   reaper_ur22c_pin.sh watch   # loop forever (used by the systemd user service)
set -uo pipefail

# $1 = -o (source/capture & REAPER:out) | -i (sink/playback & REAPER:in)
# $2 = extended regex; prints first matching port name
port() { pw-link "$1" 2>/dev/null | grep -m1 -E "$2"; }

reconcile() {
  # Do nothing unless Reaper is up with its input ports registered.
  pw-link -i 2>/dev/null | grep -qx 'REAPER:in1' || return 0

  local ur_c0 ur_c1 ur_p0 ur_p1 ye_c0 ye_c1
  ur_c0=$(port -o 'UR22C.*pro-input.*capture_AUX0')
  ur_c1=$(port -o 'UR22C.*pro-input.*capture_AUX1')
  ur_p0=$(port -i 'UR22C.*pro-output.*playback_AUX0')
  ur_p1=$(port -i 'UR22C.*pro-output.*playback_AUX1')
  ye_c0=$(port -o 'Yeti.*capture_FL')
  ye_c1=$(port -o 'Yeti.*capture_FR')

  # inputs: UR22C capture -> Reaper (pw-link is idempotent; errors if link exists)
  [ -n "$ur_c0" ] && pw-link "$ur_c0" REAPER:in1 2>/dev/null
  [ -n "$ur_c1" ] && pw-link "$ur_c1" REAPER:in2 2>/dev/null
  # outputs: Reaper -> UR22C playback
  [ -n "$ur_p0" ] && pw-link REAPER:out1 "$ur_p0" 2>/dev/null
  [ -n "$ur_p1" ] && pw-link REAPER:out2 "$ur_p1" 2>/dev/null

  # drop any Yeti -> Reaper input links (both pairings, in case of swap)
  for ye in "$ye_c0" "$ye_c1"; do
    [ -n "$ye" ] && pw-link -d "$ye" REAPER:in1 2>/dev/null
    [ -n "$ye" ] && pw-link -d "$ye" REAPER:in2 2>/dev/null
  done
  return 0
}

case "${1:-once}" in
  once)  reconcile ;;
  watch) while true; do reconcile; sleep 1; done ;;
  *) echo "usage: $0 {once|watch}" >&2; exit 1 ;;
esac
