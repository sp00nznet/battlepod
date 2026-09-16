#!/bin/sh
# Replay the cockpit boot and check it still reaches every milestone it reached
# before. The firmware narrates itself over its serial console, so its own
# output is the ground truth - no golden file of ours, and nothing of VWE's in
# the repo.
#
# The corpus is the VWE release, which cannot be redistributed. Point
# VWE_GAME_FILES at the extracted "Console Files/Game Files" directory; without
# it this skips rather than fails.

set -eu

BIN=${BIN:-./build/battlepod.exe}
[ -x "$BIN" ] || BIN=./build/battlepod

if [ ! -x "$BIN" ]; then
    echo "conformance: $BIN not built; run make first" >&2
    exit 1
fi

echo "== self-check =="
"$BIN" --selftest

if [ -z "${VWE_GAME_FILES:-}" ] || [ ! -f "${VWE_GAME_FILES}/Full_Load_3_0" ]; then
    cat >&2 <<EOF

conformance: SKIPPED - no release present.

  The corpus is VWE Release 13.1.8, which this repo does not and will not
  redistribute. Get it from https://archive.org/details/vwe-release-13.1.8,
  extract it with unar, and set:

    VWE_GAME_FILES="<extracted>/.../BattleTech 13.1.8/Console Files/Game Files"

EOF
    exit 0
fi

OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

# Scenario 1: a cold boot with everything the pod's absent boot monitor would
# have supplied - vectors, a timebase and its service table - plus stubs for the
# three boards that are not modelled. Runs until the firmware settles into its
# main loop polling for a packet.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" \
    --duart 11000 --rstub 3FF00000 --monitor --clock 2000808 \
    --poke 50001000=55000000 --set 40000100=1234567 \
    --steps 60000000 --top 0 > "$OUT" 2>&1 || true

# Scenario 2: patch an RTS over the game init to reach the firmware's own
# diagnostic monitor, then type at it - ask for the clock, then walk into the
# Remote I/O submenu and request a lamp.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" \
    --duart 11000 --set 2138A64=4E754E75 --duart-in 'c\r' \
    --steps 5000000 --top 0 >> "$OUT" 2>&1 || true

"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" \
    --duart 11000 --set 2138A64=4E754E75 --duart-in 's\r3\r' \
    --steps 8000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 3: with interrupts running, drive one of each Remote I/O device and
# check the packets that reach the wire, checksums and all.
for cmd in 's\r3\r05\r01\r' 's\r2\r80\r05\r' 's\r1\r80\rBATTLTEC\r'; do
    "$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" \
        --duart 11000 --set 2138A64=4E754E75 --duart-in "$cmd" \
        --steps 20000000 --top 0 >> "$OUT" 2>&1 || true
done

# Scenario 4: hand the booted firmware one received packet through the stubbed
# boot monitor and check it consumes it - the release-buffer service is called
# exactly once in response.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" \
    --duart 11000 --rstub 3FF00000 --monitor --clock 2000808 \
    --poke 50001000=55000000 --set 40000100=1234567 \
    --packet 00 --steps 60000000 --top 0 >> "$OUT" 2>&1 || true

# One checkpoint per line: each is a string the firmware must still print.
CHECKS="BTS2--Up
TI Reset Sent
TI Reset Complete
Allocating 2000 RAM for resource map
Allocate handle 1, addr 10000000, error 0
Building resource map
Res Type 1 header found
Res Type 4 header found
Res Type 2 header found
Res Type 7 header found
Giving load resource map command, size 1268
Load Resource Map, error 0
Freeing resource map RAM
Free, error 0
main game loop (SecCom 674 bytes).
renderer commands: 6 posted
cmd 6    op=00000006
boot monitor services called
BattleTech 2 Test Program
y - START TEST GAME
Time 00:00:00:00 Raw Clock: 0
Lamp number in hex (00 - 3b, 50 - 53 and 60)
01 00 03 03 D3 05 01 D9
01 00 03 03 D2 80 05 57
01 00 0A 0A D1 80 42 41 54 54 4C 54 45 43 A4
  +1C  x1
01 00 01 01 D5 D5
  lamp 05 brightness 01
  bargraph 80 bars 5
  display 80 \"BATTLTEC\""

pass=0
total=0
echo
echo "== boot checkpoints =="
# Read with IFS cleared so leading and trailing spaces in a checkpoint survive.
while IFS= read -r check; do
    [ -n "$check" ] || continue
    total=$((total + 1))
    if grep -qF "$check" "$OUT"; then
        pass=$((pass + 1))
        printf '  ok    %s\n' "$check"
    else
        printf '  FAIL  %s\n' "$check"
    fi
done <<EOF
$CHECKS
EOF

# The model archive gets its own checkpoints. These are floors, not equalities:
# the decoder is meant to get better, and a number going up should not fail a
# build - but a number going down means something that used to decode no longer
# does, which is exactly what this is for.
TI_RES="${VWE_GAME_FILES}/Cockpit Software/battletech_ti_res"
if [ -f "$TI_RES" ]; then
    echo
    echo "== model archive =="
    CHECKTEXT=$(python tools/model.py "$TI_RES" --stats 2>/dev/null)
    check_at_least() {
        got=$(echo "$CHECKTEXT" | grep -F "$1" | head -1 | cut -d: -f2 | awk '{print $1}')
        total=$((total + 1))
        if [ -n "$got" ] && [ "$got" -ge "$2" ]; then
            pass=$((pass + 1))
            printf '  ok    %-32s %s (floor %s)\n' "$1" "$got" "$2"
        else
            printf '  FAIL  %-32s %s (floor %s)\n' "$1" "${got:-?}" "$2"
        fi
    }
    check_at_least "header +0x58 is a known opcode" 130
    check_at_least "stream walks to a return"        130
    check_at_least "vertex count matches the header" 120
    check_at_least "vertices reproduce the box"      84
    check_at_least "box within 2% of the model size" 105
    check_at_least "material count matches"          56
fi

# The cockpit ROM's vehicle table is checked against something the ROM does not
# control: a spreadsheet in the release writes out three loadouts in words, and
# decoding those three records has to produce them.
ROM="${VWE_GAME_FILES}/Cockpit Software/ROM3_0"
if [ -f "$ROM" ]; then
    echo
    echo "== vehicle table =="
    CHECKTEXT=$(python tools/vehicles.py "$ROM" --check 2>/dev/null)
    check_at_least "vehicle records that decode" 38
    check_at_least "chassis in the vehicle table" 6
    check_at_least "weapons named" 20
    check_at_least "loadouts matching by name" 3
    check_at_least "loadouts matching in full" 2
fi

echo
echo "== tool self-checks =="
for t in tools/model.py tools/render.py tools/tms340run.py tools/vehicles.py; do
    total=$((total + 1))
    if python "$t" --selftest >/dev/null 2>&1; then
        pass=$((pass + 1))
        printf '  ok    %s --selftest\n' "$t"
    else
        printf '  FAIL  %s --selftest\n' "$t"
    fi
done

echo
echo "conformance: $pass/$total checkpoints passed"

if [ "$pass" -ne "$total" ]; then
    echo
    echo "--- run output ---" >&2
    cat "$OUT" >&2
    exit 1
fi
