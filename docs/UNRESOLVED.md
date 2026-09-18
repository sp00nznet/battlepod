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

**`0xC5` is `ROUTER_STATUS_MSG`.** Three agreeing facts - built by router code,
carries a `strncpy` of up to `0x50` bytes plus a longword, and the console logs
exactly one message of that description. Not a decode. Settled by: the console's
encoder, which needs the work in FALSE-TRAILS.md to succeed first.

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

**`0x3FFFE168` and `0x3FFFE174`**, in the TI renderer's window, are read by the
main game loop and formatted onto Remote I/O displays `0x80` and `0x86` as raw
`%08x`. What they count is unknown.

**The unidentified device at `0x00010007`-`0x00010015`**: two interleaved 8-bit
parts, probed once at init. Candidates remain the second serial port, a timer,
or the ARCNET controller.

---

## Papered over

Places where something is deliberately faked, and what breaks if the fake is
wrong.

**`--set 40000100=1234567` in five conformance scenarios** stands in for the
Amiga writing its ready word. Without it the firmware spins forever. Now
understood rather than cargo-culted, but it is still us pretending to be a board
we do not emulate.

**`--set 2138A64=4E754E75`** patches an `RTS` over the game init so the
diagnostic monitor is reachable. Every result obtained through the monitor is
therefore from a cockpit that has been prevented from starting a game.

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

- **Which lamp is which.** The method is known - drive an input, watch the id on
  the Remote I/O wire, read the status line printed in the same frame - and the
  transport works in both directions. The firmware does not light the panel
  until a game runs. A boot emits exactly one Remote I/O frame.
- **The display list.** A boot posts one type 0 record and a `0xFFFFFFFF`
  terminator. There is nothing to draw.
- **The arms.** `516` and `517` are identified as the right and left assemblies,
  each with five alternative loadouts, but their placement is per-frame.
- **The SecCom block's contents.** Its address and size are known; it is zeroed
  and populated on a game start, so the pointer at `0x02194452` is still zero
  after `Secondary Started`.
- **What the 33 in-game opcodes mean.** The dispatch is mapped and the vehicle
  state structure is beginning to show - a word flag at `+0x92`, floats at
  `+0x2E` and `+0x100`, 24-byte records at `+0x140` - but nothing exercises them.
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
