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
trap 'rm -f "$OUT" "$OUT.rgb" "$OUT.pkt" "$OUT.game"' EXIT

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
'TI ERROR!  Dump of fixed area error variables'
'TI_ErrorNumber   0x%x'
'TI_FPUPC         0x%x'
'Class_ID=%d, Number=%d, Thing_Flags=0x%08x'
----- PERIODIC -----
02104EC4  lea
0213CE58  lea
02139084  move.l
JJoint 1 Angle 0.000000
Type 0, Color 0, Flags 7
tap 0214465C hit 1
tap 0214C770 hit 1
cmd 200  op=00000006
    viewport  (0,0)-(479,359)  480x360  centre (239,179)
        pick (16,16) -> entity 0 part 0
  93  10000.0000  1.0000  60.0000  0.0940  0.0620  0.0940  0  0  0
tap 0212DB70 hit 1
tap 0213BB92 hit 1
tap 0213BA92 hit 1
tap 021188BE hit 1
tap 021189D4 hit 1
tap 0210E22E hit 1
set 021F99AE = 00000001 at pc 02122154
tap 02130296 hit 1
tap 0214C57E hit 1
tap 0212D058 hit 1
tap 0212ED04 hit 1
tap 0212EFDC hit 1
tap 0212F02C hit 1
  0000  00 00 00 00 00 01 00 00 00 01 00 00 00 07 00 00
  0000  00 00 00 02
mission opcodes executed: 8192
  0000  42 31 5F 42 61 74 74 6C 65 54 65 63 68 5F 31 00
tap 0211786C hit 1
tap 02117788 hit 1
0213F35E  fmul.d
02144646  asr.l
0212DE74  bra
0212E2E0  btst
021188C8  move.b
021198A6  cmpi.w
02118D06  jsr
02118D3A  jsr
02119A5A  move.l
02119426  jsr
02119A10  muls.w
0211A004  cmpi.w
0211A340  cmpi.w
02119084  add.l
'\nderef:Illegal value type %d!'
'Interpreter error, bad opcode %02xh at offset 0x%04lx!'
0212DCF8  fadd.s
       100.0000    8.2000 -200.0000 
tap 02138F8E hit 3
tap 02144724 hit 1
  0010  00 00 00 01 FF FF FF FF 00 00 00 08 00 00 00 0A
  0020  00 00 00 00 00 00 00 00 00 00 01 DF 00 00 01 67
  0030  00 00 01 E0 00 00 01 68 00 00 00 EF 00 00 00 B3
Course 1.00000, Speed 90.00000, X 100.00000, Y 200.00000, Z 5.40000
QProfile Cleared
02139328  subq.l
0211EB74  addi.l
  0000  52 6F 74 61 74 65 20 43 61 6D 65 72 61 00 4D 6F
'Course %3.5f, Speed %3.5f, X %3.5f, Y %3.5f, Z %3.5f'
'Type %d, Color %d, Flags %d'
'Joint %d Angle %f'
021396CE  adda.l
02139670  lea
----- CULLING -----
----- RENDERER -----
----- ROUTER -----
----- EVENTS -----
Cone Reject     0
Remaining time = 600
My_Mech_Ptr = 0x21f99ac
Class_ID=0, Number=0, Thing_Flags=0x00000007
0211E0D8  cmpi.l
02106CC6  cmpi.l
0211D62C  cmpi.l
02150BA0  cmpi.l
02150CF6  cmpi.l
0211DC80  pea    'Mech'
0211DCCC  pea    'Camship'
0211DDFE  pea    'Hovercraft'
0211DE5A  pea    'VTV'
0211DEA6  pea    'Copter'
0211E044  pea    'Escape pod'
'Create unknown thing %d, class %d received'
02138CE2  move.l
02139B4E  move.l
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

# Scenario 4n: the renderer's fixed error area, named by the ROM itself. The
# TI ERROR! dump is a straight run of fifteen longwords from 0x3FFFE164, each
# printed with its own label, and two of those addresses were listed as
# measured and unexplained until this was read.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02138CE2:6 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# and the entity header, from the periodic report: Class_ID, Number, Thing_Flags
# at +0x02, +0x06 and +0x0A of My_Mech_Ptr.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02139B34:7 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# The labels themselves never reach the console on a healthy boot - nothing
# errors and the periodic report is not running - so they are read out of the
# image instead, by the same tool that names handlers from their strings.
if [ -f "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" ]; then
    python tools/fnstr.py "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" 020FFFE4         02138CB8:200 02139B20:60 >> "$OUT" 2>&1 || true
