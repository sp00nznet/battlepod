# Roadmap

Background and the original field notes are in [PLAN.md](PLAN.md); the hardware
findings are in [DEVICES.md](DEVICES.md).

## Done

**Phase 0 — ground truth.** Load-script parser, image header decode, Musashi
68020 core, sparse memory with a bus logger. Produced the cockpit's address map
by observation.

**Phase 1 — boot.** Identified the renderer as a TMS340 family part and
decoded its
handshake and command protocol. Stubbed the renderer, audio signature and Amiga
handshake far enough for the firmware to parse its resource archive and reach
`main game loop (SecCom 674 bytes).`

**Phase 2 — talking back.** Identified the serial ports as an MC68681 DUART and
modelled both channels including receive, which reaches the firmware's built-in
diagnostic monitor and makes every subsystem drivable in isolation. Recovered
the Remote I/O device map and packet framing from it.

**Phase 3 — interrupts.** Found VBR (`0x02000000`, left there by the boot
monitor), modelled the DUART's interrupt logic, and supplied the free-running
timebase the monitor maintained. Lamps, bar graphs and alphanumeric displays now
emit real Remote I/O packets with verifying checksums.

**Phase 4 — a complete boot.** Found the boot monitor's service table at
`0x02000400`, stubbed it, and mapped the renderer's memory properly. The
cockpit now boots end to end and settles into its main loop polling for a
packet.

**Phase 5 — the renderer named and run.** It is a **TMS34020** with a
**TMS34082** floating-point coprocessor, both identified from instructions that
exist on no other part. `tools/tms340dis.py` reads 98% of its code;
`tools/tms340run.py` runs it, brings up the hardware, takes the display
interrupt and walks a display list handed to it.

**Phase 6 — the display list and the model format.** The list is a flat array
of longwords with nine record types, decoded from the 68020's emitters and
confirmed against the renderer's own walker. A type 1 resource turned out not
to be a mesh at all but a **threaded program** of 45 opcodes; `tools/model.py`
runs it and every one of the 130 models in the archive now walks to a return.

**Phase 7 — pictures.** `tools/render.py` draws what comes out: z-buffered
flat-shaded triangles, cast shadows, a graded sky, at the pod's own 480x360.
Terrain mesas, towers, buildings and mech parts all come out recognisable
against period footage.

## Next

**The four draw opcodes.** `$200` puts down a single pixel at a vertex, `$220`
fills a rectangle between two, and `$280`/`$2A0` draw a sized marker — the
running lights and panel glow on a mech. All four are measured and gated on
visibility; none is interpreted, so `render.py` draws a model's polygons but
not its lights.

**The bounding-box gap.** 120 models decode the right number of vertices and 84
reproduce their stated box. The failures are all *inside* the stated box, which
is what you would see if the box was computed by the authoring tool over a mesh
that was decimated before it reached the file. If that is right the gap is a
ceiling and not a bug, and saying so with evidence would close it.

## Blocked, and on what

**A standing mech.** The archive holds **rigs, not poses**: `$460` says which
sub-models make up an object and `$040` says how their nodes compose, but the
transforms that place them come from a table the 68020 fills in per frame. Two
independent lines of evidence agree on this — the parts' bounding boxes, and
the instruction stream. Getting a pose means running the game.

**Starting a game.** Still the oldest blocker. The firmware consumes packets
and the opcode dispatch is mapped, but the byte encoding of each message is
not, and the sender — the Macintosh console — is behind THINK C's `CREL`/`DREL`
relocations.

**Two coprocessor operations.** Short-form `CEXEC` splits its command across
two words, and one mode 3 routine is unidentified. The scanned TMS34082
handbook is not legible enough at those tables to settle either, and guessing
would put numbers on screen no cockpit produced.

**Type 7, 607 KB of the archive.** Compressed, and the decompressor at
`0xFE0090F0` is readable — but the first longword is shared across whole groups
of records rather than being a per-record length, so there is no oracle to
check a decompressor against. Everything else in this project was settled by
having one.

## Later

- Draw a whole display list rather than one model at a time. `render.py` takes
  a resource id today; the list format is decoded and the pieces are there.
- Remote I/O: keyboard or HOTAS to stick, throttle, pedals; lamps, heat scale
  and bargraphs somewhere visible.
- The Amiga 500 secondary display: either HLE the 674-byte SecCom protocol or
  run the 61 KB Aztec C program on a second Musashi context.
- Audio: decode `btAudio.dld`'s `A5A5` record stream.
- ARCNET over UDP, and multi-pod games.
- The Macintosh operator console — only needed for the real operator UI, since
  everything it supplies is plaintext in the release.

## Deferred, deliberately

- **Static recompilation.** Needs a known memory map to know which accesses are
  MMIO, and buys speed that a 1996 68020 does not need. Revisit only if a
  standalone binary becomes the goal.
- **Cycle accuracy.** Nothing so far depends on it.
- **Emulating the TMS340 for real.** The strategy is to intercept the display
  list, not to reimplement the silicon. Worth reconsidering only if the command
  protocol turns out to be unreadable from the 68020 side — so far it has been
  entirely readable.

## Out of scope

- Inter-centre modem linking (the `Dial_List` phone numbers).
- Mission Review (BTMR / RPMR).
- Redistributing any VWE material, in any form.

## Before this repo goes public

In addition to the checklist in the repo rules:

- [ ] **Decide on `DEVICES.md`.** The repo rules ban committing "generated
      headers, symbol maps, or struct definitions reconstructed from
      proprietary binaries" and "disassembly listings". `DEVICES.md` is
      hand-written device documentation, which is how every emulator project
      works — but it quotes a handful of short disassembled sequences as
      evidence for the TMS340 identification and the command protocol. That is
      fine in a private repo and is a deliberate call to make before going
      public, not one to discover afterwards.
- [ ] Email PropWash at Virtual World Entertainment first. Not legally
      required, costs nothing, and a hostile rightsholder is the only thing
      that can kill this. The preservation project asked for this tool.
- [ ] Lead with Red Planet rather than BattleTech where a choice exists — same
      engine, same hardware, no third-party trademarks attached.
