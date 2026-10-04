#!/bin/sh
# Start a game on the emulated pod and fly it from the keyboard.
#
# Sends what the operator console sends to start a game - a welcome with a
# visibility range, a MECH_CLASS for your Mech and one for an opponent, the
# scenario's map as 0xE4s, and PLAYER_LINK - then opens the cockpit's windows
# with the main view drawn from the pod's own frames.
#
#   W / S    throttle up / down        A / D   stick left / right
#   space    fire                      T       target select
#   L        searchlight               Esc     quit
#
# The Mech drops in first and ignores its controls until it lands; give it a
# few seconds.
#
# usage: tools/play.sh [scenario] [vehicle-record]
#   scenario        a file under Scenarios/ (default BadLands-16)
#   vehicle-record  0-37, tools/vehicles.py lists them (default 0, MadCat Prime)
#
# Needs VWE_GAME_FILES set as for tools/conformance.sh, and `make cockpit`.
# PLAY_STEPS bounds the run and PLAY_ARGS adds options; the harness uses both
# with SDL_VIDEODRIVER=dummy and BATTLEPOD_NO_HOLD=1 to play one headless.
# PLAY_PKT=FILE keeps the start-of-game packets in FILE; with BIN=none it
# stops there, for a machine that has the cockpit but no Python (netlab's
# recipe runs cockpit.exe on its test VM with that file).

set -eu

GF=${VWE_GAME_FILES:?set VWE_GAME_FILES to the Game Files directory of the release}
SCEN=${1:-BadLands-16}
VEH=${2:-0}
BIN=${BIN:-./build/cockpit.exe}
[ "$BIN" = none ] || [ -x "$BIN" ] || { echo "play: $BIN not built; run make cockpit" >&2; exit 1; }

if [ -n "${PLAY_PKT:-}" ]; then OUT=$PLAY_PKT; else OUT=$(mktemp); trap 'rm -f "$OUT"' EXIT; fi


python - "$GF/Scenarios/$SCEN" "$VEH" > "$OUT" <<'PY'
import struct, subprocess, sys
scen, veh = sys.argv[1], int(sys.argv[2])
lines = subprocess.run([sys.executable, "tools/mapsend.py", scen],
                       capture_output=True, text=True, check=True).stdout.splitlines()

# A drop point from the scenario - facing, x, y, height - preferring one
# that faces 0, the one heading whose direction is measured (toward -Y).
text = open(scen, "rb").read().decode("mac-roman", "replace").replace("\r", "\n")
drops = []
for l in text.split("\n"):
    f = l.split()
    if len(f) == 5 and f[4] == "-1":
        drops.append([float(v) for v in f[:4]])
drop = next((d for d in drops if d[0] == 0.0), drops[0])
facing, x, y, _ = drop

def pkt(op, n, fields):
    b = bytearray(n); b[0] = op
    for off, fmt, v in fields:
        struct.pack_into(fmt, b, off, v)
    return " ".join("%02X" % c for c in b)

def mech(thing, rec, x, y, heading, name):
    return pkt(0xE4, 0x60, [(0x0E, ">l", 1), (0x12, ">l", thing),
                            (0x16, ">f", x), (0x1A, ">f", y), (0x1E, ">f", 5.4),
                            (0x22, "8s", name), (0x4A, ">h", rec),
                            (0x50, ">f", heading)])

# Facing 0 walks toward -Y: the opponent stands 150 ahead of a drop facing 0.
print(lines[0]); print(lines[1])                      # comment, 0xE5
print(mech(1, veh, x, y, facing, b"Pilot"))
print(mech(2, 8, x, y - 150.0, 180.0, b"Loki"))
for l in lines[2:]:
    print(l)
print(pkt(0xED, 0x40, [(0x0A, "16s", b"B1_BattleTech_1"), (0x32, ">l", 1)]))
PY
[ "$BIN" != none ] || exit 0

"$BIN" "$GF/Full_Load_3_0" --duart 11000 --rstub 3FF00000 --rirq --astub \
    --monitor --clock 2000808 --set 40000100=1234567 \
    --packet-file "$OUT" --live-pod --steps ${PLAY_STEPS:-100000000000} --top 0 ${PLAY_ARGS:-}