fi

# Scenario 4o: the class numbering. Create_Thing is a dense switch over classes
# 0 to 18, and six of its arms push a name before they build anything, so the
# numbering comes out of the ROM rather than out of a guess.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0211E0D8:5 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# The view heading is Course plus the field after it, wrapped at 360, and the
# matrix builders convert degrees to radians - the units, from the code.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0212DCEC:5 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0213F35E:2 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# record_end computes the length as the longwords written minus two, which is
# the 2 + len rule proved from the writing side.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02144646:2 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# The builder jumps past its other three draw-object emitters, and +0xBB bit 0
# opens a type 3 record carrying the viewer's own position instead.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0212DE74:2 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0212E2E0:3 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# Missions are bytecode: a fetch-decode loop over 162 opcodes, with the ROM
# naming the machine in its own error messages.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 021188BE:4 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 021198A6:5 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# Create_Thing has exactly one caller in the whole ROM, and it is bytecode
# opcode 0x24 - so a thing is only ever made by a mission script.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02118D06:14 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# The operand stack is typed: push writes a tag at +0 and the value at +4, one
# 0x4C-byte frame at a time. And 0x44 is return.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02119A54:6 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02119426:4 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# 0x65 pushes a local - operand times the frame size, plus a frame base - and
# 0x70 and 0x73 dispatch again on their operand, eleven ways each.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02119A10:3 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0211A004:2 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0211A340:2 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0211906A:8 --steps 1 --top 0     >> "$OUT" 2>&1 || true
if [ -f "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" ]; then
    python tools/fnstr.py "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" 020FFFE4         0211A306:100 >> "$OUT" 2>&1 || true
fi
if [ -f "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" ]; then
    python tools/fnstr.py "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" 020FFFE4         0211972E:80 >> "$OUT" 2>&1 || true
fi
# Create_Thing is one of seven sites with the same five-instruction class
# switch; the other six are here so a change to any of them shows up.
for a in 02106CC6 02106E08 0211D62C 0211D7F0 02150BA0 02150CF6; do
    "$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis "$a":5 --steps 1 --top 0         >> "$OUT" 2>&1 || true
done
if [ -f "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" ]; then
    python tools/fnstr.py "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" 020FFFE4         0211DC76:500 >> "$OUT" 2>&1 || true
fi

# Scenario 4p: make the pod report on itself. 0x021BB1A0 is a request flag -
# the main loop calls the status report when it is set and clears it again -
# and the in-game message 0x73 is what normally raises it. Setting it directly
# gets the whole report out of a booted pod: the DUART's own view of itself,
# the renderer's culling counters, frame-rate statistics, the router's traffic
# high-water marks and the event queues'.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --astub --clock 2000808     --set 40000100=1234567 --set-at 02122154 21BB1A0=00000001     --steps 60000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4q: the mech dump names the position fields. Its printf arguments are
# pushed right to left, so the last push is the first conversion: Course from
# +0xF8, Speed from +0x114, then X, Y and Z from +0x26, +0x2A and +0x2E. That
# is the firmware saying what those three longwords are, rather than us
# inferring it from the console's field lists.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 021396CA:12 --steps 1 --top 0     >> "$OUT" 2>&1 || true
# and the thirty-slot mech table it walks, which is not the entity table.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0213966A:4 --steps 1 --top 0     >> "$OUT" 2>&1 || true
if [ -f "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" ]; then
    python tools/fnstr.py "${VWE_GAME_FILES}/Cockpit Software/ROM3_0" 020FFFE4         02139660:100 0213A146:40 >> "$OUT" 2>&1 || true
fi

# Scenario 4r: the command the README tells a reader to run. It had rotted -
# it named an option the binary does not have - and nothing here was checking
# it, because every other scenario is written against the flags rather than
# against the documentation. Now the front page is a test.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --astub --set 40000100=1234567     --steps 200000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4s: the animation editor. A state byte at 0x0215DCF7 subscripts a
# table of names at 0x021698EA, and the names are an editor's - rotate and move
# a camera, a focus, an object and a joint, step frames, play back, load and
# save. The F6-FF message block writes exactly the load, save and append states.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02104EBA:5 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --peek 0210108F:80 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 4t: 0xBE names an owner. Two 42-byte records, each a key byte and a
# forty-character name, initialised with key 0xFF and looked up by matching the
# key against an entity's Owner byte.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0213CE3E:10 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0211EB74:4 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 4u: event kind 0x0A is an in-game message, and the arm routes it by
# the class of the pod's own mech - a VTV one way, a Copter nowhere, anything
# else to the byte-0x13 dispatch.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 0213907E:4 --steps 1 --top 0     >> "$OUT" 2>&1 || true
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0" --dis 02139328:4 --steps 1 --top 0     >> "$OUT" 2>&1 || true

