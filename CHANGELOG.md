# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The model tools are in the conformance harness**, which now runs
  **38/38** rather than 30/30. Five of the new checkpoints are the model
  archive's own numbers - the header opcode, clean walks, vertex and material
  counts, and the bounding-box check - recorded as *floors* rather than
  equalities, since the decoder is meant to improve and a number going up
  should not fail a build while a number going down means something that used
  to decode no longer does. The other three run each tool's `--selftest`.
- README documents `model.py` and `render.py`, which it had not mentioned at
  all, and the disassembler's figure is corrected from 95% to 98%.

- **Found the mechs.** Rendering all 81 models that produce polygons puts three
  dozen chunky red-brown parts in the high ids, 463 to 514, and their bounding
  boxes give the game away: `491 == 494`, `492 == 495`, `493 == 496` exactly,
  and `516`/`517` occupy mirrored half-spaces. Left and right limbs, modelled
  once and used twice.
- **The parts carry no joints** - one transform node each and no transform
  opcode executed - so a part is rigid and authored about its own pivot, which
  is why its box has to include the origin. Drawing a set together piles them at
  the origin instead of assembling. What places them is the display list: each
  object record carries its own 3x3 and translation, so the 68020 emits one
  record per part per frame with the joint angles baked in. The TI holds rigid
  parts, the 68020 holds the skeleton.

- **`tools/render.py` — the first geometry drawn out of the archive.**
  Z-buffered flat-shaded triangles, one directional light, a graded sky and a
  hazed ground, at the pod's own 480x360, written as a PNG with nothing but the
  standard library. Model 30 comes out as a **terrain mesa**, recognisably one
  of the buttes standing behind the mechs in the reference footage - which is a
  better check than any count, because the thing that comes out looks like the
  thing the pod drew.
- A model has to be walked down **one** level of detail to be drawn: taking
  every branch stacks the near and far versions in one frame and renders as a
  lump. Which side carries the detail differs per model, so the renderer tries
  both and keeps the fuller one.
- **What the model's bounding box actually spans**: the vertices *and the
  origin* - several models bound an axis at exactly `0.0` where no vertex
  reaches, which is a part keeping its own pivot inside its box - and *every
  value ever written to a vertex slot*, not just the survivors, because each
  level of detail rewrites the same slots. Vertices alone matched 41 of 84;
  plus the origin, 55; every write plus the origin, **63**. Archive-wide the
  box check goes 41 -> **63** of 130.

- **`tools/model.py` — the model format, and a tool that runs it.** A type 1
  resource is not a mesh but a **threaded program** of 45 opcodes, the same
  design as the display list, run by the renderer at `0xFE00EDB0` against a
  table at `0xFE00EEA0`. Vertices are IEEE float triples carried inline;
  polygons are index lists with a material; materials are six longwords of
  which three are a colour. The stream starts at header `+0x58` and that is a
  valid opcode in **130 of 130** models.
- The model's own bounding box is the validator: where a walk completes it is
  demonstrably right, and model 24 decodes 246 vertices against a header that
  says 246, 29 materials against 29, and reproduces its stated box exactly.
- Branch and call targets are bit offsets; `$160` is `2 + 3n`; `$520`/`$540`
  take one operand each, not five.
- **The model branch predicate.** `$320`, `$360` and `$420` do not carry a
  target, they carry a *program*, run by a second threaded interpreter at
  `0xFE018910` through a 24-entry table at `0xFE018A00` - postfix, five
  one-operand push forms then operators taking none, terminated by `$000`.
  `$320 $080 $000 $040 $00C8 $260 $000 $1440` is "if value(0) >= 200, jump
  0x1440 bits on": a distance test choosing a level of detail, which is where
  most models keep their geometry. `$2C0` is the unconditional form.
  Clean walks went 38 -> **98** of 130, vertex counts matching the header
  31 -> **84**, boxes reproduced 17 -> **41**, materials 31 -> **55**.
