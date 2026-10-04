# Unresolved, assumed, and papered over

What this project does **not** know, separated by how it does not know it. The
distinction matters: a thing measured and unexplained is a lead, a thing assumed
is a liability, and a thing papered over is a bug waiting to be blamed on
something else.

Anything here that later gets settled should move into the technical documents
and out of this one.

---

## Assumed, not measured

Things the project relies on that rest on inference rather than evidence.
Each says what would settle it.

**`461`-`466` are the six torsos, in chassis order.** The skeletons `451`-`456`
are named from the cockpit ROM's vehicle records, which is solid. The torso
block is *inherited* from the `+10` id alignment. Corroborated by polygon count -
the four Clan chassis at 248-386 and the two Inner Sphere ones at 71 and 66,
splitting exactly where the ROM puts the boundary - but not proven. Settled by:
any table binding a part id to a chassis, which does not exist anywhere in the
cockpit software.

**Which of `0xF6`-`0xFF` is which console setup message.** The block is
identified as the pod's mode machine and each handler's effect on the ROM's
globals is written down, but the console's names - `COCKPIT_CONFIG_MSG`,
`PLAYER_CONFIG`, `SHADOW_ROM` and the rest - cannot be attached to numbers from
the receiving side alone. Settled by: the console's encoders, or a captured
session.

**Where the node ID reaches the software from.** The System 3.0 manual
documents an 8-position Node ID DIP switch on the CPU board front plate. The
firmware reads its address from `0x0218AEB0` and never writes it except to
copy the game identity at `0x02179D32` into it when acting as a router; this
project sets both by hand, and with them set pods talk (see DEVICES.md, *Two
pods*). Whether the switch reaches `0x0218AEB0` through the boot monitor or
is the ARCNET controller's own node id is still not known. Settled by: a real
boot monitor, or a capture of what a configured pod puts in that pair.

**The feet are `473`/`476` and `493`/`496`.** By elimination from the seven-id
block the rest of each leg came from. The adjacency rule that decides every
other joint cannot decide these - a foot hangs on a node with nothing below it,
so both orientations score identically, gap 0.00 and overlap 0.42 either way.

---

## Measured and unexplained

Numbers that are right and have no story.

**The reverse-jointed chassis come out 7.50 units wide against the 4.00 their
own rig declares.** `493`/`496` are 3.60 across and hang at ankles 3.90 apart.
Either those are not the feet or they do not hang at the ankle. Nothing else in
the block fits better. The straight-legged three come out 4.60 wide, which is
the ordinary rounding everything here has.

**Three models poke more than 10% outside the bounding box they state**, worst
at 50%, where 105 of 120 are within 2%. Something quantises or nudges the
extremes - plausibly a last step in an authoring tool, but not evidenced.

**One model in BadLands-16 (`21`) decodes to no geometry** while the other
sixteen it names decode fine.

**`AMIGA3_0` jumps to `$0000E112`, which is zero in its own image.** The word
sits in a hole of zeros from about `0xE000` to `0xE400` in the data section, so
the program cannot start itself. Something writes that word first; the 68020 is
the obvious candidate, given it makes 208 distinct references into the Amiga's
memory window.

**The part at `0x00010007`-`0x00010015` has no name.** What it does is no
longer open - two four-register control ports at a stride of 4, touched by
eight instructions in the whole ROM, each run doing set/clear/clear/set of one
mask (`0x40`, then `0x84`) immediately after the interrupt vectors it goes with
are installed. See DEVICES.md. What is missing is only the chip. **Not settled by the
paper**: every published manual and patent has been checked and none is
board-level - see SOURCES.md. Settled by: a board photograph, or a schematic
that has not been scanned.

---

## Papered over

Places where something is deliberately faked, and what breaks if the fake is
wrong.

**`--set 40000100=1234567` in five conformance scenarios** stands in for the
Amiga writing its ready word. Without it the firmware spins forever. Now
understood rather than cargo-culted, but it is still us pretending to be a board
we do not emulate.

**`--set 2138A64=4E754E75`** patches an `RTS` over the game init so the
diagnostic monitor is reachable, and every result obtained through the monitor
so far is from a cockpit prevented from starting a game. **This is now
avoidable**: typing `x` at the in-game console leaves the game and reaches the
same menu with nothing patched. The existing scenarios have not been rewritten
to use it, so the caveat still applies to them.

**The audio board's ring is drained by us, not by a DSP.** `--astub` writes
the 68020's head index straight into the tail and raises the signature's low
byte on the first push, so the ROM's download check passes and the boot stops
complaining. Nothing plays a sound and `btAudio.dld` is thrown away. If the
real board ever needed to be *slower* than instant - a game that paces itself
against the audio FIFO - this would hide it.