# Scenario 4v: the in-game console. The "second dispatch over packet byte 0x13"
# is a keyboard: kind 0x0A is posted from one site, a one-byte console read, and
# byte 0x13 is the low byte of its parameter. Typing at the modelled serial port
# with nothing patched gets answers - and `x` leaves the game for the monitor,
# which is how the monitor is supposed to be reached.
for key in J Q s x; do
    "$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"         --duart 11000 --rstub 3FF00000 --monitor --astub --clock 2000808         --set 40000100=1234567 --duart-in "$key"         --steps 90000000 --top 0 >> "$OUT" 2>&1 || true
done

# Scenario 4w: the whole loop. Make entity 0 a Mech and put it in the thirty-slot
# table, send it a movement packet at the wire, then type `d` and let the pod
# say where it thinks it is. Everything between the wire and the print is the
# cockpit's own code. Speed comes back scaled by 360, which is what the dump
# does to +0x114, so 0.25 prints as 90.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --astub --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001 --set-at 02122154 21943DA=021F99AC     --packet 'EC 00 00 00 00 00 00 00 00 00 00 00 42 C8 00 00 43 48 00 00 40 AC CC CD 3F 80 00 00 00 00 00 00 3E 80 00 00 00 00 00 00'     --duart-in 'd' --steps 90000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4x: the pod builds a frame. With entity 0 a Mech in the thirty-slot
# table, both display-list emitters run and the buffer holds a 480x360 viewport
# and a draw-object record. The taps are the evidence that it draws at all.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --astub --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001 --set-at 02122154 21943DA=021F99AC     --tap 0214465C --tap 02144724 --peek 0218AF14:96     --steps 200000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4y: the renderer's frame-complete interrupt. Vector 0x42, cause 0x50
# in bits 4-6 of the word at 0x3800001C, acknowledged by clearing bit 7. Its arm
# stamps the timebase into 0x0217A326, which Async_Render clears on the way out
# and the end-of-frame code waits on. --rirq raises it after every render.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001 --set-at 02122154 21943DA=021F99AC     --tap 0214C770 --tap 02138F8E --steps 300000000 --top 0 >> "$OUT" 2>&1 || true
# and with the completion delayed past the clear that would wipe it, frames flow:
# 400 renderer commands where there were six.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001 --set-at 02122154 21943DA=021F99AC     --steps 300000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4z: a frame with the mech in it. Place entity 0 at X 100, Y 200,
# Z 5.4 with an 0xEC packet and let the frames run: the display list's transform
# comes back as (X, Z + 2.8, -Y) with a one-degree yaw from Course 1.0, and the
# item stream carries real drawing opcodes. Wire to picture, in one run.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001 --set-at 02122154 21943DA=021F99AC     --packet 'EC 00 00 00 00 00 00 00 00 00 00 00 42 C8 00 00 43 48 00 00 40 AC CC CD 3F 80 00 00 00 00 00 00 3E 80 00 00 00 00 00 00'     --tap 0212DB70 --steps 300000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4A: start a mission. 0xED is dispatched on the class of the entity it
# names - the id is at packet +0x32 - and class 19's arm starts the spawner
# task, which had never run in any session before this.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567 --set-at 02122154 21FA062=00000013     --packet 'ED 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01'     --tap 0213BB92 --tap 0211786C --tap 02117788     --steps 300000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4B: run a mission script. The name goes in the 0xED packet at +0x0A
# and the entity it names must be class 19, the mission class. The record takes
# the name, the interpreter's program counter lands in the ROM's bytecode, and
# the fetch-decode loop runs.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567 --set-at 02122154 21FA062=00000013     --packet 'ED 00 00 00 00 00 00 00 00 00 42 31 5F 42 61 74 74 6C 65 54 65 63 68 5F 31 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01'     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0'     --tap 021188BE --tap 021189D4 --tap 0210E22E --peek 021A5DBC:16 --vmtrace     --steps 900000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4C: 0xED's class 1 arm is the player-link path, and it is reachable -
# entity 1 a Mech, entity 2 the mission, three packets in order. It changes
# nothing about what the mission executes, which is the point.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21FA062=00000001 --set-at 02122154 21FA716=00000013     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0'     --packet 'ED 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01'     --packet 'ED 00 00 00 00 00 00 00 00 00 42 31 5F 42 61 74 74 6C 65 54 65 63 68 5F 31 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 02'     --tap 0213BA92 --tap 0213BB92     --steps 900000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4D: My_Mech_Ptr's class gates the whole game. Arena slot 0 is set up
# with class 0, the per-frame dispatch at 0x02138F8E switches on that class, and
# only class 1 - Mech - reaches the routine that would build a real one. Giving
# slot 0 a class breaks the circle: the class 1 arm runs, and a mission run goes
# from 400 renderer commands to the count a pod reaches with no mission at all.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567 --set-at 02122154 21F99AE=00000001     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 02 00 00 00 00 00 00 00 00 00 09 27 C0'     --packet 'ED 00 00 00 00 00 00 00 00 00 42 31 5F 42 61 74 74 6C 65 54 65 63 68 5F 31 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01'     --tap 02130296 --tap 02138F8E     --steps 900000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4E: create a thing. `0xF8` is the animation editor's create command;
# its arm switches on the payload longword at +0x02 and selector 1 builds a
# class 1 Mech through the arena allocator. The entity that comes back is the
# first this project has ever made: class 1, Number 1, Thing_Flags 7, and the
# arena cursor at 0x021A5DB8 moved on.
#
# This only works because the packet buffer no longer sits under the clock. The
# selector spans bytes 2..5 and the timebase at 0x02000808 used to land on 4..7.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --packet 'F8 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --tap 0214C57E --tap 0212D058     --peek 021FA060:16 --peek 021A5DB8:4     --steps 900000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4F: the viewer's class is what turns geometry on. With arena slot 0
# left at class 0 the pod posts a display list with no draw-model items at all;
# give it class 1 and the same run posts hundreds, naming models 72, 73, 95 and
# 96. Add a created Mech and the firmware's own cone-culling report goes from
# Total 0 to Total 1 - the entity is a candidate the culler tests.
#
# Checked with check_contains below rather than a CHECKS line, because the item
# opcodes are written with a leading $ and CHECKS is a double-quoted string.
DRAW=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --monitor --astub --clock 2000808     --set 40000100=1234567 --set-at 02122154 21F99AE=00000001     --steps 200000000 --top 0 2>&1 || true)
NODRAW=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --monitor --astub --clock 2000808     --set 40000100=1234567     --steps 200000000 --top 0 2>&1 || true)