- The box check still lags the count check and the gap is written down as the
  hypothesis it is, not as a finding: it is not transforms, and walking every
  branch mixing levels of detail explains part of it but not all.

- **Reference footage, and a correction.** Two period videos carry real screen
  capture - the BattleTech 3.0 Dooley Trainer and a Discovery Channel piece -
  and they show **flat-shaded, untextured solid polygons with cast shadows**,
  a gradient sky and distance haze. An earlier note here called the target
  texture-mapped on the strength of VWE's 1994 press kit; that press kit was
  describing a *plan* for a next cockpit, not this one. The archive says the
  same thing and should have been checked first: six type 2 bitmaps totalling
  22,632 bytes against 130 models is a font and some HUD furniture, not a
  texture library. One frame shows a pod interior with all four surfaces at
  once. Wireframe does appear in this product - in the post-game debrief
  screen, and nowhere in the world view. See RENDERING.md.
- **What the pod actually looked like, settled.** Not wireframe: the renderer's
  code segment contains **zero `LINE` instructions**, and only ten of the
  TMS34020's own block primitives against 517 coprocessor operations - so the
  spans are written by hand, which is what shading requires because `FILL` does
  one flat colour. The frame buffer is 480x360 at 16 bits per pixel. And VWE's
  1994 press kit describes the cockpit then in development - the Tesla pod,
  which is this release - as the one that "utilizes texture mapped graphics".
  The mech art in the operations manuals is print illustration, not screen
  capture. See RENDERING.md.

### Fixed

- **The object record's trailing groups are pick queries, not geometry**, and
  both the docs and `--rstub` said geometry. Seven longwords each, capped at 32:
  the 68020 writes a screen X and Y, and the renderer fills in what it drew at
  that pixel - entity, sub-part tag and position - while drawing, reading the
  frame buffer at `0xFE01A280` and restoring the pixel afterwards. It is how the
  cockpit knows what is under the crosshairs. `--rstub` now decodes them.
- **DEVICES.md contradicted itself on the renderer's command dispatch table**,
  listing it two rows off - opcodes 3 to 12 with 1 and 2 null. The command loop
  does `DEC A0` before indexing, entry 0 jumps to the reset code and entry 1
  writes error, handle and address, so entry *i* serves opcode *i+1*.

- `tools/tms340dis.py` printed the cross-file `MOVE` (`0x4E00`) with both
  operands in the same register file. Bit 4 is the *direction*: `FE01A150` is
  `MOVE A12, B0` and is followed by `CPW B0, B0`, and `FE013210` has to reach
  `B9`, the colour `VLCOL` latches. The interpreter already had this right.

- **`MOVE *Rs+, Rd` clobbered the value it loaded when the two registers were
  the same.** The renderer's item dispatch is exactly that instruction -
  `MOVE *A0+, A0`, fetching a handler address through the register it advances
  - so the interpreter was jumping into the middle of its own jump table. On
  the hardware the loaded value wins. Self-tested.
- **The item stream is not inside the object record.** The renderer reads the
  object's `+0x58` as a 1-based index into the list built from **type 7**
  records and hands that record's payload to the interpreter. What follows the
  object's own header is geometry - `+0x88` groups of seven longwords, which is
  what the emitter's `7n + 33` was saying - run through a *second* item
  interpreter with its own table at `0xFE018A00`. `--rstub` and `--render` both
  corrected.

### Added

- **The TMS34082's command word, and the first coprocessor routine running.**
  The 32 bits after a `CMOV*`/`CEXEC` opcode are the coprocessor's instruction:
  `ID | ra | rb | rd | md | fpuop`. The `md` field needs no guessing - all nine
  commands R.BIN issues during a render agree with it, each matching the mode
  its TMS34020 instruction implies. **Mode 3 selects a routine from the '82's
  internal ROM**, about 160 of them documented, which is what changes the size
  of this job: the arithmetic is documented silicon, not microcode to reverse.