**Sixteen 68881 transcendental opmodes are host `libm` calls**, added to
Musashi by `tools/musashi_fpu.py` because it implements a subset and dies on
the rest. A real 68881 rounds to its own 80-bit extended format and sets
exception bits these do not; nothing here has needed that, and if a result ever
looks wrong in the last few digits this is where to look.

**`--rirq` completes a render after a fixed instruction count and always
successfully.** The delay exists because the real board could not be instant -
`Async_Render` clears the render-done flag two instructions after ringing the
doorbell - but `RIRQ_DELAY` is a number chosen to be comfortably past that, not
a measurement of any real board. It is a knob: `--rirq LEVEL:DELAY`. A real
board takes time and can report cause `0x60` - a list of callbacks - as well as
`0x50`. The stub only ever reports frame-complete, so anything that depends on
render latency or on the other cause is invisible here.

**The renderer, audio and Amiga boards are stubbed** rather than modelled. The
display list is intercepted on the 68020 side by design - see ARCHITECTURE.md -
but that is a decision, not an emulation.

**The boot monitor is stubbed** from a service table at `0x02000400` that the
real monitor would have filled. Its packet queue is our own.

**Model materials default to 0.7 grey** when a polygon names a material the
model never defined. Rare, and it would show as a grey face rather than a
crash.

**A lamp id we have never been told about is drawn as an outline, not as
dark**, because unknown is not off. A cosmetic choice, but it is a choice.

---

## Blocked on a running game

Not unknown so much as unreachable. Everything here is waiting on the same
thing: the pod has never been made to start a mission.

*Less of this list than it looks, now. The entity arena turns out to be built
during an ordinary boot, and fields in it can be driven from the wire - see
DEVICES.md. What is missing is a mission, not the objects a mission would
move.*

- **Which lamp is which.** The method is known - drive an input, watch the id on
  the Remote I/O wire, read the status line printed in the same frame - and the
  transport works in both directions. The firmware does not light the panel
  until a game runs. A boot emits exactly one Remote I/O frame.
- **What the leading type 0 record is.** Every frame opens with
  `{0, 2, 2, 1}` followed by a `0xFFFFFFFF` separator, and nothing read so far
  says what it configures.
- **What it takes to make a second entity draw.** The frame builder is
  `0x0212DB70`, reached per-viewer from event kind 2, and it is called sixteen
  times in a run **always with entity 0**. Giving entity 1 a class, a number,
  flags, a mech-table slot, the `+0xBB` draw bit and a position from the wire
  changes nothing. Whatever enumerates the world for drawing is inside the
  builder and is not being reached. **Settled in outline**: the world is
  populated by a **bytecode program**, the programs are **in the ROM** behind a
  table of thirteen named entry points, and a pod handed no mission has an
  empty spawn list. `0xED` runs a script, `B1_BattleTech_1` executes, and its
  **spawn opcode `0x0B` runs**. The **game length** turned out to be
  `0xE5`'s packet `+0x3C`, seconds times a hundred into the mission clock, and
  sending it before `0xED` sets the clock and starts the mission - and still
  nothing is created. Traced with `--vmtrace`, a properly started
  `B1_BattleTech_1` executes **8192 opcodes using 65 distinct ones** across 979
  distinct bytecode addresses, revisiting its hot address every hundred to two
  hundred instructions. That is a main loop doing work. **Not waiting for a
  player**: linking one through `0xED`'s class 1 arm leaves the trace
  byte-for-byte identical. **Not waiting for the renderer**: running with and
  without `--rirq` leaves it identical too. It does respond to the script -
  `B2_BattleTech_2` diverges at the 1418th opcode - so the trace is not a
  constant.
  **`0x24` was a false lead**, and so was every other creation opcode. This is
  now closed rather than suspected: the successor rule accounts for **every
  jump in an 8192-instruction trace**, so the reachability walk can be
  trusted, and it finds **no creation opcode in either game's scripts** -
  BattleTech 13 routines / 2329 instructions, Red Planet 18 / 4688, with all
  979 executed addresses inside the first. Both constructors share one 16-slot
  allocator at `0x0211E15E` and each has exactly one caller, which is its
  unused mission opcode. In this ROM they are unreachable.
  A write trap on entity 1's class word says the same from the other side: on
  a boot with a mission running, the only writes to it are two zeroes from the
  arena init. **Nothing ever gives an entity a class.** Now largely settled - see below - but not from the wire. Settled by: finding
- **What the trailing integers on a scenario line are.** The map arrives as
  `0xE4` (see DEVICES.md, *The world arrives as `0xE4`*), and every field its
  arms read is placed except these: one integer after the scale on classes 3
  and 6 (`8` throughout BadLands), two on class 2 (`0 30`). `tools/mapsend.py`
  sends the last as the flags and class 2's first as its `+0x26`. Settled by:
  what the flags bits do, or the console's map sender.