# Scenario 4G: which of the draw-model emitter's 21 call sites actually run.
# Three do, and they are all inside the Mech's own cull-and-draw op: two ask for
# a constant model (0x60 and 0x5F, 96 and 95) and the third takes one out of
# 0x021BB172. Eight taps used to be the limit and the ninth onward were dropped
# in silence, which made every call site look unreached.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --monitor --astub --clock 2000808     --set 40000100=1234567 --set-at 02122154 21F99AE=00000001     --tap 0212ED04 --tap 0212EFDC --tap 0212F02C     --steps 200000000 --top 0 >> "$OUT" 2>&1 || true

# Scenario 4H: the created Mech, seen. Two things stood between it and the
# frame, and neither was the renderer. The cull test at 0x02111636 passes a
# thing only within its own radius plus the pod's visibility range - which is
# 0x02193C24 + 0x02193C28, written only by 0xE5's handler from packet +0x44 and
# +0x48, and every 0xE5 sent so far carried zeros there. And its cone test uses
# tan of the viewer's +0x118, a half field of view the Mech constructor sets to
# 30 degrees and a hand-classed entity 0 never gets. With a range of 500, the
# viewer 40 units off facing 180, and +0x118 = 30, the Mech arrives: a type 3
# naming model 0x1C4 (452, the MadCat), a type 4 for its shadow and a type 5
# for its searchlight. The control is the same run with the range left zero.
SEEN=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567 --set-at 02122154 21F99AE=00000001     --set-at 02122154 21F99D2=45FA0000 --set-at 02122154 21F99D6=45F8C000     --set-at 02122154 21F9AC4=41F00000 --set-at 02122154 21F9AA4=43340000     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0 00 00 00 00 00 00 01 F4 00 00 01 F4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --packet 'F8 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --frame-out "$OUT.rgb"     --steps 400000000 --top 0 2>&1 || true)
UNSEEN=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567 --set-at 02122154 21F99AE=00000001     --set-at 02122154 21F99D2=45FA0000 --set-at 02122154 21F99D6=45F8C000     --set-at 02122154 21F9AC4=41F00000 --set-at 02122154 21F9AA4=43340000     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --packet 'F8 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --steps 400000000 --top 0 2>&1 || true)

