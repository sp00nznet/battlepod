# VWE System 3.0 cockpit CPU board — observed device map

Everything here was observed by running the pod's own image set under
`battlepod` and watching the bus, plus reading the 68k side of each driver. No
schematic for this board is known to survive; this is the substitute.

Written by hand from bus traces, the ROM's own console output, and
disassembly. It contains no VWE code or data.

Current state: the cockpit boots to **`main game loop (SecCom 674 bytes).`**
with the renderer, audio and Amiga boards stubbed, and its built-in diagnostic
monitor can be driven interactively over the modelled serial port.

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
| `0x00010007–0x00010015` | byte, odd, stride 4 | two interleaved 8-bit parts, probed once at init; unidentified. Candidates on this board: the second serial port, a timer, or the COM90C66 ARCNET controller |
| `0x00011000–0x0001101C` | byte, even, stride 2 | serial console UART |
| `0x02000000–0x02FFFFFF` | — | CPU board DRAM: game image, resources, heap, stack |
| `0x20000000–0x3FFFFFFF` | long | TMS340 renderer memory window |
| `0x38000022` | word | one write of `0x7FFF` then read back during renderer setup; unidentified |
| `0x3FFFFFB8` | long | renderer comm block pointer (TI byte address) |
| `0x3FFFFFBC` | long | renderer ready / command-done word |
| `0x40000000–…` | — | "Secondary" board: an Amiga 500 driving the MFD screen |
| `0x50000000–…` | long | audio board |

`DEVELOPMENT` lands at `0x02FFFF00` — an 11-byte marker string in DRAM.

### Serial ports: an MC68681 DUART at 0x00011000

Register N at `0x11000 + N*2`, channel A on registers 0-7 and channel B on 8-15.
The init sequence the driver writes at `0x0215B4C0` is textbook 68681:

| register | address | written | meaning |
|---|---|---|---|
| IMR | `0x1100A` | `0x00` | interrupts masked |
| IVR | `0x11018` | `0x47` | interrupt vector 0x47 |
| CRA | `0x11004` | `0x10`, `0x05` | reset MR pointer, then RxEN+TxEN |
| MR1A/MR2A | `0x11000` | `0x93`, `0x07` | mode, written twice through the auto-incrementing pointer |
| CSRA | `0x11002` | `0xBB` | clock select A — 9600 baud both ways |
| CRB | `0x11014` | `0x10`, `0x05` | reset MR pointer, then RxEN+TxEN |
| MR1B/MR2B | `0x11010` | `0x13`, `0x07` | 8 bits, no parity, 1 stop |
| CSRB | `0x11012` | `0xCC` | clock select B — 19200 baud both ways |
| ACR | `0x11008` | `0x00` | baud rate set 1 |
| SET OP | `0x1101C` | `0x01` | assert an output pin |

Per channel: status at `+2`, receive and transmit share `+6`.

| channel | status | data | carries |
|---|---|---|---|
| A | `0x11002` | `0x11006` | the Remote I/O board, 9600 baud |
| B | `0x11012` | `0x11016` | the console, 19200 baud |

`getchar` for channel B, at `0x0215B55A`, is the whole receive path:

```
0215B55A  move.b  $11012.l, D0     ; SRB
          andi.b  #$1, D0          ; RxRDY
          beq     0215B55A         ; spin
          move.b  $11016.l, D0     ; RBB
          rts
```

Modelling status bit 0 (RxRDY) plus bit 2 (TxRDY) is enough to both read the
firmware's output and type back at it.

### The built-in diagnostic monitor

`ROM3_0` contains a complete serial monitor. It is *after* the game
initialisation in the boot function at `0x02123FC0`, so it appears only when
that returns; patching an `RTS` over the init call reaches it directly:

```
--duart 11000 --set 2138A64=4E754E75
```

The firmware then prints its menu and waits:

```
BattleTech 2 Test Program

a - Zero Real Time Clock              l - Test Alloc and free commands
b - Set Hour/Minute/Second/Hundreds   m - Test binary loader from A00000
c - Display Real Time Clock once      n - Start TI
d - Display Real Time Clock cont.     o - Set RIO to 115200 baud
e - Read from I/O board port A        p - Start Secondary
f - Read from console, send to port A q - Turn on all remote I/O displays and lights
g - Read/display RIO_A data           r - Display decoded remote I/O data
h - Send a string out RIO_A           s - Test remote I/O devices
i - RIO protocol loopback test        y - START TEST GAME (Secondary, TI and 68020)
j - RIO protocol buffer exercizer     z - Quit
k - Send reset to renderer
```

Commands that need subsystems the patched-out init would have set up will fall
over; the clock, and the Remote I/O submenus, work as they are.

### Remote I/O board

Menu item `q`, "turn on all remote I/O displays and lights", still emits nothing
even with interrupts and the monitor stubbed, while the individual device
commands under `s` all work. Unexplained.


`s` opens a submenu — Display, Bar Graph, Lamp — and each prompts with its own
valid range. That is the cockpit's device map, given up by the firmware:

| device | ids |
|---|---|
| lamps | `0x00`-`0x3B`, `0x50`-`0x53`, `0x60` (each takes a brightness) |
| displays | `0x80`-`0x91` |
| bar graphs | `0x80`-`0x91` except `0x8C`, `0x8D`, `0x8F` |

A lamp command is a three-byte payload built at `0x02143820`:

```
D3  <lamp>  <brightness>
```

`0xD3` is the lamp opcode. `0x02143852` loops it over lamps `0x00`-`0x53`,
which is menu item `q`.

Payloads are framed by `rio_send` at `0x0215B924`:

```
01  <node & 0x3F>  <len>  <checksum>  <payload...>  <checksum>
```

with the node byte from `[0x021822F8]` and a raw-passthrough mode selected by
`[0x0218230B]`.

`rio_send` only appends to a queue at `[0x021822FE]`; the DUART's transmit
interrupt drains it. With interrupts modelled, packets reach the wire:

| command | bytes on channel A |
|---|---|
| lamp `0x05`, brightness `0x01` | `01 00 03 03 D3 05 01 D9` |
| bar graph `0x80`, 5 bars | `01 00 03 03 D2 80 05 57` |
| display `0x80`, `"BATTLTEC"` | `01 00 0A 0A D1 80 42 41 54 54 4C 54 45 43 A4` |

