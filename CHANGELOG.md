# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