# Scenario 4I: the chassis is the word at 0xF8's +0x08, and it is an index
# into the ROM's 38 vehicle records - the same order tools/vehicles.py reads
# them in. Record 34 is the Avatar Prime, skeleton 456.
AVATAR=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001     --set-at 02122154 21F99D2=45FA0000 --set-at 02122154 21F99D6=45F8C000     --set-at 02122154 21F9AC4=41F00000 --set-at 02122154 21F9AA4=43340000     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0 00 00 00 00 00 00 01 F4 00 00 01 F4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --packet 'F8 00 00 00 00 01 00 00 00 22 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --frame-out "$OUT.rgb"     --steps 400000000 --top 0 2>&1 || true)

# Scenario 4J: a pilot, with nothing written by hand. 0xED is PLAYER_LINK: it
# switches on the class of the entity its +0x32 names, and for a Mech,
# 0x021350FA makes that entity My_Mech_Ptr when the packet's +0x08/+0x09 are
# this pod's node. Create a Mech, link it, and the pod is flying it.
LINKED=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0 00 00 00 00 00 00 01 F4 00 00 01 F4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --packet 'F8 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --packet 'ED 00 00 00 00 00 00 00 00 00 42 31 5F 42 61 74 74 6C 65 54 65 63 68 5F 31 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00'     --peek 0218AEE4:4     --steps 400000000 --top 0 2>&1 || true)

# Scenario 4K: the world. 0xE4 in the game table is the console's create
# message - the one its log calls "Reset world", MECH_CLASS and "Downloading
# Map". 0x0213CF5E switches on the class at +0x0E and builds the thing into
# the arena slot +0x12 names. One class 3 object, model 132, 100 units ahead
# of the viewer, is drawn by the world pass like any Mech.
TERRAIN=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001     --set-at 02122154 21F99D2=45FA0000 --set-at 02122154 21F99D6=45F8C000     --set-at 02122154 21F9AC4=41F00000 --set-at 02122154 21F9AA4=43340000     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0 00 00 00 00 00 00 01 F4 00 00 01 F4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --packet 'E4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 03 00 00 00 14 45 FA 00 00 45 FB E0 00 00 00 00 00 00 00 00 84 3F 80 00 00 43 34 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --frame-out "$OUT.rgb"     --steps 250000000 --top 0 2>&1 || true)

# Scenario 4L: a whole map. tools/mapsend.py turns BadLands-16's 882 objects
# into 0xE4 packets and the viewer stands at its second drop point, inside a
# base. The buildings around it are drawn from the pod's own frame.
MAP=""
if [ -f "${VWE_GAME_FILES}/Scenarios/BadLands-16" ]; then
    python tools/mapsend.py "${VWE_GAME_FILES}/Scenarios/BadLands-16" > "$OUT.pkt"
    MAP=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001     --set-at 02122154 21F99D2=45A84800 --set-at 02122154 21F99D6=45ECB800     --set-at 02122154 21F9AC4=41F00000 --set-at 02122154 21F9AA4=43340000     --packet-file "$OUT.pkt"     --frame-out "$OUT.rgb"     --steps 900000000 --top 0 2>&1 || true)
fi

# Scenario 4M: MECH_CLASS is 0xE4 class 1. Its arm hands 0x0212D10A the
# position, the name at +0x22, a heading at +0x50 and the vehicle record at
# +0x4A - here 34, the Avatar, facing 90.
MECHCLASS=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --set-at 02122154 21F99AE=00000001     --set-at 02122154 21F99D2=45FA0000 --set-at 02122154 21F99D6=45F8C000     --set-at 02122154 21F9AC4=41F00000 --set-at 02122154 21F9AA4=43340000     --packet 'E5 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 09 27 C0 00 00 00 00 00 00 01 F4 00 00 01 F4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --packet 'E4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 01 45 FA 00 00 45 FB E0 00 40 AC CC CD 41 76 61 74 61 72 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 22 00 00 00 00 42 B4 00 00 00 00 00 00 00 00 00 00 00 00 00 00'     --frame-out "$OUT.rgb"     --steps 250000000 --top 0 2>&1 || true)

