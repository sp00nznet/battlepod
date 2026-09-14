# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `--duart` models the cockpit's MC68681 DUART, both channels, including the
  receive path — so the firmware can be typed at, not just listened to.
- `--duart-in` types at the console receiver.
- Channel A transmits are captured and hex-dumped as the Remote I/O protocol.
- Conformance now also drives the firmware's diagnostic monitor: 20 checkpoints.

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
- RIO packets are framed `01 <node> <len> <csum> <payload> <csum>`; a lamp
  payload is `D3 <lamp> <brightness>`. Transmission is interrupt-driven and
  queues in RAM, so nothing reaches the wire until interrupts are modelled.

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