Both checksums verify in every case: the header one is `node + len`, the
trailing one is the sum of the payload alone (`D2` is cleared between them).

| opcode | device | payload after the opcode |
|---|---|---|
| `0xD1` | display | id, then 8 ASCII characters |
| `0xD2` | bar graph | id, then the number of bars to light |
| `0xD3` | lamp | id, then brightness |
| `0xD5` | — | none. Sent once during boot: `01 00 01 01 D5 D5` |

## Interrupts

`ROM3_0` contains no `MOVEC` to VBR, yet `0x0215B9C2` — the first thing the
boot function calls — writes vectors to absolute addresses:

```
move.l #$214c708, $2000108.l     ; vector 66
move.l #$215b69a, $200011c.l     ; vector 71 = 0x47, the DUART
move.l #$215b69a, $20003fc.l     ; vector 255
```

So **VBR is `0x02000000`**, the CPU board's RAM base, left there by the pod's
boot monitor. The DUART's own interrupt vector register is programmed to
`0x47`, which is vector 71 — exactly the slot the firmware fills.

The handler at `0x0215B6A4` is short:

```
movem.l D0/A0, -(A7)
move.b  $1100a.l, D0     ; ISR
btst    #$1, D0          ; RxRDY A  -> receive handler at 0215B6CC
btst    #$0, D0          ; TxRDY A  -> transmit handler at 0215B8D0
movem.l (A7)+, D0/A0
rte
```

`0x0215B5B2` sets `IMR = 0x03` (channel A transmit and receive) and leaves the
channel A transmitter *disabled* with `CRA = 0x08`. Queueing a packet enables
it; the transmit handler disables it again when the queue drains, which is what
stops the interrupt re-asserting. Modelling TxRDY as simply "the transmitter is
enabled" reproduces that exactly.

## The timebase lives outside the dump

`0x02000808` — just past the vector table — is read in **336 places in
`ROM3_0` and written in none**. It is a free-running counter the boot monitor
maintained, and it is the firmware's universal timebase. Without one, every
timeout in the game waits forever, so the harness supplies it.

## The boot monitor's service table

The pod's boot ROM is not in the release, but the firmware calls into it. Six
thunks at `0x0212C72C` all dispatch the same way:

```
movea.l $216fae2.l, A6        ; monitor globals, statically 0x02000800
movea.l $216fade.l, A0        ; monitor service table, statically 0x02000400
movea.l ($18,A0), A1          ; pick a slot
jsr     (A1)
```

Both pointers are initialised data in the image, and they land immediately
above the vector table at VBR — `0x02000000` vectors, `0x02000400` services,
`0x02000800` globals with the timebase at `+8`. That is the monitor's API.

| slot | called from | arguments | returns |
|---|---|---|---|
| `+0x10` | `0x0210E1AC` | pointer, long — `(0x0219E0AC, 0x7D00)` | — |
| `+0x14` | `0x0210E19C` | pointer, long — `(0x021963AC, 0x7D00)` | — |
| `+0x18` | `0x02122E96` | none | pointer, or NULL |
| `+0x1C` | 4 sites | none | — |
| `+0x20` | unused | word | word |
| `+0x24` | `0x02146A76`, `0x02146D38` | word, word, pointer | word status |

`+0x10` and `+0x14` are called back to back with two contiguous 32000-byte
buffers, `+0x24` takes what reads as (node, length, buffer) and returns a
status, and `+0x18` polls for a pointer that may be NULL. That is the shape of
a packet interface, and ARCNET is the only network the cockpit has.

Installing a table of stubs that answer "nothing, no error" is enough: the
firmware boots through it and settles into its main loop polling `+0x18`,
which is exactly what a cockpit does while it waits for the operator console to
send it a game. Reaching that point is where the boot currently ends — not on a
fault, but on an empty network.

## The resource archive

`tools/resmap.py` walks it. The layout is taken from the firmware's own parser
at `0x0214D0AC`, not guessed: a flat sequence of 16-byte headers, each
optionally followed by its data, terminated by a header whose id is `-1`.

| offset | size | meaning |
|---|---|---|
| +0x00 | u32 | resource id — the numbers the firmware prints |
| +0x04 | u32 | type class |
| +0x08 | u32 | flags; bit 4 of the low byte marks an **alias** |
| +0x0C | u32 | count, **or** the id this resource is an alias for |

When bit 4 is clear, `count * 4` bytes of data follow the header. When it is
set the resource has no data of its own and `+0x0C` names another resource
instead — which is why the parser stores that field either way but only
advances past data in the first case.

The walk accounts for every byte of `battletech_ti_res` (1,568,960 against a
1,568,948-byte file, the difference being the truncated terminator) and yields
ids that match the firmware's own printed listing **exactly, all 418, across all
four types**.

| type | count | bytes | what it is |
|---|---|---|---|
| 1 | 130 | 841,264 | **3D models** |
| 2 | 6 | 22,632 | bitmaps, stored compressed |
| 4 | 151 | 90,696 | **aliases** — named handles onto other resources |
| 7 | 131 | 607,664 | the bulk payloads the aliases point at |

**Type 1 is geometry**, and the header proves it. The seven floats at `+0x24`
are an axis-aligned bounding box followed by a bounding sphere radius:
`min <= max` holds on all three axes in **130 of 130** resources, and the
seventh float is less than or equal to the box-corner distance in **127 of
130** — equal exactly when a corner vertex exists, smaller when the geometry is
tighter than its box. That is a bounding sphere, not a coincidence.

**Type 4 is an alias table.** 136 of the 151 carry no data at all; every one of
those 136 resolves to a real resource, and 131 of them point at a type 7. The
ids give the game away — type 4 occupies 201–260 and 321–380, type 7 occupies
261–320 and 381–440, and alias id *X* points at id *X+60*.

**Type 7 is the payload.** High entropy (6.8 bits per byte against 3.8 for
geometry and 2.9 for type 2), large — one is 113 KB — and reached only through
its alias. Compressed or packed data; not floats, not opcodes.

**Type 2 is six bitmaps.** A constant tag `0x7F20`, a depth field of 8 or 24, a
width of 48, 64, 384 or 480, a small paired field, and a declared size that
works out to `width * 96 + 80` — a 96-row image. The stored data is far smaller
than that declared size, so it is compressed.

