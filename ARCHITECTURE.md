# Where this is going

The hardware findings are in [DEVICES.md](DEVICES.md), the renderer in
[RENDERING.md](RENDERING.md), and the near-term work in
[ROADMAP.md](ROADMAP.md). This file is the long view: what the finished thing
should be, what shape it takes, and which decisions are already settled by
evidence rather than by taste.

## First, how it actually plays

Worth answering before designing anything around it, because it is the
opposite of what the name suggests to people who know the tabletop game.

**It is a real-time first-person simulator.** Not turn-based, not a wargame
with a 3D skin. The cockpit ROM's own strings settle it:

```
SHUTDOWN IN %d SECONDS        TWISTING TORSO LEFT
SHUTDOWN AVOIDED              CENTERING THE TORSO
TORSO ACTUATOR DAMAGED        STICK TURNS / TIPS TORSO
LEFT ARM GUNS DESTROYED       RADAR AT 2 KM RANGE
AMMO BAY FIRE                 Course %3.5f, Speed %3.5f, X %3.5f, Y %3.5f, Z %3.5f
```

and the release notes talk in seconds and frame rates — *"should be able to
shoot down a Tarantula in 3 seconds or less with sustained fire"*, *"8 player
games may encounter significant Frame Rate hits"*.

What it keeps from the tabletop is the **data model**, and it keeps all of it.
Every vehicle record carries 21 hit locations each with **separate armour and
internal structure** values; weapons have heat as a float and range in metres;
ammunition is counted per bay and a bay can cook off. Heat builds, and at the
top of the scale you shut down unless you pull `MANUAL OVERRIDE` — the
tabletop's shutdown-avoidance roll, turned into a switch on the panel. Losing
an arm loses the guns on it; losing a torso actuator caps your torso twist.

So: BattleTech's bookkeeping, run continuously, with a pilot in a box. That is
why the pod exists rather than a game of it.

It is also **multiplayer first**. A centre ran up to 8 pods on one game, out of
a roster of 11 maps and a team list of eight houses in eight colours, refereed
from an operator console, with a camera ship watching and Mission Review
printing score sheets afterwards. A single-pod build is a development
convenience, not the product.

## The three programs, and why that is the shape

The release is organised as three pieces of software and this project should
stay organised the same way, because the seams between them are already
protocols we have decoded rather than interfaces we would be inventing.

| the release calls it | what it is | where we are |
|---|---|---|
| **Cockpit Software** | the pod: 68020, TMS34020 renderer, Amiga secondary display, audio DSP, Remote I/O panel | boots, renders, panel talks |
| **Ops Con** | the operator's Macintosh: picks the map, the teams and the mechs, and starts the game | not started — and should be **written, not emulated** |
| **Mission Review / Camera Ship** | the spectator view and the after-action report | out of scope for now |

## The target

One process for the pod, several windows, and everything that crosses a
boundary crossing it as the wire format the real hardware used.

```
                    ┌──────────── battlepod (one process) ───────────┐
                    │                                                │
  main view  ◄──────┤  68020 (Musashi) ── display list ── rasteriser │
  480x360           │        │                                       │
                    │        ├── RIO serial stream  ──► panel windows│
  panel windows ◄───┤        │      (0xD1 display, 0xD2 bar,         │
  lamps, gauges,    │        │       0xD3 lamp; inputs back)         │
  soft labels       │        │                                       │
                    │        ├── Amiga secondary display ──► window  │
  secondary  ◄──────┤        │                                       │
                    │        └── ARCNET frames ──► UDP               │
                    └────────────────────────│───────────────────────┘
                                             │
                    ┌────────────────────────┴───────────────────────┐
                    │  centre server: the ARCNET segment, over UDP   │
                    └──┬──────────────┬──────────────┬───────────────┘
                       │              │              │
                    other pods    ops console    camera ship
```

### Why one process and several windows

The panels want to be separate windows the user can drag onto a second monitor,
and SDL does multiple windows in one process without ceremony. Splitting them
into separate *processes* would mean inventing an IPC channel to carry a serial
stream that is already a single ordered byte stream — cost with no benefit.

So: **one process, one window per panel group, each independently movable,
resizable and closable**, with the layout remembered. A closed panel is not a
disabled panel; the bytes still arrive, nothing is drawn.

### Why the seam is the RIO wire and not an API

Every panel window is a consumer of the Remote I/O byte stream, which is
already decoded, framed and checksum-verified:

```
01  <node & 0x3F>  <len>  <checksum>  <payload>  <checksum>
D1 <id> <8 ASCII>     an alphanumeric display      ids 0x80-0x91
D2 <id> <bars>        a bar graph                  ids 0x80-0x91 less three
D3 <id> <brightness>  a lamp                       ids 0x00-0x3B, 0x50-0x53, 0x60
```

Keeping that as the boundary buys three things for free. A panel can be moved
out of process later without redesign. A panel can be replaced by **real
hardware** — someone with a salvaged cockpit can point the stream at a serial
port. And the panel layer can be tested against captured bytes with no emulator
running at all.

