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
documents an 8-position Node ID DIP switch on the CPU board front plate and
says communication is impossible without it. The firmware never writes
`0x0218AEB0`/`B1`. So the switch is read either by the boot monitor - which
this project stubs - or by the ARCNET controller as its physical node ID, in
which case the `(net, node)` pair the game filters on is a different number
altogether. Nothing measured says which. Settled by: a real boot monitor, or a
capture of what a configured pod actually puts in that pair.

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
  **spawn opcode `0x0B` runs**. What is missing is a **game length**: the
  walker only creates a queued thing once its due time has passed, and the
  mission clock at `0x02193C1C` is negative on a pod nobody has told how long
  the game lasts. Settled by: whichever message carries the game length -
  `Game_Setup` in the release has a time in it.
- **The arms.** `516` and `517` are identified as the right and left assemblies,
  each with five alternative loadouts, but their placement is per-frame.
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
- **The input report format.** The receive interrupt hands each byte to a state
  machine through a function pointer at `0x0217FBE4`. Feeding all 256 opcodes
  past the firmware's decoder produced nothing.

---

## Deliberately not attempted

- **Type 7**, 607 KB of the archive. Compressed, decompressor readable at
  `0xFE0090F0`, but the first longword is shared across groups of records rather
  than being a per-record length - so there is no oracle, and everything else
  here was settled by having one.
- **Two TMS34082 operations**: the short-form `CEXEC` command packing and one
  mode 3 routine. The scanned handbook is not legible at those tables, and
  guessing would put numbers on screen no cockpit produced.
- **Audio.** `btAudio.dld` is 989 KB of ADSP-2100 code. Different CPU, no
  emulator, a project of its own.