# Scenario 4N: a game, started the way the console's log starts one and with
# nothing written into memory by hand. 0xE5 for the range, two MECH_CLASS
# 0xE4s - a MadCat at BadLands' second drop point facing 0 and a Loki 100
# units ahead of it - the map as 882 more 0xE4s, and PLAYER_LINK to the
# MadCat. The pod flies it: the eye is at the Mech's cockpit, 8.2 up, and the
# Loki is in the frame with the terrain.
GAME=""
if [ -s "$OUT.pkt" ]; then
    { head -2 "$OUT.pkt"
      echo 'E4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 01 45 A8 48 00 45 EC B8 00 40 AC CC CD 4D 65 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'
      echo 'E4 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 02 45 A8 48 00 45 E9 98 00 40 AC CC CD 54 68 65 6D 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 08 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'
      tail -n +3 "$OUT.pkt"
      echo 'ED 00 00 00 00 00 00 00 00 00 42 31 5F 42 61 74 74 6C 65 54 65 63 68 5F 31 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00'; } > "$OUT.game"
    GAME=$("$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808     --set 40000100=1234567     --packet-file "$OUT.game"     --peek 0218AEE4:4     --frame-out "$OUT.rgb"     --steps 900000000 --top 0 2>&1 || true)
fi

# Scenario 5: say IDENTIFY_YOURSELF to the booted pod and catch what it builds
# to send back. The tap stands at the door of the packet sender and dumps the
# caller's buffer, because the reply is a stack argument and never reaches a
# device we model.
"$BIN" "${VWE_GAME_FILES}/Full_Load_3_0"     --duart 11000 --rstub 3FF00000 --monitor --clock 2000808     --poke 50001000=55000000 --set 40000100=1234567     --packet '00 00 00 08 00 01 00 00 00 00 00 00'     --tap 021468A4 --tap-dump -0xD2 64     --steps 60000000 --top 0 >> "$OUT" 2>&1 || true

pass=0
total=0

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

check_contains() {
    total=$((total + 1))
    if echo "$CHECKTEXT" | grep -qF -- "$1"; then
        pass=$((pass + 1))
        printf '  ok    %s
' "$1"
    else
        printf '  FAIL  %s
' "$1"
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
echo
echo "== boot checkpoints =="
# Read with IFS cleared so leading and trailing spaces in a checkpoint survive.
while IFS= read -r check; do
    [ -n "$check" ] || continue
    total=$((total + 1))
    # -- so a checkpoint that begins with a dash is a pattern, not an option.
    if grep -qF -- "$check" "$OUT"; then
        pass=$((pass + 1))
        printf '  ok    %s\n' "$check"
    else
        printf '  FAIL  %s\n' "$check"
    fi
done <<EOF
$CHECKS
EOF

echo
echo "== geometry =="
CHECKTEXT="$DRAW"
check_contains 'item $240'
check_contains 'item $2C0'
check_count()  {
    total=$((total + 1))
    got=$(echo "$CHECKTEXT" | grep -cF -- "$1" || true)
    if [ "$got" -ge "$2" ]; then
        pass=$((pass + 1))
        printf '  ok    %-32s %s (floor %s)
' "$1" "$got" "$2"
    else
        printf '  FAIL  %-32s %s (floor %s)
' "$1" "$got" "$2"
    fi
}
check_count 'item $240' 300
CHECKTEXT="$NODRAW"
check_count_zero() {
    total=$((total + 1))
    got=$(echo "$CHECKTEXT" | grep -cF -- "$1" || true)
    if [ "$got" -eq 0 ]; then
        pass=$((pass + 1))
        printf '  ok    %-32s %s (must be 0)
' "$1" "$got"
    else
        printf '  FAIL  %-32s %s (must be 0)
' "$1" "$got"
    fi
}
check_count_zero 'item $240'

CHECKTEXT="$SEEN"
check_contains 'type 3, 286 longwords'                      # the Mech's model record
check_contains 'FFFFFFFF        1C4'                        # naming model 452, the MadCat
check_contains '300.0000   150.0000     0.9397     0.9848'  # its searchlight
check_contains 'entity 1 model 452 at (8000.0, 8000.0, 5.4): 224 polygons'  # drawn from the pod's camera
CHECKTEXT="$UNSEEN"
check_count_zero 'type 3,'                                  # no visibility range, no Mech
CHECKTEXT="$AVATAR"
check_contains 'entity 1 model 456 at (8000.0, 8000.0, 5.4)'        # vehicle record 34, the Avatar
CHECKTEXT="$LINKED"
check_contains '0000  02 1F A0 60'                                  # My_Mech_Ptr is the created Mech
check_contains 'pick (240,180)'                                     # and the HUD centres on its view
CHECKTEXT="$TERRAIN"
check_contains 'entity 20 model 132 at (8000.0, 8060.0, 0.0): 57 polygons'  # a class 3 from 0xE4
CHECKTEXT="$MECHCLASS"
check_contains 'entity 1 model 456 at (8000.0, 8060.0, 5.4)'   # MECH_CLASS: an Avatar where it was put
if [ -n "$MAP" ]; then
    CHECKTEXT="$MAP"
    check_contains 'entity 733 model 11 at (5365.0, 7660.0, 0.0): 11 polygons'  # BadLands, from the drop
    check_count_zero 'Create unknown thing'
fi
if [ -n "$GAME" ]; then
    CHECKTEXT="$GAME"
    check_contains '0000  02 1F A0 60'                                   # the pod is flying thing 1
    check_contains 'height 8.20'                                         # from its cockpit
    check_contains 'entity 2 model 451 at (5385.0, 7475.0, 5.4): 206 polygons'  # and sees the Loki
fi

# The model archive gets its own checkpoints. These are floors, not equalities:
# the decoder is meant to get better, and a number going up should not fail a
# build - but a number going down means something that used to decode no longer
# does, which is exactly what this is for.
TI_RES="${VWE_GAME_FILES}/Cockpit Software/battletech_ti_res"
if [ -f "$TI_RES" ]; then
    echo
    echo "== model archive =="
    CHECKTEXT=$(python tools/model.py "$TI_RES" --stats 2>/dev/null)
    # Some evidence is a line of text, not a number: the proof that `0x64`
    # pushes a string is that the bytes read as one.
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
    # VWE printed a Mech Damage Heat Chart for players. Every configuration and
    # every weapon on it has to be in the ROM, and the ones the ROM has that the
    # chart does not are the five whose names say they are test builds.
    check_at_least "chart configurations found in the ROM" 33
    check_at_least "chart weapons found in the ROM" 20
    check_exactly  "configurations the ROM has and the chart does not" 5
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

# The missions are bytecode routines in the ROM, behind a table of named entry
# points. Thirteen of them: two scenarios, eight cameras, and three displays.
if [ -f "$ROM" ]; then
    echo
    echo "== mission scripts =="
    CHECKTEXT=$(python tools/missions.py "$ROM" --check 2>/dev/null)
    check_at_least "mission routines named" 13
    check_at_least "entry offsets ascending" 1
    check_at_least "BattleTech scenarios" 2
    check_at_least "follow-cockpit cameras" 8
    # Operand lengths are counted from each handler's own program-counter
    # steps, not from a table anyone typed in.
    CHECKTEXT=$(python tools/mission_dis.py "$ROM" --lengths 2>/dev/null)
    check_at_least "opcodes with a handler" 94
    check_at_least "opcodes that are control flow" 7
    check_at_least "taking 0 operand bytes" 70
    check_at_least "taking 1 operand bytes" 12
    check_at_least "taking 2 operand bytes" 8
    check_at_least "taking 4 operand bytes" 1
    check_at_least "taking 6 operand bytes" 1
    check_at_least "taking 8 operand bytes" 1
    check_exactly "opcodes whose operand length depends on the stream" 1

    # Lengths inferred from handlers are a reading, not a measurement, so hold
    # them up against the interpreter itself: --vmtrace logs the bytecode
    # program counter and the opcode dispatched at it, and consecutive entries
    # give the length of every instruction the pod actually executed. This is
    # what caught `0x09` and `0x60`, both of which read their operand through a
    # helper rather than stepping the counter themselves.
    sed -n '/mission opcodes executed/,/^$/p' "$OUT" > "$OUT.vm"
    CHECKTEXT=$(python tools/mission_dis.py "$ROM" --trace "$OUT.vm" 2>/dev/null)
    check_at_least "trace entries" 8192
    check_at_least "distinct opcodes" 65
    check_at_least "straight-line lengths confirmed" 7612
    check_exactly "lengths the trace contradicts" 0
    # The reachability walk is only worth anything if the successor rule
    # accounts for every jump the pod actually made. It now does, and this is
    # the check that says so.
    check_exactly "jumps the successor rule misses" 0
    rm -f "$OUT.vm"

    # `0x64` pushes a string literal, and the proof is that the bytes it skips
    # read as text. This is the check that would have caught the earlier
    # reading, where they were taken for inline code - the resume address
    # agreed with the trace either way, so only the content tells them apart.
    CHECKTEXT=$(python tools/mission_dis.py "$ROM" B1_BattleTech_1 --limit 24 2>/dev/null)
    check_contains "push 'exitScreen'"
    check_contains "push 'VGL Universe 34933'"
    CHECKTEXT=$(python tools/mission_dis.py "$ROM" T1_Nose_Only_1 --limit 200 2>/dev/null)
    check_contains "push \"('NoseCam')\""

    # The ROM carries both games' scripts and picks a table at boot. Neither
    # game's scripts reach an opcode that creates anything - which is the whole
    # of what a week of looking for the branch that guarded one established.
    CHECKTEXT=$(python tools/mission_dis.py "$ROM" --reach 2>/dev/null)
    check_at_least "BattleTech routines" 13
    check_at_least "BattleTech instructions" 2329
    check_exactly "BattleTech creation opcodes" 0
    check_at_least "RedPlanet routines" 18
    check_at_least "RedPlanet instructions" 4688
    check_exactly "RedPlanet creation opcodes" 0

    # The strings say what a script is for, and they are the whole of what is
    # known about the other game on this hardware.
    CHECKTEXT=$(python tools/mission_dis.py "$ROM" --strings 2>/dev/null)
    check_contains "Martian Football: live from Red Planet"
    check_contains "Red Team"
    check_contains "Crusher"
    check_contains "*Winner-Cam*"
    check_contains "STATS (kills/deaths)"
    check_contains "Map view"
fi

# Who else calls this. A routine with one caller is explained by that caller;
# the reading that entity creation belongs to the mission interpreter rests on
# `Create_Thing` having exactly one, so the search has to cover every call form
# a 68k program has - `bsr.b` included.
if [ -f "$ROM" ]; then
    echo
    echo "== call sites =="
    CHECKTEXT=$(python tools/xref.py "$ROM" 020FFFE4 --calls 0211DC1E 0211DBA2 0211E15E 2>/dev/null)
    check_exactly "0211DC1E" 1          # Create_Thing, from opcode 0x24's arm
    check_exactly "0211DBA2" 1          # the class 4 constructor, from 0x21's
    check_exactly "0211E15E" 2          # the allocator, from both of them

    # The three arena allocators - the routines that actually give an entity a
    # class. Each caller asks for exactly one class, so the counts are a
    # census of what this build can make.
    CHECKTEXT=$(python tools/xref.py "$ROM" 020FFFE4 --calls 0214C4FC 0214C57E 0214C61E 0212D058 02134F06 2>/dev/null)
    check_exactly "0214C4FC" 4          # class 4 three times, class 9 once
    check_exactly "0214C57E" 9          # one caller per class, Mech included
    check_exactly "0214C61E" 0          # the top-of-arena pool, never used
    check_exactly "0212D058" 2          # the class 1 Mech constructor
    check_exactly "02134F06" 2          # the routine that decides My_Mech_Ptr

    # The draw path. 0x021452F0 writes the item $240 opcode and a model id;
    # 0x021444E8 is the bulk append that gets the staged items into the list.
    CHECKTEXT=$(python tools/xref.py "$ROM" 020FFFE4 --calls 021452F0 021444E8 0212DB70 2>/dev/null)
    check_exactly "021452F0" 21         # the draw-model emitter
    check_exactly "021444E8" 1          # append N longwords to the display list
    check_exactly "0212DB70" 1          # the Mech's per-frame cull-and-draw op
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
for t in tools/model.py tools/render.py tools/tms340run.py tools/vehicles.py tools/opscon.py tools/fnstr.py tools/netmsg.py tools/entityfields.py tools/musashi_fpu.py tools/missions.py tools/mission_dis.py tools/mapsend.py; do
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