Cross-checking against `red_planet_ti_res` — a different game on the same engine
— confirms the format: 441 resources, the same four types, **128 type-4
resources all of them zero-length aliases, all 128 resolving to a type 7**, a
clean one-to-one table. Its type 2 set is the same six ids at the same sizes,
and ids 90 and 94 are byte-for-byte identical across both games, so those two
are engine data rather than game content.

### The 68020 never looks inside a model

`--watch` logs accesses inside a *mapped* region, which the unmapped log cannot
see. Pointed at the whole loaded archive across a complete boot, the answer is
unambiguous:

| offset read | times | reading PC |
|---|---|---|
| `+0x00` | 1672 | `0x0214D0F2` |
| `+0x0C` | 1118 | `0x0214D156`, `0x0214D1DE` |
| `+0x04` | 422 | `0x0214D172` |
| `+0x08` | 418 | `0x0214D13C` |
| `+0x0B` | 418 | `0x0214D122` |

Nothing at all past offset 16, on any resource, of any type — and every reading
PC sits inside the resource-map builder at `0x0214D0AC`. The 68020 walks the
headers to build its map and never reads a byte of the bodies.

So the type 1 model body is parsed by the TMS340 code in `R.BIN`, and no amount
of 68k disassembly will reach it. Reading it means reading TMS340 code — 28 KB
of it, and `tools/tms340dis.py` now does, partially.

The renderer kernel is **identical across both games**: `R.BIN3_0` and
`R.BIN2_5` are byte-for-byte the same in BattleTech and Red Planet. It is engine
code, not game content, which is a useful thing to know before spending effort
on it.

The entry decodes cleanly and agrees with the sequence worked out by hand
earlier:

```
FE000040  DINT
FE000050  CLR     A0
FE000060  MOVE    A0, @$FFFFFDA0
FE0000C0  DINT
FE000100  MOVE    A0, @$FFFFFDE0      ; the handshake word the 68020 polls
FE0001C0  MOVI    #$FE034DC0, SP      ; stack, inside the uploaded image
FE0001F0  MOVI    #$0001, A0
FE000210  MOVE    A0, @$FFFFFDE0      ; state = 1
FE000290  CALLA   $FE000780
FE0002C0  MOVI    #$0003, A0
FE000310  CALLA   $FE0016D0
```

Coverage, measured three ways because one number would mislead: **49% of all
words**, **70% ignoring zero fill** — the image holds data as well as code — and
**100% over the renderer's hardware init**. What makes any of it trustworthy is the
cross-check: **164 of 164 absolute call and jump targets land inside the image,
on all three renderer binaries.** A decoder that had lost sync would scatter
targets across a 512 MB address space and essentially none would fall inside a
28 KB window.

The graphics group is in — `PIXT` in all six addressing forms, the six
`PIXBLT` variants, `FILL L`/`FILL XY` and `LINE`.

The absolute-move group at `0x0400`–`0x07FF` used to be the largest gap, and
was for a while settled wrongly. The TMS34020 User's Guide (August 1990) gives
it as `0000 01F1 100R SSSS` for a store and `0000 01F1 101R DDDD` for a load,
with bit 9 choosing which of the two field-size registers applies:

| opcode | instruction |
|---|---|
| `0x0580` / `0x0780` | `MOVE Rs, @address` — store, field 0 / field 1 |
| `0x05A0` / `0x07A0` | `MOVE @address, Rd` — load, field 0 / field 1 |
| `0x05C0` / `0x07C0` | `MOVE @address, @address` |
| `0x05E0` / `0x07E0` | `MOVB` store / load |

Reading `0x05A0` and `0x07A0` as stores as well — which is what the firmware's
*writes* alone seemed to show — is what broke the display interrupt for two
sessions. Its handler read-modify-writes `INTPEND`:

```
FE000DF0  MMTM    SP, #$8000
FE000E10  MOVE    @$C0000120, A0, 0   ; INTPEND
FE000E40  ANDNI   #$00000400, A0      ; clear DIP, the display interrupt
FE000E70  MOVE    A0, @$C0000120, 0
FE000EA0  CLR     A0
FE000EB0  MOVB    A0, @$FE028020      ; the flag the main loop waits on
FE000EE0  MOVE    @$FFFF0BC0, A0, 1   ; a frame counter
FE000F10  INC     A0
FE000F20  MOVE    A0, @$FFFF0BC0, 1
FE000F50  MMFM    SP, #$0001
FE000F70  RETI
```

With a store where the load belongs, `INTPEND` never clears, `$FE028020` never
clears, and the renderer times out of its vertical-blank wait 500,000 times and
restarts hardware initialisation — which is exactly the symptom that had been
mistaken for a missing hardware poll.

One more thing that group taught: **`MMTM` and `MMFM` do not share a mask.**
`MMTM`'s bit 15 names A0; `MMFM`'s bit 0 does. Every matched pair in the image
is an exact bit reversal — `#$8000`/`#$0001`, `#$E000`/`#$0007`,
`#$B000`/`#$000D`, 25 pairs, no exceptions. Reading both the same way pops the
saved register into the stack pointer, which sends `RETI` to address zero.

### The renderer's side of the command protocol

Walking `R.BIN` from its entry reaches the renderer's main loop at
`0xFE006D80`, and it decodes with **no unknown words at all**. It is the
protocol already decoded from the 68020 side, seen from the other end:

```
FE006DD0  MOVE    *A1, A8, 1          ; A8 = the comm block
FE006E20  SRL     #3, A2              ; bit address to byte address
FE006E30  MOVE    A2, @$FFFFFDC0      ; publish it where the 68020 reads it
FE006ED0  MOVE    A0, *A8(32), 1      ; status word = 0   (block + 4 bytes)
FE006EF0  MOVI    #$31415926, A0
FE006F20  MOVE    A0, @$FFFFFDE0      ; say hello
wait:
FE006F90  MOVE    *A8(32), A0, 1      ; poll the status word
FE006FB0  JRNE    command
FE006FF0  JRUC    wait
command:
FE007000  ADDI    #$0040, A8          ; the queue is block + 8 bytes
FE007020  MOVE    *A8+, A0, 1         ; next command word
FE007040  JRN     done                ; 0xFFFFFFFF terminates
FE007050  DEC     A0
FE0070A0  SLL     #5, A0              ; index by opcode - 1
FE0070B0  ADDI    #$FE028460, A0      ; dispatch table
FE0070E0  MOVE    *A0, A0, 1
FE007100  CALL    A0
```

