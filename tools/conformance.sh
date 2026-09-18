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
# The panel renderer shares the Remote I/O decoder; its self-check is built
# without SDL so it runs anywhere.
[ -x ./build/paneltest.exe ] && ./build/paneltest.exe --selftest
[ -x ./build/viewtest.exe ] && ./build/viewtest.exe --selftest
# The same emulator built with SDL, hosting the windows itself.
[ -x ./build/cockpit.exe ] && ./build/cockpit.exe --selftest

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
  display 80 \"BATTLTEC\"
20 01 00 20 47 41 4D 45 20 52 55 4E 4E 49 4E 47
Hex data from remote I/O is displayed below
[d3]
set 0218AEB0 = 01020000 at pc 02122D9C
tap 0214604E hit 1
text 56704, data 4720, bss 692, linked at 0
  absflag 1 (no relocations)
Starting Secondary
Secondary Started
4007e000, 
674, (-
clr.b   (A0)
12a,A0), D0
12e,A0), D0
132, D0
tap 0212300A hit 1
tap 02123062 hit 1
tap 021230C8 hit 1
b9, D0
47, D0
f6, D0
a, D0
0214C44E  cmpi.l
  0000  02 1F 99 AC 02 1F A0 60
  0000  41 20 00 00 42 48 00 00 43 16 00 00
  0000  44 7A 00 00 47 1C 40 00 45 9C 40 00
tap 021492D8 hit 1
  0000  55 00 00 01
02122184  jsr
0215BA8A  move.b
0215B9F8  ori.b
02123336  ori.b"

# Scenario 4b: the other direction on the Remote I/O link. Nothing had ever
# driven that receiver, and the stick, throttle and pedals arrive on it. The
# firmware's own "display hex data from remote I/O" shows the payload of a frame
# fed in, with the framing stripped - which is the whole transport, proven by
# the firmware rather than by us.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --set 2138A64=4E754E75 --duart-in 'g'     --rio-in '01 00 03 03 D3 05 01 D9'     --steps 40000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4c: give the pod a network identity once it is running, which is
# what a configured cockpit looks like, and the network receive gets past its
# first test instead of returning -1 before touching anything.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --clock 2000808     --poke 50001000=55000000 --set 40000100=1234567     --set-at 02122D9C 0218AEB0=01020000 --set-at 02122D9C 0218AEB4=00000102     --tap 0214604E --steps 60000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4g: the SecCom message ring - the indices it keeps and the slot
# arithmetic, straight out of the enqueue.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0212C1EC:24 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 4f: the SecCom block's address, read straight out of the code that
# sets it up - the base written to its pointer, then 0x674 bytes zeroed, then
# the handshake.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02138B52:11 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 4e: bring the secondary display up through the firmware's own menu.
# The handshake is a spin on 0x40000100 waiting for the Amiga to say it is
# ready; supplying that word gets past it and the firmware says so.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --set 2138A64=4E754E75 --set 40000100=1234567     --duart-in 'p' --steps 40000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4d: load the Amiga secondary display's own program and run it. It is
# a 601A image linked at zero with no relocations, so it goes where it expects
# to be rather than where the cockpit stages it.
if [ -f "${VWE_GAME_FILES}/Cockpit Software/AMIGA3_0" ]; then
    "$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"         --amiga "${VWE_GAME_FILES}/Cockpit Software/AMIGA3_0"         --steps 200000 --top 0 >> "$OUT" 2>&1 || true
fi