- Short-form `CEXEC` is recorded and **not executed**: it splits its command
  between two words and the scanned handbook's diagram of that split is not
  legible enough to settle, so a run reports how many it met rather than
  running them wrongly.
- `CEXEC $D800` decodes as `SCALE` - the perspective divide and viewport
  transform - and now runs. A render walk reports one routine executed and
  **one still unidentified**, named rather than guessed.
- `MCADDR` is written before the draw, so the renderer points the coprocessor
  at something first.

- **The renderer accepts a display list and walks it.** `tms340run.py --render`
  builds one from the format in DEVICES.md and drives R.BIN at it directly,
  which is the only way to see the renderer draw: the 68020 only builds a list
  once a game has started. It is also a test of the format, and it found two
  things missing from it - the list header is **two** longwords, not one, and a
  **type 2 record is not optional**: with no draw order the renderer collects
  every object and iterates an empty list.
- **Why nothing draws yet, measured rather than assumed.** The whole object
  path runs - 236 instructions, no unimplemented opcode - and culls the object
  before its item stream, because its transform at `0xFE0220F0` is
  `CEXEC`/`CMOVGC`/`CMOVCM` and nothing else. The walk needs **ten distinct
  coprocessor commands, twelve issued**, of which eight are register and memory
  transfers and only two are operations: `CEXEC $E000` and `CEXEC $D800`. That
  is the size of the TMS34082 work standing between here and a first frame.
- PIXBLT, FILL and PIXT in the interpreter, taking their operands from the B
  file the way the hardware does, including the binary-source form that expands
  one bit per pixel into COLOR1 and COLOR0 - which is how the cockpit draws
  text. Self-tested.
- `MOVE *Rs+, *Rd+`, `MOVE *-Rs, *-Rd` and `MOVE *Rs(o), *Rd(o)`, which the
  object draw uses to stream a transform through. Code segment recognition
  95% -> **97%**.
- `--boot N` to give the hardware bring-up its own budget, and a coprocessor
  command log so a run says exactly which commands it needed.

- **The display list format**, read off the two emitters in ROM3_0 that build
  it rather than off the wire. It is a flat array of big-endian longwords with
  a leading count, copied verbatim into the renderer's memory. Record type 8 is
  a viewport - its width, height and centre are derived from its corners by the
  emitter, which is what identifies it. Record type 1 draws an object and
  carries twelve IEEE single-precision floats that read as the identity only
  as four rows of three: a 3x3 rotation and a translation row. So the 68020
  sends a *matrix*, and the coprocessor does the transform. The renderer
  confirms the shape: it takes two pointers into the object, one at the start
  of the twelve and one at the start of the fourth row. Record `[+4]` is the
  length of what follows the type and length words, which is why the emitter
  writes `7n + 33` for a record 35 longwords long.
- **The pod's screen resolution: 480 x 360.** The object record carries `479`
  and `359` as the screen extent, and running R.BIN leaves the renderer's own
  WEND register holding `$016701DF` - 359 by 479. Two sides of the machine,
  same number.
- The renderer's full command set. There are ten opcodes, not four: 4 is
  compact, 6 is render, 7 follows every render with the constant 5, and 10
  loads a palette. A request record is 12 bytes, not 8 - 20 for allocate.
  Rendering goes through `Async_Render` at `0x0214D302`, not through the
  opcode 6 wrapper, which is dead code.
- **The renderer's side of the same list**, which agrees with it. Its command
  dispatch is a ten-entry table at `0xFE028460` where entry *i* serves opcode
  *i+1*, so opcode 6 is `0xFE007630`, which converts its argument from a byte
  to a bit address and calls the walker at `0xFE009D80`. The record dispatch
  table at `0xFE00A160` has **nine record types, 0 to 8**, and every handler
  only files the record into a bucket; a second pass walks record type 2, which
  is the **draw order** - 1-based indices into the objects - and is what the
  firmware's `Render List Overflow` counts.
