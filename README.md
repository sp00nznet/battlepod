# battlepod

A bring-up harness for the Virtual World Entertainment BattleTech cockpit — the
arcade pods that ran in BattleTech Centers from 1990 to the late nineties. It
loads the pod's own software exactly the way the arcade's operator console did,
runs the cockpit's 68020, and reports what the hardware underneath was asked to
do.

There is no schematic for this board, and no emulator for it. This is how you
find out what it was.

## Status

**v0.1.0 — alpha, a research tool, not a game.** Geometry out of the archive
renders; the cockpit itself does not. Conformance: **38/38** checkpoints.

The cockpit boots from its own image set to `main game loop (SecCom 674 bytes).`
with three boards stubbed. Along the way it parses its resource archive and
prints the index — 418 resources whose format is now decoded, including 130 3D
models with verified bounding volumes. The graphics processor
has been identified and its command protocol decoded, and the firmware's own
diagnostic monitor can be driven interactively over the modelled serial port —
far enough to make the cockpit's lamps, bar graphs and alphanumeric displays
emit real Remote I/O packets, checksums and all. See
[DEVICES.md](DEVICES.md) for the map, [RENDERING.md](RENDERING.md) for what it
would take to reproduce all four of a cockpit's surfaces, and
[ROADMAP.md](ROADMAP.md) for what's next.

It does not contain, and will never contain, any VWE code or data. You supply
your own copy.

## The machine

A BattleTech Center was organised in **sides** of eight cockpits. Each side had
its own network and its own operator.

```
                         Ethernet / EtherTalk
   Operations Macs ─── Mission Review ─── OpsCon Mac
                                              │  A/ROSE ARCNET NuBus card
                                              │
                                     ARCNET (RG62 coax, star hub)
          ┌──────────┬──────────┬─────────────┴────┬──────────────┐
      cockpit 1  cockpit 2  cockpit 3    ...   cockpit 8     camera ship
```

The Macintosh side is **not** where the game lives. OpsCon is a file server with
a launch button: the operator picks a scenario and a team list, and OpsCon
pushes a set of binaries down the ARCNET into each cockpit's memory, then tells
it to jump. Everything after that happens inside the pod.

### Inside one cockpit

The card cage holds four boards on a backplane:

```
  ┌──────────────────────────────────────────────────────────────┐
  │ CPU board   68020 + 68881                                    │
  │             game simulation, display lists, ARCNET           │──▶ main screen
  │                                                              │
  │   0x20000000  ──▶  TMS34020 renderer   (rasterises)          │
  │                      └─▶ TMS34082 FPU (3D maths)            │
  │   0x40000000  ──▶  "Secondary": an Amiga 500  ───────────────│──▶ MFD screen
  │   0x50000000  ──▶  audio board                               │──▶ speakers
  │   serial      ──▶  Remote I/O board                          │◀── stick, throttle,
  │                    (lamps, bargraphs, heat scale, LCDs)      │    pedals, keypad
  └──────────────────────────────────────────────────────────────┘
```

The two surprises, if you have only read the marketing:

- The **"Amiga board" is a literal Amiga 500 motherboard** on a VWE carrier
  card. It does not run the game — it draws the cockpit's secondary
  multi-function display. Its code is 61 KB compiled with Manx Aztec C.
- The **renderer is a Texas Instruments TMS34020 graphics processor with a
  TMS34082 floating-point coprocessor**, and its entire bit-addressed address
  space is mapped into the 68020 at `0x20000000`. The 68020 uploads the
  renderer's microcode at boot, byte-reversing every longword on the way
  because the TMS340 is little-endian and the 68020 is not. The '20 rasterises;
  the '82 does the 3D arithmetic, driven over the coprocessor bus by 419
  `CEXEC`/`CMOV*` instructions in R.BIN. See DEVICES.md for how the part was
  identified from the instruction stream.

### What gets loaded where

`Full_Load_3_0` — a nine-line text file in the release — is the whole boot
recipe:

| image | loads at | what it is |
|---|---|---|
| `ROM3_0` | `0x020FFFE4` | the game: 68020 code, 534 KB |
| `BattleTech_68020_Res` | `0x02AC0000` | 68020-side resources |
| `R.BIN3_0` | `0x02AE0000` | TMS340 microcode |
| `BattleTech_TI_Res` | `0x02B00000` | geometry and renderer resources, 1.5 MB |
| `btAudio.dld` | `0x02D00000` | audio download image |
| `AMIGA3_0` | `0x400003E4` | Amiga 500 MFD program |
| `btsecond3_0` | `0x40010400` | Amiga 500 data |
| `DEVELOPMENT` | `0x02FFFF00` | an 11-byte marker enabling developer mode |
| `Go_Address` | `0x02100000` | entry point |

### What the cockpit does at boot

1. Clear bss, bring up the serial console, print `BTS2--Up`.
2. Probe the audio board; report if it doesn't answer.
3. Upload `R.BIN` into the TMS340's memory, reset it, and wait for it to write
   **`0x31415926`** — π — into a shared word. That is the renderer saying hello.
4. Ask the renderer to allocate memory, load the resource map, and free the
   scratch. Commands go through a queue in the renderer's memory; replies come
   back through the same buffer.
5. Wait for the Amiga 500 to write `0x01234567`, answer with `0x76543210`, and
   agree on a 674-byte shared communication block.
6. Push all 989 KB of `btAudio.dld` through a 32-entry ring FIFO to the audio
   board.
7. Enter the main game loop, and poll the boot monitor for an incoming packet
   until the operator console sends one.

