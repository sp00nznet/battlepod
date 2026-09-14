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

# Scenario 1: a normal cold boot, with the three unmodelled boards stubbed.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" \
    --duart 11000 --rstub 3FF00000 \
    --poke 50001000=55000000 --set 40000100=1234567 \
    --top 0 > "$OUT" 2>&1 || true

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
renderer commands: 5 posted
BattleTech 2 Test Program
y - START TEST GAME
Time 00:00:00:00 Raw Clock: 0
Lamp number in hex (00 - 3b, 50 - 53 and 60)
01 00 03 03 D3 05 01 D9
01 00 03 03 D2 80 05 57
01 00 0A 0A D1 80 42 41 54 54 4C 54 45 43 A4"

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

echo
echo "conformance: $pass/$total checkpoints passed"

if [ "$pass" -ne "$total" ]; then
    echo
    echo "--- run output ---" >&2
    cat "$OUT" >&2
    exit 1
fi
