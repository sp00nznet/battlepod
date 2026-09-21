# False trails

Every wrong turn that cost real time, and what killed it. Kept because a
negative result nobody wrote down gets paid for twice, and because the shape of
the mistakes is itself informative: on a platform this dead, the failure mode is
almost never "the data is corrupt" and almost always "the model in my head was
wrong in a way that still produced plausible output".

Each entry says what was believed, what disproved it, and what the right answer
turned out to be.

---

## Geometry and rendering

**The bounding-box gap was the opposite of what was claimed.** ROADMAP.md said
the decoded vertices all sat *inside* the box a model states, consistent with
the box being computed before a decimation pass. Measured across all 31 rather
than the four or five that had been eyeballed: **27 of them poke outside**.
Rounding does not explain it either, at any granularity from 0.05 to 1.0. What
is true is only that the misses are small - 105 of 120 within 2% of the model's
own size.

**The target was never texture-mapped.** An early note asserted texture mapping
from a 1994 press kit. Period footage and the archive's six 22 KB bitmaps both
say flat-shaded untextured polygons. Corrected before the renderer was built,
which is the only reason it was built the right way.

**A part has two extents and they are not interchangeable.** The box a model
*states* for itself decides which node it hangs on; where its vertices
*actually are* decides whether two placed parts touch. The C port used the
vertex extent for both and the MadCat came out with six parts instead of eight -
no thighs, shins hung straight on the ankles.

**Which way round a mirrored pair goes is not decided by which way it leans.**
That rule got the Loki right and the MadCat visibly wrong, because the Loki's
thigh straddles its own origin and the MadCat's sits entirely to one side.
Adjacency is what holds for both: of the two orientations, exactly one lands the
thigh's inner edge on the pelvis's outer edge, to the hundredth. All 42 limb
joints meet under that rule.

**The nine `0x64`-`0x70` handlers are not the nine map classes.** They line up
in count, which was convincing. The code refutes it: those arms subtract 5.0
from a float and compare it against -2.8. That is damage or heat, not a map
record.

**A scenario's nine-field records name their model in column 8, not column 1.**
Column 1 holds a collision hull - 0 to 7 polygons, radii in the hundreds.
BadLands places 78 terrain mesas that way, so the biggest features on the map
were drawn as flat plates until someone looked at the picture.

**The rig's stated box cannot settle part placement.** All six chassis declare
exactly `4.00 x 9.00 x 4.00` despite visibly different widths, so it is a
declared envelope rather than a measured fit. An hour went into scoring
placements against it before that registered.

---

## The cockpit's protocol

**`0x02146004` is the SiteLink modem, not the game's network receive.** Two
findings were built on top of that misreading before its own strings gave it
away - `Modem in command mode`, `Answered at 115200...Syncing up.` The state at
`0x0239DD9A` indexes eight *connection* states.

**"There is no second dispatch" was wrong twice over.** There is one, and the
reason it was invisible is that **the game reads its opcode from packet byte
`0x13`, not byte 0**. Byte 0 is the low-level type the boot monitor switches on.
Found by working backwards from the *sending* side: 43 call sites, 31 distinct
opcodes from `0xBA` to `0xED`, which said the game protocol lived nowhere near
the `0x01`-`0x07` being searched for.

**The "second dispatch over packet byte `0x13`" is the in-game keyboard.**
It was found by looking for a network dispatch, so a network dispatch is what
it was called: 33 opcodes at byte `0x13` of a message. `(8,A6)` is the event
buffer, the event is kind `0x0A`, kind `0x0A` is posted from exactly one site
in the ROM - a one-byte read from the console - and byte `0x13` is the low byte
of that longword parameter. The 33 opcodes are 33 **keystrokes**, and their
values were shouting it: `0x4A` is `J`, `0x51` is `Q`, `0x64` is `d`, `0x73` is
`s`. Settled by typing them at the modelled serial port and watching the pod
answer.

**`0x0218AEE4` is not a message queue.** It was written up as one, with `+2`
as a message type and `0x0C` as "a type it sends somewhere of its own". It is
`My_Mech_Ptr`, `+2` is `Class_ID`, and `0x0C` and `0x10` are classes 12 and 16
- a VTV and a Copter. Three wrong readings that were wrong *together*, because
each one propped the others up: once a pointer is called a queue, the field at
`+2` has to be a type, and then the constants compared against it have to be
type numbers. The firmware named the pointer itself, in a `printf`, about
thirty feet away.

**`0xF6`-`0xFF` are not the console's setup messages.** They were written up
here as "the pod's mode machine, driven from outside... where
`COCKPIT_CONFIG_MSG`, `PLAYER_CONFIG` and `SHADOW_ROM` have to land", on the
strength of being receive-only, arriving in a block, and writing what looked
like mode bytes. The numbers they write - `0x0D`, `0x0E`, `0x0F` - turn out to
be subscripts into a table of state *names*, and the names are
`Loading File...`, `Saving File...`, `Appending File...`. They are the remote
control for an **animation editor** built into the cockpit firmware. A block of
opcodes that arrive together and write the same few globals is weak evidence
for what they mean; the giveaway was there the whole time, one indexed table
away.

**`SecCom 674 bytes` is hexadecimal.** Four documents here repeated 674 as a
decimal byte count for months. The code pushes `$674` against a `%x` format:
**0x674 = 1,652 bytes**. Anything derived from a *printed* value rather than a
decoded one deserves a second look.