Every detail matches what was read off the 68020 months of guesswork ago: the
status word four bytes into the block, the queue eight bytes in, `0xFFFFFFFF`
as the terminator, and π as the ready signal.

**The dispatch table at `0xFE028460`** is indexed by `opcode - 1`, 32 bits per
entry, and holds handlers for opcodes 3 through 12:

| opcode | handler |
|---|---|
| 3 | `$FE0072A0` |
| 4 | `$FE0072D0` |
| 5 | `$FE0073F0` — load resource map |
| 6 | `$FE0074B0` |
| 7 | `$FE0075A0` |
| 8 | `$FE007630` |
| 9 | `$FE0076E0` |
| 10 | `$FE007780` |
| 11 | `$FE007880` |
| 12 | `$FE007980` |

Entries for opcodes 1 and 2 are null, so reset and allocate are handled before
the table is reached. Every handler decodes at 100%.

The table base and its indexing are confirmed independently: scanning the image
for words that *hold* handler addresses finds them at `0xFE0284A0`,
`0xFE0284C0` and `0xFE0284E0` — exactly `0xFE028460 + (opcode - 1) * 32` for
opcodes 3, 4 and 5, and nowhere else.

Two handlers are already legible. Opcode 4's is `JRUC $FE0072D0`, a branch to
itself — an unused slot that parks the processor. And `0xFE0072E0` is
`JRUC $FE000080`, a jump back into the entry sequence, which is the reset path.

What the rest of them *mean* needs the renderer's calling convention worked out
first: the handler for opcode 5 dereferences `A1` rather than reading its
argument from the queue, so a register is carrying state in from the caller.
That is the next thing to pin down, and it is what stands between here and the
model format.

### R.BIN is a scatter-load image

Not one flat block. It is a sequence of records — a big-endian target offset and
a longword count, then that much data — and the 68020 places each somewhere
different in the renderer's memory. Its own upload log says so plainly, and
parsing the file reproduces it exactly:

| TI address | longs | what it is |
|---|---|---|
| `$FE000000` | 5116 | the code |
| `$FE027F80` | 1314 | data |
| `$FE0455C0` | 1 | data |
| `$FFFF0000` | 616 | **the I/O register initialisation table** |
| `$FFFFFBC0` | 34 | the processor's trap vectors |

The records account for 28,364 of the file's 28,368 bytes; the remainder is the
`0xFFFFFFFF` terminator.

This matters twice over. The interpreter was loading the whole file flat at
`$FE000000`, so the last two segments were simply absent — which is why the
renderer's I/O setup loop, which walks a table at `$FFFF0000`, read zeroes and
spun forever writing to `$C0000000`. With the segments placed properly it
programs eight distinct video registers, as intended.

And the disassembler was treating all five segments as code at one base. Reading
only the code segment changes the picture: **72% of it was recognised** against
49% across the whole file, and only 177 words are zero fill rather than 3285.
Rebuilding the opcode tables from the TMS34020 manual took that to **95%**, with
963 of 971 call and branch targets landing inside the image.

### An address-frame correction

Every TI address this document quoted from the disassembler was **0x40 bits too
high**, and building an interpreter is what exposed it. The tool was measuring
from the start of the file, but the 8-byte header is not part of the image: the
68020's own upload log says `68K src 2ae0008 ... TI fe000000`, so file offset 8
is `0xFE000000`.

The proof is unambiguous. `CALLA $FE000780` used to land on `.word $FE00`, in
the middle of nothing; with the frame corrected it lands exactly on
`MOVI #$5007, A0`, the first instruction of the hardware-init routine. Both
tools now measure from file offset `skip`.

Addresses that came from *code operands* were never affected — they are
absolute and were always right — so the dispatch table at `0xFE028460` and the
resource offsets stand. What moved is the labelling of instruction addresses.

### The renderer's hardware init

The first thing the entry calls is the renderer bringing up its own silicon, and
it reads unambiguously:

```
FE0007C0  MOVI    #$5007, A0
FE0007E0  MOVB    A0, @$C0000080      ; TMS34020 I/O register block
FE000820  MOVB    A0, @$C0000120
FE000850  MOVB    A0, @$C0000110
FE000880  EINT
FE000890  CALLA   $FE001C50
FE0008C0  MOVI    #$A0000000, A0      ; frame buffer
FE0008F0  MOVI    #$00040000, A1      ; 0x40000 bits to clear
FE000920  CLR     A2
FE000930  MOVE    A2, *A0+, 1         ; clear it
```

`0xC0000000` is the TMS34020's documented on-chip I/O register block, and the
firmware writes three registers in it before enabling interrupts. That is a
semantic check on the disassembler, not just a structural one: the addresses it
produces land where the processor's own registers live.

The frame buffer is at bit address `0xA0000000` and the clear covers `0x40000`
bits — 32 KB, which at the pod's resolution is one screen.

One caveat: this boot never starts a game, so nothing is ever drawn. Whether the
68020 reads model bodies while rendering cannot be settled from a boot alone.
But it does not do so to load them.

### What is known about a type 1 model

Not much beyond the bounding volume, and it is worth being precise about why.

The nine longwords before the bounding box are not counts of fixed-size records.
A brute-force search over every pair of those fields, with integer strides up to
64 and a free constant, fails to explain the resource size for even half of the
130 models. So the body is variable-length — sections with their own internal
structure, not arrays of a fixed stride.

What the renderer does with a model is clearer. It maintains a pool of
**"solids"**: the allocator at `0x0214891E` caps the count at `0x5DC` (1500) and
bumps a pointer by `0x20`, so a solid is **32 bytes**. The initialiser at
`0x021488E8` fills one by copying six longwords from a source, then a word at
`+0x18`, a word at `+0x1A`, and clearing a long at `+0x1C`.

Three primitive kinds are validated on the way in — the firmware complains about
each by name:

```
Weird solid direction %f... shape %d      Suspect solid data... shape %d
Weird ARES direction %f... shape %d       Suspect ARES data... shape %d
                                          Suspect cylinder data... shape %d
```

So models are built from solids, cylinders and something called ARES, each
carrying a direction that gets sanity-checked. Solids are allocated from nine
sites across the firmware, not just the model loader, so they are a general
runtime structure rather than a file-format artifact.

### The 68020-side archive, and what it holds