# Scenario 4h: hand the pod a game message and follow it in. A byte-0 opcode the
# low-level dispatch does not claim falls through to the router, passes the
# identity filter, and is handed to Post_Event as an event of kind 3 - which is
# the whole inbound path for a message from the operator console.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --clock 2000808     --poke 50001000=55000000 --set 40000100=1234567     --packet '30 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 21'     --tap 0212300A --tap 02123062 --tap 021230C8     --steps 60000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4i: the game's own message dispatch - a 71-entry jump table over
# packet byte 0, opcodes 0xB9 to 0xFF, which is the range the pod also sends in.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0213CF2C:7 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 4j: ten of those opcodes, 0xF6 to 0xFF, share one arm, and that arm
# is a second dispatch of its own over the same byte - the pod's configuration
# and mode messages, which it only ever receives.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02104356:6 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# and the arena the entity table indexes: 1000 entities of 0x6B4 bytes.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0214C440:6 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 4k: drive a mech from outside. The static reading says opcode 0xE1
# carries seven floats and that the handler writes them into the entity the
# packet names, at +0x26, +0x2A, +0x2E, +0xAA, +0xB2, +0xB6 and +0xAE. This
# proves it on the running firmware: inject the packet, then read entity 1 out
# of memory. Nothing here is patched or stubbed - the packet goes in at the
# wire and the cockpit's own code puts the numbers where they land.
#
# Entity 1 is at 0x021FA060: the boot builds 1000 entities of 0x6B4 bytes from
# 0x021F99AC and fills the pointer table at 0x02189F10.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --clock 2000808     --poke 50001000=55000000 --set 40000100=1234567     --packet 'E1 00 00 00 00 00 00 00 00 00 00 01 41 20 00 00 42 48 00 00 43 16 00 00 44 7A 00 00 45 9C 40 00 46 40 E4 00 47 1C 40 00'     --peek 02189F10:8 --peek 021FA086:12 --peek 021FA10A:12     --steps 60000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4l: boot with the audio board answered rather than poked. The board
# is a ring the 68020 fills and the DSP drains; --astub drains it as fast as it
# is filled and reports the download complete, which is the last of the ROM's
# four subsystem checks to stop failing. The bus log is the evidence: with the
# poke the download shows as 1.2 million open-bus accesses, with the board it
# shows as none, because the ring is real memory.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --astub --clock 2000808     --set 40000100=1234567 --tap 021492D8 --peek 50001000:4     --steps 200000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4m: the watchdog. Get_Event, the top of the game's event pump, holds
# a deadline against the free-running timebase and calls a three-instruction
# subroutine when it passes - 0x80 then 0x00 into 0x00010000. That is a pulse on
# a byte register from the one function that runs every frame, which is what a
# watchdog kick looks like and where one belongs.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02122164:9 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0215BA8A:3 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# and the two control ports beside it, written by eight instructions in the
# whole ROM and by nothing else, each time right after interrupt vectors are
# installed.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0215B9E4:6 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02123336:4 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 5: say IDENTIFY_YOURSELF to the booted pod and catch what it builds
# to send back. The tap stands at the door of the packet sender and dumps the
# caller's buffer, because the reply is a stack argument and never reaches a
# device we model.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --clock 2000808     --poke 50001000=55000000 --set 40000100=1234567     --packet '00 00 00 08 00 01 00 00 00 00 00 00'     --tap 021468A4 --tap-dump -0xD2 64     --steps 60000000 --top 0 >> "$OUT" 2>&1 || true

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
    check_exactly() {
        got=$(echo "$CHECKTEXT" | grep -F "$1" | head -1 | cut -d: -f2 | awk '{print $1}')
        total=$((total + 1))
        if [ "$got" = "$2" ]; then
            pass=$((pass + 1))
            printf '  ok    %-32s %s (must be %s)
' "$1" "$got" "$2"
        else
            printf '  FAIL  %-32s %s (must be %s)
' "$1" "${got:-?}" "$2"
        fi
    }
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

    ROM3="${VWE_GAME_FILES}/Cockpit Software/ROM3_0"
    if [ -f "$ROM3" ]; then
        echo
        echo "== hit locations =="
        CHECKTEXT=$(python tools/model.py "$TI_RES" --zones "$ROM3" 2>/dev/null)
        check_at_least "models tagging hit locations" 27
        got=$(echo "$CHECKTEXT" | grep -F "tags outside 1 to 21" | cut -d: -f2 | awk '{print $1}')
        total=$((total + 1))
        if [ "${got:-1}" = "0" ]; then
            pass=$((pass + 1)); printf '  ok    %-32s %s
' "tags outside 1 to 21" "$got"
        else
            printf '  FAIL  %-32s %s