- **The item stream and its 25 opcodes.** After an object record's 35-longword
  header come items whose opcodes step by `0x20` because the renderer uses the
  opcode *directly* as a bit offset into its table at `0xFE0229E0` and then
  `JUMP`s - a threaded interpreter. Twenty-five entries there, and the 68020
  has an emitter for every one, which is where each item's length comes from.
  Two of them carry a C string copied with the bytes reversed per longword.
- `battlepod --rstub` now decodes a display list when a render command posts
  one - records, matrix, item stream and strings - and `--selftest` walks a
  synthetic one, since nothing in the release sends a render command until a
  game starts.
- `JUMP Rs` (`0x0160`), which the item interpreter uses and both tools were
  missing.

- The renderer's processor is identified: a **TMS34020**, not the TMS34010 it
  had been read as, driving a **TMS34082 floating-point coprocessor**. R.BIN
  executes `SETCDP`, `SETCSP`, `SETCMP`, `RPIX`, `VLCOL`, `VFILL` and `CLIP`,
  none of which exist on a '10, and 419 `CEXEC`/`CMOV*` coprocessor
  instructions - the first of them five instructions after reset. Both tools
  now follow the TMS34020 User's Guide (August 1990) instead of the '10's.
- `tools/tms340run.py --selftest`: assertions pinning the three decodings that
  had been wrong - absolute load versus store, the MMTM/MMFM mask order, and
  SUBXY's flags.
- `tools/tms340run.py --fb FILE`: write the renderer's frame buffer out as a
  PGM. Its geometry comes from the renderer itself - DPTCH bits a row, PSIZE
  bits a pixel - and reads 512x512 at 16 bits per pixel. Nothing is drawn into
  it yet; the point is that "did it render" is now a question with an answer.
- `tools/tms340run.py --skip-unknown`: step over unrecognised opcodes and count
  them, for measuring how much further a run would get. A diagnostic, never a
  claim that the run was faithful.
- The XY instruction group (ADDXY, SUBXY, CMPXY, MOVX, MOVY, CVXYL, CVSXYL,
  ADDXYI), the coprocessor group including CEXEC's two-word short form at
  `0xD800`, RPIX, the SETC*P family, the field-1 SEXT and ZEXT forms, and
  absolute memory-to-memory MOVE. Recognition of the code segment goes from
  72% to **95%**, and branch targets landing inside the image from 98% to 99%.
- The full branch condition table. Only 7 of the 16 conditions were evaluated;
  the arithmetic never set carry or overflow at all, so LT/GE/LE/GT/HI/LS could
  not have worked.

- `tools/tms340run.py`: an interpreter for the renderer's TMS34020 code. If
  R.BIN executes it draws its own frames, which would make the model format
  something the renderer reads rather than something that has to be decoded.
  It runs 3,000,000 instructions without meeting an unknown opcode, brings up
  the hardware, writes the on-chip I/O registers and clears the frame buffer -
  262,144 writes to 0xA0000000.
- A real bit-addressed memory model: fields are read and written at arbitrary
  bit addresses across word boundaries, and SETF sets the size and
  sign-extension per field. Every move uses the field its opcode selects.
- Instruction coverage for MOVB, the immediate arithmetic forms, ADDK/SUBK,
  CALLR, DSJ and DSJS, PUSHST/POPST/GETST/PUTST, MMTM/MMFM, the
  single-register arithmetic, multiply, divide, modulo, BTST and CALL Rd.

### Fixed

