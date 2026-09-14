# VWE System 3.0 cockpit CPU board — observed device map

Everything here was observed by running the pod's own image set under
`battlepod` and watching the bus, plus reading the 68k side of each driver. No
schematic for this board is known to survive; this is the substitute.

Written by hand from bus traces, the ROM's own console output, and
disassembly. It contains no VWE code or data.

Current state: the cockpit boots to **`main game loop (SecCom 674 bytes).`**
with the renderer, audio and Amiga boards stubbed.

```
make
./build/battlepod.exe "<release>/Console Files/Game Files/Full_Load_3_0" \
    --tty 11016 --rstub 3FF00000 --poke 50001000=55000000 --set 40000100=1234567
```

---

## Image format

Every downloadable image carries a 28-byte header:

| offset | size | meaning |
|---|---|---|
| 0x00 | u16 | `0x601A` — also a valid `BRA.S +0x1A` to the entry stub at 0x1C |
| 0x02 | u32 | text size |
| 0x06 | u32 | data size |
| 0x0A | u32 | bss size |
| 0x0E | 14 | not yet identified |
| 0x1C | — | entry stub, normally `JMP abs.l` |

Confirmed: `text + data + 28 == filesize` for every headered image in 13.1.8,
and the C runtime's first act is to clear exactly `[load + 28 + text + data,
+ bss)` — `ROM3_0` clears `0x02182754..0x023ED7FE`, that range to the byte.

`Full_Load_3_0` names the load addresses; `Go_Address` is the entry. Images
without the header (`*_res`, `*.dld`, `R.BIN*`, `DEVELOPMENT`) are plain data.

## Address map

| range | width | what it is |
|---|---|---|
| `0x00010007–0x00010015` | byte, odd, stride 4 | two interleaved 8-bit parts, probed at init; unidentified |
| `0x00011000–0x0001101C` | byte, even, stride 2 | serial console UART |
| `0x02000000–0x02FFFFFF` | — | CPU board DRAM: game image, resources, heap, stack |
| `0x20000000–0x3FFFFFFF` | long | TMS340 renderer memory window |
| `0x38000022` | word | one write of `0x7FFF` then read back during renderer setup; unidentified |
| `0x3FFFFFB8` | long | renderer comm block pointer (TI byte address) |
| `0x3FFFFFBC` | long | renderer ready / command-done word |
| `0x40000000–…` | — | "Secondary" board: an Amiga 500 driving the MFD screen |
| `0x50000000–…` | long | audio board |

`DEVELOPMENT` lands at `0x02FFFF00` — an 11-byte marker string in DRAM.

### Serial console

| address | direction | role |
|---|---|---|
| `0x00011012` | read | status; polled before each character |
| `0x00011016` | write | transmit data |
| `0x00011000`, `02`, `04`, `08`, `0A`, `10`, `14`, `18`, `1C` | write | init, written once at reset |

Capturing writes to `0x00011016` is enough to read everything the ROM prints;
open bus reads as all-ones and the ROM takes that as "ready". The receive path
has not been identified yet — that is what stands between us and the
diagnostic menu the ROM contains.

### The renderer is a TMS340x0

The ROM logs its own upload of `R.BIN3_0` and names both address spaces:

```
68K src 2ae0008, 68k dest 3fc00000, TI fe000000, Count 5116
68K src 2ae649c, 68k dest 3fffe000, TI ffff0000, Count 616
68K src 2ae6e44, 68k dest 3fffff78, TI fffffbc0, Count 34
```

Three facts, all verified:

1. **`TI_address = (68k_address - 0x20000000) * 8`**, exactly, for all five
   uploaded segments. Renderer addresses are *bit* addresses — the signature of
   the TI TMS34010 / TMS34020. Its 512 MB bit-addressed space is mapped
   linearly into the 68020 at `0x20000000`. The ROM performs the inverse itself
   with a literal `addi.l #$20000000` after reading the comm block pointer.

2. The copy **reverses byte order within each longword**: all 5116 longwords
   written to `0x3FC00000` match `R.BIN3_0` read little-endian from file offset
   8. Big-endian 68k feeding a little-endian TMS340.

3. `R.BIN3_0` decodes as TMS340 code. Its entry reads:

   ```
   0360              DINT
   0780 FDE0 FFFF    MOVE  A0, @0xFFFFFDE0     ; the handshake word
   09EF 4DC0 FE03    MOVI  #0xFE034DC0, A15    ; stack pointer, inside the upload
   09C0 0001         MOVI  #1, A0
   0780 FDE0 FFFF    MOVE  A0, @0xFFFFFDE0     ; state = 1
   09C0 0002 ...                               ; state = 2
   0D5F 0780 FE00    CALLA 0xFE000780
   ```

   `0xFFFFFDE0` is the bit address of `0x3FFFFFBC`, and `0xFE034DC0` lands
   inside the uploaded region. 34010 vs 34020 is still open.

