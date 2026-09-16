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
| **Ops Con** | the operator's Macintosh: picks the map, the teams and the mechs, and starts the game | not started — **lift it to read it, write it to run it** |
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

What this does not settle is **which lamp is which**: we have 64 lamp ids and
18 display ids from the firmware's own diagnostic menu, but not their legends.
See "The panel" below — it is a labelling job, and it turns out not to need a
photograph.

## The panel

Three sources, and they agree, which is the only reason any of this is worth
writing down.

### What the controls do, from the firmware

The cockpit ROM prints a status line every time a switch is thrown, so the
switch inventory is recoverable without ever seeing a cockpit. From `ROM3_0`
around `0x0329A2`-`0x032BB5`, `0x02B613`-`0x02B695` and `0x055392`-`0x055415`:

| what it is | the ROM's own words |
|---|---|
| torso twist | `TWISTING TORSO LEFT` / `RIGHT`, `CENTERING THE TORSO`, `TORSO ACTUATOR DISABLED` |
| view | `MOVING VIEW UP` / `DOWN` |
| vision mode | `VISIBLE LIGHT ACTIVE`, `INFRARED ACTIVE`, `SEARCH LIGHT ON` / `OFF` |
| secondary display | `RADAR DISPLAY SELECTED`, `MAP DISPLAY SELECTED`, `DAMAGE DISPLAY SELECTED`, `MAP GRID ON` |
| radar | `ZOOM IN RADAR`, `ZOOM OUT RADAR`, `RADAR AT 2 KM RANGE` |
| targeting | `TARGET SELECT`, `INDIRECT FIRE MODE`, `FORWARD OBSERVER ON` / `OFF`, `FO SELECT` |
| stick mode | `STICK STEERS`, `STICK TURNS / TIPS TORSO`, `STICK MOVES CROSSHAIRS` |
| pedals | `PEDALS STEER`, `FINE PEDALS`, `REGULAR PEDALS` |
| handling | `STOPS WITH INERTIA`, `STOPS INSTANTLY`, `DIRECTION STABILIZATION IS ON` |
| reactor | `SHUTDOWN IN %d SECONDS`, `SHUTDOWN AVOIDED`, `MANUAL OVERRIDE`, `REACTOR RESTARTING` |
| pilot mode | `BASIC MODE`, `STANDARD MODE`, `VETERAN MODE`, `MASTER MODE`, `PANEL TRAINING MODE`, `CROSSHAIR ON` / `OFF` |

That last row is a difficulty ladder built into the cockpit: a novice gets a
crosshair, instant stops and coarse pedals; a master gets none of it. There is
even a `PANEL TRAINING MODE` for teaching the switches themselves.

And the damage messages line up one-for-one with the 21 hit locations the
vehicle records carry — `LEFT LEG DISABLED`, `TOP SPEED REDUCED`,
`RIGHT ARM GUNS DESTROYED`, `MISSILE PACK DESTROYED`, `TORSO ACTUATOR DAMAGED`,
`AMMO BAY FIRE`.

### What the panels are called, from the manual

The *VWE System 3.0 User Guide and Technical Manual* is the right generation for
this release and it names the panels as hardware, which is the decomposition
worth building to. The card cage holds **CPU, Amiga, Sound Board/Intercom,
Remote I/O, Weapons A, Weapons B, Keypad, Buttons, LCD**, and the manual's
description of each:

| panel | the manual's words |
|---|---|
| **Player Interface Device** | "Change the pilot mode from basic to standard to veteran to master... these also control crosshairs, fine/standard pedal control and VTV monitor configuration" |
| **Weapons Displays** (A and B) | "On the left and right side of the Main Monitor. These display and control weapons configuration" |
| **Advanced Function** | "Radar Zoom, infrared, Indirect Firing Control, Search Light Control, Mech Torso Centering" |
| **Video Select Panel** | "Selects between Radar, Map and Indirect Firing Control in BT" |
| **Key Pad** | "Used for cockpit maintenance and for overheat codes in BT" |
| **Joystick / Throttle / Foot pedal** | vehicle control, speed, steering |