- **The display interrupt now runs, and with it the whole vertical-blank path.**
  Two decoding errors kept it dead. `0x05A0`/`0x07A0` are absolute *loads*, not
  stores - the manual gives the group as `0000 01F1 100R SSSS` for a store and
  `0000 01F1 101R DDDD` for a load - so the handler's read-modify-write of
  `INTPEND` never read anything and never cleared the pending bit. And `MMFM`'s
  register mask is `MMTM`'s reversed: bit 15 names A0 in one and bit 0 names it
  in the other, which every one of the 25 matched pairs in the image confirms.
  Reading both the same way popped the saved register into the stack pointer and
  sent `RETI` to address zero.

  With both fixed the renderer stops timing out of its frame wait - 1,142,192
  spins down to 5,078 - and gets through double-buffer setup to boot stage 5.
  Execution reaches 570,000 instructions before the first unknown opcode, up
  from 20,000.
- `0x38000022` is the renderer's reset line, not an open question: the
  monitor's `n - Start TI` prints "Starting TI, screen should clear" and writes
  a word to it.
- Reaching the diagnostic monitor by patching an `RTS` over the game
  initialisation also disabled menu item `y - START TEST GAME`, which calls
  that same function. Patching the call site instead leaves both working.
- `BTST K, Rd` occupies the whole of `0x1C00`-`0x1FFF`, five bits of constant -
  it was decoded as a two-register form, so a quarter of the block was
  unrecognised. Code segment recognition 97% -> **98%**.
- `SUBI IW` is `0x0BE0`, not `0x0CE0`.
- `DSJ` and `DSJS` printed targets with no load base, and `DSJS` measured its
  displacement from its own address rather than the next instruction. Branch
  targets landing inside the image went from 94% to 99%.
- `MOVE Rs, Rd` across register files (`0x4E00`) wrote the destination in the
  source's file.
- Every TI instruction address the disassembler printed was 0x40 bits too high:
  the 8-byte file header was being counted as part of the image, when the
  68020's upload log says file offset 8 is TI 0xFE000000. Building the
  interpreter is what exposed it. `CALLA $FE000780` now lands on the first
  instruction of the hardware-init routine instead of mid-data.

- Relative branch and call targets were missing the image's load base, so every
  `JR`, `CALLR` and `DSJ` target the disassembler printed was wrong. Validation
  now covers relative branches as well as absolute ones, which takes the check
  from 164 targets to 982: 938 of them land inside the image.

### Added

- `tools/tms340dis.py`: a TMS340 disassembler, written from the encodings in
  the User's Guide. 36% of `R.BIN` is recognised - the
  register-indirect MOVE family and the graphics group are the gaps - but 164 of
  164 absolute call and jump targets land inside the image on all three renderer
  binaries, which is what shows it is in sync. Now 49% of all words, 70%
  ignoring zero fill, and 100% over the renderer's hardware init.
- `--watch BASE:LEN` logs accesses inside a mapped region, which the unmapped
  log cannot see. Pointed at a loaded resource it shows exactly which offsets
  the firmware reads and from where.
- The disassembler now decodes FPU instructions, following `--cpu`. The
  cockpit's geometry and physics code is dense in them and previously read as
  `dc.w $f2xx`.
- `tools/resmap.py`: walks a cockpit resource archive. The format comes from the
  firmware's own parser, and the walk accounts for every byte of the file and
  reproduces the firmware's printed index exactly.
- `RENDERING.md`: what it would take to reproduce all four of a cockpit's
  surfaces - the 3D view, the secondary screen, the panel and the controls -
  and which are blocked on what.
- The captured Remote I/O stream is decoded back into cockpit panel state:
  which lamp is lit and how brightly, where each bar graph stands, what each
  soft-label display reads. That is what a panel renderer consumes.
- `tools/macres.py`: lists and extracts Macintosh resources, from a raw fork or
  the AppleDouble sidecar `unar` writes. Gets at the operator console's 20 CODE
  segments.
- `tools/logproto.py`: recovers the cockpit network protocol from an operator
  console log. The console logged every message it exchanged with the pods by
  name, so a surviving log specifies the protocol directly.
- `--packet` hands the booted firmware one received packet through the stubbed
  boot monitor. The firmware consumes it and releases the buffer, which is how
  delivery is confirmed.