Reading that loader answered a different question than expected. The shape
builder at `0x02148B18` starts by calling `0x02143502`, and that lookup does not
touch the TI archive at all — it searches **`battletech_68020_res`**, loaded at
`0x02AC0000`. So the two `_res` files are not two halves of one thing; they are
the renderer's data and the 68020's own.

Its layout, taken from that lookup:

```
u32  number of kinds
     u32 kind, u32 offset          (one pair per kind)
per kind, at its offset:
u32  number of records
     u32 id, u32 size, u32 offset, u32 0     (16 bytes, sorted, binary-searched)
```

The record chain verifies exactly: each offset is the previous offset plus its
size, and the last record ends on the final byte of the file.

**Kinds 0 and 1 hold shapes.** A shape is a `u32` count followed by that many
**26-byte elements — six floats and a word**, which is why `size == 4 + 26 *
count` holds for **228 of the 244 records** across both games' archives. The 16
exceptions are all kind 2, which is a different payload.

The shape builder reads one element at a time, copies its six longwords out,
scales the first float by a caller-supplied factor, and normalises an angle
argument into `[0, 360)` — `fcmp.d #$40768000` is a literal 360.0. Each element
becomes one entry in the renderer's solid pool.

**These shapes are keyed by the same ids as the visual models.** In Red Planet,
**64 of its 65 shape ids are also type 1 model ids** in `red_planet_ti_res`.
So the architecture is: the TI holds the visual geometry, and the 68020 keeps a
much coarser solid-and-cylinder version of the same object — 163 elements across
54 shapes in one kind, 90 across 57 in the other — for whatever it has to do in
software. A Mad Cat that takes hundreds of polygons to draw is a handful of
solids to collide with.

That also explains the primitive vocabulary. Solids, cylinders and ARES are not
how the pod draws; they are how it *reasons* about shape.

## The network packet interface

The firmware's main loop polls monitor slot `+0x18` and, when it gets a pointer,
reads the packet like this (`0x02122E96`):

```
pkt = monitor_get()           ; +0x18, NULL when nothing waiting
if (!pkt) keep idling
len    = (word)[pkt+2]        ; sign-extended
body   = pkt + 4
opcode = (byte)[body]
```

So a received packet is a short header - a word the receive path does not read,
then the body length - followed by the body, whose first byte is the opcode.
`--packet` feeds one in through the stubbed monitor; the firmware consumes it
and calls `+0x1C` once, which is how delivery is confirmed.

The dispatch at `0x02122FBC`:

| opcode | goes to |
|---|---|
| `0x00` | `0x02122ED0` — formats `GAME RUNNING %d %d %d GAME_NAME` and sends a reply |
| `0x01`-`0x07`, `0x20`, `0x21` | `0x02122F32` |
| `0xC7` | `0x02122F78` |
| `0xE4` | `0x02122F3C` |
| anything else | `0x02145E90` |

`0x02145E90` is not the game layer — the strings around it are
`Master router ready`, `Slave router ready, trip time %d`,
`Timeout, no CONNECT after dial command OK`, `*** NETWORK OVERLOAD ***`,
`----- ROUTER -----`. That is the inter-centre modem link from `Dial_List`,
where one pod per side acts as the router. It filters on a pair of bytes at
`0x0218AEB6`/`B7` against `0x02179D32`/`33` — a node and game identity the
packet must match at `body[2]` and `body[3]`.

Whatever starts a game is therefore among the low opcodes.

### The protocol, from the operator console's own log

The release carries a `Console Log` from a working BattleTech Center, running
from February to October 1995 — about 68,000 logged messages, each with the
console's source file and line. The console logged every message it exchanged
with the pods **by name**, which makes the log a protocol specification written
by the software itself.

`tools/logproto.py` recovers it from a log you supply. The message vocabulary:

| message | fields |
|---|---|
| `IDENTIFY_YOURSELF` | node. The pod answers either `BOOT CODE version V (netN)` from its boot monitor, or `GAME RUNNING … GAME_NAME` once the game is up — which is the reply built by opcode `0x00` |
| `SHADOW_ROM` | node |
| `Load <path> to node N at <hex>` | one per image, the address matching the Load script |
| `Set Go_Address on node N to <hex>` | |
| `GO` | node, address |
| `COCKPIT_CONFIG_MSG` | node, forward node, cockpit name — each answered with `Acknowledged - node N` |
| `PLAYER_CONFIG` | node, cockpit name, pilot name |
| `MECH_CLASS` | class, thing number, type, name |
| `Drop Location` | x, y, z |
| `NET_CONFIG_SEND_MSG`, `GAME_SETUP_SEND_MSG` | net, node — chunked, with running totals |
| `GAME_OVER` | node |

and a game start runs:

```
SHADOW_ROM / GO for every node
Configuring Cockpits    COCKPIT_CONFIG_MSG per node, each acknowledged
                        PLAYER_CONFIG per node
Reset world
Creating vehicles       MECH_CLASS + Drop Location per vehicle
Downloading Map
```

The `COCKPIT_CONFIG_MSG` "forward" field chains the nodes — each cockpit points
at the next, and the last points at 128, the console. That is the ring the
`Net_Configuration` file describes.

Two useful cross-checks fall out. The log is a System 2.5 site, loading `ROM2_5`
at `0x8FFFE4` with `Go_Address` `0x900000` — exactly what `Full_Load_2_5` says,
against `0x020FFFE4` / `0x02100000` for 3.0, so the loader model holds across
pod generations. And `MECH_CLASS`'s type field is the vehicle id from
`Vehicle_List`, the same number that appears in the last column of `Game_Setup`.
Those plaintext files map directly onto the wire.

What is still missing is the byte encoding of each message. The names and field
order are known; the layout is not.

### What one injected packet does

With `--packet`, a packet whose address fields match is not acted on directly —
it is copied into a 100-slot ring at `0x02183716`, 256 bytes per slot, and
handed to `0x021228D6` with a tag of 3. The consumer only runs during a game, so
a single packet into an idle cockpit is queued and nothing more.

Sweeping all 256 opcodes with a minimal body confirms it: every one behaves
identically — consumed, released, queued — with a single exception. **`0xC6`**
reaches the modem router and makes it log `Function:%d Timeout %d, Size %d`.
That is a SiteLink message, not a game one.