Inputs go back the same way: the stick, throttle and pedals are analog values
arriving on the same wire, so a keyboard, a gamepad or a real HOTAS all land in
the same place.

The one thing this does not settle is **which lamp is which**. We have 64 lamp
ids and 18 display ids from the firmware's own diagnostic menu, but not their
legends. Those come from photographs of a cockpit and from watching which ids
light when — a labelling job, not a decoding one.

## Networking

The pods were an **ARCNET** token ring (SMC COM90C66), with the operator
console on the same segment and a modem router linking centres. Two layers,
and they are not the same problem:

**Pod to pod** is the game layer — positions, fire, damage. Encapsulate each
ARCNET frame in one UDP datagram and let a small **centre server** be the
segment: pods connect to it, it relays. That keeps the token-ring ordering
semantics out of the wire (nobody needs them) while preserving frame
boundaries, and it makes a game over the internet the same code as a game on a
LAN with a different address. Eight pods at a modest frame rate is nothing for
UDP.

**Console to pod** is the setup layer, and we already have its complete message
vocabulary — recovered from a `Console Log` that shipped in the release, in
which a real centre logged every message it exchanged with its pods **by name**
for eight months of 1995:

```
SHADOW_ROM / GO per node        MECH_CLASS  class, thing, type, name
COCKPIT_CONFIG_MSG per node     Drop Location  x, y, z
PLAYER_CONFIG  node, cockpit, pilot     GAME_OVER  node
```

`Net_Configuration` in the release even documents the topology in its own
comments — node type 1 is the ops console, 2 a cockpit, 3 a camera, 4 a router
— along with each node's place in the loop and which load script to use.

## The operator console: write it, do not emulate it

This is the strategic call in this document.

Starting a game is the oldest blocker in the project. The obvious route —
emulate the Macintosh console — is the expensive one: it means a 68k Mac, its
toolbox, and getting past THINK C's `CREL`/`DREL` relocations, all to run a
program whose entire job is to read plaintext files and send named messages.

Those plaintext files are in the release and we have already parsed most of
them. `Vehicle_List` gives 38 vehicles over six chassis. `Team_List` gives
eight houses in eight colours. `Scenario_List` gives eleven maps.
`Script_List`, `Game_Setup`, `Net_Configuration`, the load scripts. And the
message vocabulary is not guessed, it is transcribed from the console's own log.

So the console becomes a few hundred lines that read the release's own data
files and speak the recovered protocol — and it gives us a game start, which
unblocks the pose data, which unblocks everything downstream of it. It is also
the piece that makes the thing playable by other people, which no amount of
further decoding does.

The camera ship and Mission Review follow the same logic later, and neither is
on the critical path.

## Order of work

1. **Controls and the panel windows.** The RIO stream already carries verified
   packets; give it somewhere to go. Least risk, most immediately visible.
2. **The main view in SDL.** Today `render.py` writes PNGs; the same geometry
   into a window at the pod's 480x360, upscaled with the aspect kept.
3. **The operator console**, speaking the recovered protocol to one local pod.
   This is the unlock: a real game start means real pose data, which finishes
   the standing mech and gives the renderer a display list that came from the
   game rather than from us.
4. **ARCNET over UDP** and the centre server, at which point two pods on one
   LAN is the same code as two pods across the internet.
5. **The secondary display**, either by running the 61 KB Aztec C program on a
   second Musashi context or by reimplementing the 674-byte SecCom protocol.
6. **Audio**, decoding `btAudio.dld`'s record stream.
7. **Camera ship and Mission Review**, once there is something worth watching.

## Decisions already made, and why

- **Intercept the display list; do not emulate the TMS34020 for pixels.** The
  command protocol turned out to be entirely readable from the 68020 side, so
  the renderer is a modern rasteriser fed real commands. `tools/tms340run.py`
  stays as the reference the rasteriser is checked against, not as the thing in
  the hot path.
- **Wire formats at every boundary.** RIO bytes for the panel, ARCNET frames
  for the network, the console's named messages for setup. Nothing in this
  system needs an interface we invented.
- **No cycle accuracy.** Nothing found so far depends on it, and a 1996 68020
  is not a performance problem in 2026.
- **Lead with Red Planet where a choice exists.** Same engine, same hardware,
  same everything — and no third-party trademarks attached.

## What is still genuinely unknown

- **Where the arms go.** `516` and `517` are identified as the right and left
  arm assemblies but their placement is per-frame, so it arrives with the pose
  data at step 3.
- **The byte encoding of the setup messages.** We have their names, fields and
  order from the log, and the opcode dispatch from the firmware, but not the
  layout of each body. This is the main risk in step 3 — though a pod that
  answers `IDENTIFY_YOURSELF` is a fast feedback loop to solve it in.
- **Type 7**, 607 KB of compressed archive with no per-record length to check a
  decompressor against.
- **Two TMS34082 operations** whose manual pages do not survive legibly.
- **Which lamp is which**, as above: a labelling job.