- `--monitor` installs a stub service table for the pod's boot monitor, which
  is not in the release, and reports which slots the firmware calls. With it the
  cockpit boots all the way to its main loop instead of dying on a null call.
- The renderer stub now maps the renderer's memory as real RAM and keeps its
  ready word and comm pointer restored, so the firmware stops reporting
  `TI ERROR!` and posts its sixth command.
- Interrupts. `src/battlepod_m68kconf.h` turns on Musashi's interrupt
  acknowledge hook so the DUART's programmed vector is honoured, and the DUART
  model tracks IMR, the command registers and the interrupt status register.
- `--vbr`, `--sr` and `--irq-level`. VBR now defaults to `0x02000000`, which is
  where the firmware's own vector writes say the boot monitor left it.
- `--clock ADDR[:N]`, a free-running counter standing in for the timebase the
  boot monitor maintained at `0x02000808`.
- Remote I/O packets are captured and hex-dumped, and the stop report names the
  last exception vector fetched.
- `--duart` models the cockpit's MC68681 DUART, both channels, including the
  receive path — so the firmware can be typed at, not just listened to.
- `--duart-in` types at the console receiver.
- Channel A transmits are captured and hex-dumped as the Remote I/O protocol.
- Conformance now also drives the firmware's diagnostic monitor and checks the
  Remote I/O packets byte for byte: 23 checkpoints.

### Changed

- `--tty` is gone, replaced by `--duart`. The part is identified now, so the
  tool models it rather than guessing at a write-only address.
- `--help` regrouped and corrected; several options were missing from it.

### Findings

- R.BIN is a scatter-load image: records of a big-endian target offset and a
  longword count, each followed by its data, which the 68020 places at five
  different TI addresses. The records account for all but the four-byte
  terminator. Only the first segment is code; the fourth is the I/O register
  initialisation table at 0xFFFF0000 and the fifth the processor's trap
  vectors.
- Loading it flat, which is what both tools did, left those segments absent -
  so the renderer's I/O setup loop read zeroes and spun forever writing to
  0xC0000000. Placed properly it programs eight distinct video registers.
- Disassembling only the code segment gives 72% recognised rather than the 49%
  previously reported across the whole file; the earlier figure counted data
  segments as code.
- SETF is encoded 0000 01F1 01FE SSSSS - field select in bit 9, sign-extend in
  bit 5, size in the low five bits with zero meaning 32. 0x0550 and 0x0740 are
  SETF; that much of the earlier reading holds.
- 0x0620 and 0x0660 are three words, not one: that reading lands execution on
  the stack-pointer setup, where treating them as one word leaves an
  unexplained 0x000D mid-entry. Their effect is still unknown. Their operands
  look like a table of globals 32 bits apart, but modelling them as absolute
  loads changed nothing observable, so that guess was withdrawn rather than
  kept.
- The renderer's dispatch table base and indexing are confirmed independently:
  the only places in the image holding handler addresses are exactly
  0xFE028460 + (opcode - 1) * 32 for opcodes 3, 4 and 5. Opcode 4's handler
  branches to itself - an unused slot - and 0xFE0072E0 jumps back into the entry
  sequence, which is the reset path.
- The renderer's main command loop at 0xFE006D80 decodes with no unknown words,
  and is the same protocol already read off the 68020: status word four bytes
  into the comm block, queue eight bytes in, 0xFFFFFFFF terminator, pi as the
  ready signal. Its command dispatch table is at 0xFE028460, indexed by
  opcode - 1, with handlers for opcodes 3 to 12; opcode 5 is load resource map.
- Right shifts encode 32 minus the count, which the disassembler now accounts
  for - it was printing SRL #29 where the firmware means SRL #3, the bit-address
  to byte-address conversion.
- The manual's absolute-move table is the least legible part of the scan and its
  load/store split contradicts the firmware. Settled from the data instead: all
  seven writes to the renderer state word use 0x0780, and 0x0580 writes the
  TMS34020's own I/O registers, so both are stores. The rest of that opcode
  group is left unrecognised rather than guessed.