`battlepod` replaces step 0 — the ARCNET download — by placing the same files at
the same addresses, runs the 68020 with [Musashi](https://github.com/kstenerud/Musashi),
and either logs or stands in for everything the CPU board talks to.

## Getting Started

From a clean machine.

**Prerequisites**

- A C compiler (GCC 9+ or Clang 10+; on Windows, MSYS2 mingw-w64 works)
- `make`, `git`, Python 3.8+ (for `tools/`)
- [The Unarchiver CLI](https://theunarchiver.com/command-line) (`unar`), to
  unpack the release — it is a StuffIt archive with Macintosh resource forks

**1. Get the release.** `battlepod` ships no game data. Download
*VWE Release 13.1.8* from the Internet Archive:
<https://archive.org/details/vwe-release-13.1.8>

**2. Extract it.** Use a short destination path — the archive nests deeply
enough to hit Windows' 260-character path limit.

```
unar -k visible -o /path/to/vwe "VWE Release 13.1.8.sit"
```

Both `.sit` files in that item contain the same 85 entries; one is a StuffIt 4.5
re-stuff for compatibility. Either will do.

**3. Build.**

```
git clone <this repo> battlepod && cd battlepod
make deps      # clones Musashi into third_party/
make
make test      # -> selftest OK (cpu runs, unmapped writes logged, pc tracked)
```

**4. Boot a cockpit.**

```
GF="/path/to/vwe/.../VWE Release 13.1.8/VWE Center Kit/Mac Files/2.5-3.0 Related Files/VWE Release 13.1.8/BattleTech 13.1.8/Console Files/Game Files"

./build/battlepod.exe "$GF/Full_Load_3_0" \
    --tty 11016 --rstub 3FF00000 --poke 50001000=55000000 --set 40000100=1234567
```

Expected output, in the `console output` block:

```
BTS2--Up
Audio subsystem is NOT properly downloaded!
...
TI Reset Sent
TI Reset Complete
Allocating 2000 RAM for resource map
Allocate handle 1, addr 10000000, error 0
Building resource map

Res Type 1 header found
11 12 13 14 15 16 17 18 19 22 24 27 30 31 32 ...
...
Giving load resource map command, size 1268
Load Resource Map, error 0
Freeing resource map RAM
Free, error 0

 main game loop (SecCom 674 bytes).
```

That text is the cockpit's own firmware narrating itself over its serial
console. Every line of it comes out of the pod, not out of this tool.

**5. Talk to it.** `ROM3_0` carries a complete diagnostic monitor, reached once
the game initialisation returns. Patch an `RTS` over that call to land in it
directly, and type at it:

```
./build/battlepod.exe "$GF/Full_Load_3_0"     --duart 11000 --set 2138A64=4E754E75 --duart-in 's
3
'
```

```
BattleTech 2 Test Program

a - Zero Real Time Clock
...
s - Test remote I/O devices
y - START TEST GAME (starts Secondary, TI and 68020 in tandem
z - Quit

s   s  ok!
1 - Display command
2 - Bar Graph command
3 - Lamp command
3Lamp number in hex (00 - 3b, 50 - 53 and 60)
```

The valid ranges in those prompts are the cockpit's device map, given up by the
firmware itself. Answer them and the packet reaches the wire:

```
remote i/o: 8 bytes sent on duart channel A
  0000  01 00 03 03 D3 05 01 D9
```

`01` start, node `00`, length `03`, header checksum `03`, then the payload
`D3 05 01` — lamp 5 at brightness 1 — and its checksum `D9`. The frames are
decoded back into cockpit panel state:

```
remote i/o: 1 frames decoded
  lamp 05 brightness 01
```

which is what a panel renderer consumes. See [RENDERING.md](RENDERING.md).

## Usage

Run with no arguments for the full option list. The ones that matter:

| flag | what it does |
|---|---|
| `--duart BASE` | model the MC68681 DUART at `BASE`; channel B is the console, captured and fed |
| `--duart-in TEXT` | type `TEXT` at the console receiver (`
`, `
` work) |
| `--rstub ADDR` | stub the TMS340 renderer: comm block at `ADDR`, acknowledge every command, log the queue, serve allocations |
| `--poke ADDR=HEX` | unmapped reads at `ADDR` return `HEX` |
| `--set ADDR=HEX` | write a longword into RAM after loading, for answers a device would have left there |
| `--tick ADDR` | unmapped long reads at `ADDR` return a rising counter — walks past a poll-until-it-changes handshake |
| `--clock ADDR[:N]` | free-running counter at `ADDR`, one tick per `N` instructions — the firmware's timebase, which its boot monitor maintained |
| `--vbr ADDR` | vector base register (default `02000000`, where the pod's monitor left it) |
| `--irq-level N` | interrupt level the DUART asserts |
| `--monitor [ADDR]` | install a stub boot-monitor service table (default `02000400`) and report which slots get called |
| `--packet HEX` | hand the firmware one received packet (body bytes, first is the opcode) |
| `--ram BASE:LEN` | declare a RAM region (hex); repeatable |
| `--trace N` | disassemble the first `N` instructions, marking unmapped accesses inline |
| `--dis ADDR[:N]` | disassemble `N` instructions at `ADDR` and exit |
| `--watch BASE:LEN` | also log accesses inside a mapped region, so a loaded resource shows which offsets get read and from where |
| `--csv FILE` | write the full unmapped-access table |
| `--cpu TYPE` | `68020` / `68030` / `68040` |

Everything outside declared RAM is logged: address, width, read and write
counts, the PC that first touched it, and the last value written. That log is
how the device map in [DEVICES.md](DEVICES.md) was built.

**Disassemble the TMS340 renderer:**

```
python tools/tms340dis.py "$GF/Cockpit Software/R.BIN3_0" --skip 8 --base 0xFE000000
python tools/tms340dis.py "$GF/Cockpit Software/R.BIN3_0" --skip 8 --base 0xFE000000     --count 20000 --validate
```

98% of the code segment is recognised, and 963 of 971 call and branch targets
land inside the image, which is the check that it is in sync rather than
confidently wrong. `--segments` shows the scatter-load layout; `--code`
disassembles only the segment that holds code.

**Walk the resource archive:**

```
python tools/resmap.py "$GF/Cockpit Software/battletech_ti_res"
python tools/resmap.py "$GF/Cockpit Software/battletech_ti_res" --dump 11
```

**Read a 3D model.** A type 1 resource is not a mesh, it is a threaded program
of 45 opcodes; `model.py` runs it and collects the vertices, polygons and
materials it draws:

```
python tools/model.py "$GF/Cockpit Software/battletech_ti_res" --stats
python tools/model.py "$GF/Cockpit Software/battletech_ti_res" --id 24
python tools/model.py "$GF/Cockpit Software/battletech_ti_res" --id 24 --obj out/m24.obj
```

`--stats` runs all 130 and reports the checks the data itself provides — every
model carries a bounding box its vertices have to reproduce, which is what
makes a wrong decode fail loudly instead of quietly.

**Draw one:**

```
python tools/render.py "$GF/Cockpit Software/battletech_ti_res" --id 30 --out out/mesa.png
```

Z-buffered flat-shaded triangles at the pod's own 480x360, written as a PNG
with nothing but the standard library. Model 30 comes out as one of the terrain
mesas that stand behind the mechs in the period footage. See
[RENDERING.md](RENDERING.md) for what the pod looked like and why flat shading
is the right target.

**Extract Macintosh resources** (the operator console's code lives in them):

```
python tools/macres.py "$GF/../Console 1.5.12.a01.rsrc" CODE
python tools/macres.py "$GF/../Console 1.5.12.a01.rsrc" CODE 1 out/code1.bin
```

**Recover the network protocol from an operator console log:**

```
python tools/logproto.py "$GF/../Console Log"            # message vocabulary
python tools/logproto.py "$GF/../Console Log" --sequence # one game start, in order
```

The console logged every message it exchanged with the pods by name. A
surviving log is a protocol specification written by the software itself.

**Find the code behind any console message:**

```
python tools/xref.py "$GF/Cockpit Software/ROM3_0" 020FFFE4 "TI Reset Complete"
#   TI Reset Complete    file 04CC59  addr 0214CC3D
#       0214CB04  pea (d16,PC)
./build/battlepod.exe "$GF/Full_Load_3_0" --dis 214CB04:20
```

The firmware is unusually talkative, so this is the fastest route into any
driver in it.

**Conformance:**

```
make conformance VWE_GAME_FILES="$GF"
```

Replays the boot and checks it still reaches every milestone it reached before,
reporting a pass count (currently 38/38). Skips with a clear message if no
release is present, since the corpus cannot be redistributed.

### A note on the CPU profile

The board is a 68020 with a 68881 FPU. Musashi only enables its FPU on the
68040 profile, so that is the default here and the tool says so on every run.
`--cpu 68020` is available and will take an F-line exception the moment the
firmware uses floating point.

## Building from source

```
make deps      # fetch Musashi
make           # build/battlepod.exe
make test      # self-check
make clean
```

No dependencies beyond a C compiler and Musashi, which is MIT-licensed and
fetched rather than vendored.

## Prior art

[WarlockD/Battletech-VME-3.0-Decompile](https://github.com/WarlockD/Battletech-VME-3.0-Decompile)
(June 2024) is the only other public work on this hardware. Despite the name it
contains no decompilation — it is a research dossier: the release itself,
board photographs, and the datasheets for the parts its author identified,
with notes inviting someone to take a serious crack at it.

Those notes are worth reading before this one. They independently reach the
same load map, and the uncertainty they leave open about the renderer
("TMS34010, maybe an 020, not sure yet") is now settled — it is an 020. They
also name two parts this project had not yet
identified: the sound board's **Analog Devices ADSP-21020** DSP — which is why
`btAudio.dld` is a `.dld`, the Analog Devices downloadable-executable extension
— and the **SMC COM90C66** ARCNET controller. The System 3.0 manual confirms
the sound board carries "several Analog Devices ADSP's" with sample memory in
DRAM.

Nothing is copied from that repository into this one. It is GPL-3.0 and it
distributes the VWE material directly; this project is MIT and distributes
none. Part numbers are facts, and are credited above.

## Provenance

The software this tool reads was published by the Battletech Pod Preservation
Project at <https://archive.org/details/vwe-release-13.1.8>, with a stated hope
that someone would build exactly this. Copyright in it belongs to Virtual World
Entertainment LLC, which is still operating; BattleTech and MechWarrior are
trademarks of The Topps Company and Microsoft, licensed to VWE. This project is
not affiliated with any of them.

No VWE material is in this repository — no images, no resources, no extracted
assets, no disassembly of theirs. The tool ships; the data does not. You supply
your own copy of the release, and everything the tool generates lands in
`out/`, which is gitignored.

## License

MIT — see [LICENSE](LICENSE). Applies to this tool only.
