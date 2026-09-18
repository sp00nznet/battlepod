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

**Multi-file edit scripts that abort partway leave the tree inconsistent** and,
worse, leave a commit message describing changes that were never made. Edit one
file at a time.