**The pod sends 38 opcodes, not 31, and the sender has 45 call sites, not
43.** The first count took the nearest preceding `move.b #imm,(d16,A6)` as the
opcode, which is right for most senders and silently wrong for the ones that
write the opcode before a branch - it picks up some later byte instead. The fix
is to require the displacement to be the *same* one the call's
`pea (d16,A6)` pushes, so the store is provably into that buffer's first byte.
A count that only ever moves upward when the method is tightened is a count
that was measuring the method.

**The SecCom block is not in the first 64K of the Amiga window.** Watching
`0x40000000`-`0x4000FFFF` across a full run found only the handshake word, and a
conclusion was drawn from that. The block is at `0x4007E000`.

---

## The operator console

The console's message names and field lists are known; the opcode that goes
with each is not, and this is where most of the failed effort went.

**THINK C's far model does not reach globals through A5.** The whole plan -
resolve the globals, trace `A5` displacements to the encoders - rested on that.
The application has **zero `lea (d16,A5),An` sites and eight `pea (d16,A5)` in
260 KB of code**. It puts absolute 32-bit `DATA` offsets inline in the code
instead, with `CREL` saying where they are.

**The message strings are not statically referenced at all.** Six ways of
reaching them, every one empty:

| looked for | result |
|---|---|
| a `CREL` fixup site holding the offset | all 4,256 fixups target `0x0072`-`0x31CA`; none above |
| a `DREL` slot pointing at it | slot contents stop at `0x7468`, just below the messages |
| any `DATA` longword equal to the offset | none in 39,096 bytes |
| a 32-bit constant in any segment | none |
| a 16-bit constant in any segment | none |
| `pea`/`lea (d16,A5)` with a fitted base | 8 sites and 0 sites; no base fits |

The mechanism is not at fault - the same technique finds `CArray.c`,
`CObject.c`, `CWindow.c` and an assertion message - and the extraction matches
the resource fork byte for byte. Those particular strings are simply not on the
end of any static reference.

**`DATA` opens with a longword `600`, and the resource holds exactly 600
printable strings.** Striking, and still a coincidence: read as offsets in three
framings, only 12 to 16 of the 600 land on a string start where an index would
land on all.

**`pea $10012.l` is a lookup token, not a hardware address.** Nearly published
as the resolution of the unidentified device at `0x00010007`-`0x00010015`. It is
an argument to a table search at `0x02122550`. That range is still unidentified.

---

## Tooling, twice over

**`0xFFFFFFFF` in a display list is a separator, not the end.** The stub's
walker treated it as a record type and stopped, so every display list this
project ever decoded read as "a type 0 record and a terminator - nothing to
draw", and that sentence went into the documentation as a fact about the
cockpit. A real frame has one after the leading record and carries straight on
with the viewport, the object and its item stream. One longword, misread, hid
every frame the pod ever built.

**A stub that is too fast is as wrong as one that is too slow.** The renderer
stub completed a render the instant the doorbell was rung, and `Async_Render`
clears the render-done flag two instructions later - so the completion was
wiped by the code that requested it, and the pod waited for ever for a frame it
had already finished. It looked for months like the firmware rendering once and
stopping, and it was read that way in these documents. Hardware takes time, and
a model that takes none is not the fastest possible hardware; it is hardware
that finishes before the caller has stopped talking.

**A string extractor that rejected control characters threw away most of the
firmware's log lines.** `fnstr.py` accepted only printable ASCII between two
NULs, and the firmware ends nearly every log line with a newline. So it
reported "no strings" for handler after handler, and those silences were read
as findings. The damage was retroactive as well as current: the sweep that
named `0xC5` had already been run with the broken filter. Fixed by allowing
tab, newline and carriage return; the same sweep then named eight opcodes,
including `0xBA` as damage and `0xC6` as `ROUTER_MODEM_COMMAND_MSG`. A filter
that silently produces *fewer* results is the dangerous kind, because nothing
about the output says it is wrong.

**A header that is not in the Makefile's dependency list will hand you a fixed
decoder reporting the old numbers.** This happened with `mesh.h`, and then again
with `scene.h` and `rig.h` after `mesh.h` was fixed but the lesson was not
generalised. Every header is now one `HDRS` variable.

**A cleared byte looks exactly like a byte copied from packet offset zero.**
The difference tool attributed each changed run to the packet offset whose
value it matched, which is sound for every value but one. `0xE8`, whose entire
effect is to zero an entity's class and return the slot to the pool, was
reported as copying packet `+0x00` into the entity - a reading that would have
made the one message that *destroys* a thing look like one that configures it.
An inference that is right for 255 values out of 256 still needs the 256th
handled explicitly.

**Bash heredocs eat backslash escapes in generated source.** `\n` inside a
heredoc becomes a real newline, which produces unterminated string literals in C
and Python alike. It cost time on at least five occasions. Use the `Write` tool,
or build the escape with `chr(92)`.

**The quickstart in README.md did not run.** It told the reader to pass
`--tty 11016`, an option the binary does not have and, as far as the history
goes, never had under that name; the working flag is `--duart 11000`. Nobody
noticed because everyone working on this had the real command in their shell
history. **The conformance harness never touches the documented command**,
which is exactly the gap that lets a front-page example rot. Checked by running
it.

**A checkpoint beginning with a dash was read by `grep` as an option.** Five
checkpoints - `----- PERIODIC -----` and its siblings - failed while the text
they were looking for sat in the output file. `grep -qF -- "$check"` fixes it.
The failure mode is the bad kind: the harness said the firmware had changed
when the harness was what was wrong.

**Multi-file edit scripts that abort partway leave the tree inconsistent** and,
worse, leave a commit message describing changes that were never made. Edit one
file at a time.