So starting a game needs the whole ordered sequence with real field contents,
not one packet. That is a protocol project, not a next step.

### Reading the sender is blocked on THINK C relocations

The obvious shortcut — read `Console 1.5.12.a01`, which builds these messages —
does not work yet. `tools/macres.py` extracts its 20 `CODE` segments cleanly
(228 KB) and every protocol string is in its `DATA` resource, the A5 globals
image. But no `CODE` segment contains an A5-relative reference to any of them,
at either plausible displacement and in either the 16- or 32-bit form.

The application is THINK C's far model, and it carries `CREL` and `DREL`
resources: code and data relocations applied at load time. The operands on disk
are placeholders. Reading the sender means implementing those relocation tables
first — a reverse-engineering job in its own right, on an undocumented format.

## Renderer command 6

With the renderer's memory mapped as real RAM (the firmware reads a fixed error
block out of the top of it, and reports `TI ERROR!` if that reads as open bus),
the main loop posts one more command:

```
cmd 6  op=6  addr 0x100007D0  0  7  5
```

using the 9000-byte allocation from command 2. Its meaning is not yet known.

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
   the TI TMS340 family. Its 512 MB bit-addressed space is mapped
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
   inside the uploaded region.

4. **The processor is a TMS34020, and it drives a coprocessor.** This was open
   for a long time and is now settled by the firmware's own instruction stream.
   R.BIN executes opcodes that do not exist on a TMS34010:

   | opcode | instruction | what it does |
   |---|---|---|
   | `$0273` | `SETCDP` | recompute CONVDP from DPTCH |
   | `$0251` | `SETCSP` | recompute CONVSP from SPTCH |
   | `$02FB` | `SETCMP` | recompute CONVMP from MPTCH |
   | `$0280` | `RPIX` | replicate a pixel across a register |
   | `$0A00` | `VLCOL` | latch the VRAM colour register |
   | `$0A57` | `VFILL` | VRAM block fill |
   | `$08F2` | `CLIP` | clip to the window |

   `SETCDP` in particular appears exactly where it must: immediately after
   `MOVI #$2000, B3`, which is the destination pitch it reads.

   And at `$0600`–`$06FF` sit 419 coprocessor instructions — `CEXEC`,
   `CMOVGC`, `CMOVCG`, `CMOVMC`, `CMOVCM` — each three words, opcode plus a
   32-bit command naming the coprocessor and the operation. The '20's
   coprocessor is the **TMS34082 floating-point unit**, and the very first one
   the renderer executes is at reset, five instructions in:

   ```
   FE0000F0  MOVI    #$CA000438, A0
   FE000120  CMOVGC  A0, $000D4C00
   FE000150  CMOVCG  A0, $000C4E00
   ```

   That is where the renderer's 3D arithmetic goes, and it is the reason the
   geometry cannot be followed by reading the '20's code alone.

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

That table was incomplete in two ways. A request record is **12 bytes**, not 8
— `[+0]` opcode, `[+4]` argument, `[+8]` unused — except opcode 2, whose record
is 20. And there are ten opcodes, not four. Each has its own wrapper function in
the ROM, all built the same way and all naming themselves in their error
message:

| opcode | command | wrapper |
|---|---|---|
| 1 | reset | `0x0214C9A0` |
| 2 | allocate (20-byte record; returns handle and address) | `0x0214CD20` |
| 3 | free | `0x0214CDDC` |
| 4 | compact | `0x0214CE58` |
| 5 | load resource map | `0x0214CED8` |
| 6 | **render** | `0x0214CF62` (never called) |
| 7 | follows every render, argument 5 | — |
| 10 | load palette | `0x0214CFF0` |

Rendering does not go through the opcode 6 wrapper — that one is dead code.
It goes through **`Async_Render` at `0x0214D302`**, which posts two records in
one request: opcode 6 with the display list's address, then opcode 7 with the
constant 5, then the terminator.

### The display list

`0x021444E8` is the only caller of `Async_Render`, and it is where the list
crosses from the 68020 into the renderer:

```
if (cursor > limit) { "68020 render list is bigger than memory buffer in TI"; return; }
count = *list                       ; leading longword: how many longwords follow
copy count longwords, 68k RAM -> TI memory
Async_Render(ti_address, flags)
```

So the list is **a flat array of big-endian longwords with a leading count**,
copied verbatim. Its records are built by two emitters, and reading them gives
the format without having to run anything.

**Record type 8 — viewport** (`0x0214465C`, 12 longwords, cursor += 0x30):

| offset | contents |
|---|---|
| `+0x00` | `8` |
| `+0x04` | `10` |
| `+0x08`…`+0x14` | x0, y0, x1, y1 |
| `+0x18` | x1 − x0 + 1 — width |
| `+0x1C` | y1 − y0 + 1 — height |
| `+0x20` | (x0 + x1) >> 1 — centre x |
| `+0x24` | (y0 + y1) >> 1 — centre y |
| `+0x28`, `+0x2C` | two more arguments |

The width, height and centre are *derived* from the corners by the emitter,
which is what identifies the record: nothing else computes those four values
from those four.

**Record type 1 — draw object** (`0x02144724`, cursor += 0x8C):

| offset | contents |
|---|---|
| `+0x00` | `1` |
| `+0x04` | record length in longwords: `7n + 33`, for `n` items |
| `+0x08`…`+0x34` | twelve IEEE single-precision floats, written as `1,0,0 / 0,1,0 / 0,0,1 / 0,0,0` |
| `+0x38` | argument |
| `+0x3C` | `1.0f` |
| `+0x40` | argument |
| `+0x4C` | `479` |
| `+0x50` | `359` |
| `+0x54`…`+0x5C` | three arguments |
| `+0x60`…`+0x84` | ten arguments |
| `+0x88` | `n`, the item count |

Those twelve floats only read as the identity at one shape: **four rows of
three**, a 3x3 rotation and a translation row. As four rows of four they are
three copies of `(1,0,0,0)`, which is nothing. The shape is the evidence.

**`479` and `359` are the screen extent**, and they are the first hard number
for the pod's resolution: **480 x 360**. They check out against the renderer
from the other side — running R.BIN in `tools/tms340run.py` leaves WEND (B6)
holding `$016701DF`, which is Y = 359, X = 479. Two independent sides of the
machine, same number.

So the 68020 hands the renderer a **transform matrix**, not transformed
vertices. The TMS34082 does the transform, which is why the coprocessor is on
that board at all.