### Renderer handshake and command protocol

Fully decoded from `0x0214CC50`:

```
post_command():
  wait until [0x3FFFFFBC] == 0x31415926      ; renderer alive (pi)
  wait until [commblock+4] == 0              ; previous command complete
  *cursor++ = 0xFFFFFFFF                     ; terminate the staging buffer
  len = cursor - 0x023A9EEE                  ; staging buffer, in 68k RAM
  memcpy(commblock+8, 0x023A9EEE, len)       ; request into the queue
  [commblock+4] = 1                          ; post
  wait until [commblock+4] == 0              ; renderer done
  memcpy(0x023AA2F2, commblock+8, len)       ; reply back out
```

`commblock` comes from `[0x3FFFFFB8] + 0x20000000`. The request and the reply
share one buffer.

Request layout: `[+0]` opcode, `[+4]` argument, terminator `0xFFFFFFFF`.
Reply layout: `[+8]` error, `[+0xC]` handle, `[+0x10]` address — that order,
read straight off the ROM's unpacking of the reply.

| opcode | meaning |
|---|---|
| 1 | reset — "TI Reset Sent" / "TI Reset Complete" |
| 2 | allocate, size at `[+4]` |
| 3 | free, handle at `[+4]` |
| 5 | load resource map, address at `[+4]` |

Observed boot sequence:

```
cmd 1  op=1                          TI reset
cmd 2  op=2  size 0x7D0   (2000)     resource map scratch
cmd 3  op=5  addr 0x10000000         load resource map, size 1268
cmd 4  op=3  handle 1                free it
cmd 5  op=2  size 0x2328   (9000)
```

A bump allocator handing back addresses in mapped TI memory is enough to get
the resource loader running.

### Resource archive

With the allocator answering, the ROM parses the resource files and prints its
own index — four type classes and several hundred numbered resources:

| type | count | ids |
|---|---|---|
| 1 | 130 | 11–19, 22, 24, 27, 30–51, 57–69, 80–85, 100–119, 131–159, 451–517 |
| 4 | 191 | 70–96, 121–130, 201–260, 321–380 |
| 2 | 6 | 90, 94, 134–137 |
| 7 | 140 | 180–200, 261–320, 381–440 |

Then: `Giving load resource map command, size 1268` / `Load Resource Map,
error 0`. Decoding what each type holds is the next real prize — `battletech_ti_res`
is 1.5 MB with big-endian IEEE floats from offset 0x30, so geometry is in there.

### Secondary (Amiga 500) handshake

From `0x0214DA2A`, in the clear:

```
wait until [0x40000100] == 0x01234567     ; Secondary ready
[0x40000108] = 0x400
[0x40000104] = 0x76543210                 ; 68020 acknowledges
```

Board-local offsets 0x100/0x104/0x108. The ROM later reports
`main game loop (SecCom 674 bytes).` — a 674-byte communication block shared
with the Amiga.

### Audio board

Base `0x50001000`, cached by the ROM at `[0x0217A0AC]`.

| offset | role |
|---|---|
| `+0x00` | signature; the ROM requires the top byte to be `0x55`, else "Audio subsystem is NOT active!" |
| `+0x04` | head index, byte offset, advanced by the 68020 |
| `+0x08` | tail index, advanced by the audio board |
| `+0x0C..+0x8B` | 32-longword ring buffer |

Producer side (`0x02149190`): `next = (head + 4) & 0x7C`; spin while
`next == tail`; store at `base + 0xC + ((head>>2) & 0x1F) * 4`. The 68020 pushes
all 247,254 longwords of `btAudio.dld` through this FIFO — and `btAudio.dld`
itself is a record stream tagged `A5A5`, which is what shows up on the bus.

With only the signature answered the ROM gets further and reports
"Audio subsystem is NOT properly downloaded!" — it checks the download too.

## Open questions

- Which parts sit at `0x00010007..0x00010015`, and what is `0x38000022`?
- The UART receive register — needed to drive the ROM's built-in diagnostic
  menu, which can start the renderer, the Secondary and a test game on demand.
- Resource type semantics (1, 2, 4, 7).
- 34010 or 34020.
- ARCNET has still not been touched; the boot reaches the main loop without it.
- After the audio download the ROM jumps through a null pointer. Expected while
  three boards are stubs, but worth revisiting once any of them is real.
