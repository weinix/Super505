#!/usr/bin/env bash
# gx49_keys.sh — live MIDI monitor for the Nektar Impact GX49 (or any port).
# Prints each key/control you touch: note number, note name, velocity, and the
# Muldjord DrumGizmo drum that note triggers. Use it to find the right octave
# for playing drums.
#
# Usage:   tools/gx49_keys.sh              # auto-detects the Impact GX49
#          tools/gx49_keys.sh "Launchpad"  # match any port by name substring
#          tools/gx49_keys.sh 32:0         # or an explicit client:port
# Stop:    Ctrl-C
set -euo pipefail

MATCH="${1:-Impact GX49}"

# Resolve to a client:port. If the arg already looks like N:M, use it as-is.
if [[ "$MATCH" =~ ^[0-9]+:[0-9]+$ ]]; then
  PORT="$MATCH"
  NAME="$MATCH"
else
  line="$(aseqdump -l 2>/dev/null | grep -i -- "$MATCH" | head -1 || true)"
  if [[ -z "$line" ]]; then
    echo "No MIDI input port matching '$MATCH'. Available ports:" >&2
    aseqdump -l >&2
    exit 1
  fi
  PORT="$(awk '{print $1}' <<<"$line")"
  NAME="$(sed -E 's/^ *[0-9]+:[0-9]+ +//' <<<"$line")"
fi

echo "Listening on $PORT  ($NAME)"
echo "Press keys/pads/knobs on the controller. Ctrl-C to stop."
echo "----------------------------------------------------------------------"

# stdbuf keeps the pipeline line-buffered so events print the instant you play.
stdbuf -oL aseqdump -p "$PORT" 2>/dev/null | stdbuf -oL awk '
BEGIN {
  split("C C# D D# E F F# G G# A A# B", NM, " ")
  # Muldjord 20%-bleed Midimap.xml: note -> drum
  D[35]="Kick (L)";      D[36]="Kick (R)";     D[37]="Snare (rest)"
  D[38]="Snare";         D[41]="Tom 4 (low)";  D[42]="Hi-hat closed"
  D[45]="Tom 3";         D[46]="Hi-hat open";  D[47]="Tom 2"
  D[48]="Tom 1 (high)";  D[49]="Crash L";      D[51]="Ride R"
  D[52]="China";         D[53]="Ride R bell";  D[55]="Ride L bell"
  D[57]="Crash R";       D[59]="Ride L"
}
function noteName(n,   oct) { oct = int(n/12) - 2; return NM[(n%12)+1] oct }
function num(s) { gsub(/[^0-9-]/, "", s); return s+0 }
function field(key,   i) { for (i=1;i<=NF;i++) if ($i==key) return num($(i+1)); return "" }
/Note on/ {
  n=field("note"); v=field("velocity")
  drum = (n in D) ? D[n] : "-- (no drum mapped)"
  printf("NOTE ON   note %-3d  %-4s  vel %-3d  ->  %s\n", n, noteName(n), v, drum)
  fflush(); next
}
/Note off/ {
  n=field("note")
  printf("note off  note %-3d  %-4s\n", n, noteName(n)); fflush(); next
}
/Control change/ {
  printf("CC        controller %d  value %d\n", field("controller"), field("value")); fflush(); next
}
/Pitchbend|Pitch bend/ { printf("PITCH BEND value %d\n", field("value")); fflush(); next }
/Program change/ { printf("PROGRAM   %d\n", field("program")); fflush(); next }
'