Read that against the firmware table above and it is the same machine described
twice. Player Interface Device is `BASIC`/`STANDARD`/`VETERAN`/`MASTER MODE`
with `CROSSHAIR ON` and `FINE PEDALS`. Advanced Function is `ZOOM IN RADAR`,
`INFRARED ACTIVE`, `INDIRECT FIRE MODE`, `SEARCH LIGHT ON`, `CENTERING THE
TORSO` — five legends, five status lines, in the manual's own order. Video
Select is the three `… DISPLAY SELECTED` lines.

**So the panel windows fall out of the hardware**: Weapons A, Weapons B,
Buttons (the interface/advanced/video-select group), Keypad, LCD, plus the two
monitors. Not a layout we invented.

The manual also gives the analog ranges, which the input path needs on day one.
All are optical encoders read by the Remote I/O board:

| control | released / centred | full |
|---|---|---|
| throttle | `$0000` (sometimes wrapping to `$FFF0`) | `$0340` |
| foot pedals | `$0000` | `$0340` |
| joystick, each axis | `$0000` centred | about ±`$80` |

And a diagnostic worth having: keystroke `1` in the root menu lights **every LED
segment in the cockpit**, which is a panel test we can run against our own
renderer the moment it exists.

### What it looks like, from photographs

Photographs of a surviving pod give the arrangement:

- **Five green monochrome MFDs**, bezels marked `MFD`: three in a bank above
  the viewport, two flanking the centre console. Each has a row of four red
  buttons above and below it — **eight soft keys per display**, which is where
  most of the 64 lamp ids go.
- A **centre console** below the viewport carrying the radar/map/damage scope,
  heat and speed, with its switch legends printed down both edges: `ZOOM`,
  `SHUTDOWN`, `AUXIL MODE`, `MAP`, `DMG`, `TGT`, `FLUSH`, `CROUCH`, `RANGE`,
  `MULTI`, `LIGHT`, `SEARCH LIGHT`, `CENTER`, `AUTO`, `PILOT MODE`.
- A **numeric keypad** on the coaming, for pilot identity.
- A `CAUTION — DO NOT TOUCH VIEWPORT GLASS` label, because the main view is a
  real optical assembly rather than a screen you look at.

Read those legends against the table above and they are the same switches:
`ZOOM`/`RANGE` are the radar pair, `MAP`/`DMG`/`TGT` the three secondary-display
modes, `SEARCH LIGHT` and `LIGHT` the vision pair, `CENTER` the torso, `PILOT
MODE` the difficulty ladder, `SHUTDOWN` the reactor.

**Caveat, and it matters.** The photographs available are of a *later* pod
generation than this release — their main view is texture-mapped under a
clouded sky and their centre console is a colour LCD, where 13.1.8 is
flat-shaded and drives a mono CRT plus discrete lamps and bar graphs. So the
photographs are evidence for the **family** — how many MFDs, how many keys each,
what the legends say — and not proof of this build's exact layout.

### Which lamp is which

Still unknown, and it does not need a photograph to fix. The pod tells us: drive
an input, watch which lamp id changes on the Remote I/O wire, and read the
status line the firmware prints at the same moment. `SEARCH LIGHT ON` arriving
in the same frame as lamp `0x2A` going to brightness 1 names lamp `0x2A`.

That makes the mapping an experiment inside our own emulator rather than an
archaeology problem — the same kind of oracle everything else here was settled
by. It needs the input path wired first, which is step 1 of the order of work
anyway.


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

## The operator console: lift it to read it, write it to run it

This section used to say *write it, do not emulate it*, on the grounds that
emulating meant a 68k Mac, its Toolbox and THINK C's relocations. That was too
binary, and it ignored a tool we already have. `macrecomp` in the sibling
workspace is a 68k Mac static-recompilation toolkit — extract, disassemble with
Toolbox traps annotated, lift to C against an SDL2 runtime — and it has HyperCard
booting, which is a *larger* program than this one.