- The renderer's hardware init reads cleanly: it writes three registers in the
  TMS34020's documented I/O block at 0xC0000000, enables interrupts, then clears
  0x40000 bits of frame buffer at bit address 0xA0000000. That the addresses land
  on the processor's own register block is a semantic check on the disassembler.
- The renderer kernel is engine code, not game content: `R.BIN3_0` and
  `R.BIN2_5` are byte-identical between BattleTech and Red Planet.
- The 68020 never reads inside a model. Watching the whole archive across a
  complete boot shows reads only at offsets 0, 4, 8, 0x0B and 0x0C - the 16-byte
  header - with every reading PC inside the resource-map builder. The model body
  is parsed by the TMS340 code in R.BIN, so reading it means reading TMS340 code.
- The 68020-side archive format: a kind directory, then per kind a binary-searched
  table of 16-byte records, with the record chain verifying to the last byte of
  the file. Kinds 0 and 1 hold shapes - a count then 26-byte elements of six
  floats and a word - which `size == 4 + 26*count` confirms for 228 of 244
  records.
- Shapes are keyed by the same ids as the visual models: 64 of Red Planet's 65
  shape ids are also type 1 model ids. The TI holds the visual geometry and the
  68020 keeps a far coarser solid-and-cylinder version of the same object.
- Corrects an assumption recorded earlier: solids, cylinders and ARES are not
  the drawing primitives. They are the 68020's own representation.
- The renderer keeps a pool of up to 1500 "solids" of 32 bytes each, built from
  three validated primitive kinds: solids, cylinders and ARES, each with a
  direction the firmware sanity-checks.
- A type 1 model's body is variable-length: no relation of the form
  `a*field + b*field + c` explains the resource size for even half the models,
  so the header fields are not counts of fixed-stride records.
- The resource archive format: 16-byte headers, `-1` terminated, with an alias
  bit that makes `+0x0C` name another resource instead of counting data.
- Type 1 is 3D models - bounding box valid in 130 of 130, bounding sphere in
  127 of 130. Type 4 is an alias table, all 136 aliases resolving. Type 7 holds
  the payloads they point at. Type 2 is six compressed bitmaps, two of them
  identical across BattleTech and Red Planet.
- Corrects an earlier miscount: the archive holds 418 resources (130/6/151/131),
  not 467. The earlier figures were eyeballed from the console listing; the
  parser now agrees with the firmware id for id.

- The serial ports are an MC68681 DUART at `0x00011000`, register N at
  `N*2`. Channel A is the Remote I/O board at 9600, channel B the console at
  19200.
- `ROM3_0` contains a full diagnostic monitor, reachable by patching an `RTS`
  over the game init call at `0x02138A64`.
- Remote I/O device map, from the monitor's own prompts: lamps `0x00`-`0x3B`,
  `0x50`-`0x53`, `0x60`; displays `0x80`-`0x91`; bar graphs `0x80`-`0x91`
  except `0x8C`, `0x8D`, `0x8F`.
- RIO packets are framed `01 <node> <len> <node+len> <payload> <sum(payload)>`.
  Opcodes: `D1` display (id plus 8 ASCII characters), `D2` bar graph (id plus a
  bar count), `D3` lamp (id plus brightness). All three now reach the wire with
  both checksums verifying.
- VBR is `0x02000000`. Nothing in the release sets it, but the firmware writes
  vector 71 to `0x0200011C` and the DUART's vector register is `0x47`.
- `0x02000808` is read in 336 places and written in none: the timebase came
  from the boot monitor, which is not in the dump.
- The boot monitor exports a service table at `0x02000400` with globals at
  `0x02000800`, both immediately above the vector table at VBR. The slots the
  firmware uses have the shape of a packet interface - two 32000-byte buffers
  registered at `+0x10` and `+0x14`, a `(node, length, buffer)` send at `+0x24`,
  and a poll at `+0x18` returning a pointer or NULL.
