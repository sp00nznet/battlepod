# Roadmap

Background and the original field notes are in [PLAN.md](PLAN.md); the hardware
findings are in [DEVICES.md](DEVICES.md).

## Done

**Phase 0 — ground truth.** Load-script parser, image header decode, Musashi
68020 core, sparse memory with a bus logger. Produced the cockpit's address map
by observation.

**Phase 1 — boot.** Identified the renderer as a TMS340x0 and decoded its
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

## Next

**Start a game over the network.** Packets can be handed to the firmware and it
consumes them, the opcode dispatch is mapped, and the message vocabulary and
game-start order are now known from the operator console log. What is missing is
the byte encoding of each message.

Two ways to get it, and they check each other:

- Read the pod's handlers for the low opcodes, which is where the game messages
  land.
- Read the sender. `Console 1.5.12.a01` is a 68k Macintosh application in the
  release - 20 `CODE` resources, about 228 KB, built with THINK C - and it is
  the authority on what the console puts on the wire. The same disassembler
  already works on 68k code; what is needed is extracting and relocating `CODE`
  resources out of the resource fork.

**The geometry is nearby.** The renderer code carries `Out of Solids...`,
`Weird solid direction %f... shape %d`, `Suspect ARES data... shape %d` and
`Suspect cylinder data... shape %d` - so solids, cylinders and "ARES" are the
display list's primitive types. That is a thread straight into the resource
archive.

**Resource archive.** Four type classes, 467 resources, index already printed
by the firmware. `BattleTech_TI_Res` is 1.5 MB with big-endian IEEE floats from
offset 0x30, so the geometry is in there. Decoding the container is what makes
a first screenshot possible.

**Display list capture.** The firmware calls it a Dlist and has overflow errors
named for it. Intercepting it is the point at which this stops being a probe
and starts being a renderer.

## Later

- Draw the display list with a modern renderer.
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
