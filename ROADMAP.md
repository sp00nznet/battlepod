# Roadmap

Background and the original field notes are in [PLAN.md](docs/PLAN.md); the hardware
findings are in [DEVICES.md](docs/DEVICES.md).

Open questions are tracked in [docs/UNRESOLVED.md](docs/UNRESOLVED.md), split
into what is assumed, what is measured and unexplained, and what is papered
over. Wrong turns and their disproofs are in
[docs/FALSE-TRAILS.md](docs/FALSE-TRAILS.md).

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

**Phase 8 — the protocol, both ends.** The game's message table is a 71-entry
jump on packet byte 0; the senders are 45 call sites that each write their own
opcode. 38 opcodes sent, 46 handled, and where a message is both sent and
received the two ends agree on 44 field pairs and disagree on none.

**Phase 9 — the entity system.** A thousand-slot arena built on every boot, a
thirty-slot table of participants, nineteen classes with six of them named from
the ROM, and seven class-dispatched operations. A packet injected at the wire
moves real fields; `tools/entityfields.py` maps which, by difference, on the
running firmware. Eleven fields named, nine of them by the firmware's own
printf labels.

**Phase 10 — the pod reports on itself.** All four subsystem checks pass, the
audio board is modelled rather than poked, and setting one flag gets the
firmware's own frame-rate, culling, router and event statistics out of a booted
cockpit. That is the measurement to beat.

**Phase 11 — the pod draws, and a mission runs.** The renderer's
frame-complete interrupt is raised, frames flow, and the display list decodes:
a 480x360 viewport, a draw object whose transform is built from a position sent
over the wire, a `$2C0` camera item with a 60-degree field of view, and a
head-up display. Separately, a mission is started by sending `0xED` to a class
19 entity, and it runs.

**Phase 12 — missions are bytecode.** The pod carries a **162-opcode
interpreter** and thirteen named routines in its ROM - two BattleTech
scenarios, eight cameras, three displays. `tools/missions.py` lists them,
`tools/mission_dis.py` disassembles them against operand lengths measured from
each handler, and `--vmtrace` logs what a running mission actually executes.
The machine is a typed stack machine: 0x4C-byte operand frames carrying a type,
a locals frame, six value types, a typed load and store, and named control
flow. A world is populated by a program, instruction by instruction, and
`Create_Thing` has exactly one caller in the ROM - bytecode opcode `0x24`.

## Next

**The four draw opcodes.** `$200` puts down a single pixel at a vertex, `$220`
fills a rectangle between two, and `$280`/`$2A0` draw a sized marker — the
running lights and panel glow on a mech. All four are measured and gated on
visibility; none is interpreted, so `render.py` draws a model's polygons but
not its lights.

**The bounding-box gap**, which turned out not to be the thing this file
previously said it was. The claim here was that the failures all sit *inside*
the stated box, consistent with the box having been computed over a mesh that
was decimated before it reached the file. Measured across all 31 rather than
the handful that had been eyeballed, **27 of them poke outside it** — the
opposite. Rounding does not explain it either.

What does explain it is that the misses are *small*. Allowing any of the eight
reflections and measuring the error against the model's own size:

```
  exact                 89 of 120
  within 0.5% of span   91
  within 2% of span    105
  within 10% of span   117
```

Three models are worse than 10% and the worst is 50%. So the decode is right
and something quantises or nudges the extremes — a plausible last step in an
authoring tool, but not yet evidenced. `--stats` reports the 2% and 10% figures
alongside the strict one, and the harness guards the 2% number.

## Blocked, and on what

**A standing mech — done, and this section was wrong about why it could not
be.** The claim here was that the archive holds rigs and no poses at all.
`$040` turned out to carry three floats of offset, so a skeleton *is* a rest
pose; running the chain gives hips, torso and two jointed legs that land inside
the model's own stated bounding box. `render.py --mech` hangs the parts on it
by matching each part's box against the node offsets, and all six chassis
assemble to eight parts and draw.

What genuinely is not in the archive is where the **arms** go. `$480`'s tags
identify them — `516` is the right arm and weapon pod, `517` the left, five
alternative loadouts each — but hung on the shoulder nodes they reach well
outside the mech's own bounding box and run six units along z on a machine four
deep, which reads as an arm authored along an axis and rotated per frame. The
MadCat skeleton has no shoulder nodes at all, which it visibly needs, so at
least one mount is supplied rather than stored. Animation beyond the rest pose
is likewise per-frame from the 68020.

**Starting a game.** Still the oldest blocker, but no longer for the reason
this file used to give. It said the byte encoding of each message was unknown
and that the sender — the Macintosh console — was behind THINK C's
`CREL`/`DREL` relocations. **The encoding is mapped**, from the pod's own two
ends rather than from the console: 44 field pairs agreeing, the entity
structure behind them, and a way to measure any message's effect on the running
firmware.

The *sequence* is now known too, and it works: `0xE5` carries a game length,
`0xED` names a mission script and the class 19 entity to run it on, and
`--packet` takes them in order. The mission runs. Its spawn opcode runs.

**What is missing is smaller and stranger than it was.** In eight thousand
executed instructions a mission never runs `0x24`, the only instruction in the
machine that creates anything. It is not stuck - the opcode mix is wide and
changing - it is polling, and whatever it polls is false on a pod with one
entity, no players and nothing else on the wire. Settling that means naming
more of the 94 opcodes, and in particular what the typed loads in its loop are
reading.

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
- The Amiga 500 secondary display: either HLE the 1,652-byte SecCom protocol or
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