' "tags outside 1 to 21" "${got:-?}"
        fi
    fi

    # Two independent ports of one interpreter: tools/model.py and src/mesh.h.
    # Both are held to the same floor, so a port that quietly drops an opcode
    # fails here rather than turning up as a rendering bug much later.
    echo
    echo "== the two decoders agree =="
    CHECKTEXT=$(python tools/model.py "$TI_RES" --fall 2>/dev/null
                "$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --mesh-all --steps 1 --top 0 2>/dev/null)
    check_at_least "models decoded in python" 130
    check_at_least "models decoded in C" 130
    check_at_least "polygons decoded in python" 2515
    check_at_least "polygons decoded in C" 2515
    check_at_least "vertices decoded in python" 5578
    check_at_least "vertices decoded in C" 5578

    # The release's own scenario files, read with the grammar the operator
    # console parses them by. Every object names a model resource, so a whole
    # map is a list of things this project already decodes and draws.
    SCN="${VWE_GAME_FILES}/Scenarios/BadLands-16"
    if [ -f "$SCN" ]; then
        echo
        echo "== a whole map =="
        CHECKTEXT=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --scene "$SCN" --steps 1 --top 0 2>/dev/null)
        check_at_least "scenario objects placed" 882
        check_at_least "scenario models used" 17
        check_at_least "scenario models decoded" 16
        check_at_least "scenario drop points" 16
    fi

    echo
    echo "== whole mechs =="
    CHECKTEXT=$(python tools/render.py "$TI_RES" --mechs 2>/dev/null)
    check_at_least "chassis that assemble whole" 6
    check_at_least "parts placed on skeletons" 48
    check_at_least "limb joints that meet" 42
    check_at_least "mech polygons in python" 1291

    # The same placement rules, ported to src/rig.h, assembling from the
    # archive in the emulator's own memory. Both are held to the same numbers.
    CHECKTEXT=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --rig-all --steps 1 --top 0 2>/dev/null)
    check_at_least "chassis assembled whole in C" 6
    check_at_least "parts placed in C" 48
    check_at_least "mech polygons in C" 1291
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

# The operator console is the sender. It logs every message it puts on the wire
# by name and with its fields, so its own strings are a protocol specification -
# checked here against tools/logproto.py, which recovers the same vocabulary
# from a real centre's log.
OPSCON="${VWE_GAME_FILES}/../../Console 1.5.12.a01.rsrc"
if [ -f "$OPSCON" ]; then
    echo
    echo "== operator console =="
    CHECKTEXT=$(python tools/opscon.py "$OPSCON" --check 2>/dev/null)
    check_at_least "messages recovered from the console" 31
    check_at_least "entity classes and wire messages" 25
    check_at_least "file grammars recovered" 27
fi

# The two halves of the game protocol have to agree, and where a message is both
# sent and received the same field has to appear on both sides - the sender
# reading it out of the entity structure and the handler writing it back in.
# Any disagreement there is a decoding error, so the floor for it is zero.
#
# The two halves of the game protocol have to agree. The receiver is a 71-entry
# jump table over packet byte 0; the senders are 45 call sites that each write
# their own opcode into the front of the buffer. Every opcode the pod sends must
# be one the table covers, and ROUTER_STATUS_MSG's shape - an 80-byte string
# then a longword, in a 100-byte packet - has to come back out of the sender.
if [ -f "$ROM" ]; then
    echo
    echo "== the game protocol =="
    CHECKTEXT=$(python tools/netmsg.py "$ROM" --check 2>/dev/null)
    check_at_least "call sites found" 45
    check_at_least "opcodes the dispatch handles" 46
    check_at_least "distinct handlers" 37
    check_at_least "opcodes the pod sends" 38
    check_at_least "sent opcodes inside B9..FF" 38
    check_at_least "field pairs confirmed by both ends" 44
    check_at_least "distinct structure offsets" 46
    check_exactly  "field pairs the two ends disagree on" 0
    check_at_least "C5 payload bytes" 100
fi

echo
echo "== tool self-checks =="
for t in tools/model.py tools/render.py tools/tms340run.py tools/vehicles.py tools/opscon.py tools/fnstr.py tools/netmsg.py; do
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