- **Which way a heading turns.** `0xE4`'s headings reach `+0xF8` and the type
  3's matrix; `--frame-out` turns models by `atan2` of that matrix, and a
  Mech at 90 degrees is side-on whichever sign is right. Settled by: an
  asymmetric model at 90, against period footage.
- **What visibility range the console sends.** The pod's view limit is
  `0xE5` `+0x44` plus `+0x48`, and with both zero nothing but the head-up
  display is ever drawn. 500 each is what this project uses, and it is a guess;
  why the range comes in two halves is not known either. Settled by: a captured
  `0xE5`, or the console's encoder.
- **What the type 4 record under the Mech is.** Model `0x55` at ground level,
  scaled (1, 1, 2) - a shadow by position, not by evidence.
- **What `0xE2` says, and where a downed pilot goes.** A pod whose Mech dies
  sends `0xED` from its own address, then an 8-byte `0xE2`, and stops
  broadcasting. The `0xED` looks like a relink to an escape pod or a camera;
  neither has been followed. Settled by: tapping the death routine's callees
  on the dying pod.
- **An arm that aims.** Which arm a Mech carries and where it hangs at rest
  are settled (RENDERING.md, *The arms*): vars 4 and 6 of its display-list
  record, at offsets from its root through instances 5 and 3. Those
  instances are identity in every frame seen so far, and the 3x3 after the
  fifteen joint transforms is unidentified. Settled by: frames of a Mech
  turning its torso or firing, and which words move.
- **What the SecCom ring carries.** Its structure is known - a 32-slot ring of
  42-byte messages at `+0x132`, with indices at `+0x12A` and `+0x12E` - and it
  is set up during an ordinary boot. But a boot only ever finds it empty, so
  what a message *contains* needs something to send one. The 298 bytes below
  `+0x12A` are also unidentified.
- **What each entity field *is*.** The arena is built on an ordinary boot -
  1000 entities of 0x6B4 bytes - and the bytes each message writes are now
  measured on the running firmware rather than read out of the handlers, for
  sixteen opcodes across eight classes - 57 field slots, 467 of the 1716
  bytes an entity occupies. **Eleven fields are named**, nine of them by the
  firmware's own printf labels: `+0x00` Owner, `+0x02` Class_ID, `+0x06`
  Number, `+0x0A` Thing_Flags, `+0x26`/`+0x2A`/`+0x2E` X, Y and Z, `+0x7E`
  Type, `+0x82` Color, `+0xF8` Course, `+0x114` Speed - plus `+0x9C`, the
  sequence `0xD2` refuses to go backwards on. The other 46 slots are located
  but not named; that still needs a game running to watch a field change
  against something visible.

- **Which of the seven unnamed classes is `EXPLOSION_CLASS` and which is
  `ANIMATOR_CLASS`.** Six classes are now named from the ROM's create-thing
  dispatcher - 1 `Mech`, 8 `Escape pod`, 9 `Camship`, 10 `Hovercraft`,
  12 `VTV`, 16 `Copter` - see DEVICES.md. Seven more arms build something
  without logging a name (2, 3, 6, 11, 14, 17, 18), and the console's remaining
  class names have to be among them. Settled by: a string on one of those seven
  constructors, or a scenario that creates one.
- **What the left pedal and the stick's other axis do.** The stick steers
  in advanced mode with "stick turns" (see DEVICES.md, *The controls*), and
  `A4` turns in basic mode. `A3` at full scale moved nothing watched, and
  `A1` and `A2` turning opposite ways reads like two halves of one axis more
  than X and Y. Settled by: reading `0x0214E064`.
- **What weapon each trigger fires, and what hit the Loki.** `A5` alone fires
  and destroys a Loki at 100 units; `A6` and `A7` set other bits of the same
  mask. Which of the MadCat's weapons each group holds, and what the class 11
  shots are, is not read. Model 80, the hit effect, is a type 4 resource and
  `--frame-out` does not draw it.
- **Type 7**, 607 KB of the archive. Compressed, decompressor readable at
  `0xFE0090F0`, but the first longword is shared across groups of records rather
  than being a per-record length - so there is no oracle, and everything else
  here was settled by having one.
- **Two TMS34082 operations**: the short-form `CEXEC` command packing and one
  mode 3 routine. The scanned handbook is not legible at those tables, and
  guessing would put numbers on screen no cockpit produced.
- **Audio.** `btAudio.dld` is 989 KB of ADSP-2100 code. Different CPU, no
  emulator, a project of its own.