- The boot now ends with the cockpit idling in its main loop, polling for a
  packet that never arrives - which is what a pod does while it waits for the
  operator console.
- A received packet is a word, a body length, then the body; the first body byte
  is the opcode. Opcode 0 formats `GAME RUNNING %d %d %d GAME_NAME` and replies;
  opcodes 1-7, 0x20 and 0x21 share a handler; 0xC7 and 0xE4 have their own.
- Everything else goes to the inter-centre modem router - the code behind
  `Dial_List`, with `Master router ready`, `NETWORK OVERLOAD` and the AT command
  timeouts - not to the game layer.
- The protocol's message vocabulary and the order of a game start, recovered
  from the operator console log in the release: IDENTIFY_YOURSELF, SHADOW_ROM,
  per-image Load, Set Go_Address, GO, COCKPIT_CONFIG_MSG, PLAYER_CONFIG,
  MECH_CLASS with Drop Location, GAME_OVER.
- `MECH_CLASS`'s type field is the vehicle id from `Vehicle_List`, which is also
  the last column of `Game_Setup` - those plaintext files map onto the wire.
- Remote I/O opcode `0xD5`, no payload, sent once during boot.
- A packet that passes the address checks is queued into a 100-slot ring at
  `0x02183716` for a consumer that only runs during a game. Sweeping all 256
  opcodes with a minimal body changes nothing except `0xC6`, which the modem
  router logs - so a single packet cannot start a game.
- The operator console is THINK C far model with `CREL`/`DREL` relocations, so
  its string references are placeholders on disk. Reading the sender needs those
  relocation tables implemented first.

### Fixed

- CI lint no longer fails on Musashi's macro `#include`; cppcheck now lints
  only this project's source.

## [0.1.0] - 2026-09-14

First working harness. The cockpit boots from its own image set to its main
game loop with the renderer, audio and Amiga boards stubbed.

### Added

- `battlepod`: loads a VWE Load script, places each image at the address the
  script names, and runs the cockpit's 68020 on a Musashi core.
- Sparse 4 GB page table with a bus logger: every access outside declared RAM
  is recorded with width, read and write counts, first PC, and last value
  written, reported by region and by address, optionally as CSV.
- `--tty` serial console capture, which reads the firmware's own boot
  narration.
- `--rstub`, a stand-in for the TMS340 renderer: answers the handshake,
  acknowledges commands, logs the queue, and serves allocations from a bump
  allocator.
- `--poke`, `--set`, `--tick` for standing in for devices that only have to
  answer one question.
- `--trace` and `--dis` for reading the firmware.
- `--cpu` to select the Musashi profile; defaults to 68040 because that is the
  only profile with the FPU enabled.
- `--selftest`, a self-check that the CPU runs, unmapped writes are logged and
  the PC is tracked.
- `tools/xref.py`: find the instruction that points at a console message.
- `tools/conformance.sh`: replay the boot and check it still reaches every
  milestone, run by `make conformance`.
- `DEVICES.md`: the cockpit CPU board's address map, the image header format,
  the renderer command protocol, the resource archive index, and the Amiga and
  audio handshakes.

### Findings

- The renderer is a TI TMS340x0. Its bit-addressed space maps into the 68020 at
  `0x20000000`; `TI_address = (68k_address - 0x20000000) * 8` holds exactly for
  every uploaded segment, and the firmware performs the inverse itself.
- The renderer signals ready with `0x31415926`.
- The image header is 28 bytes: `0x601A`, then text, data and bss sizes.
- The audio board is a 32-longword ring FIFO at `0x50001000`.
- The Amiga 500 handshake is `0x01234567` in, `0x76543210` back.

[Unreleased]: https://github.com/sp00nznet/battlepod/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sp00nznet/battlepod/releases/tag/v0.1.0