So the right question is not whether to use it but what for, and its own
`scan_traps.py --coverage` answers that in one command. Run against the
console:

```
  call sites  920/1624 (56%)
  distinct    159/345 (46%)

  missing, by manager, ranked by call sites:
      207 sites   3 traps  SANE (float)
      121 sites  29 traps  QuickDraw
       52 sites  21 traps  TextEdit
       43 sites   1 traps  Print Mgr
       40 sites  18 traps  Window Mgr
       38 sites  26 traps  File Mgr
```

For comparison the toolkit scores Shufflepuck Cafe at 92% and HyperCard at 76%.
The console is a full Macintosh application — menus, editable text fields, a
print path for score sheets — so it carries more Toolbox surface than a game
does, and **the entire 44% gap is operator-interface furniture we do not want**.

The binary says the same thing about itself. It names its own source files, and
there are 53 of them: **36 are THINK Class Library** — `CApplication`,
`CDirector`, `CDialogDirector`, `CEditText`, `CPrinter` — and only **17 are
VWE's own**:

```
Functions.c   Load.c       LongQD.c      OpConApp.c    OpConData.c
OpConDoc.c    OpConMain.c  SiteLink.c    Start.c       SyncSettings.c
TBUtilities.c TCLUtilities.c TestSeq.c   Utilities.c   Verification.c
ResClientOpConDoc.c
```

`Start.c` and `Load.c` are what we are missing. And the message names are all
in one contiguous string region, `0x76C8`-`0x90AE` — `GAME_OVER`,
`COCKPIT_CONFIG_MSG`, `PLAYER_CONFIG`, `Drop Location`, `MECH_CLASS`,
`IDENTIFY_YOURSELF`, `SHADOW_ROM`, `NET_CONFIG_SEND_MSG` — so the network layer
is one module, not scattered.

**So: lift to read, write to run.**

Use macrecomp's front end on those modules to recover **the byte layout of each
message**, which is the one thing we do not have and the thing that gates a
game start. Reading them needs no Toolbox at all. Then write the console
itself, because everything else it does is read plaintext files that are in the
release and already parsed — `Vehicle_List`, `Team_List`, `Scenario_List`,
`Script_List`, `Game_Setup`, `Net_Configuration`, whose own comments document
the node types — and drive a UI we would rather design than reproduce.

Full recompilation stays available if the encodings turn out to be tangled
enough that running the original is cheaper than reimplementing it. The
`DREL`/`CREL` relocation resources are the first thing to work out either way:
10,524 bytes of data fixups, needed before a string pointer in `DATA` resolves
to the string it names.

## Step 1, done: the panel in windows

`make panel` builds `build/panel.exe`. It takes a Remote I/O capture and draws
it in three windows you can drag anywhere:

```
./build/battlepod.exe "$GF/Full_Load_3_0" --duart 11000 \
    --set 2138A64=4E754E75 --duart-in 's\r3\r05\r01\r' --rio-dump out/one.rio
./build/panel.exe out/panel.rio
```

Left and right scrub a frame at a time, home and end jump to either end, and
the frame number is in the title bar.

**It takes the wire, not an API.** `battlepod --rio-dump` writes the byte
stream the cockpit sent on DUART channel A, and the panel reads that file.
`src/rio.h` holds the frame walker and the panel state and is the only thing
the two share - the emulator does not know the panel exists. Three consequences
fall out for free: the panel runs with no emulator present, it is testable
against captured bytes, and the same stream could one day go to a serial port
with a salvaged cockpit on the end.

The capture that drives it is **real firmware output**, not a mock. Each frame
came out of a separate run of the pod's own diagnostic monitor, driven over the
modelled serial port and concatenated:

```
01 00 03 03 D3 05 01 D9        lamp 05 to brightness 01
01 00 03 03 D2 80 05 57        bar graph 80 to 5 bars
01 00 0A 0A D1 80 42 41 54 ... display 80 reads BATTLTEC
```

Worth recording: **a boot emits one frame and no more.** The firmware sends a
single `D5` during startup and then nothing, because it does not light the
panel until a game is running - which is still blocked. So until the operator
console exists, a rich capture has to be assembled a command at a time. That is
not a limitation of the panel; it is the same blocker as everywhere else,
showing up in a new place.

### Windows by device, not by cockpit panel - for now

The three windows are lamps, displays and bar graphs. That is a grouping by
device class, and the real cockpit is not built that way: the System 3.0 manual
names the boards as Weapons A, Weapons B, Buttons, Keypad and LCD.

Grouping by board is what should happen, and it needs one thing we do not have
- which lamp id sits on which board. **Scrubbing is how that gets answered**:
step a frame at a time and watch which id changes against what the firmware
says it just did. The panel was built with that in mind rather than as a
viewer, which is why it scrubs at all.

Until then it draws what is known and marks what is not: a lamp nobody has ever
addressed is drawn as an empty outline rather than as dark, because unknown is
not off.


## Step 2, done: the main view

`make view` builds `build/view.exe`, and `render.py --raw` feeds it:

```
python tools/render.py "$GF/Cockpit Software/battletech_ti_res"     --mech 452 --raw out/madcat.rgb --spin 60
./build/view.exe out/madcat.rgb --fps 24
```

Sixty frames of a MadCat turning, at the 480x360 the display list says the pod
ran, in a window that opens at double size and letterboxes rather than
stretches when it is dragged to some other shape. Space plays and pauses, the
arrows step, escape quits.

The frames are **plain RGB with no container**, which is the same bargain the
panel makes with the Remote I/O byte stream: the producer is Python today and
will be C in the pod eventually, and the window does not care. A file that does
not divide evenly into frames is reported as a size mismatch rather than shown
sheared by a row.

## The pieces together: `make cockpit`

The panel and the main view started as separate programs reading files. They
are now **one process with four windows**, which is what the target at the top
of this file asks for:

```
./build/cockpit.exe "$GF/Full_Load_3_0" --duart 11000     --set 2138A64=4E754E75 --duart-in 's30501'     --live out/madcat.rgb --steps 40000000
```

`cockpit.exe` is `battlepod.c` compiled with `-DBATTLEPOD_SDL`. The emulator
runs the firmware, and every 200,000 instructions it walks whatever new Remote
I/O bytes have appeared on DUART channel A into the panel state and redraws.
**The panel lights up as the firmware drives it**, rather than after the fact
from a capture.

`battlepod.exe` is the same source without SDL, so the batch tool and the
harness never grow the dependency, and `panel.exe` and `view.exe` still run
standalone from files. The drawing is shared through `src/paneldraw.h`; the
emulator does not know it is being watched and the drawing does not know where
the bytes came from.

The emulator outruns the cockpit by a wide margin - a budget that would be
minutes of pod time goes by in seconds - so when the run ends the windows stay
up with the panel in its final state until they are closed.

The main view is still fed from a file of raw frames, because the rasteriser is
`tools/render.py`. When it is C in this process the texture stays and only the
source changes.

## Order of work

1. ~~**Controls and the panel windows.**~~ Done for output: `make panel`,
   three windows, driven from a capture of the wire. Inputs - stick, throttle,
   pedals back up the same link - are what is left of this step, and the
   manual's encoder ranges are above.
2. ~~**The main view in SDL.**~~ Done: `make view`, the pod's 480x360 in a
   resizable window, letterboxed rather than stretched. `render.py --raw
   --spin N` writes the frames.
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
- **Which lamp is which.** Not a decoding problem: drive an input, watch the
  lamp id on the wire, read the status line the firmware prints. It needs the
  input path wired, which is step 1 anyway.