### The renderer reading the same list

All of the above came off the 68020. The renderer's side of it is in R.BIN, and
it agrees — which is the check, because the two were derived independently.

The renderer's command dispatch is a **ten-entry table at `0xFE028460`**, one
longword every 32 bits, and entry *i* serves opcode *i+1*: entry 0 jumps
straight to the reset code, and entry 1 allocates and writes back three reply
words — error, handle, address — which is exactly the 20-byte record the ROM
builds for opcode 2. So **opcode 6 is `0xFE007630`**, which shifts its argument
left by 3 (byte address to bit address) and calls the display-list walker at
`0xFE009D80`:

```
FE009EE0  ADDI  #$0040, A0          ; past the list header
FE009F00  MOVE  *A0+, A1, 1         ; record type
FE009F10  JRN   $FE009FE0           ; negative terminates the list
FE009F20  MOVE  *A0+, A2, 1         ; length, in longwords
FE009F30  SLL   #5, A2              ; -> bits
FE009F40  ADD   A0, A2              ; where the next record starts
FE009F60  SLL   #5, A1              ; type * 32 bits
FE009F70  ADDI  #$FE00A160, A1      ; -> the record dispatch table
FE009FA0  MOVE  *A1, A1, 1
FE009FB0  CALL  A1
```

That settles the header: **`[+4]` is the length of what follows the type and
length words**, not of the whole record — which is why the emitter writes
`7n + 33` for a record it advances the cursor 35 longwords past.

The table at `0xFE00A160` has **nine entries, types 0 to 8**, and every handler
is two instructions: they only *file* the record.

| type | handler | what it does with the record |
|---|---|---|
| 0 | `0xFE009FC0` | nothing — returns into the walker |
| 1 | `0xFE00A280` | appends to the object list at `0xFE0325C0` |
| 2 | `0xFE00A2A0` | keeps it in A12 — the draw order |
| 3, 4 | `0xFE00A2C0` | indexes by its first word into the table at `0xFE028A20` |
| 5 | `0xFE00A320` | the same |
| 6 | `0xFE00A380` | appends to `0xFE0327C0` |
| 7 | `0xFE00A3A0` | appends to `0xFE0329C0` |
| 8 | `0xFE00A3C0` | appends to the viewport list at `0xFE032BC0` |

Then a second pass walks the type 2 record, which holds **1-based indices into
the objects collected from the type 1 records** — the draw order, and the thing
behind the firmware's `Render List Overflow`. For each one it calls
`0xFE00A3E0`, which takes two pointers into the object: one at its start and
one 0x24 bytes in. In the ROM's numbering that second one is `+0x2C`, the start
of the fourth row of those twelve floats. **The renderer itself treats them as
a 3x3 and a translation**, which is the confirmation that the shape is right.
It also reads `+0x40` as a 1-based index into the viewport list, so that field
is which viewport the object draws into.

### The item stream

The items are **not** inside the object record, which is what it looked like
from the 68020 side. The renderer reads the object's `+0x58` as a **1-based
index into the list the type 7 records built**, and hands *that* record's
payload to the item interpreter:

```
FE00B230  MOVE  *A0(640), A0, 1     ; the object's +0x58
FE00B250  JREQ  $FE00B2F0           ; zero -> no items
FE00B260  DEC   A0
FE00B270  SLL   #5, A0
FE00B280  ADDI  #$FE0329C0, A0      ; the type 7 list
FE00B2B0  MOVE  *A0, A7, 1
FE00B2C0  CALLA $FE022800           ; run its items
```

What follows the object's own header is geometry: the renderer takes `+0x88`
as a count and passes what comes after to `0xFE019D50`, which transforms it
through the coprocessor. The emitter's length formula settles the shape —
`7n + 33` for `n` at `+0x88` means **n groups of seven longwords**. That
routine runs a *second* item interpreter of the same design, with its own
24-entry table at `0xFE018A00`, which is why there are two.

Items and their opcodes are **multiples of `0x20` because the renderer uses the
opcode directly as a bit offset**:

```
FE022930  MOVE  *A7+, A0, 1
FE022940  ADDI  #$FE0229E0, A0      ; opcode is already the offset, in bits
FE022970  MOVE  *A0+, A0, 1
FE022980  JUMP  A0
```

A threaded interpreter: each handler jumps back to `0xFE022930` for the next
item. The table at `0xFE0229E0` has **twenty-five entries, `0x000` to `0x300`**,
and the 68020 has an emitter for every one of them — 22 that write their opcode
as an immediate, two that write a string, and one that appends a bare zero,
which is the end marker the table's entry 0 handles. A second table with the
same stride sits at `0xFE018A00`.

Each emitter gives the item's length. Two of them, `0x1E0` and `0x200`, carry a
C string copied a longword at a time **with the bytes reversed**, which is the
same reversal the image upload does and is what makes them read correctly on a
little-endian TI:

| opcode | longwords | opcode | longwords |
|---|---|---|---|
| `0x000` | 1 (end) | `0x1A0` | 3 |
| `0x020` | 1 | `0x1C0` | 2 |
| `0x040` | 8 | `0x1E0` | 1 + string |
| `0x060` | 2 | `0x200` | 1 + string |
| `0x080` | 1 | `0x220` | 2 |
| `0x0A0` | 1 | `0x240` | 2 |
| `0x0C0` | 1 | `0x260` | 6 |
| `0x0E0` | 1 | `0x280` | 1 |
| `0x100` | 3 | `0x2A0` | 1 |
| `0x120` | 3 | `0x2C0` | 11 |
| `0x140` | 3 | `0x2E0` | 1 |
| `0x160` | 4 | `0x300` | 1 |
| `0x180` | 2 | | |

### Handing the renderer a list

`tools/tms340run.py --render` builds a display list from the format above and
drives R.BIN at it directly, which is the only way to watch the renderer draw:
the 68020 only builds a list once a game has started, and starting one needs a
network. It is also a test of the format — a list built from these notes either
walks or it does not.

It walks. The renderer takes it, dispatches record 8 to the viewport collector
and record 1 to the object collector, reaches the terminator, and runs its
second pass. Three things the format needed, all found this way:

- **The list header is two longwords, not one.** The walker does
  `ADDI #$0040, A0` before its first record, and the 68020's copy loop takes
  its length from the first of them.
