#!/usr/bin/env bash
# lp_map.sh — interactively map Launchpad Pro MK3 pads to the MIDI they emit,
# to verify the RiftwayLabsLooper note layout. User-paced: it prompts for each pad,
# you press that pad once, then hit ENTER, and it prints what the device sent.
#
# Reads via ALSA seq (works even while Reaper/PipeWire hold the raw device).
# Captures BOTH the MIDI port (36:0) and the DAW port (36:2) so we can see
# which port a pad actually uses and whether the note matches what RiftwayLabsLooper
# expects.
#
# Usage: tools/lp_map.sh         # map the Record, Stop, Clear rows (cols 1-5)
#        tools/lp_map.sh all     # also map Reverse + Select rows
set -uo pipefail

# Resolve the Launchpad ALSA-seq client number by name (card numbers vary).
CLIENT=$(aseqdump -l 2>/dev/null | awk '/Launchpad Pro MK3/{print $1; exit}' | cut -d: -f1)
[ -z "${CLIENT:-}" ] && CLIENT=$(aconnect -l 2>/dev/null | awk -F'[ :]' '/client .*Launchpad/{print $2; exit}')
if [ -z "${CLIENT:-}" ]; then echo "ERROR: Launchpad not found in ALSA seq (aseqdump -l)"; exit 1; fi
P_MIDI="${CLIENT}:0"   # LPProMK3 MIDI
P_DAW="${CLIENT}:2"    # LPProMK3 DAW
echo "Launchpad seq client = $CLIENT  (MIDI=$P_MIDI  DAW=$P_DAW)"

LOG=$(mktemp)
# One capture per port, tagged, appended to the same log. stdbuf+--line-buffered
# keep it real-time; drop clock/sensing noise at the source.
stdbuf -oL aseqdump -p "$P_MIDI" 2>/dev/null | grep --line-buffered -viE "Clock|Active Sensing" | sed -u 's/^/[MIDI] /' >> "$LOG" &
stdbuf -oL aseqdump -p "$P_DAW"  2>/dev/null | grep --line-buffered -viE "Clock|Active Sensing" | sed -u 's/^/[DAW ] /' >> "$LOG" &
trap 'kill $(jobs -p) 2>/dev/null; rm -f "$LOG"' EXIT
sleep 0.6

# button label | expected RiftwayLabsLooper note
ROWS=(
  "Track 1 RECORD (top-left pad)|81"
  "Track 2 RECORD|82"
  "Track 3 RECORD|83"
  "Track 4 RECORD|84"
  "Track 5 RECORD|85"
  "Track 1 STOP (2nd row)|71"
  "Track 2 STOP|72"
  "Track 3 STOP|73"
  "Track 4 STOP|74"
  "Track 5 STOP|75"
  "Track 1 CLEAR (amber row)|61"
  "Track 2 CLEAR|62"
  "Track 3 CLEAR|63"
  "Track 4 CLEAR|64"
  "Track 5 CLEAR|65"
)
if [ "${1:-}" = "all" ]; then
  ROWS+=(
    "Track 1 REVERSE|41" "Track 2 REVERSE|42" "Track 3 REVERSE|43" "Track 4 REVERSE|44" "Track 5 REVERSE|45"
    "Track 1 SELECT|31"  "Track 2 SELECT|32"  "Track 3 SELECT|33"  "Track 4 SELECT|34"  "Track 5 SELECT|35"
  )
fi

echo
echo "=== RiftwayLabsLooper Launchpad pad map ==="
echo "Press ONLY the named pad once, then hit ENTER. (Ctrl-C to stop early.)"
echo "Result columns: PAD = what you pressed | EXPECT = note RiftwayLabsLooper wants | GOT = what the device sent"
echo
printf "%-34s %-7s %s\n" "PAD" "EXPECT" "GOT"
printf "%-34s %-7s %s\n" "----------------------------------" "------" "------------------------------"

for entry in "${ROWS[@]}"; do
  label="${entry%%|*}"; expect="${entry##*|}"
  mark=$(wc -l < "$LOG")
  # prompt on stderr so stdout stays clean for copy/paste
  printf ">>> Press [%s] then ENTER... " "$label" >&2
  read -r _ || break
  new=$(tail -n +$((mark+1)) "$LOG" 2>/dev/null \
        | grep -viE "Clock|Active Sensing|aftertouch|subscribed|Waiting|^.MIDI. Source|^.DAW . Source")
  # first note-on (vel>0) preferred; else first meaningful event
  got=$(echo "$new" | grep -iE "Note on" | grep -viE "velocity 0$" | head -1)
  [ -z "$got" ] && got=$(echo "$new" | grep -iE "Note|Control|Program|Pitch" | head -1)
  got=$(echo "$got" | sed -E 's/  +/ /g; s/^ //')
  [ -z "$got" ] && got="(nothing captured)"
  printf "%-34s %-7s %s\n" "$label" "$expect" "$got"
done

echo
echo "=== copy everything from 'PAD ... GOT' down, paste it back to the session ==="