- **Without a type 2 record nothing draws at all.** The renderer collects
  every object and then iterates the draw order; with no draw order it spins
  on an empty one. Record type 2 is not optional.
- **The item stream belongs in a type 7 record**, not in the object. Put it in
  the object and the interpreter never runs.

It also found a bug in the interpreter rather than in the format. The item
dispatch is `MOVE *A0+, A0` — it fetches a handler address through the same
register it advances — and the postincrement was being applied after the load,
so the renderer jumped into the middle of its own jump table. On the hardware
the loaded value wins.

With both right the renderer runs the whole object path — 236 instructions,
no unimplemented opcode — and draws nothing, for a reason that is now measured
rather than assumed. The object's transform goes through `0xFE0220F0`, which
is `CEXEC`/`CMOVGC`/`CMOVCM` and nothing else, and with no coprocessor to
answer them the object is culled before its item stream is ever interpreted.

**The whole walk needs ten distinct coprocessor commands**, twelve issued:

```
CMOVGC  $001B4C00 x2     CEXEC   $0000E000 x1
CMOVMC  $01C09E0C x2     CMOVCM  $00178F02 x1
CMOVGC  $00004C0D x1     CMOVMC  $00008D0C x1
CMOVGC  $00024C0D x1     CEXEC   $0000D800 x1
CMOVGC  $00044D0D x1     CMOVCM  $00008F03 x1
```

Eight of those are register and memory transfers. Only two are operations —
`CEXEC $E000` and `CEXEC $D800`.

### The TMS34082 command word

The 32 bits after a `CMOV*`/`CEXEC` opcode are the coprocessor's instruction
word, and the TMS34082 Designer's Handbook (1991) gives its fields:

```
31-29 ID   28-25 ra   24-21 rb   20-16 rd   15-14 md   13-8 fpuop   7-0 ...
```

`md` is the field that matters and it needs no guessing: **every one of the
nine commands R.BIN issues during a render agrees with it.** The three
`CMOVGC`s read `01`, the four memory moves read `10`, the two `CEXEC`s read
`11` — which are exactly the modes the TMS34020 instructions carrying them
imply. The low byte holds the other GSP register the '20's own opcode had no
room for. The register file is the handbook's Table 4-3: `RA0`–`RA9`, `C`,
`CT`, `STATUS`, `CONFIG`, `COUNTX`, `COUNTY`, `RB0`–`RB9`, `VECTOR`, `MCADDR`,
`SUBADD0`, `SUBADD1`.

Two things follow. `CMOVGC A12, $001B4C00` writes register `0x1B` — `MCADDR`,
the indirect address register — with `$00010007`, so the renderer points the
coprocessor at something before it runs. And **mode 3 selects a routine from
the '82's internal ROM**, of which the handbook lists about 160. That is the
finding that changes the size of the job: the arithmetic the renderer needs is
*documented silicon*, not microcode somebody would have to reverse.

`CEXEC $0000D800` decodes as mode 3, fpuop `$18` — **`SCALE`, "scale and
convert coordinates for viewport"**, whose algorithm the handbook gives in
full:

```
RA0..RA3 = X, Y, Z, W      RA7..RA9 = Sx, Sy, Sz     RB7..RB9 = Cx, Cy, Cz
X' = (X/W) * Sx + Cx       Y' = (Y/W) * Sy + Cy      Z' = (Z/W) * Sz + Cz
```

The perspective divide and viewport transform, in exactly the place a renderer
does them. `tools/tms340run.py` implements it, and a render walk now reports:

```
coprocessor routines run: SCALE x1
coprocessor routines still missing: mode 3 fpuop $20 x1
```

With the item stream in the right place the interpreter runs end to end and the
renderer returns to its idle command loop, having processed the list. It still
draws nothing: the text item wants state the earlier items in a real stream
would have set.

**One routine left unidentified.** Table 7-1 reads `$020` as an integer `MOVE`,
which does not fit what the calling code does — it loads six values into
`RA0`–`RA5` and reads two back from `RB7` — so the `type` and `size` bits
almost certainly compose into the ROM address as well, and that part of the
scanned table is not legible enough to settle. It is named rather than guessed:
a fabricated transform would put numbers on the screen no cockpit ever
produced.

`battlepod --rstub` decodes all of this the moment a render command arrives —
records, matrix, item stream and the strings. Nothing in the release sends one
yet, because a cockpit that has not started a game never renders, so
`--selftest` walks a synthetic list instead. That is what keeps the decoder
honest until a real one turns up.

### Reaching the diagnostic monitor without disabling the game

The monitor is reached by making the game initialisation at `0x02138A64`
return. Patching an `RTS` over the function itself works, but menu item
`y - START TEST GAME` calls that same function, so the test game becomes a
no-op that prints `ok!`. Patch the **call site** instead and both work:

```
--set 2123FEC=60044E71          # bra.s over the jsr, leaving the function intact
```

Menu item `n - Start TI` resolves an old open question: it prints "Starting TI,
screen should clear" and writes a word to `0x38000022`. **That is the
renderer's reset line.**

One trap for anyone reading tables straight out of `ROM3_0`: the file carries a
28-byte `0x601A` header, so a load address maps to **file offset + 28**. The
monitor's jump table at `0x02124858` reads as sixteen entries of nonsense
without it.

### Resource archive

With the allocator answering, the ROM parses the resource files and prints its
own index — four type classes and several hundred numbered resources:

and the archive format is decoded — see **The resource archive** below.

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

An Analog Devices DSP board. The System 3.0 manual: "Contained inside the sound
board are several Analog Devices ADSP's used for processing sounds stored. The
sample memory of the sound board is stored in DRAM mounted on the board."
WarlockD's dossier names the part as **ADSP-21020**, which also explains the
`.dld` extension — that is the Analog Devices downloadable-executable format.
Not independently verified here.

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

- Which parts sit at `0x00010007..0x00010015`?
- The UART receive register — needed to drive the ROM's built-in diagnostic
  menu, which can start the renderer, the Secondary and a test game on demand.
- Resource type semantics (1, 2, 4, 7).
- ARCNET has still not been touched; the boot reaches the main loop without it.
  The controller is reported to be an **SMC COM90C66**, on the CPU board.
- After the audio download the ROM jumps through a null pointer. Expected while
  three boards are stubs, but worth revisiting once any of them is real.
