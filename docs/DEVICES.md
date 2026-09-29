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
    --duart 11000 --rstub 3FF00000 --astub --set 40000100=1234567
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

**Three instructions store the one's complement of their immediate**, and the
best evidence for it is that fixing it made two halves of this project stop
contradicting each other. The renderer's resource loader tests its flag word
with what reads at face value as `BTST #27`; the archive format, decoded years
apart from the 68020 side, says the flag is *bit 4*. Complemented, `~27 & 31`
**is** 4. Two independent readings that disagreed now agree exactly.

 `CMPI`,
`SUBI` and `BTST` all carry the `IMMCOM` flag in TI's own assembler: it flips
the value you wrote before encoding it, and the hardware flips it back. Read
the encoding at face value and the renderer's command-loop bounds check comes
out as

```
FE007020  CMPI  #$FFFFFFEF, A0      ; -17, compared with JRHS - meaningless
```

when what it says is

```
FE007020  CMPI  #$00000010, A0      ; 16, the size of the dispatch table
```

The resource decompressor at `0xFE0090F0` is the other place it shows: its
escape test reads `CMPI #$000000FF` — a `0xFF` byte, which is a sensible thing
to escape on — and not `#$FFFFFF00`, which nothing could ever equal. `BTST`'s
five-bit constant is complemented the same way, so its bit numbers were wrong
too.

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
entry:

| opcode | handler | |
|---|---|---|
| 1 | `$FE0072A0` | reset — jumps straight to the reset code |
| 2 | `$FE0072D0` | allocate — writes back error, handle and address |
| 3 | `$FE0073F0` | free |
| 4 | `$FE0074B0` | compact |
| 5 | `$FE0075A0` | load resource map |
| 6 | `$FE007630` | **render** |
| 7 | `$FE0076E0` | |
| 8 | `$FE007780` | |
| 9 | `$FE007880` | |
| 10 | `$FE007980` | |

An earlier version of this table was listed two rows off, claiming the entries
served opcodes 3 to 12 with 1 and 2 null. They are not: the command loop does
`DEC A0` before indexing, entry 0 is a jump to the reset code, and entry 1
writes three reply words — error, handle, address — which is exactly the
20-byte record the ROM builds for allocate. Every handler decodes at 100%.

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

## The secondary display, and why it will not start on its own

The pod's second screen is an Amiga board. Its program, `AMIGA3_0`, had never
been looked at; `battlepod --amiga` now loads and runs it.

It is a plain **601A image**: text 56,704, data 4,720, bss 692. Its header says
`ABSFLAG = 1` - **no relocation table** - and its first instruction is
`jmp $0000E112`, an absolute address inside its own data. So it is linked to
run at **zero**, which is what a bare-metal display board with no operating
system looks like, and it is loaded where it expects to be rather than at the
`0x400003E4` the cockpit's load script stages it at.

**It does not start.** The word at `0xE112` is zero in the file, under either
mapping of the header, and the trace shows it plainly:

```
   0  00000000  jmp     $e112.l
   1  0000E112  ori.b   #$0, D0        ... and on through zeros
```

There is a hole of zeros around `0xE000`-`0xE400` inside the data section, and
the entry points into it. Something fills that word before the program runs,
and it is not the image.

The other board is the obvious candidate and the evidence agrees: `ROM3_0`
carries **208 distinct references into `0x40000000`-`0x40010000`**, the Amiga's
memory window, with `0x40000000` itself referenced **137 times**. The two
boards share memory, and the display is driven across it rather than booted.

So the next question is that interface - which is also the 1,652-byte SecCom
protocol the roadmap has been carrying as a to-do since the start. `AMIGA3_0`
names `MAPDISP!` and `NAVSECT!`, and `btsecond3_0` names `SECTOR`, `TARGET` and
`DAMAGE`, which are the three modes the cockpit firmware's own status lines
select between.

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

### The pod answers

Say `IDENTIFY_YOURSELF` to the booted cockpit and it replies. This is the first
message exchanged with the pod in either direction, and it is what step 3 of
the plan needs as a feedback loop.

```
--packet '00 00 00 08 00 01 00 00 00 00 00 00'
--tap 021468A4 --tap-dump -0xD2 64

  0000  20 01 00 20 47 41 4D 45 20 52 55 4E 4E 49 4E 47
  0010  20 33 32 32 38 20 36 30 30 20 32 20 47 41 4D 45
  0020  5F 4E 41 4D 45 00 ...

  = 20 01 00 20  "GAME RUNNING 3228 600 2 GAME_NAME"
```

which is exactly the reply the operator console logged in 1995, from the other
side of the same wire.

`--tap ADDR` is new and is what made it visible. `--watch` says what touched a
region of memory; a tap says what the registers held when execution arrived
somewhere, and `--tap-dump OFF N` adds N bytes at `A6+OFF`. The reply never
reaches a device we model - it is a stack argument to the packet sender - so
the only way to read it is to stand at the sender's door as it goes out.

### Reading the packet handlers, which is easier than reading the Mac

The plan was to lift the operator console's 68k code for the byte layouts. The
pod's side is easier: it is already in the emulator, and a decoder is as good a
specification as an encoder.

The dispatch at `0x02122FBC` is a chain of `subq`/`beq` rather than a table:

| opcode | handler | what it does |
|---|---|---|
| `0x00` | `0x02122ED0` | builds the identity reply above and sends it |
| `0x01`-`0x07`, `0x20`, `0x21` | `0x02122F32` | **discarded** in this state |
| `0xC7` | `0x02122F78` | replies with `0xC7` |
| `0xE4` | `0x02122F3C` | reads or sets the timebase at `0x02000808` |
| anything else | `0x02145E90` | the inter-centre router |

Worth knowing: **the low opcodes are thrown away here** - `0x02122F32` releases
the packet and returns to the main loop without looking at it. That is not the
whole story, and the next section is why: this dispatch serves the boot
monitor's queue, and a game message arriving off the network never reaches it.

The identity handler writes its reply as four bytes and a `sprintf`:

```
buf[0] = 0x20        the reply's own opcode
buf[1] = 0x01
buf[2] = 0x00
buf[3] = 0x20
buf[4..] = sprintf("GAME RUNNING %d %d %d GAME_NAME", timebase, ..., ...)
send(dest_word, 0xCC, buf, 5)        length 204, priority 5
```

### The header the sender writes

`0x021468A4` takes `(dest word, length, buffer, priority)` and fills a header
over the front of the buffer. Which fields it writes depends on the route -
local net, remote net, or through the router - but the shape is constant:

```
buf[0]    the opcode, already there from the caller
buf[1]    priority >> 24
buf[2..3] one 2-byte (net, node) address
buf[4..5] another
buf[6..7] another
```

drawn from three places: the destination argument, our own address at
`0x0218AEB0`, and the game identity at `0x02179D32`. Those are the same two
locations DEVICES.md already found the router filtering on, and the same fields
the console names in every one of its messages - `to net %ld, node %ld`. The
console's error string names the rest of what a packet carries:

```
ERROR: Orig. %d, Pri. %d, Num. %ld, Time %ld, String:
```

an origin, a priority, a sequence number and a timestamp.


### The game's own message dispatch

There *is* a second dispatch. An earlier section here said there was not, and
that was wrong twice over: it exists, and the messages it handles are not the
opcodes `0x01`-`0x07` that were being looked for at all.

It was found from the sending side. The packet sender at `0x021468A4` has **45
call sites**, 28 of them in one module between `0x0213E332` and `0x0213EE92`,
and each writes its own opcode into `buf[0]` first. Pulling those out gives
**38 distinct opcodes the pod can send, from `0xB9` to `0xED`** - a range that
has nothing to do with `0x01`-`0x07`. That said the game protocol lives
somewhere else, and made it worth looking for the receiving half in the same
neighbourhood.

```
02139E64  link    A6, #-4
02139E6C  movea.l ($8,A6), A0     the packet
02139E70  moveq   #0, D0
02139E72  move.b  ($13,A0), D0    the opcode
02139E76  bra     $213A332        33 arms
```

**This is not a packet at all.** It was read here as a second network dispatch
over byte `0x13` of a message, which is wrong. `(8,A6)` is the **event
buffer**, the event is **kind `0x0A`**, and kind `0x0A` is posted from exactly
one site in the whole ROM:

```
02122D60  pea    (-$1,A6)
02122D66  jsr    $215dafa.l        read one byte from the console
02122D6E  move.b (-$1,A6), D0
02122D78  pea    $a.w
02122D7C  jsr    $21228d6.l        Post_Event(kind 0x0A, 0, 0, byte)
```

Byte `0x13` of the event is the **low byte of that longword parameter**. So
the 33 "opcodes" are **33 keystrokes**, and their values say so: `0x4A` is
`J`, `0x51` is `Q`, `0x64` is `d`, `0x73` is `s`, `0x78` is `x`. This is the
pod's **in-game console**, and it answers.

Typing at the modelled serial port proves it. With the game running and no
firmware patched, every key that does something does it:

```
J   Joint 1 Angle 0.000000 ... the skeleton's joint angles
Q   Profile Cleared
q   021bb1ac 00000000 00000000, then Profile Cleared - a hex dump
s   the whole status report: 68681, CULLING, RENDERER, ROUTER, EVENTS
x   BattleTech 2 Test Program - it drops to the diagnostic monitor
```

**`x` is how you leave a game.** Every monitor result in this project so far
came from a cockpit with `RTS` patched over the game's entry, because the boot
runs the game and never returns. It returns if you ask it to.

The dispatch is 33 arms wide and covers `0x21` to `0x7A`:

```
  21  Post_Event(kind B1, param 33)     37  Post_Event(kind B1, param 41)
  2A  Post_Event(kind B1, param 3C)     38  Post_Event(kind B1, param 42)
  2B  Post_Event(kind B1, param 3D)     39  Post_Event(kind B1, param 40)
  2C  Post_Event(kind B1, param A8)     3B  3D  4A  51  64  66  68  69
  2D  Post_Event(kind B1, param 43)     6A  6B  6C  6F  70  71  73  75
  32..36  Post_Event(kind B1, 04 08 0C 10 14)   78  79  7A
```

Most arms do one thing: turn the wire message into an **event of kind `0xB1`**
with a parameter, and hand it to `Post_Event` - which is the queue measured
two sections above. So a game message is not acted on where it arrives; it is
translated into an event and queued, exactly as the modem path does with its
own traffic.

The dispatch is reached from the **kind `0x0A`** arm of the event switch, and
which handler runs depends on the class of the pod's own mech - see below. An
earlier reading of that arm as a message pump over a queue at `0x0218AEE4` was
wrong; `0x0218AEE4` is `My_Mech_Ptr`. Near it sits the string
`Test Event, message# %d`, which is the firmware naming what it is doing.

### What these messages are, and what they are not

The obvious guess was that this table is the console's setup sequence - the
`COCKPIT_CONFIG_MSG`, `MECH_CLASS` and map-download messages the log names.
The nine handlers from `0x64` to `0x70` even line up in count with the nine
`*_CLASS` records the map file carries. **The code says otherwise**, and it is
worth writing down so the guess is not made twice.

The arms that do more than queue an event operate on the **local vehicle's
state** through a pointer at `0x0218AEE4`:

```
0x68   [$218AEE4 + 0x2E]  -= 5.0    then compares it against -2.8
0x3B   [$218AEE4 + 0x100] -= 2.0
0x66   [$218AEE4 + 0x92] = 0xFFFF, call $0215A9B4, clear it again
0x4A   walks 24-byte records from [$218AEE4 + 0x140], reading a float from each
```

Subtracting five from a float and checking a threshold is damage or heat, not a
map record. So `0x21`-`0x7A` is the **in-game** message set - what pods say to
each other and what the console says during a mission - and the setup sequence
is not obviously in this table at all.

That also gives the first sight of the vehicle state structure: a word flag at
`+0x92`, floats at `+0x2E` and `+0x100`, and an array of 24-byte records at
`+0x140`.

Putting names to individual opcodes needs the other end. The console's log
gives every message a name and a field list; its code writes the opcode that
goes with each. Reading that means the `DREL` fixups and an A5 cross-reference,
which is the job `macrecomp`'s front end was picked for.

So the picture is: **byte 0 for the monitor, byte `0x13` for the game, and
`Post_Event` underneath both.** What is still not known is what any individual
opcode means - the console's own log gives names and fields for the messages it
sends, and those names now have a numbering to be matched against.


### The game loop, and the message table at the end of it

Following the injected packet the rest of the way gives the loop's shape and,
at the end of it, the message vocabulary this project has been after since the
beginning.

The loop is an event pump:

```
02138F58  pea   (-$9e,A6)          a buffer
02138F5C  pea   $FFFF.w            take anything
02138F60  jsr   $2122154           Get_Event
          nothing -> round again
          a hook at (-$8a,A6), if set -> call it
          otherwise -> switch on the event's kind at $2139306
```

and the kind switch runs `-2`, `-1`, `1`, `2`, **`3`**, `0xA`, `0xB0`, `0xB1`,
`0xC0`, `0xD0`, `0x10000`, `0x10003`. **Kind 3 - a network packet - goes to
`0x0213B80A`**, which takes the packet out of the event at `+0x10`, reads
**byte 0**, and branches into a jump table:

```
0213CF2C  subi.w #$B9, D0
0213CF30  cmpi.w #$47, D0        71 entries
0213CF34  bcc    $213CF44        out of range: drop it
0213CF38  lea    (-$9c,PC), A0   the table, at 0213CE9E
0213CF40  jmp    (PC,D0.w)
```

**Opcodes `0xB9` to `0xFF`, of which 46 have their own handler**, the rest
falling to a common exit. `0xF6`-`0xFF` share one. That range is the same one
the pod *sends* in - 38 opcodes from `0xB9` to `0xED`, found from its 45 calls
to the packet sender - so this is one symmetric protocol rather than
two, and the console's messages live in it.

Confirmed by walking a packet into it: `--packet '30 ...'` reaches
`0x02139044`, the kind-3 arm, and then `0x0213B80A`.

Note this is **not** the dispatch at `0x0213A332` that reads byte `0x13`. Both
exist and they are reached by different routes; the byte-0 table is the one a
packet off the wire lands in.

### Both halves of the protocol, and the shape of a packet

The receiving table gives 71 opcodes; the sending side gives what goes in them.
`tools/netmsg.py` reads both and puts them beside each other.

**The senders.** `0x021468A4` has **45 call sites**. Each builds its packet in
a stack buffer and writes its own opcode into the buffer's first byte before
the call, as `move.b #$xx,(d16,A6)` - and the displacement is the same one the
`pea (d16,A6)` at the call pushes, which is what makes the pairing safe rather
than merely nearby. That gives **38 distinct opcodes, `0xB9` to `0xED`**, every
one of them inside the `0xB9`-`0xFF` range the receiver's table covers.

*(An earlier count here said 31 opcodes from `0xBA`. It was reading only the
nearest preceding immediate byte store, which misses a sender whose opcode is
written before a branch; matching the displacement against the call's buffer
argument finds the rest.)*

Putting the two sides together splits the vocabulary three ways:

| | opcodes | what it means |
|---|---|---|
| **sent and received** | 29 | pod to pod - the simulation itself |
| **received only** | `BE C4 C6 D3 E4 E5 EE` and `F6`-`FF` | commands the pod obeys |
| **sent only** | `C5 C8 CE D0 D4 D5 D6 E2 E6` | reports the pod files |

which is a useful thing to know before naming anything: a receive-only opcode
comes from the operator console or the router, and a send-only one goes to
them. `0xC6`'s handler runs the modem string `+++`, `0xC4`'s prints `Master
router ready` / `Slave router ready`, `0xE5`'s prints `WELCOME %s` - all three
receive-only, all three console-to-pod, exactly as that split predicts.

**The shape of a packet.** The sender writes an 8-byte header - opcode,
priority, and three 2-byte (net, node) addresses - and the body begins at
`+0x08`. Most of the simulation messages open the same way:

```
+00  b   opcode
+08  l   entity id          from the entity's own +0x06
+0C  l   entity +0x26       three consecutive longwords, carried by
+10  l   entity +0x2A       every state message that names an entity
+14  l   entity +0x2E
+18..    message-specific
```

The three longwords are **measured**; calling them a position is inference,
from the console logging `x float, y float, z float` right after `thing` in
every one of its entity messages, and from `+0x2E` already being known to hold
a float. Beyond them each message draws a different set of fields out of the
same structure - `0xE1` takes `+0xAA`, `+0xB2`, `+0xB6`, `+0xAE`; `0xD2` takes
sixteen fields from `+0xC4` to `+0x120`; `0xDD` takes nineteen from `+0x2A4` to
`+0x2E0` - so the entity structure can be mapped out from the messages that
report it, which is the first purchase anything has had on it.

**`0xC5` is `ROUTER_STATUS_MSG`, now by layout and not only by description.**
Its sender is a 100-byte packet:

```
02145E24  pea    $50.w
02145E28  move.l ($8,A6), -(A7)
02145E2C  pea    (-$5c,A6)        buffer+8
02145E30  jsr    $215d9f4.l       strncpy
02145E36  move.b #$c5, (-$64,A6)  buffer+0
...       move.l ($c,A6), (-$c,A6)   buffer+0x58
```

an 80-byte string at `+0x08` and a longword at `+0x58`, which is
`status string, status code long` written out. No other message the pod sends
has that shape.

### The entity table, and the structure the messages report

A handler does not search for the thing a message names. It indexes:

```
0213BBE6  movea.l (-$64,A6), A0      the packet
0213BBEA  move.l  ($8,A0), D0        the entity id
0213BBEE  asl.l   #2, D0
0213BBF0  lea     $2189f10.l, A0     the entity table
0213BBF6  move.l  (A0,D0.l), (-$68,A6)
```

**`0x02189F10` is an array of entity pointers indexed by the id on the wire**,
and it is referenced from **231 sites** across the ROM - the game's master
object table. An id in a packet is a subscript, which is why the protocol can
name a thing in four bytes.

What follows the lookup is the message's field list, run backwards:

```
0213BC00  adda.l #$c,   A0           packet+0x0C
0213BC0A  adda.l #$26,  A1           entity+0x26
0213BC10  move.l (A0), (A1)
```

repeated once per field. So a handler is the exact inverse of its sender, and
that gives a check nothing else here has: for every message the pod both sends
and receives, the same field must appear on both sides - the sender reading it
out of the entity, the handler writing it back in. `netmsg.py --fields`:

```
D2  +10>26= +14>2A= +18>2E= +1C>D0= +20>D4= +24>D8= +28>F0= +2C>E8= +30>EC=
    +34>C4= +38>C8= +3C>CC= +44>100= +40>104= +48>120= +08>B4=
DF  +0C>26= +10>2A= +14>2E= +18>110= +1C>10C= +20>114=
E1  +0C>26= +10>2A= +14>2E= +18>AA= +1C>B2= +20>B6= +24>AE=
```

**44 field pairs agree and none disagree**, which is a real result: the two
readings were taken from different code by different methods, and they are
consistent to the byte.

Five stores look like disagreements and are not. `0xDD` writes packet `+0x40`
into **six** places - `+0x2E0`, `+0x2F8`, `+0x310`, `+0x340`, `+0x358`,
`+0x370` - unrolled, one value broadcast across sibling records **0x18 = 24
bytes apart**, with one 0x30 gap where a record is skipped. Twenty-four-byte
records are already known to live in this structure.

The offsets the messages touch, assembled from every message that touches them:

```
26 2A 2E        every message that names an entity carries these three
6A 6E           0xDC, on its own
AA AC AE B2 B4 B6
C4 C8 CC CE D0 D4 D8 DC
E8 EC F0
100 104 10C 110 114 120
2A4..2D0        fifteen consecutive fields, 0xDD
2E0 2F8 310 340 358 370   the 24-byte records
```

**46 distinct offsets in one structure**, recovered without ever running the
game. It is not the whole entity - `+0x92` and `+0x140` are known from
elsewhere and no message reports them - but it is the first map of it, and each
entry is anchored by two independent pieces of code rather than one.

### Driving a mech from outside

Everything above is a static reading. This is the same claim made on the
running firmware.

The boot builds the world before any game starts. `0x0214C422` is the loop:

```
0214C424  muls.l #$6b4, D0
0214C42C  lea    $21f99ac.l, A0     the arena
0214C43A  lea    $2189f10.l, A0     the table
0214C440  move.l A3, (A0,D0.l)
0214C44E  cmpi.l #$3e8, D2          1000 of them
```

**1000 entities of `0x6B4` = 1,716 bytes each**, from `0x021F99AC` to
`0x0239C8CC`, with the pointer table filled in as it goes. Entity 0 is built
differently from the rest and gets class `7` at its `+0x0A`.

So entity 1 is at `0x021FA060`, and a packet naming id 1 has somewhere to land.
Inject one - byte 0 `0xE1`, id `1` at `+0x08`, then seven floats chosen to be
unmistakable:

```
--packet 'E1 00 00 00 00 00 00 00 00 00 00 01
          41 20 00 00 42 48 00 00 43 16 00 00
          44 7A 00 00 45 9C 40 00 46 40 E4 00 47 1C 40 00'
```

and read the entity back out:

```
peek 021FA086:   41 20 00 00  42 48 00 00  43 16 00 00
peek 021FA10A:   44 7A 00 00  47 1C 40 00  45 9C 40 00
```

`+0x26` is 10.0, `+0x2A` is 50.0, `+0x2E` is 150.0, `+0xAA` is 1000.0, `+0xAE`
is 40000.0, `+0xB2` is 5000.0. **All seven fields in the places the static
reading said, including the two the sender writes out of order.**

Nothing on that path is patched or stubbed. The bytes go in at the wire and the
cockpit's own code carries them through the low-level dispatch, the router, the
identity filter, `Post_Event` as an event of kind 3, the event pump, the byte-0
table and the handler. It is the first time anything in this project has made
the game's own state move, and it is a scenario in the harness so it stays
true.

### Asking the firmware which bytes a message writes

Reading the handlers statically covers the ones that unpack with the
compiler's plain copy idiom and misses the ones that do arithmetic on the way
in. `tools/entityfields.py` asks the firmware instead, by difference:

- boot the cockpit and dump entity 1;
- boot it again with one packet injected at the wire, dump entity 1 again;
- whatever differs is what that message wrote.

Both runs are deterministic, so the difference is the message and nothing else.
The packet's body is a **ramp** - byte `n` holds the value `n` - so a longword
that lands in the entity carries its own packet offset with it and the map
falls out of the dump rather than out of a reading.

Two things had to be got right before it worked, and both are findings.

**The entity id has to be real.** A ramp body would put `0x08090A0B` where the
id goes, and the handler would index a 1000-entry table with it. `+0x08` is
forced to 1 in one variant and `+0x0C` in the other, because those are the only
two places a message puts the id.

**`entity+0x02` is the class, and handlers switch on it.** `0xDF` writes only
the three position fields and stops:

```
0213C2A4  movea.l (-$68,A6), A0
0213C2A8  move.l  ($2,A0), D0        the class
0213C2AC  bra     $213c374
...
0213C374  subq.l #8, D0   beq ...    class 8:  nothing more
0213C37A  subq.l #2, D0   beq ...    class 10: three more fields
0213C380  bra    $213cf44            anything else: drop
```

and the arena loop clears `+0x02` on every entity at boot, so an entity nobody
has configured takes the do-nothing arm. Writing a class in first - at
`Get_Event`, which both runs reach, not at the dispatch, which only the
injected run reaches - makes the rest of each handler visible.

### What the sweep says

With entity 1 given class 10, **14 of the opcodes write the entity they name**,
between 1 and 90 bytes each:

```
B9  +0AC   2 from packet+0E   +67C  24 from packet+10
CC  +026  12 from packet+0C   +072  16 computed      +086   8 from packet+28
CD  +026  12 from packet+0C   +06A   4 from packet+32  +076  12 from packet+18
    +08A   4 from packet+2C   +0A6   1 from packet+31
D2  +026  12   +09E   2   +0B4   4   +0C4  24   +0E8  12   +100   8   +120   4
DD  +026  12   +0AA   2   +0D8   4   +2A4  48, then packet+40 into six
                                     records 0x18 apart
DE  +026  12 from packet+10   +056   4 from packet+0C   +07E  24 from packet+1C
E1  +026  12 from packet+0C   +0AA  16
```

with `CA`, `D7`, `D9`, `DC`, `DF` and `E0` writing between one and sixteen
bytes each. Every field the static reading found is here, in the same place -
and the messages the static reading could not follow, `B9` `CA` `CC` `CD` `D7`
`D9` `DC` `DE` `E0` `E8`, are now mapped as well.

The broadcast in `0xDD` shows up exactly as the code said: packet `+0x40` into
`+0x2E0`, `+0x2F8`, `+0x310`, `+0x340`, `+0x358`, `+0x370`.

### The same sweep as a Mech

Repeating it with entity 1 given **class 1, `Mech`** - the pod's own kind -
raises the count from 14 to **16 opcodes**, and the differences are all
class-sensitive arms rather than noise:

- `0xDF` writes only the three position fields, because its extra arms are for
  classes 8 and 10, an escape pod and a hovercraft.
- `0xE0` writes **one byte at `+0xBB`** from packet `+0x04` as a Mech, where as
  a Hovercraft it wrote four bytes at `+0xC4`.
- `0xEC` writes four more fields - `+0xC0`, `+0xF8`, `+0x114` and 24 bytes at
  `+0x694`.
- `0xE7` appears, and it is the most legible result in the sweep:

```
E7  +1E8  4 from packet+0C    +230  4 from packet+18
    +200  4 from packet+10    +248  4 from packet+1C
    +218  4 from packet+14    +260  4 from packet+20
```

**six consecutive longwords going into six records `0x18` = 24 bytes apart.**
That is a second array of 24-byte records, at `+0x1E8`, alongside the one
`0xDD` broadcasts into at `+0x2E0`. One message sets one field of six records
in order; the other sets one field of six records to the same value. Both are
24-byte strides, and the entity structure is now known to contain at least two
arrays of them.

The sweep is worth running per class for that reason: what a message does
depends on what the thing is, and a single run at one class reports a subset
and gives no sign that it has.

### The whole map, across eight classes

Sweeping classes 0, 1, 2, 9, 10, 12, 16 and 18 and taking the union gives what
the network can write into an entity: **16 opcodes, 57 field slots, 467 bytes**
of the 1716 an entity occupies.

```
B9  +AC/2  +67C/24
CA  +DB/1  +E4/4  +2B0/12
CC  +26/12 +72/16 +86/8
CD  +26/12 +6A/4  +76/12 +8A/4 +A6/1
D2  +26/12 +9E/2  +B4/4  +C4/24 +E8/12 +100/8 +120/4
D7  +DC/4
D9  +6D/1
DC  +6A/8  +B6/4  +CE/4
DD  +26/12 +AA/2  +D8/4  +2A4/48 then +40 into 2E0 2F8 310 340 358 370
DE  +26/12 +56/4  +7E/24
DF  +26/12 +10C/12
E0  +BB/1  +C4/4  +CE/4
E1  +26/12 +AA/16
E7  +1E8/4 +200/4 +218/4 +230/4 +248/4 +260/4
E8  +5/1   (cleared - the slot is freed)
EC  +26/12 +C0/4  +F8/8  +114/4 +694/24
```

Class 1, `Mech`, sees the most - 16 opcodes against 12 to 14 for the others -
which is what one would expect of the class the pod itself is.

Two messages become legible now that the fields have names.

**`0xEC` is the movement update.** It carries X, Y, Z at `+0x26`, then
`+0xF8`-`+0xFF` - which is **Course** and the longword after it - then `+0x114`
**Speed**, then a 24-byte block at `+0x694`. Position, heading and speed in one
packet is exactly what a distributed simulation sends thirty times a second,
and `0xEC` is one of the 29 the pod both sends and receives.

**`0xDE` configures a mech.** Its 24-byte block at `+0x7E` starts exactly at
**Type**, with **Color** at `+0x82` inside it. A message that sets what a mech
*is* and what colour it is drawn, which is what a console does when a player
picks a chassis.

### Class 0 is a free slot, and `0xE8` makes one

Running the sweep twice, once with the class the boot leaves and once with a
class written in, separates the messages that need a configured entity from the
ones that do not: **12 opcodes at class 0, 14 at class 10**. Only `0xDF` writes
more of the entity at the higher class; `0xE0` and `0xE8` do nothing at all at
class 0.

`0xE8` is worth following, because it is the one message whose effect is to
*remove* something. It switches seven ways on the class:

```
0213CA4C  subq.l #1, D0  beq ...     class 1
0213CA52  subq.l #8, D0  beq ...     class 9
0213CA58  subq.l #1, D0  beq ...     class 10
0213CA5E  subq.l #1, D0  beq ...     class 11
0213CA64  subq.l #1, D0  beq ...     class 12
0213CA68  subq.l #1, D0  beq ...     class 13
0213CA6C  subq.l #6, D0  beq ...     class 19
```

each arm calling a different routine - a teardown per kind of thing - and then
every class, not only those seven, ends with the entity's class **zeroed**.
Sweeping the class from 0 to 23 and injecting `0xE8` each time shows exactly
that: every non-zero class loses its class byte, and class 0 changes nothing.

So **class 0 is a free slot**. That is also what the arena loop leaves behind -
`clr.l ($2,A3)` on all thousand entities - and it means the boot state is not
"a thousand blank objects" but "a thousand free slots", with `0xE8` the message
that returns one to the pool.

The class numbers the firmware distinguishes so far are **1, 8, 9, 10, 11, 12,
13 and 19**. The console's taxonomy has the names for them - `MECH_CLASS`,
`VTV_CLASS`, `HOVER_CLASS`, `COPTER_CLASS`, `CAMERAMAN_CLASS`,
`ANIMATOR_CLASS`, `POD_CLASS`, `EXPLOSION_CLASS` and the map classes - and
nothing measured yet joins a name to a number.

### The class numbers, from the ROM's own create-thing dispatcher

`0x0211DC40` creates a thing of a given class, and it is a dense switch:

```
0211E0D8  cmpi.l #$13, D0        nineteen classes, 0 to 18
0211E0DE  bcc    $211e092        out of range
0211E0E2  move.w (-$32,PC,D0.w), D0
0211E0E6  jmp    (PC,D0.w)
```

with the out-of-range arm logging
`Create unknown thing %d, class %d received`. Six of the arms push a name
before they build anything, and those names sit in one block right after the
jump table:

```
Mech  Camship  Hovercraft  VTV  Copter  Escape pod
```

Walking the table and reading the string each arm pushes gives the numbering:

| class | | class | | class | |
|---|---|---|---|---|---|
| **1** | `Mech` | **9** | `Camship` | **12** | `VTV` |
| **8** | `Escape pod` | **10** | `Hovercraft` | **16** | `Copter` |

Seven more arms create something without naming it - 2, 3, 6, 11, 14, 17 and
18, each calling a different constructor - and 0, 4, 5, 7, 13 and 15 are
rejected as unknown.

**This joins the console's taxonomy to numbers.** `MECH_CLASS` is 1,
`HOVER_CLASS` 10, `VTV_CLASS` 12 and `COPTER_CLASS` 16 by name; `POD_CLASS` is
8 and `CAMERAMAN_CLASS` 9 on the strength of `Escape pod` and `Camship` being
the only candidates. `EXPLOSION_CLASS` and `ANIMATOR_CLASS` are presumably
among the seven unnamed arms, and nothing says which.

It also lines up with the switches found in the message handlers. `0xDF`
treats class 8 and class 10 differently - an escape pod and a hovercraft - and
`0xE8`, which removes a thing, has teardown arms for 1, 9, 10, 11, 12, 13 and
19: `Mech`, `Camship`, `Hovercraft`, `VTV` and three that the creator does not
build, including 19, which is past the end of this table altogether.

### Seven class dispatchers, and a matrix

`Create_Thing` is not the only operation that switches on the class. Six more
sites carry the identical five-instruction shape:

```
0C80 00000013   cmpi.l #$13, D0     nineteen classes
640A            bcc    +10          out of range: do nothing
D040            add.w  D0, D0
303B 00CE       move.w ($ce,PC,D0.w), D0
4EFB 0000       jmp    (PC,D0.w)
```

at `0x02106CC6`, `0x02106E08`, `0x0211D62C`, `0x0211D7F0`, `0x02150BA0` and
`0x02150CF6`. Reading each table gives which classes implement which
operation:

| classes implemented | sites |
|---|---|
| 1 2 3 4 5 6 8 9 10 11 12 14 15 17 18 | `02106CC6`, `0211D62C` |
| 1 2 3 4 5 6 8 9 10 11 12 14 15 16 17 18 | `02150BA0` |
| 1 2 3 6 8 9 10 11 12 14 16 17 18 | `0211E0D8` (`Create_Thing`) |
| 1 8 9 10 11 12 17 18 | `02106E08`, `0211D7F0` |
| 1 8 9 10 11 12 16 17 18 | `02150CF6` |

So the entity system is **class-polymorphic with nineteen slots and at least
seven virtual operations**, and the shape of the matrix is informative on its
own: `1`, `8`-`12`, `17` and `18` implement everything, which is the set that
includes every named class except `Copter`; `2`-`6`, `14` and `15` implement
the wide operations but not the narrow ones; and **`0`, `7` and `13` implement
nothing anywhere**, which fits `0` being a free slot.

Three classes - `4`, `5` and `15` - are implemented by other dispatchers but
**rejected by `Create_Thing`**, so something other than `Create_Thing` makes
them.

And one loose end that is worth stating rather than smoothing over: `0xE8`,
which removes a thing, has a teardown arm for **class 19**, reached by
`subq.l #6` after 13. Every dispatcher here stops at 18. Nothing else read so
far uses class 19.

### An ordering guard

`0xD2` opens with one before it does anything:

```
0213BFEC  movea.l ($8,A6), A0
0213BFF0  movea.l (-$28,A6), A1
0213BFF4  movea.l ($4,A0), A0       something off the event
0213BFF8  cmpa.l  ($9c,A1), A0      against the entity's +0x9C
0213BFFC  ble     $213c1d4          not newer: drop the whole message
```

so `+0x9C` is a sequence or timestamp and a late update is discarded rather
than applied - which is what a state-replication protocol over an unreliable
LAN has to do, and the first evidence here that this one does it.

### Eight opcodes with names

`tools/fnstr.py` was throwing away every string that ended in a newline, which
is most of what the firmware logs - see FALSE-TRAILS.md. With that fixed, the
handlers say a good deal more about themselves:

| opcode | what its handler says | reading |
|---|---|---|
| `0xBA` | `old damage spreader` | damage, applied to a named entity |
| `0xC4` | `Master router ready, Delay %f`, `Slave router ready, trip time %d`, `Slave router going idle`, `# %d, AVG Time %f, Trip %ld, Out %ld, Back %ld, RTC %ld, Error %ld` | the router's own ready-and-timing report |
| `0xC6` | `Send Modem Attention`, `+++`, `OK`, `Function:%d Timeout %d, Size %d` | **`ROUTER_MODEM_COMMAND_MSG`** |
| `0xD3` | `Camera 1` | camera selection |
| `0xE5` | `WELCOME %s` | a player greeted by name |
| `0xEB` | `Burst damage not correctly handled!!` | burst damage |
| `0xED` | `Hover_Player_Link()`, chassis names, `Camera 1`, `THRUSTOK` | a player's vehicle created and linked |
| `0xEE` | `I am the router (coo-coo-ca-chu)` | the router announcing itself |

**`0xC6` is `ROUTER_MODEM_COMMAND_MSG`**, on the same standard of evidence that
named `0xC5`. The console logs that message as
`node long, command string, function long, timeout long`; the handler runs the
modem - `Send Modem Attention`, `+++`, waiting for `OK` - and logs
`Function:%d Timeout %d, Size %d` followed by `%s`. Function, timeout, a
length and a string, in a handler that drives a modem. Nothing else in the
vocabulary has that shape, and `0xC6` is receive-only, which is what a command
from the console has to be.

The other seven are descriptions rather than names: what the handler is *for*
is clear, which console message it is is not. `0xBA` and `0xEB` being damage is
worth having on its own - they are the first two opcodes tied to the
simulation rather than to the plumbing, and `0xBA` is one of the 29 the pod
both sends and receives, which is how damage has to work when every pod runs
its own copy of the world.

### `0xF6`-`0xFF`: a dispatch inside the dispatch

The ten opcodes that share an arm share it because the arm is **another
dispatch over the same byte**:

```
02104356  subi.w #$f6, D0
0210435A  cmpi.w #$a, D0        ten entries
0210435E  bcc    $210436a
02104366  jmp    (PC,D0.w)      the table, at 02104342
```

All ten are receive-only, and all ten write the pod's own configuration rather
than anything in the world:

| | |
|---|---|
| `FF` | takes a word from the packet at `+2` into `0x0218AEF8` |
| `FE` `FD` | save the current mode byte `0x0215DCEE` into `0x0218AEFA`, set mode 5, then write `0x0D` (`FE`) or `0x0F` (`FD`) into three mode bytes and `0x0C` into a fourth |
| `FC` | the largest handler in the block, 0x77A bytes, four calls to `0x02146D20` |
| `FB` | reads a mode byte and, on one arm, copies two longwords from the packet into `0x0215DD2A`/`0x0215DD2E` |
| `F6` | a longword from the packet at `+2` into `0x0215DCFE` |
| `F7` | a longword from the packet at `+2`, converted to float, into `0x0215DD0E` |

**An earlier reading here was wrong.** It said this was the pod's mode machine
and that `COCKPIT_CONFIG_MSG`, `PLAYER_CONFIG` and `SHADOW_ROM` had to land in
it. The state numbers give it away: `0x0D`, `0x0E` and `0x0F` are indices into
a table of names, and the names are `Loading File...`, `Saving File...` and
`Appending File...`. This block is the remote control for the **animation
editor** the firmware ships with - see below. The console's setup messages land
somewhere else, and where is not settled.

### Event kind `0x0A` is an in-game message, and your own class routes it

The kind switch resolves to thirteen arms:

```
  -2  02139CC   1  0213906A   0xB0 0xB1 0xC0 0xD0  02139210
  -1  02139B8   2  0213911A   0x10000  02138F8E
              3  02139044     0x10003  02139054
           0x0A  0213907E     0x10006  02139034
```

**Kind `0x0A` is where an in-game message arrives**, and the arm does something
this project had read wrongly:

```
0213907E  movea.l $218aee4.l, A0      My_Mech_Ptr
02139084  move.l  ($2,A0), D0         its Class_ID
021390A6  subi.l #$c, D0   beq ...    class 12, VTV   -> $2153afc
021390AE  subq.l #4, D0    beq ...    class 16, Copter -> nothing
021390B2  bra    $213909a             anything else   -> the byte-0x13 dispatch
```

**An earlier note here called `0x0218AEE4` a message queue, `+2` a message type
and `0x0C` a type it "sends somewhere of its own".** All three were wrong and
they were wrong together: `0x0218AEE4` is `My_Mech_Ptr`, `+2` is `Class_ID`,
and `0x0C` and `0x10` are **classes 12 and 16** - a VTV and a Copter. So what
happens to an in-game message depends on **what the player is flying**: a VTV
handles them in its own code, a Copter ignores them, and a Mech takes them to
the byte-`0x13` dispatch.

That also keeps the two dispatches properly apart, and now names the route.
The byte-0 table is reached by **kind 3**, a packet off the wire. The
byte-`0x13` table is reached by **kind `0x0A`**. The `Post_Event(kind 0xB1,
param)` that so many byte-0 handlers end with goes to neither: kinds `0xB0`,
`0xB1`, `0xC0` and `0xD0` all land on `0x02139210`.

### `0xBE` names an owner, and there are two of them

The largest receive-only handler turns out to be short and specific. It takes
an index from the packet, refuses anything but 0 or 1, and writes into a
42-byte record:

```
0213CE32  move.l ($c,A0), (-$6c,A6)   the index
0213CE3E  cmpi.l #$2, (-$6c,A6)       0 or 1 only
0213CE58  lea    $21b74c2.l, A0       42 bytes per record
0213CE6C  move.b ($10,A0), (A1)       packet+0x10 -> record+0, a key
0213CE70  pea    $27.w
0213CE88  jsr    $215d9f4.l           strncpy(record+1, packet+0x11, 39)
0213CE92  clr.b  ($28,A0)             and terminate it
```

So each record is **a key byte and a 40-byte name**, and there are exactly
two. `0x0213B7B2` initialises both with key `0xFF`, which is the empty marker.

What the key is matched against settles what the pair are for.
`0x0211EA58` walks the two records looking for one whose key equals
**the first byte of an entity** - which the `TI ERROR!` dump calls
`Last Object Owner` - and hands the matching name back:

```
0211EB58  move.b (A0), D0            the record's key
0211EB5A  cmp.b  (-$13,A6), D0       against the entity's Owner
0211EB60  addq.l #1, A0              matched: the name is at record+1
0211EB74  addi.l #$2a, (-$18,A6)     next record, 42 bytes on
0211EB7C  cmpi.l #$2, (-$8,A6)       two of them
```

**`0xBE` names an owner.** Two owners, each with a forty-character name, looked
up by whatever owns an entity. Two owners in a BattleTech Center is two sides,
which fits the `R1_Red_Planet_1` and `B1_BattleTech_1` strings in `0xED`'s
handler - an `R` and a `B` side. The console's `SITELINK_NAME_MSG`
(`to net long, node long, site long, name string`) is the obvious candidate,
and it is a candidate, not a decode: nothing here says whether an owner is a
side, a centre or a console.

### The firmware ships with an animation editor

`0x0215DCF7` holds a state byte, and `0x02104EBA` uses it as a subscript:

```
02104EBA  move.b $215dcf7.l, D0
02104EC0  extb.l D0
02104EC2  asl.l  #2, D0
02104EC4  lea    $21698ea.l, A0     a table of string pointers
02104ECA  move.l (A0,D0.l), -(A7)
```

The table names all fifteen states:

```
 1 Rotate Camera     6 Rotate Joint     11 Manual Play
 2 Move Camera       7 Move Joint       12 Play Stopped
 3 Move Focus        8 Frame Mode       13 Loading File...
 4 Rotate Object     9 Delete Frame?    14 Saving File...
 5 Move Object      10 Auto Play        15 Appending File...
```

**The cockpit's own firmware contains an animation editor**: move and rotate a
camera, a focus point, an object and a joint; step frames; play back
automatically or by hand; load, save and append files. The function that reads
the state also prints `Frame %02ld/%02ld` and two triples of floats, which is a
frame counter and a position-and-rotation readout.

That explains several things that were loose:

- **`ANIMATOR_CLASS`** in the operator console's taxonomy, which had no
  counterpart anywhere in the pod.
- **In-game message `0x4A`**, which dumps `Joint %d Angle %f` - the editor's
  own view of a skeleton.
- **`0xF6`-`0xFF`**, which set exactly the states `0x0D`, `0x0E` and `0x0F`:
  load, save and append. They are the editor's remote control.
- **Why the archive has skeletons with named joints at all.** Somebody posed
  them, on this hardware, through this tool.

`0x021084E8` carries `Camera positions for map file` in the same region, so the
animation editor is not the only authoring tool in here - which also explains
`CAMERA_POSITION` being one of the scenario grammars the console parses.

### A game message, followed all the way in

An earlier reading here said the low opcodes are discarded and left it there.
That was incomplete in a way that mattered: **a game message does not use one of
them.** Byte 0 carries a low-level type, and anything the dispatch at
`0x02122FBC` does not claim - it knows only `0`, `1`-`7`, `0x20`, `0x21`,
`0xC7`, `0xE4` - falls through to the router at `0x0212300A`. What the router
does not consume reaches a second identity filter at `0x02123062`:

```
if buf[6..7] == [$2179D32..33]   ours, the game identity
if buf[6..7] == [$218AEB2..B3]   ours as well, a second address
else                             forward it
```

and anything ours is handed to `Post_Event` at `0x021230C8` as an **event of
kind 3**.

That path has now been walked with a real packet. Handing the pod a body whose
first byte is `0x30` - claimed by nothing - and whose byte `0x13` is a game
opcode gets all three taps:

```
--packet '30 00 ... 00 21'

  tap 0212300A hit 1      the router fall-through
  tap 02123062 hit 1      the identity filter
  tap 021230C8 hit 1      Post_Event, kind 3
```

**This is the first time anything injected from outside has reached the game's
event queue**, and it is the inbound half of what an operator console does.

What does not happen is the other half: the event sits in the queue because the
**message pump does not run**. `0x02139E64`, the dispatch that reads byte `0x13`
and turns it into an event of kind `0xB1`, is never reached during a boot. The
loop that drains the queue is part of a mission, not of coming up.

### Two receive paths, and which is which

The question left over from the identity reply was where opcodes `0x01`-`0x07`
go once a game is running, since the dispatch at `0x02122FBC` throws them away.
The answer is that they never reach that dispatch at all. **There are two
receive paths and they are not the same one.**

```
02122D9C   the receive loop
  D0 = [$21BB0EA] << 8 + $2183716      a 256-byte slot, indexed
  jsr $2146004                          take a packet from the network
  if (len > 0) {
      if (buf[0] == 0xE4) ... adjust the timebase from buf[0x0A]
      if (buf[6] != [$2179D32] || buf[7] != [$2179D33])
          forward it: this one is not ours          <- the router
      else
          Post_Event(3, 0, 0, buf)                  <- ours: queue it
  }
  pkt = monitor_poll()                   +0x18, the boot monitor's own queue
  if (pkt) { len = pkt[2]; body = pkt+4; opcode = body[0]; goto 02122FBC }
```

So the chain of `subq`/`beq` at `0x02122FBC` serves **the boot monitor's queue**
at service `+0x18`, which is where ARCNET traffic arrives - and that is where a
game message from the console lands. A packet that comes in off the **site
link** instead is posted as an event.

That also confirms the header from the receiving side. `buf[6]` and `buf[7]`
are matched against `0x02179D32`/`33`, which is exactly where the sender at
`0x021468A4` writes the game identity. The two ends agree.

### Post_Event, and a 400-slot queue

`0x021228D6` is not a dispatcher. It takes a kind and three longwords and files
them, and the firmware names it in its own error string:

```
In Post_Event, event queue full!
```

Two kinds have dedicated slots of their own rather than queue entries - kind
`0x0C` at `0x021BB0F2` and kind `2` at `0x021BB118`, each stamped with the
timebase from `0x02000808` as it goes in. Everything else, network packets
included, goes into a table at `0x021B7566` in records of **0x26 bytes** up to
`0x021BB0C6`, which is **exactly 400 slots**.

So a game message is not handled when it arrives. It is timestamped, queued,
and picked up by the game loop - which is not running, because no game has
started. The low opcodes were never being discarded by the wrong handler; they
were going to the right one, into a queue nobody is draining yet.

This is the same wall in a new place, but it is a more useful shape of wall:
it names where to look when a game does start, and it says that writing the
operator console does not need a second dispatch to be found first.


### The site link, and a correction

Two sections below were written on a wrong reading and are corrected here
rather than quietly edited. **`0x02146004` is not the game's network receive.
It is the SiteLink modem.** Its own strings settle it:

```
Modem in command mode
Answered at 115200...Syncing up.
Answered at 9600...Syncing up.
```

and the state it runs on, `0x0239DD9A`, indexes an eight-entry jump table of
connection states, with state 0 matching an `OK
` from a Hayes modem. That is
the inter-centre link from `Dial_List`, not the ARCNET the console talks over.

So of the two receive paths in the main loop, the one that posts events is the
**modem**, and the one that reaches the opcode dispatch - boot monitor service
`+0x18` - is where ARCNET traffic arrives. And the question of where game opcodes `0x01`-`0x07` are handled dissolved
once the game's own dispatch turned up: it reads its opcode from byte `0x13`,
not byte 0, and its messages run `0x21` to `0x7A`. See the section above.

What survives unchanged is the shape of both mechanisms, which is worth keeping
because both are real: `Post_Event` and its 400-slot queue, and an identity
that the firmware only ever reads. Only the wire they belong to was wrong.

### The pod's identity is something it is told, not something it works out

`0x0218AEB0` holds this cockpit's address as a `(net, node)` byte pair, and
`0x02179D32` holds the game's. Watching them across a whole boot:

```
  address    size     reads   writes  first pc
  0218AEB0   b       273621        0  02122B50
  0218AEB1   b       273621        0  02122B5E
```

**Two hundred and seventy-three thousand reads and not one write.** The
firmware never sets them; its startup clears the bss they live in and they stay
zero until something outside puts an address there. That something is the
operator console, which is why `Net_Configuration` carries a node number per
cockpit and why `COCKPIT_CONFIG_MSG` exists.

While they are zero the **site link** can do nothing - and the same pair is
read by the router filter in the main loop, so an unconfigured pod also
forwards nothing. The modem receive at `0x02146004` opens with

```
if (peer == game identity)      return -1      ; both zero: taken
if (mine != peer)               return -1
```

so an unconfigured pod returns "nothing received" before touching a device, a
buffer or a byte.

Supplying an address once the pod is running - which is what a configured
cockpit looks like - gets past it:

```
--set-at 02122D9C 0218AEB0=01020000 --set-at 02122D9C 0218AEB4=00000102 \
--tap 0214604E

  set 0218AEB0 = 01020000 at pc 02122D9C
  tap 0214604E hit 1
  tap 0214604E hit 2
```

The receive body now runs every time round the main loop. What it does there is
a jump table on a state at `0x0239DD9A`, eight states wide, and the state is
**0** - where it touches no hardware at all. No new address appears in the
unmapped log, so the received data is software-buffered rather than read from
the ARCNET controller at this point, and states 1 to 7 are the next question.

Two small tools came out of this and are worth keeping. `--peek ADDR:N` reads
memory when the run ends, which is how the zeros were found; `--set-at PC
ADDR=HEX` writes a longword the first time execution reaches an address, which
is the only way to supply configuration that the firmware's own startup would
otherwise wipe.


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

### The first opcode with a name: `0xC5`

Putting names to the 38 opcodes the pod sends means reading the other end, and
one of them can be had without any of that work.

`0x02145E1C` builds a message and the shape is distinctive:

```
02145E1C  link  A6, #-$64
02145E24  pea   $50.w                 up to 0x50 bytes
02145E28  move.l ($8,A6), -(A7)       the caller's string
02145E2C  pea   (-$5c,A6)
02145E30  jsr   $215D9F4              strncpy
02145E36  move.b #$C5, (-$64,A6)      the opcode, at the struct's base
02145E3C  move.l ($c,A6), (-$c,A6)    a longword from the caller
02145E4E  ... two words from $239DD9E and $239DDA4
```

So a `0xC5` carries **a text line of up to eighty characters and a number**.
Its callers are the arms of the SiteLink modem's state machine - the ones that
print `Modem in command mode` and `Answered at 115200...Syncing up.`

The console logs exactly one message with that shape, and it is the router's:

```
ROUTER_STATUS_MSG from node %ld, status %s, status code %ld
```

a status **string** and a status **code**, from the router. Sent by router code,
carrying a string and a number, and the only console message of that
description. **`0xC5` is `ROUTER_STATUS_MSG`.** That is inference from three
agreeing facts rather than a decode, so it is written here as such - but it is
the first opcode in this protocol with a name, and it was free.

The console's own code corroborates the *shape* if not the name: `CODE_18`
compares a received packet's byte against `#$C5` and nothing else in that form,
which is what a special case for one message type looks like.

### What reading the console's globals cost, and what it bought

The plan was to resolve the console's globals and trace `A5` displacements to
the message encoders. **THINK C's far model does not use `A5` that way**: this
application has **zero `lea (d16,A5),An` sites and eight `pea (d16,A5)` in 260
KB of code.** It puts absolute 32-bit `DATA` offsets inline in the code
instead, and `CREL` says where they are - a flat list of ascending 16-bit
offsets per segment, each naming a longword that holds one. `DREL` does the
same inside `DATA`, in two encodings, both measured as `DATA_size + (v -
0x10000)`.

That is confirmed rather than assumed, and it now lives in `macrecomp` as
`tools/relocs.py`, which is where general THINK C support belongs.

### The console's log strings are not statically referenced

The message names and field lists this project relies on - `COCKPIT_CONFIG_MSG
node %d, forward %d, name %s` and its thirty neighbours - sit in the console's
`DATA` resource from `0x7572` to `0x93C0`. Finding the code that passes each
one to its logger would give the opcode that goes with it, which is the last
thing standing between here and a working operator console.

**Nothing in the application refers to them.** That is measured, not assumed:

| looked for | result |
|---|---|
| a `CREL` fixup site holding the string's offset | all **4,256** fixups target `0x0072`-`0x31CA`; none above |
| a `DREL` slot holding a pointer to it | slot contents that are valid offsets stop at `0x7468` |
| any `DATA` longword equal to the offset | none, across all 39,096 bytes |
| the offset as a 32-bit constant in any segment | none |
| the offset as a 16-bit constant in any segment | none |
| `pea (d16,A5)` / `lea (d16,A5),An` with a fitting base | 8 sites and **0** sites respectively, no base fits |

The extraction is not the problem: `DATA.bin` matches the resource fork byte
for byte from file offset `0x156`, and the same technique does find references
to other strings - `CArray.c`, `CObject.c`, `CWindow.c`, an assertion message -
through `CREL` sites and `DREL` slots alike. The mechanism works. These
particular strings are simply not on the end of it.

Two leads remain, both unexplored:

**Five of the twenty code segments carry no `CREL` at all** - `CODE_0`, `1`,
`11`, `12` and `13`, the last three being 500, 3,714 and 1,274 bytes. Whatever
reaches its data another way is in there.

**`DATA` opens with a longword `600` and then 600 words**, with strings
beginning around `0x4B4`. There are also exactly 600 printable strings in the
resource, which is a striking coincidence - but the table is not an index of
them: read as offsets in any of three framings, only 12 to 16 of the 600 land
on a string start, where an index would land on all of them. So the coincidence
stays a coincidence until something explains it.


### The console as its own specification

The plan was to lift the operator console's code to read what it puts on the
wire. In the end no lifting was needed: **the console logs every message it
sends, by name and with its fields**, and those `printf` format strings sit in
its `DATA` resource in one contiguous region, `0x7572`-`0x93C0`. A format
string is a field list written by the program that sends it.

`tools/opscon.py` reads them out — 31 messages, and it is checked against
`tools/logproto.py`, which recovers the same vocabulary from the other end: the
`Console Log` a real centre kept through 1995. The sender and its diary agree.

```
COCKPIT_CONFIG_MSG   node int, forward int, name string
PLAYER_CONFIG        node int, cockpit string, name string
PLAYER_LINK          node long, name string
IDENTIFY_YOURSELF    node long
SHADOW_ROM           node int
MECH_CLASS           thing long, class long, x float, y float, z float
CREATE_THING         node long, name string
FINAL_LAUNCH_MSG     to net long, node long, cockpitsRunning long
NET_CONFIG_SEND_MSG      to net long, node long
GAME_SETUP_SEND_MSG      to net long, node long
CONSOLE_CHAT_MSG         to net long, node long, msg string
CONSOLE_CONTROL_MSG      to net long, node long, type long
ROUTER_MODEM_COMMAND_MSG node long, command string, function long, timeout long
ROUTER_STATUS_MSG        from node long, status string, status code long
SITELINK_NAME_MSG        to net long, node long, site long, name string
```

The entity taxonomy comes with it, and it is wider than the vehicle list
suggested. Alongside `MECH_CLASS` there are `VTV_CLASS`, `HOVER_CLASS`,
`COPTER_CLASS`, `CAMERAMAN_CLASS`, `ANIMATOR_CLASS`, `POD_CLASS` and
`EXPLOSION_CLASS` — three of which the console will tell you are *unsupported*
by this build, which is itself worth knowing.

Some other things fell out of the same region:

```
ERROR: Orig. %d, Pri. %d, Num. %ld, Time %ld, String:
Packet_Check: *Unknown type* Orig. %ld, Type %ld
Source %d, Destination %d, Count %d
```

so a packet carries an **origin, a priority, a sequence number and a
timestamp** — the header this project has been guessing at from the receiving
side.

### The map file format, for free

The console reads the release's own data files with `scanf`, and those grammars
are in the same region, each followed by the log line naming what the parsed
line becomes. `opscon.py --formats`:

```
GROUND_CLASS      %d %d %f %f %f %f %f %d %d
TERRAIN_CLASS     %d %d %f %f %f %f %f %d
ICON_CLASS        %d %d %f %f %f %f %f %d
SWITCH_CLASS      %d %d %f %f %f %f %f %d %d %d %d %d
DOOR_CLASS        %d %d %f %f %f %f %f %d %d %f %f %d %d
LIGHT_CLASS       %d %d %f %f %f %f %f %d %d %d %f %f %f %f %f %f %f %f %f
CAMERA_POSITION   %d %d %f %f %f %f %f %d "%[^"]" %d %d %d %f %f
VTV_CLASS         %d %f %f %f %f %d %d
MECH_CLASS        %d %f %f %f %f %d %d
```

with the log lines reading the first fields back as `thing`, `class`, `shape`,
`x`, `y`, `z`. The setup files come with them —
`Reading Net_Configuration` takes `%d %d %d %d %d %d %d %s %s "%[^"]"`, which
is exactly the ten columns `Net_Configuration` documents in its own comments,
and `Game_Setup` takes `%d %d %d %d %d %d %d "%[^"]"` followed by a scenario
file, a time, an environment and a haze setting.

### What is still missing

The fields and their C types, not their **order and width on the wire**. A
`long` in a log line is a `long` in the program, but whether it goes out as
four bytes, two, or ASCII is not something a format string can tell us. That
does need the code — and now it is a narrow question about a handful of
functions in `Start.c` and `Load.c` rather than an open one about a 260 KB
application.


### The renderer's error block, named by the ROM

`TI ERROR!` is printed with a fixed dump of fifteen longwords, and the ROM
labels every one of them. The dump is a straight run from `0x3FFFE164` in the
renderer's window:

```
3FFFE164  TI_RoutineID          3FFFE184  TI_LastCommand
3FFFE168  TI_ErrorNumber        3FFFE188  TI_ShapePCOffset
3FFFE16C  TI_ProfileSP          3FFFE18C  TI_ProcPC
3FFFE170  TI_FPUStatus          3FFFE190  TI_ScanConv_Flag
3FFFE174  TI_FPUPC              3FFFE194  TI_PolygonCount
3FFFE178  TI_VideoIntTimer      3FFFE198  TI_LastObject
3FFFE17C  TI_LastShape          3FFFE19C  TI_ProcSP
3FFFE180  TI_LastZone
```

followed by `Processor Stack Dump from 0x%x` and `Profile Stack Dump`, eight
longwords each.

**This settles two addresses that were measured and unexplained.**
`0x3FFFE168` and `0x3FFFE174` are read by the main game loop and pushed onto
Remote I/O displays `0x80` and `0x86` as raw `%08x`; what they counted was
listed as unknown. They are **`TI_ErrorNumber`** and **`TI_FPUPC`** - so the
cockpit puts the renderer's error code and the address its floating-point unit
died at on the panel, where an operator can read them off a cabinet that will
not start. That is exactly the kind of thing an arcade site needs and exactly
the kind of thing no manual bothers to write down.

`TI_LastObject` is not a pointer but a **`Number`** - the dump indexes the
entity table with it:

```
02138DDA  move.l $3fffe198.l, D0      TI_LastObject
02138DE0  asl.l  #2, D0
02138DE2  lea    $2189f10.l, A0       the entity table
02138DE8  move.l (A0,D0.l), (-$a2,A6)
02138DF2  move.l ($2,A0), -(A7)       "Last Object Class %d"
02138E08  move.w (A1)+, (A0)+         "Last Object Owner %d", from +0x00
```

### The entity header, in the firmware's own words

Three of those labels name fields this project had located but not named. The
periodic status report prints, from `My_Mech_Ptr`:

```
02139B4E  move.l ($2,A0), -(A7)
02139B44  move.l ($6,A0), -(A7)
02139B3A  move.l ($a,A0), -(A7)
02139B52  pea    "Class_ID=%d, Number=%d, Thing_Flags=0x%08x"
```

so:

| | |
|---|---|
| `+0x00` word | **Owner** - from the `TI ERROR!` dump's `Last Object Owner` |
| `+0x02` long | **Class_ID** - the field every handler switches on |
| `+0x06` long | **Number** - the id that goes on the wire, and the table index |
| `+0x0A` long | **Thing_Flags** |

`Number` being both the wire id and the subscript is now confirmed from three
directions: the senders read `+0x06` into the packet, the handlers index the
table with what the packet carries, and the error dump indexes the table with
a field it calls `TI_LastObject`.

**`0x0218AEE4` holds `My_Mech_Ptr`** - a pointer to this pod's own entity. An
earlier note here described it as the source of a message pump, which is what
the code around it does with it; naming it settles what it points at.

The same report is worth knowing about for its own sake:

```
----- PERIODIC -----
Average fps   %f
Worst case    %d (%f fps)
Best case     %d (%f fps)
Currently     %d (%f fps)
Remaining time = %ld
My_Mech_Ptr = %p
Class_ID=%d, Number=%d, Thing_Flags=0x%08x
```

The pod keeps its own frame-rate statistics and prints them on the console,
which will be the measurement to beat when any of this runs.

### The in-game messages start to have names

With the arms of the byte-`0x13` dispatch mapped one-to-one to opcodes, the
ones that log something name themselves:

| | |
|---|---|
| `0x4A` | `Joint %d Angle %f` - dump the skeleton's joint angles |
| `0x51` | `Profile Cleared` |
| `0x64` | dump every mech: `Mech %d`, `Type %d, Color %d, Flags %d`, `Course %3.5f, Speed %3.5f, X %3.5f, Y %3.5f, Z %3.5f` |
| `0x71` | a hex dump |
| `0x73` | the periodic status report |

These are operator and developer commands, which is what one would expect of a
message type a console sends to a pod mid-game.

### `+0x26`, `+0x2A` and `+0x2E` are X, Y and Z

`0x64`'s dump settles the oldest assumption in the entity work. The arguments
to `Course %3.5f, Speed %3.5f, X %3.5f, Y %3.5f, Z %3.5f` are pushed
right-to-left:

```
021396CE  adda.l #$2e, A0    fmove.s (A0), FP0   push     Z
021396E0  adda.l #$2a, A0    fmove.s (A0), FP0   push     Y
021396F2  adda.l #$26, A0    fmove.s (A0), FP0   push     X
02139704  adda.l #$114, A0   fmul.d #360.0       push     Speed
02139722  adda.l #$f8, A0    fmove.s (A0), FP0   push     Course
02139730  pea    "Course %3.5f, Speed %3.5f, X %3.5f, Y %3.5f, Z %3.5f"
```

so the three longwords every entity message carries after the id are **X at
`+0x26`, Y at `+0x2A` and Z at `+0x2E`** - the firmware's own words, not an
inference from the console's field lists. Two more fields come with them:
**`+0xF8` Course** and **`+0x114` Speed**, the latter scaled by 360 on the way
out, which is what turns a fraction of a revolution into degrees.

### A second table: thirty mechs

The same dump walks a table that is not the entity table:

```
0213966A  move.l (-$4,A6), D0
0213966E  asl.l  #2, D0
02139670  lea    $21943da.l, A0      thirty slots
02139676  move.l (A0,D0.l), (-$8,A6)
0213967C  tst.l  (-$8,A6)            empty: skip
0213968A  tst.l  ($a,A0)             Thing_Flags zero: skip
02139742  cmpi.l #$1e, (-$4,A6)
```

**`0x021943DA` holds thirty entity pointers**, and the boot clears all thirty
in the same routine that builds the entity arena - `clr.l (A0,D0.l)` with
`cmpi.l #$1e`. So the thousand-slot arena holds everything in the world and
this holds the **participants**: thirty is the number of mechs a game can have,
and it is the table an operator's "show me every mech" walks.

Two more fields are named by that dump as well: **`+0x7E` Type** and
**`+0x82` Color**, both words.

## Driving a mech and asking the pod where it is

Everything the last few sections found can be put in one line, and it closes a
loop this project has been working towards from the beginning.

Make entity 0 a `Mech` and put it in the thirty-slot table:

```
--set-at 02122154 21F99AE=00000001    Class_ID = 1
--set-at 02122154 21943DA=021F99AC    slot 0 -> entity 0
```

send it a movement packet at the wire - opcode `0xEC`, entity id 0, then X, Y,
Z, Course and Speed where the field map says they go - and type `d` at the
in-game console. The pod answers:

```
dMech 0
Type 0, Color 0, Flags 7
Course 1.00000, Speed 90.00000, X 100.00000, Y 200.00000, Z 5.40000
```

Every step between the wire and that print is the cockpit's own code: the
low-level dispatch, the router, the identity filter, `Post_Event`, the event
pump, the byte-0 message table, `0xEC`'s handler, the entity structure, the
in-game keyboard, and the dump routine. Nothing is faked except giving the
entity a class.

**Speed comes back as 90 from a packet that carried 0.25**, because the dump
multiplies `+0x114` by 360 on its way out - which is the field map and the
printf argument order both being right at once. And `Z` is 5.4, which is the
height every scenario drop point in the release uses.

### One emulator gap had to be closed first

The moment an entity is a `Mech`, the firmware reaches an FPU operation
Musashi does not implement:

```
fpgen_rm_reg: unimplemented opmode 0F at 0212E37A
```

Opmode `0x0F` is **FTAN**. Musashi implements a useful subset of the 68881's
transcendentals and calls `fatalerror()` on the rest, and the mech code needs a
tangent. `tools/musashi_fpu.py` adds the missing sixteen - `FSINH`, `FLOGNP1`,
`FETOXM1`, `FTANH`, `FATAN`, `FASIN`, `FATANH`, `FTAN`, `FETOX`, `FTWOTOX`,
`FTENTOX`, `FLOGN`, `FLOG10`, `FLOG2`, `FCOSH`, `FACOS` - each a one-line libm
call in the shape the existing `FSIN` and `FCOS` cases already use. It is a
script rather than a patch file because `third_party/musashi` is cloned by
`make deps` and a context diff rots against upstream; it is idempotent and
`make deps` runs it.

## Starting a mission

`0xED` is dispatched on the class of the entity it names - and the id is at
packet `+0x32`, not `+0x08`:

```
0213BA74  move.l ($32,A0), D0     the entity id
0213BA7A  lea    $2189f10.l, A0
0213BA8A  move.l ($2,A0), D0      its Class_ID
0213BA8E  bra    $213bbae         eight arms
```

The arms cover classes **1, 7, 9, 10, 12, 13, 16 and 19**, and the last one is
the interesting one:

```
0213BB9A  jsr $213fa0e.l
0213BBA4  jsr $211786c.l          start the mission
```

`0x0211786C` schedules `0x02117788` as a **kind `0x10000` event three ticks
out**, and `0x02117788` reschedules itself the same way every time it runs. It
is the task that creates things.

**So a mission is started by sending `0xED` to a class 19 entity.** Give
entity 1 a `Class_ID` of 19 and send one:

```
tap 0213BB92 hit 1     the class 19 arm
tap 0211786C hit 1     mission start
tap 02117788 hit 16    the spawner, ticking
```

where the spawner had never run at all before. **Class 19 is the mission
itself**, not a vehicle - which is why `Create_Thing` refuses to build it, its
table stopping at 18, and why `0xE8` carries a teardown arm for a class no
constructor makes.

`0x02193C1C` is the **mission clock in hundredths of a second** - the spawner
divides it by 100.0 - and it is negative on a pod with no mission. Setting it
to 60000 makes the spawner take its active branch at `0x02117802` instead of
the idle one.

**What is still missing is the script.** The spawner runs, takes the active
branch, and creates nothing, because what to create and when is scenario data
the operator console sends. That is the same gap as the mission sequence in
ROADMAP.md, now reached from the other end.

## Missions are bytecode

Following the spawner down gives the thing this project had no idea was there.

The task `0x02117788` hands four arguments to `0x021187D0`, one of them a
structure at `0x021A5DBC`, and that structure is a **script object**:

| | |
|---|---|
| `+0x0000` | the script's program counter, saved across calls |
| `+0x1C84` | the operand stack pointer |
| `+0x1C88` | a second stack pointer |
| `+0x1C90` | a wait timer, counted down by the elapsed time |
| `+0x1C94` | the next thing to create |
| `+0x1C98` | the mission clock reading at which to create it |

and the loop that runs it is a **bytecode interpreter**:

```
021188BE  movea.l (-$10e,A6), A0     the script PC
021188C2  addq.l  #1, (-$10e,A6)
021188C8  move.b  (A0), D0           fetch one byte
021188CA  bra     $21198a6
...
021198A6  cmpi.w #$a2, D0            162 opcodes
021198AA  bcc    $211972e             out of range
021198B0  lea    (-$150,PC), A0       the table, at 02119762
021198B8  jmp    (PC,D0.w)
```

**162 opcodes, of which 94 have a handler** and 93 handlers are distinct. The
ROM names the machine itself in its own error messages:

```
Interpreter error, bad opcode %02xh at offset 0x%04lx!
Popped NULL return address, interpreter stopping.
```

so it has a call stack as well as an operand stack, and the operand stack is a
stack of **0x4C-byte frames** at `0x021B74B6` - the readers `0x02119D16` and
`0x02119D48` pop one and return its `+0x04`, one as an integer and one after
multiplying by 100 and truncating, which is how a script says *seconds* and the
engine stores hundredths.

The opcode that schedules a spawn is one of the 94:

```
021189D4  jsr    $2119d48.l           pop: what to create
021189DC  move.l D0, ($1c94,A0)
021189E0  jsr    $2119d16.l           pop: when, in seconds
021189E8  fmul.d #$40590000, FP0      x 100
02118A00  move.l D0, ($1c98,A0)
```

**So a mission is a program, and the world is populated by running it.** The
spawn list is empty on a pod that has been handed no mission - `+0x1C94` reads
zero and `+0x1C98` reads `0xFFFFFFFF` - which is the whole reason nothing has
ever appeared in a frame. Not a missing flag, not an unset field on an entity:
no program.

### The missions are in the ROM

`0x021186BC` is how the interpreter is entered, and its third argument is a
**name**: it walks to the NUL, and truncates anything longer than sixteen
characters. Its second argument is `[0x0216F49C]`, which on a booted pod is
`0x0216B378` - a table of named entry points in the ROM's own data.

An entry is a NUL-terminated name and a big-endian 16-bit offset, and the table
has no count; it simply stops. `tools/missions.py` reads it:

```
B1_BattleTech_1    06FC
B2_BattleTech_2    0A88
FC1_Follow_Cockp   113A      FC5_Follow_Cockp   1186
FC2_Follow_Cockp   114D      FC6_Follow_Cockp   1199
FC3_Follow_Cockp   1160      FC7_Follow_Cockp   11AC
FC4_Follow_Cockp   1173      FC8_Follow_Cockp   11BF
exitScreen         11D2
T1_Nose_Only_1     13D3
T2_Camera_Only_1   1499
```

**Thirteen routines: two BattleTech scenarios, eight follow-a-cockpit cameras,
an exit screen, a nose camera and a camera-only view.** Which is a BattleTech
Center's whole repertoire - the game, and the spectator displays that watched
it.

`B1_BattleTech_1` is one of the strings sitting in the `0xED` handler, beside
`R1_Red_Planet_1`. An earlier note here guessed those were **side
identifiers**, an `R` side and a `B` side. They are **script names**, and
`0xED` names the script to run.

### How a mission is set up

`0xE4` turns out to be multiplexed: its handler reads packet `+0x0E` and
dispatches twenty ways, `-1` to `18`. **Sub-command 13 builds a mission
record.** Sending one reaches `0x0211743C`, which:

- copies a **name** out of the packet into the record's first bytes;
- clears seven words at `+0x450`-`+0x45C` and stamps the timebase at `+0x45E`;
- initialises **two sub-objects of `0x79A6` = 31,142 bytes** at `+0x466`;
- and calls the interpreter's init on the script object at `+0xF7B2`, which is
  exactly where those two sub-objects end.

So a mission record is about 70 KB, and `0x021A5DBC` holds the one the pod is
running. The init clears the program counter to **zero** - the bytecode is
supplied by entering a routine by name, not by loading a file.

### Running a mission script

The last link is short. `0x0211786C` - the mission start that class 19's `0xED`
arm reaches - ends by calling `0x02117C28`, which enters the interpreter by
name, and the name it passes is **the `0xED` packet's `+0x0A`**:

```
021179A4  movea.l ($8,A6), A0
021179A8  adda.l  #$a, A0        the name, in the packet
021179B0  move.l  (-$8,A6), -(A7)
021179B4  jsr     ($272,PC); ($2117c28)
```

So one message does all of it. Give entity 1 a `Class_ID` of 19, put
`B1_BattleTech_1` at `+0x0A` of an `0xED` packet and the entity's id at
`+0x32`, and send it:

```
peek 021A5DBC:  42 31 5F 42 61 74 74 6C 65 54 65 63 68 5F 31 00
                B  1  _  B  a  t  t  l  e  T  e  c  h  _  1
script PC:      0216B7F1        in the ROM's bytecode, past the name table
tap 021188BE    the fetch-decode loop, running
```

**The mission's bytecode is executing.** The spawner hands the interpreter an
elapsed time every few ticks, the script sets a wait of `0x4C` hundredths -
three quarters of a second - and the timer counts down by four per call and is
set back to `0x4C` again, so the program is **looping on a wait**.

Nothing is created yet. The script runs and waits, and what it is waiting for
is the next question - a start signal, or players, or a state the pod has not
been put in. But the machine underneath it is working: a named routine in the
ROM, entered by a message off the wire, executing on an interpreter, driven by
a scheduled task, with its own wait timer counting down in real time.

### Reading a mission

`tools/mission_dis.py` disassembles one, and both things it needs come out of
the ROM rather than out of a guess.

**Where a routine starts.** The name lookup at `0x021186FC` reads the entry's
16-bit value and *adds the table's own address*, so the program counter is
`table + offset` and the name table sits at the front of the blob it indexes.

**How long an instruction is.** Every handler that takes an operand begins by
stepping the interpreter's program counter, and that step is one instruction -
`addq.l #1,(-$10e,A6)`. Counting those in a handler gives the operand length,
measured rather than assumed:

```
opcodes with a handler: 94
opcodes that are control flow: 7
  taking 0 operand bytes: 74
  taking 1 operand bytes: 13
  taking 2 operand bytes: 7
```

So it is a **stack machine**: four fifths of the instruction set takes no
operand at all. And the two counts line up exactly - **the seven opcodes that
take a 16-bit operand are the seven that write the program counter**, so a
two-byte operand is a jump displacement.

Two things had to be corrected to get there, and both were the tool's fault
rather than the firmware's. Some arms read a 16-bit operand through
`0x0211995C` instead of stepping the counter twice, so counting only the byte
steps ran the disassembly off the rails at the first jump. And a first attempt
at spotting control flow looked for any instruction touching `(-$10e,A6)`,
which marked three quarters of the instruction set as branches - **reading**
the program counter is how every operand-taking arm starts; only a write is a
jump.

`B1_BattleTech_1` begins:

```
0216BA74  49 01      0216BA80  47 01
0216BA76  49 01      0216BA82  47 01
0216BA78  49 01      0216BA84  4A 08
0216BA7A  4B 01      0216BA86  65 08
0216BA7C  4B 01      0216BA88  45
0216BA7E  47 01      0216BA89  42
```

and that is **exactly the opcode sequence the running pod executes** - tapping
the interpreter's dispatch on a live mission gives
`49 49 49 4B 4B 47 47 47 4A 65 45 42 ...`. The disassembler and the machine
agree, which is the only check available on either.

`42` is a jump, and the tool now says where to:

```
0216BA89  42  F9 DA   jump -1574 -> 0216B466
```

`0x0216B466` is the byte **immediately after the name table ends**, which is
where a program's body would start - and disassembling from there gives
`61 00, 65 FD, 72, 61 01, ...` against a live trace of `61, 65, 72, 61`.
The two readings agree across a branch as well as along a straight line.

### The first opcodes with names

Two of the 94 can be named from what they write, without reading a line of
their logic:

| | |
|---|---|
| **`0x0B`** | writes the script object's `+0x1C94` and `+0x1C98` - **at this time, run this routine**. It pops the what, then pops the when and multiplies it by 100, which is a script saying *seconds*. |
| **`0x02`** | writes `+0x1C9C`, clamped to at least 1 and compared against 2 - a small mode or count |

**And `0x0B` executes.** Running `B1_BattleTech_1` with a class 19 entity and
watching its handler: one hit.

**It is not a spawn.** An earlier reading of this called `0x0B` *create this
thing*, on the strength of the field it writes being consumed by the task that
creates things. What the task actually does with `+0x1C94` is pass it as the
**third argument of the interpreter entry** - and that argument is a *string*,
walked to its NUL and truncated at sixteen characters. So `0x0B` is
**at time T, enter this routine by name**, the same mechanism `0xED` uses to
start a mission in the first place. A mission program schedules other script
routines, and whatever creates a thing is inside one of them.

What still does not happen is the creation. The walker only acts on a queued
spawn when its due time has passed:

```
021187E6  movea.l ($1c98,A0), A0     when this thing is due
021187EA  cmpa.l  $2193c1c.l, A0     against the mission clock
021187F0  blt     $211880a           not yet
```

and `0x02193C1C` is **negative** on a pod nobody has given a game length to, so
nothing is ever due. Forcing a large value into it at the comparison does not
help - the interpreter then runs once instead of twice, so the clock is load
bearing somewhere earlier as well, and setting it behind the firmware's back
breaks more than it fixes.

**So the last missing input is a game length**, and that is something the
operator console sends: `Game_Setup` in the release carries a time, and
`FINAL_LAUNCH_MSG` is in the console's vocabulary. The pod has a mission, a
program, a spawn instruction that runs and a thing waiting to be made; what it
has not been told is how long the game lasts.

### The game length, and a sequence of packets

`0xE5` - the one that prints `WELCOME %s` - carries the game length:

```
0210E21E  move.l ($3c,A0), D0        the packet's +0x3C
0210E224  lsl.l  #1, D0              x 2
0210E226  add.l  D1, D0              x 3
0210E228  lsl.l  #3, D0              x 24
0210E22A  add.l  D1, D0              x 25
0210E22C  lsl.l  #2, D0              x 100
0210E22E  move.l D0, $2193c1c.l      the mission clock
```

**seconds times a hundred**, which is the hundredths the rest of the engine
counts in. And the main loop drains it:

```
02138F40  sub.l D0, $2193c1c.l
```

so the mission clock counts **down**, and it is negative on an idle pod for the
plainest reason there is - it has been draining from zero since the machine
booted.

That needed a second packet before the `0xED` that starts a mission, and
`--packet` could only hold one, so it now takes up to eight and delivers them
in order. A mission needs a *sequence* - a game length, then a mission, then a
start - and one packet could never have expressed that.

With `0xE5` and then `0xED`, all three landmarks fire in order: the `0xE5`
forwarder, the clock write, the `0xED` handler. The mission runs, its spawn
opcode executes, and **still nothing is created** - so there is at least one
more input, and the honest thing is to say that rather than to keep forcing
values into globals until something moves.

### A thing is only ever made by a script

`Create_Thing` is called from **exactly one place in the whole ROM**, and that
place is a bytecode opcode handler:

```
02118D06  jsr $2119d48.l      pop
02118D0E  jsr $2119d48.l      pop
02118D16  jsr $2119d16.l      pop, as an integer
02118D1E  jsr $2119d16.l      pop, as an integer
02118D26..02118D36            push all four, and the script
02118D3A  jsr $211dc1e.l      Create_Thing
```

**Opcode `0x24` creates a thing**, taking four operands off the script's stack
- two raw, two as integers. The opcode immediately before it calls
`0x0211DC14`, a sibling constructor, so there is more than one way for a script
to make something.

That looked like it settled the shape of the whole system - a mission program
populating a world instruction by instruction, with every other route
considered here looking in the wrong place. **It does not.** No mission script
in this ROM contains a `0x24`: walking all thirteen routines from their
entries, following both arms of every branch, finds none. `Create_Thing` has
one caller in the ROM and no script reaches it. See "`0x24` is not what the
mission was failing to do" below.

### What a mission actually executes

`--vmtrace` logs the interpreter's dispatch register, which gives the exact
opcode stream a mission runs - the only ground truth there is for a
disassembler working from operand lengths it inferred.

`B1_BattleTech_1`, started properly with a game length and a class 19 entity,
executes **8192 opcodes** before the budget runs out, using **65 distinct**
ones. It begins exactly as the disassembly says:

```
49 49 49 4B 4B 47 47 47 4A 65 45 42 | 61 65 72 61 61 61 61 70 61 65 72 61
```

- the twelve instructions of the entry, then the jump, then the body.

The ten most-used, with counts:

```
61:2416  65:1309  62:637  73:459  70:342  39:240  3C:222  33:221  72:144  4B:130
```

`0x61` alone is a third of everything executed, which is what a push looks
like in a stack machine.

**`0x0B` runs once and `0x24` never runs at all.** The second half of that is
not a finding: no mission script contains a `0x24` to run. The first half
stands - the mission schedules one routine - and so does the shape of the run:
it is not stuck, the opcode mix is wide and changing, and it revisits a hot
address every hundred to two hundred instructions across 979 distinct
addresses. That is a main loop doing work, not a spin.

### The stack is typed, and five opcodes have names

`0x02119A50` is the push:

```
02119A54  movea.l $21b74b6.l, A0
02119A5A  move.l  #$2, (A0)            a type tag
02119A66  addi.l  #$4c, $21b74b6.l     one frame on
02119A72  move.l  ($4,A7), (A0)        the value, at +4
```

So an operand is a **0x4C-byte frame with a type at `+0x00` and the value at
`+0x04`** - which is why the readers return `+0x04`, and why there are separate
ones for integers and floats. Pushing an integer writes tag `2`. The
interpreter does floating-point arithmetic too: one arm pops two values with
`0x02119CF6`, `fadd`s them and pushes the result.

With that, five instructions can be named:

| | |
|---|---|
| `0x0B` | at time T, enter this routine by name |
| `0x24` | create a thing - four operands, the ROM's only call to `Create_Thing`; no mission script uses it |
| `0x42` | jump, signed 16-bit displacement from the end of the instruction |
| `0x60` | push a 16.14 fixed-point constant, four operand bytes |
| `0x64` | push the address of the next instruction as a value, then skip forward over the block it names |
| `0x09` | take an `$FF`-terminated byte list into the mission record at `+0x1CA0` |
| `0x44` | **return** - pop the program counter; a null one prints `Popped NULL return address, interpreter stopping.` and halts |
| `0x61` | push a byte |
| `0x62` | push a 16-bit word |

`0x61` and `0x62` between them are over a third of everything a mission
executes, which is what a stack machine looks like from the outside.

### Locals, and two families of built-ins

**`0x65 n` pushes local `n`.** Its helper multiplies the operand byte by the
frame size and adds a second base pointer:

```
02119A10  muls.w #$4c, D0
02119A14  add.l  $21b74be.l, D0
```

So `0x021B74BE` is a **frame base**, not a second stack in the loose sense, and
the script object's `+0x1C88` - saved beside the operand stack pointer when the
interpreter yields - is where a routine's locals live. `0x65` is the
second-busiest instruction in a running mission, which is what reading
variables looks like.

**Two opcodes are multiplexed.** `0x70` and `0x73` take an operand byte and
dispatch on it again, and both sub-tables are **eleven wide**:

```
0211A004  cmpi.w #$b, D0     0x70's eleven
0211A340  cmpi.w #$b, D0     0x73's eleven
```

No other one-operand opcode does this; for the rest the operand is data. What
the operand *selects* is below - not a built-in, a **type**.

### Six value types, and two type-dispatched instructions

Calling `0x70` and `0x73` families of built-ins was the wrong reading. Both
sub-tables have **eleven slots and six implemented** - 0 to 4, and 10 - and
`0x73`'s own error message says what the operand is:

```
deref:Illegal value type %d!
```

**It is a type code.** `0x73 t` **loads** a value of type `t` - its arms end in
the push helper - and `0x70 t` **stores** one, its arms beginning with a pop.
Type 0 is a **string**: `0x70`'s slot 0 pops and then calls `strncpy`. Type 2
is the integer the plain push tags its frames with.

So the machine is typed all the way through: a 0x4C-byte operand frame carries
its type, `0x73` and `0x70` are the typed load and store, and six of a possible
eleven types exist. Which also explains why they are among the busiest
instructions in a mission - they are not calls out to the engine, they are how
the program reads and writes anything at all.

### The control flow, named

Seven opcodes write the program counter, and a real mission's execution counts
say which matter:

| | | |
|---|---|---|
| `0x64` | 127 | transforms the PC through `0x02119CC4`, which consumes a byte |
| `0x41` | 114 | **conditional branch** - reads a 16-bit displacement, pops a condition, adds the displacement if it holds |
| `0x42` | 84 | **unconditional jump**, 16-bit displacement |
| `0x44` | 84 | **return** - pop the PC; a null one halts the interpreter |
| `0x40` | 51 | the other 16-bit-displacement branch |
| `0x07` | 60 | a matched pair with `0x08`, each handing the PC to a helper |
| `0x08` | 59 | and taking a new one back |

`0x41` being the busiest branch, and `0x42` and `0x44` running the same number
of times, is what a program full of small routines and one polling loop looks
like.

**One of them defeats the operand-length rule.** `0x64` hands the program
counter to its helper *by value* and takes a new one back, and the helper does
the `addq.l #1` on its own copy - so counting the arm's own steps cannot see
the operand. There is no general rule for that, so `mission_dis.py` carries a
one-entry exception table with the reason written next to it rather than a
heuristic that would mislabel something else.

With it, `B1_BattleTech_1`'s body walks 55 instructions and stops at the same
address it stopped at before - `0x0216B4D4`, an opcode with no handler - which
is what the end of a routine looks like from a linear disassembler. The tool
stopping in the same place with a different rule is the evidence that it is
the routine ending rather than the rule being wrong.

### What the mission is not waiting for

`0xED`'s class 1 arm is the player-link path - the one whose neighbourhood
carries `Hover_Player_Link()` and the chassis names. It is reachable: give
entity 1 a `Class_ID` of 1, entity 2 a `Class_ID` of 19, and send three
packets in order - a game length, an `0xED` naming entity 1, an `0xED` naming
entity 2 with `B1_BattleTech_1` - and both arms run.

**It changes nothing.** The mission executes **8192 opcodes using 65 distinct
ones, with and without a linked player, and the two traces are identical** -
not merely similar in shape, the same opcodes in the same order. `0x24` runs
neither time.

So the loop is not waiting for a player. That is worth having: it was the
obvious hypothesis, and it is wrong.

It is not waiting for the renderer either. Run the same mission with and
without `--rirq` - with the renderer completing frames and with it never
completing one - and the traces are again identical, opcode for opcode.
Run `B2_BattleTech_2` instead of `B1_BattleTech_1` and the trace *does*
diverge, at the 1418th opcode, so the trace is not a constant: it responds to
the script and to nothing else we can currently vary.

### `0x24` is not what the mission was failing to do

The premise under all of the above was wrong. Walk every one of the thirteen
routines from its entry, following both arms of every branch, and **not one of
them contains a `0x24` anywhere**. The instruction that calls `Create_Thing`
is not in any mission script in this ROM.

So "the mission runs 8192 opcodes and never executes `0x24`" was never a
symptom of anything. It describes the design correctly: a mission script does
not create the things in a world. Whatever does, the scripts are not it, and
the search for the branch that would have led to a `0x24` was a search for
something that is not there.

What that walk *does* say is that the script bodies are small - the two
scenarios reach 70 instructions each, the cameras between 89 and 159 - while a
run touches 979 distinct addresses. The bulk of what executes is shared code
the named routines jump into, below the first named entry.

### Reading the interpreter instead of guessing at it

The trace now carries the interpreter's own program counter as well as the
opcode. It is a pointer in the interpreter's frame at `(-$10e,A6)` - the cell
every operand-taking arm steps with `addq.l #1` - and logging it turns an
opcode stream into an instruction map: consecutive entries give the exact
length of every instruction the pod executed.

Held up against that, the lengths counted from the handlers were wrong in two
places, and both were the same mistake. An arm that hands the program counter
to a *reader* consumes its operand in there, where counting the arm's own
steps cannot see it, and only one reader had been recognised:

| reader | consumes | what it reads |
|---|---|---|
| `0x0211995C` | 2 bytes | a big-endian 16-bit operand |
| `0x021199A8` | 4 bytes | 16.14 fixed point, `hi + lo/16384`, via two calls to the above |
| `0x0211A80C` | a loop | an `$FF`-terminated byte list, stored as longwords into the mission record at `+0x1CA0` and padded to two entries with `$FFFFFFFF` |

So `0x60` pushes a fixed-point constant and takes four operand bytes, not
zero, and `0x09` takes a terminated list whose length is in the stream rather
than in the handler. `tools/mission_dis.py` now reads each reader out of the
ROM instead of naming one, and the count agrees with the pod on **all 7612
straight-line steps of an 8192-instruction trace**.

Two things made that harder than it should have been, both recorded in
FALSE-TRAILS.md: a word-by-word scan reads a 68881 extension word as a branch,
and `bsr.b` is two bytes where `bsr.w` is four.

### `0x64` pushes a string literal

`0x64` was the last opcode the disassembler could not follow. Its helper
`0x02119CC4` reads one **length** byte, pushes the address of the bytes *after*
it onto the typed stack as a type 0 value, and returns that address plus the
length. The push itself is `0x02119AA8`: stack pointer at `[0x021B74B6]`,
0x4C-byte frames, type at `+0` and payload at `+4`.

So `0x64` **pushes a string literal** - a length byte, that many bytes of
NUL-terminated text, and execution resumes after them. The resume address
agrees with the trace **127 times out of 127**.

What settles it is what the bytes say. Twenty-one literals appear in the
thirteen routines:

```
'%*9n %*9L'   '%*9v'      '%1d kills'    '%1d deaths'   'Speed %1d'
'exitScreen'  'Battletech'  'VGL Universe 34933'
'STATS (kills/deaths)'     'Transition at T - %0t'
"('NoseCam')"              '(Cameras only)'
```

And the opcode that consumes one is `0x0A`, which follows a `0x64` in **70
cases out of 70**. `0x0A` calls `0x0211A89A`, and that routine is a **printf**:
a `%` test at `0x0211A8D6`, a `*` test at `0x0211A8E4`, a ctype table at
`0x0218247F`, a 39-byte output buffer at `0x021827BC`. The mission language has
formatted output, and the format strings are inline.

`0x0B` takes one too. `B1_BattleTech_1` pushes `'exitScreen'` and then runs
`0x0B` - so "schedule a routine by name" takes the name as a pushed literal,
which is why the name table exists at all.

### The blocks were never inline routines

The previous reading of `0x64` - that it pushed a *code* label and skipped the
routine body - survived because a format string disassembles. `0x25` is `%`
and `0x20` is a space, and `0x25` and `0x20` are both opcodes; so every
`printf` in the mission decoded into what looked like object-creating
instructions sitting in a branch that never ran. A search for "which branch
guards the creation opcodes" found twenty-three candidates, every one of them
a string.

With the skipped bytes treated as data, static reachability across the
thirteen routines is **986 instructions using 59 distinct opcodes**, against
979 addresses the pod actually executes - and **not one creation opcode among
them**. The four that exist are `0x21` (creates a class 4 thing, via
`0x0211DBA2`), `0x22`, `0x23` and `0x24` (`Create_Thing`), and no mission
script in the ROM reaches any of them.

### What gives an entity its class

An entity is real when its `Class_ID` at `+0x02` is non-zero, and three
routines write it. All three index the arena the same way - base `0x021F99AC`,
stride `0x6B4` - and all three write the same three fields:

```
0214C528  btst  #$0, ($d,A3)      free?
0214C530  move.l D2, ($2,A3)      the class
0214C534  move.l D3, ($6,A3)      the slot index, as Number
0214C538  move.l #$7, ($a,A3)     Thing_Flags
```

| routine | cursor | callers |
|---|---|---|
| `0x0214C4FC` | `[0x021A5DB8]`, starts at 1 | 4 |
| `0x0214C57E` | `[0x021A5DB8]`, the workhorse | 9 |
| `0x0214C61E` | `[0x023A9ED6]`, starts at **950** | 0 |

The third allocates from the top of the arena. Nothing calls it directly, and
this was read as a pool the build never uses; it is reached through a pointer,
and a fight fills it with class 5 hit effects (see *The controls*).

Each caller asks for exactly one class, which makes the nine callers of
`0x0214C57E` a table of constructors:

| class | creator |
|---|---|
| 1 **Mech** | `0x0212D060` |
| 3 | `0x0214C1A0` |
| 8 Escape pod | `0x02140E48` |
| 10 Hovercraft | `0x02111C7E`, `0x02126242` |
| 11 | `0x02137006` |
| 13 | `0x021063C4` |
| 17 | `0x02158B12` |
| 18 Hovercraft | `0x02158D3E` |

and the four callers of `0x0214C4FC` ask for class 4 (three of them) and class
9, Camship.

The class numbering comes out of `Create_Thing`'s own 19-way switch, where each
arm names what it is building:

| | | | |
|---|---|---|---|
| 1 Mech | 6 Escape pod | 8 Escape pod | 9 Camship |
| 10 Hovercraft | 12 VTV | 16 Copter | 18 Hovercraft |

Classes 0, 4, 5, 7, 13 and 15 take the arm that prints
`Create unknown thing %d, class %d received`; 2, 3, 11, 14 and 17 have arms
that do not name themselves.

### `Create_Thing` does not build into the arena

The reason its allocator strides `0x6C0` where the arena strides `0x6B4` is
that it is a different table. Opcode `0x24` passes `(-$14,A6)` - the mission's
own record - as `Create_Thing`'s first argument, and `0x0211E15E` allocates
from **16 slots of 0x6C0 bytes** inside it, starting at slot 1. Opcode `0x20`
clears the same 16 slots.

So a mission gets sixteen scripted objects of its own, and the 1000-entity
arena is something else. Both structures carry class, number and flags at the
same three offsets, which is what made them look like one thing.

### My_Mech_Ptr, and the gate in front of the whole game

Arena slot 0 is set up by hand during init - class 0, number 0, flags 7 - and
`My_Mech_Ptr` at `0x0218AEE4` points at it. `0x02134F06` is what decides
whether it keeps pointing there:

```
02134F0E  tst.l  $2193c1c.l        the game length
02134F14  ble    $2134f20
02134F16  btst   #$1, $2193c13.l
02134F1E  bne    $2134f70          -> create a real class 1 Mech
...
02134F52  move.l $2189f10.l, $218aee4.l   -> otherwise, entity 0
```

The real path builds a Mech from mission-record fields `+0x4C`, `+0x50`,
`+0x54` and `+0x58` and stores it as `My_Mech_Ptr`. The flag it tests arrives
over the wire: `0xE5`'s handler at `0x0210E212` copies packet `+0x30` straight
into `0x02193C10`, and `+0x3C` into the game length two instructions later.

**But `0x02134F06` is only reachable through a dispatch on `My_Mech_Ptr`'s own
class.** `0x02138F8E` reads `($2,A0)` from `My_Mech_Ptr` and switches on it;
class 1 takes the arm at `0x02138F9A`, which calls `0x02130296`, which calls
`0x02134F06`. A pod whose mech is entity 0 has class 0 and never gets there.

Forcing entity 0's class to 1 is enough to break the circle: `0x02130296`
then runs every frame, and a run with a mission started goes from 400 renderer
commands to 42300 - which is the count a pod reaches with no mission at all,
so what the class was suppressing is the ordinary per-frame work.

Whether the real cabinet breaks the circle some other way, or whether the
console is expected to create the mech first, is open - see UNRESOLVED.md.

### The other way in: the animation editor creates things

`0xF6` through `0xFF` all dispatch to `0x02103702`, which switches on the same
byte again and separates them:

| | | | | |
|---|---|---|---|---|
| `F6` `0x02104320` | `F7` `0x0210432E` | `F8` `0x021041B0` | `F9` `0x0210396C` | `FA` `0x02103862` |
| `FB` `0x021037CE` | `FC` `0x02103A36` | `FD` `0x0210377E` | `FE` `0x02103732` | `FF` `0x02103720` |

`0xF8` is the one that creates. It destroys whatever `0x0215DD0A` names, then
switches on the event payload's `+0x02`, and selector **1** reaches
`0x02104254` - a call to the class 1 Mech constructor whose result goes into
`0x0218AEE4`, `My_Mech_Ptr` itself.

That works, and it is the first entity this project has created:

```
peek 021FA060:
  0000  00 00 00 00 00 01 00 00 00 01 00 00 00 07 00 00
                    ^class 1     ^Number 1  ^flags 7
peek 021A5DB8:
  0000  00 00 00 02        the arena cursor moved on
```

It did not work at first, and the reason was ours. The monitor's received-packet
buffer put the packet body at `0x02000804`, and the firmware's
timebase is at `0x02000808` - four bytes in. `--clock` was overwriting bytes 4
through 7 of every packet this project has ever injected, and `0xF8`'s selector
is a longword at `+0x02`, which spans into that hole. The buffer has moved; see
FALSE-TRAILS.md.

### The viewer's class is what turns geometry on

A pod whose `My_Mech_Ptr` is arena slot 0 - class 0 - posts a display list with
**no draw-model items in it at all**. Give slot 0 a class of 1 and the same
run, step for step, posts **357**:

| run, 200M instructions | items | `item $240` draw-model |
|---|---|---|
| default | 1512 | **0** |
| slot 0 given class 1 | 2585 | **357** |

The models it names are **72, 73, 95 and 96**, all type 1 resources in the
archive, and the frame also carries an `item $2C0` with the parameter block
already recorded here (`93 10000.0000 1.0000 60.0000 0.0940 0.0620 0.0940`).
So the pod draws. What it was missing was never the renderer - it was a viewer
with a class.

**But those 357 items are the head-up display, not the world.** All three of
the draw-model calls that run sit in the targeting block of the Mech's frame
builder, `0x0212EB9E`-`0x0212F0F0`. Model `0x48` is a reticle the builder
animates - `0x021BB172` counts `0x48`..`0x4F` while there is a target and
rests on `0x48` when there is none, which is why 73 appears exactly once - and
`0x5F`/`0x60` are placed at integer screen coordinates taken from the viewer's
`+0x128`/`+0x12C`. The block's other output is a `%4.0f` range readout. The
viewer's `+0x67C` is its **target record**: `+0` a target entity index, `+8`
the range, `+0x0C`..`+0x14` the target's position.

### The Mech reaches the culler

`0x0212DB70` is the per-frame cull entry. It clears six counters and then tests
bit 0 of the viewing entity's `+0xBB`:

```
0212DB80  clr.l $2194054.l     Total
0212DB86  clr.l $2194058.l     First Distance
0212DB8C  clr.l $219405c.l     Second Distance
0212DB92  clr.l $2194060.l     Entering Clip
0212DB98  clr.l $2194064.l     Z Clip
0212DB9E  clr.l $2194068.l     Cone Reject
0212DBA4  btst  #$0, ($bb,A3)
```

Its one caller is `0x02139140`, and the six counters are exactly what the
firmware's own `----- CULLING -----` report prints. With a viewer class and a
created Mech, that report goes from

```
Cone stats
Total          0
```

to `Total 1`, with `Model Time` non-zero - the Mech is a candidate the culler
tests. Why it then produced nothing is answered below, under *Why the created
Mech drew nothing*.

### What a created Mech actually contains

The entity `0xF8` builds is not a stub. Reading it back:

* position floats at `+0x26`, `+0x2A`, `+0x2E` (`8000.0`, `8000.0`, `5.4`)
* an orientation block through `+0x50`
* armour and hit-location records from `+0x2C0`, each a name, a type and a
  count: `PPC`, `E LAS MD`, `LASER MD`, `LRM 1524`, repeated for a second side
* per-location damage tables from `+0x490`, forty of them
* `+0x690` a bounding pair and `+0x6A8` two more floats

So the constructor does the whole job. `tools/vehicles.py` reads the same
weapon names out of the ROM's 38 vehicle records, which is where these come
from.

### Why the created Mech drew nothing, and what it draws

The world pass is inside the same frame builder. `0x0212E650` walks all 1000
arena slots, skips any whose `+0x0D` bit 0 is clear, skips the viewer itself
unless its `+0x0C` bit 4 is set, and dispatches on `Class_ID` through a
13-entry table at `0x0212E944`:

| class | draw routine |
|---|---|
| 0, 7 | none |
| 1 | `0x0212F2C2` - the Mech |
| 2 | `0x02123E22` (box-tested first) |
| 3 | `0x0214C228` (box-tested first) |
| 4 | `0x0212C994` |
| 5 | `0x021233D8` (box-tested first) |
| 6 | `0x0212BF9A` (box-tested first) |
| 8 | `0x021410F2` |
| 9 | `0x0210CA40` |
| 10 | `0x0212A180` |
| 11 | `0x021374AE` |
| 12 | `0x021514A6` |

The created Mech reaches `0x0212F2C2` every frame. Its first act is to ask
`0x02111636` whether it can be seen, and every frame the answer was no.

**`0x02111636` is the culler the status report counts.** The disassembler
shows it ending at `0x021116CA`. It does not: its FPU branches are misdecoded,
and read by hand the function carries on to `0x021117CA`:

```
d = (X - cam+0x2C, -Y - cam+0x34, Z - cam+0x30)    Total++
|dx|, |dy|, |dz| each within r, else return 1      First Distance++
|d|^2 within r^2, else return 1                    Second Distance++, Entering Clip++
rotate d by the view matrix at 0x02193C5C
z' + radius < 0: return 2                          Z Clip++
(|x'| - radius) / (z' + radius) > tan: return 2
(|y'| - radius) / (z' + radius) > tan: return 2
return 0                                           Cone Reject++
```

with `r = radius + min(range, view limit)`. So **1 is out of range, 2 is out
of the view cone, 0 is visible**. The last counter carries the report's name
`Cone Reject`, but the path that increments it is the one that returns 0. The
arguments, from the Mech's routine:

| | |
|---|---|
| radius | the Mech's `+0x4A`: 5.0 |
| range | the Mech's `+0x4E`: 1085.9 |
| view limit | camera record `+0x64` + `+0x68` |
| tan | `tan(viewer+0x118 x pi/180)` |

**The view limit is the pod's visibility range, and it has always been zero.**
The camera record is written by `0x02144724`, whose `+0x64` and `+0x68` are
`(float)` of the longs at `0x02193C24` and `0x02193C28`. Those two have
**exactly one writer** in the ROM:

```
0210E29C  move.l ($44,A0), $2193c24.l
0210E2A8  move.l ($48,A0), $2193c28.l
```

in `0xE5`'s handler - the `WELCOME %s` message, which also carries the game
length at `+0x3C`. Every `0xE5` this project had sent carried zeros at `+0x44`
and `+0x48`, so the culler's reach was the Mech's own 5-unit radius. The Mech
is built at (8000, 8000); the viewer stood at the origin.

**The cone was zero wide.** `+0x118` is a half field of view: the Mech
constructor sets it to 30.0 on the Mech it builds, matching the `60.0` in the
scene's `$2C0` item. Slot 0 was only ever given a class, never constructed,
so its `+0x118` is zero and so is `tan`.

Send an `0xE5` with 500 at `+0x44` and `+0x48`, stand slot 0 40 units from the
Mech with `+0x118` = 30.0, and turn it through four headings (`+0xF8`): at 0,
90 and 270 the culler returns 2; at **180** it returns 0, and the frame grows
from 132 longwords to 446 with three records the decoder had never printed:

```
type 5   id 0x3E8, colour (1.0, 0.8, 0.4) at (8000, 8.2, -8000),
         300.0, 150.0, cos 20deg, cos 10deg                a searchlight
type 4   id 0x3E9, model 0x55 at (8000, 0, -8000),
         scale (1, 1, 2)                                   on the ground: a shadow?
type 3   entity 1, model 0x1C4 at (8000, 5.4, -8000),
         then a table of per-joint pairs                   the Mech
```

**`0x1C4` is 452, the MadCat** - one of the six chassis skeletons RENDERING.md
identifies from the archive. The searchlight's numbers are the constants the
routine pushes at `0x0212F53E`. So a created Mech is drawn, as a whole
articulated model, by the firmware's own path. Neither the renderer nor the
Mech was ever what was missing: it was a visibility range, which is the
console's to send, and a viewer that is a constructed Mech rather than a
hand-classed slot.

### A pilot, a chassis, and the frame drawn

**The chassis is `0xF8`'s `+0x08`.** The selector-1 arm at `0x02104202`
hard-codes where the Mech goes - `(8000, 8000, 5.4)`, heading 0 - and passes
the word at `+0x08` to the constructor, which stores it at the Mech's `+0x7E`.
That is the index the frame builder multiplies by `0x3BE` into the vehicle
table at `0x02170566`, and the index `tools/vehicles.py` numbers the ROM's 38
records by. The pod agrees with it on every chassis tried:

| `+0x08` | vehicle record | model in the type 3 |
|---|---|---|
| 0-3 | MadCat Prime, V1-V3 | 452 |
| 4-7 | Vulture Prime, V1-V3 | 453 |
| 8 | Loki Prime | 451 |
| 12 | Thor Prime | 454 |
| 30 | Sunder Prime | 455 |
| 34 | Avatar Prime | 456 |

The same arm then sets up a second thing at `0x02169932` with a heading of 180
and a 30-degree field at `+0x5A` - a camera looking back at what it made. So
`0xF8` selector 1 is a viewer for vehicles, which is why it fixes the position
itself. It is not the console's `MECH_CLASS`.

**`0xED` is `PLAYER_LINK`.** Its handler indexes the arena with `+0x32` and
switches on that entity's class - 1, 7, 9, 10, 12, 13, 16, 19. For a Mech,
`0x021350FA` copies the string at `+0x0A` into the entity's `+0x52` (the name
the targeting display prints for a target), and when `+0x08`/`+0x09` match
this pod's node it makes the entity **`My_Mech_Ptr`**. So the circle
UNRESOLVED.md describes - `My_Mech_Ptr` starts as class 0 slot 0, and only a
class 1 one reaches the per-frame Mech work - is broken the way the console's
log says a game starts: create the vehicles, then link each pod to its own.

```
0xE5  a range of 500 at +0x44 and +0x48
0xF8  selector 1: a MadCat in slot 1
0xED  +0x32 = 1
```

and with nothing written into memory by hand, `My_Mech_Ptr` is `0x021FA060`,
the class 1 dispatch runs every frame, and the frame is built from the Mech's
own seat: the camera at its position, the viewer's own type 3 (model `0x3A`)
and searchlight, and the head-up display centred at (240, 180).

`0x02134F06`, which builds a Mech from mission-record fields, is **not** the
start of a game. Its only caller in the Mech's per-frame work runs it when the
mission clock at `0x02193C1C` has gone negative, after tearing down the current
Mech - it is how a pod resets for the next game.

`0xE8` is the matching destroy: it switches on the class of the entity its
`+0x08` names, runs that class's teardown, and ends in `0x0214C69C`.

**What a type 3 carries.** The whole per-Mech payload the renderer gets is

| longwords | |
|---|---|
| 0 | the entity |
| 3 | the model: a skeleton, 451-456 |
| 4-12 | a 3x3 rotation |
| 13-15 | the position, as (X, height, -Y) |
| 38-81 | 21 joint (sin, cos) pairs |
| 86-277 | 16 node matrices, 4x3 each |

and a MadCat's and a Loki's differ **only in the model id**. No part ids are
in it: the renderer finds the parts from the skeleton. What follows longword
272 differs between runs in a way nothing else does and looks like memory the
record did not write.

**The `$2C0` scene item's third value is the heading**, not a near plane. It
reads 1.0, 0 and 180.0 in runs whose viewers face 1, 0 and 180 degrees - the
wrapped sum of the viewer's `+0xF8` and `+0xFC` the builder computes at
`0x0212DCEC`.

**`--frame-out`** draws the last frame that placed a model, from the pod's
own camera: the eye is the draw object's translation, the view runs along the
third row of its matrix, and each type 3 goes through the rig assembler. The
MadCat comes out 224 polygons, standing on the ground plane - its placement
height of 5.4 is the rig's hip height, so the feet meet the floor without any
adjustment. Its arms are missing, as they are from `--rig`: `516` and `517`
are placed per frame.

### The world arrives as `0xE4`

The console's log starts every game the same way - `Reset world`, `Creating
vehicles` with a `MECH_CLASS` and a `Drop Location` per pod, `Downloading
Map`, `Initialize space` - and the pod's ROM has no word for terrain at all.
All of it arrives through **one message**. In the monitor's state machine
`0xE4` sets the timebase; in the game's byte-0 table its handler is
`0x0213CF5E`, and that is a create:

```
0213CF6A  move.l ($e,A0), D0         the class
0213E228  subi.l #-1, D0             so class -1 is index 0
0213E22E  cmpi.l #$14, D0            twenty arms
          else: "Create unknown thing %d, class %d received"
```

Every arm indexes the arena with `+0x12`, copies the owner word from `+0x08`,
and writes the class and the number itself - the thing lands in the slot the
console names, which is why the log's thing numbers mean anything. Class −1
calls `0x0214C3AC`, the arena init: that is **`Reset world`**.

| packet | |
|---|---|
| `+0x08` | owner, a word |
| `+0x0A` | OR'd into Thing_Flags |
| `+0x0E` | class |
| `+0x12` | thing number, the arena slot |
| `+0x16` `+0x1A` `+0x1E` | x, y, z |
| `+0x22` | a shape (model id) for classes 2, 3, 6; a name for class 1 |

and then, per class, what its initialiser reads:

| class | initialiser | then |
|---|---|---|
| 1 Mech | `0x0212D10A` | `+0x4A` word: **vehicle record**; `+0x50`: **heading**; `+0x4C`, `+0x4E` words |
| 2 | `0x02115BE6` | `+0x26` a long, `+0x2A` **scale**, `+0x2E` **heading** |
| 3 | `0x0214BF0E` | `+0x26` **scale**, `+0x2A` **heading** |
| 6 | `0x0212BBDE` | `+0x2A` **heading** |

The scale multiplies the bounding box the per-shape table at `0x02194460`
gives, and the heading rotates it - which is how each field was told apart.

**Class 1 is `MECH_CLASS`.** An `0xE4` with class 1, vehicle record 34 at
`+0x4A` and 90.0 at `+0x50` builds a Mech where it is told to, named from
`+0x22`, with `+0x7E` = 34 and `+0xF8` = 90 - and the frame draws it as model
456, the Avatar, with its rotation in the type 3's matrix.

**Classes 2, 3 and 6 are the map.** They are the classes the scenario files'
object lines carry - BadLands-16 has 97, 743 and 42 of them - and the classes
the world pass box-tests before drawing. A scenario line is `class shape x y z
heading scale` and one or two integers more; `tools/mapsend.py` turns a
scenario into `0xE4`s, and `--packet-file` feeds them (a map is hundreds of
packets; `--packet` held eight).

One class 3 - shape 132, the commonest in BadLands - 100 units ahead of the
viewer comes back as entity 20, model 132, 57 polygons: a rock spire, drawn
from the pod's own frame. The whole of BadLands-16, 882 objects, goes in
without one `Create unknown thing`, and a viewer at the map's second drop
point stands in a base: bunkers, buildings and a tower around it, and facing
0 - the facing the drop line gives - it looks out of the base across the
mesas.

**And so a game starts with nothing written by hand.** In the log's order -
`0xE5` for the range, a MECH_CLASS `0xE4` for a MadCat at BadLands' second
drop point facing 0 and another for a Loki 100 units ahead of it, the map's
882 `0xE4`s, then `0xED` linking the pod to the MadCat - and `My_Mech_Ptr` is
thing 1, the eye is at its cockpit 8.2 up (hip height 5.4 and the 2.8 the
builder adds), and the frame holds the Loki and the terrain around it. No
`--set`, no `--set-at` on the game at all.

**What the trailing integers are is not known.** `mapsend.py` sends the last
one as the flags and class 2's first as its `+0x26`; nothing has checked
either. Nor is the heading's sign: a Mech at 90 is drawn side-on either way.

### The controls

**What an input report says.** The firmware's own diagnostic viewer at
`0x02125248` - `Waiting for remote I/O data` - decodes the panel's reports,
and names every one:

| report | viewer's line |
|---|---|
| `B0 id` | `Button %x up` |
| `B1 id` | `Button %x down` |
| `C0 id hi lo` | `Analog %x to %hd` |
| `D0 key` | `Keyboard key %x` |

`Get_Event` parses the same four at `0x02122B94` and posts each as an event of
that kind - the `0xB0`, `0xB1`, `0xC0`, `0xD0` arms of the game loop's switch,
which hand it to the pilot's vehicle by class. The sweep that found nothing
fed single framed opcodes to a pod with no Mech; there was nothing to steer.

**The receiver has two modes.** `0x0215B76A` is framed - `01`, an address, a
length, their sum, the payload, the payload's sum - and `0x0215B72C` puts raw
bytes straight into the ring at `0x0217D4B6`. A game switches between them;
the parser skips bytes it does not know, so framed reports get through
either way.

**Analog ids `A0`-`A4` go to the pilot's Mech** at `0x021317C6`, which files
the value at `+0x84`, `+0x86`, `+0x88`, `+0x8A` and `+0x8C` - unless `+0xBB`
bit 0 is set, which it is while the Mech drops in, so a report sent too early
is dropped. `Get_Event` also clamps id `A0` to 0 below -10, the manual's
throttle "sometimes wrapping to `$FFF0`".

With a linked pilot and the reports held back until after the drop
(`--rio-late`):

| report | effect |
|---|---|
| `C0 A0 0340` | speed at `+0x114` goes to **0.26944** and the Mech walks toward -Y at heading 0 |
| `C0 A4 0340` | the heading at `+0xF8` turns; with the throttle open it walks in a circle |
| `C0 A1`/`A2` `±0080`, `C0 A3 0340` | nothing moved that was watched |

**0.26944 is 97 kph in metres per hundredth of a second** - the MadCat
Prime's top speed in its vehicle record - so full throttle is exactly top
speed, and the Mech covers 0.2695 units per tick of `0x02000808`. **The
timebase counts hundredths of a second**, not milliseconds: the game length
is hundredths, and the watchdog kick every 100 ticks is once a second. It also
means `--clock`'s default of one tick per 4096 instructions runs the game at
about 400,000 instructions a second of game time.

The Mech's control code at `0x0213078C`-`0x02130BFE` reads the cells under a
mode at `+0x90`, which is 1 on a fresh Mech: `+0x8C` into the turn and the
heading, `+0x8A` into `+0x138`, the stick pair `+0x86`/`+0x88` through
`0x0214E064` into `+0x110`; modes 2 and 3 route them differently, and
`+0x134`/`+0x138` start at (240, 180), the screen centre, where the HUD draws
its reticle.

**The buttons.** Button-down reports go to `0x0213187A` and a switch on the
id at `0x02132536`. Most arms announce themselves on the head-up display
through `0x02106120`, so the table names itself:

| id | the display says | or it does |
|---|---|---|
| `00` `04` `08` | `RADAR` / `MAP` / `DAMAGE DISPLAY SELECTED` | |
| `10` | `INDIRECT FIRE MODE` | |
| `1C` / `51` | `TWISTING TORSO RIGHT` / `LEFT` | `+0xBB` bits 5 / 4 |
| `20` | `SEARCH LIGHT ON` / `OFF` | toggles `+0xBB` bit 2 |
| `24` / `2C` | `MOVING VIEW UP` / `DOWN` | `+0xBB` bits 6 / 7 |
| `28` | `CENTERING THE TORSO` | `+0xBB` bit 3 |
| `30` / `31` | `STICK MOVES CROSSHAIRS` / `STICK TURNS / TIPS TORSO` | `+0x8F` bit 1; `30` also sets `+0x90` to 3 |
| `32` / `33` | `BASIC MODE ENABLED` / `ADVANCED MODE ENABLED` | `+0x90` to 1 / 3; basic also recentres torso and crosshair |
| `34`-`3B` | | set and clear `+0x8F` bits 2-5 |
| `3C` `3D` `43` | `RADAR AT 2 KM RANGE`, `ZOOM IN RADAR`, `ZOOM OUT RADAR` | |
| `3E` `3F` | `FO SELECT` | |
| `40` | `TARGET SELECT` | |
| `41` `42` | `DAMAGE DISPLAY ON`, `MAP GRID ON` | |
| `53` | `FORWARD OBSERVER ON` / `OFF` | |
| **`A5` `A6` `A7`** | | **triggers**: set `+0x93` bits 1, 2, 0 and call `0x0215A9B4` |
| `A8` | | toggles `+0x7C` bit 0 |

`30`/`31` are why the stick seemed to do nothing: what it moves is a mode.

**The triggers fire.** A linked MadCat with a Loki 100 units ahead of it, and
one report, `B1 A5`: `0x0215A9B4` runs, the workhorse allocator hands out
class 11 things - the shots - the pod puts its fire on the wire, and a shot
flies out to about 1000 units before it is freed. The Loki takes the hits:
two class 5 things appear at slots 950 and 951, model 80, while it stands,
and between frame lists 2800 and 2900 **it dies** - `0x0213424E` sets off a
ring of explosions at offsets round the body through `0x0213EA72`, then tears
the Mech down at `0x02134D6C`. The slot is freed and the next shot reuses it.

**The top-of-arena pool is used after all.** The class 5 things at 950 and
951 are written from `0x0214C654`, inside `0x0214C61E` - the allocator the
table above says nothing calls. Nothing calls it *directly*; it is reached
through a pointer. Model 80 is a type 4 resource, in the same block as the
HUD's reticle models 72-79.

`--frame-at N` draws display list N instead of the last one that placed a
model, which is how a moment in a fight is looked at: `--frame-out` reports
which list it drew out of how many were walked. `BATTLEPOD_UNBUFFERED=1` in
the environment makes stdout unbuffered, so a run that dies keeps its output.

### The slot allocator

`0x0211E15E` is the allocator both constructors use, and it is not the entity
arena. It scans **16 slots of stride 0x6C0** from a base its caller passes,
tests bit 0 of `+0x0D` for free, and on a free slot writes the class to `+0x02`,
the slot index to `+0x06` and `7` to `+0x0A`. `0x20`'s handler clears `+0x0A`
across the same 16 slots, which is the matching reset.

Two routines call it: `Create_Thing` at `0x0211DC1E`, which passes a class
from the script, and `0x0211DBA2`, which passes a constant `4`. `Create_Thing`
has exactly one caller (`0x02118D3A`, opcode `0x24`'s arm) and `0x0211DBA2`
has exactly one (`0x02118C9A`, opcode `0x21`'s arm) - both mission opcodes,
neither of them used.

### The ROM carries two games

`0x0211786C` tests `[0x021B74B2]` and writes one of two table addresses into
`[0x0216F49C]`, which is what the name lookup walks:

```
02117874  tst.l  $21b74b2.l
0211787C  lea    $216c8ea.l, A0      the other game
0211788A  lea    $216b378.l, A0      BattleTech
```

The second table is **Red Planet and Martian Football**, the other titles this
cabinet ran:

```
R1_Red_Planet_1  rp1Exit  R2_Red_Planet_2  rp2Exit
F1_Martian_Footb F2_Martian_Footb mfExit
FC1..FC8_Follow_Cockp  lockExit  T1_Nose_Only_1  T2_Camera_Only_1
```

Eighteen routines against BattleTech's thirteen, in the same bytecode, read by
the same interpreter. Only one table had ever been read, and a write trap on
`[0x0216F49C]` is what found the other: it is written exactly once per boot,
from `0x02117890`, and the instruction three back is the branch that chooses.

### What the other game is

The strings say it, and they are the fastest description of what any of these
scripts is *for*. `mission_dis.py --strings` walks every routine in both tables
and prints the literals it can reach.

**Red Planet** is a scored race. `Score %1d`, `Scoring zones: %1d`, `%1d KPH`,
`Leader Board`, `Leader is %0n %0L`, `%0n %0L is last`, and two exit cameras -
`*Winner-Cam*` in `R1_Red_Planet_1` and `*Loser-Cam*` in `R2_Red_Planet_2`.
The whole thing is framed as a broadcast: `Live from Red Planet`.

**Martian Football** is a team sport played in the same vehicles.
`(No team)`, `Red Team`, `Blue Team`; a `Position` that is one of `Runner`,
`Blocker`, `Crusher`, or `?`; counts of `Blockers` and `Crushers`; the same
`%1d KPH` and `Cockpit view` / `Rear quadrant`; and the caption
`Martian Football: live from Red Planet`. Its title line is
`Red Planet / Martian Football`, so it is a mode of Red Planet rather than a
separate title, and its build string says so too: `VGL Universe 34934a`
against Red Planet's `34934` and BattleTech's `34933`.

For comparison, BattleTech's `B1_BattleTech_1` carries `Shoulder view`,
`Ground cam`, `Map view`, `STATS (kills/deaths)`, `%1d kills`, `%1d deaths`,
`Speed %1d` and `%2d/%3d`. These are the cockpit's on-screen text, and there
is no other source for it in the firmware.

### The interpreter's printf, and the roster behind it

`0x0A` pops a format string and calls `0x0211A89A` with two pointers out of the
mission record: `+0x1CE4` as the **roster** and `+0x1CB8` as an array of float
arguments. Output goes to a 39-byte buffer at `0x021827BC`.

A conversion is `%` then an optional `*` then a digit then a letter. The digit
is a **slot number**; `*` means take the slot number from the float argument at
that index instead, truncated to an integer. The slot is clamped to 0..19.

| letter | arm | what it prints |
|---|---|---|
| `N` `n` | `0x0211A978` | the slot's first name, from record `+0x08` |
| `V` `v` | `0x0211A9A4` | the slot's vehicle, from record `+0x0C` |
| `L` `l` | `0x0211AAB8` | the slot's last name, from record `+0x10` |
| `D` `d` | `0x0211A9D0` | an integer |
| `F` `f` | `0x0211AA74` | a float |
| `T` `t` | `0x0211AB46` / `0x0211AAD2` | a time, with separate upper and lower arms |

So `%*0n %*0L` is "the first and last name of whoever argument 0 names", and
`%*9v` is the vehicle of whoever argument 9 names - which is why the
follow-cockpit cameras use slot 9 and the scoreboard uses slot 1.

The roster is **20 slots of 30 bytes** at mission record `+0x1CE4`, and mission
opcodes `0x10` through `0x16` and `0x8D` are what maintain it. A booted pod
running `B1_BattleTech_1` has it entirely zero, and so is the 60-entry,
64-byte table at `0x02182816` that `0x10` indexes - the pod formats
`%1d deaths` into its buffer and gets `" "` and `"deaths"` with nothing in
between, because there is nobody on the roster.

### Nothing a script does creates anything

With every jump in the trace accounted for - **zero transitions the successor
rule fails to predict, over 8192 instructions** - the reachability walk is
worth trusting, and it closes the question:

| | routines | instructions | opcodes | creation opcodes |
|---|---|---|---|---|
| BattleTech | 13 | 2329 | 70 | **0** |
| Red Planet | 18 | 4688 | 68 | **0** |

Every one of the 979 addresses the pod executes is inside BattleTech's 2329.
`Create_Thing` and the class 4 constructor each have exactly one caller, each
caller is a mission opcode, and no script in either game reaches one. In this
ROM the constructors are unreachable.

### The last two lengths

`0x07` and `0x08` had been counted as jumps because their handlers write the
program counter back. They are not. Their reader `0x0211A650` works on the
caller's argument in place - `addq.l #1,($c,A6)` rather than the
`addq.l #1,(-$4,A6)` the other readers use - so matching one spelling of the
step read both as zero bytes long, and an arm that reads nothing and writes
the program counter looks exactly like a jump. They take **eight** and **six**
operand bytes. Their handlers also hand the counter over *by value*
(`move.l (-$10e,A6),-(A7)`) rather than by address, which the operand rule had
not recognised either.

One further correction fell out of it: `reader_cost` followed every call a
reader made, including the firmware's `printf` on `0x0211A650`'s bad-operand
path, and charged `0x07` for an `addq.l` inside it. A call is only another
reader if it is *handed the pointer*.

And `0x42` is a **call**, not a jump: a `0x44` at `0x0216B4CA` returns to
`0x0216BA8C`, which is where the `0x42` at `0x0216BA89` came from.

What remains of the original question is another pod on the wire, or something
in the mission record this project has not learned to fill - and the way to
tell them apart is still to name what the typed loads in the loop are reading.

## Making the pod report on itself

The firmware has a complete self-diagnostic and it can be turned on.
`0x021BB1A0` is a request flag: the main loop tests it, calls the status report
if it is set, and clears it again.

```
0213A506  tst.l  $21bb1a0.l
0213A50C  beq    $213a518
0213A50E  jsr    $21397b2           the report
0213A512  clr.l  $21bb1a0.l
```

**In-game message `0x73` is what normally raises it** - its whole arm is
`move.l #$1, $21bb1a0.l` - so this is a console asking a pod for its
statistics, and the first of the thirty-three in-game opcodes with a name.
Setting the flag directly gets the report out of a booted pod:

```
----- 68681 -----
68681 ISR ff, Adam's enable 7
Services 7, TX 7, RX 0, init1 11000000, init2 10000000
Init took 0 trys
----- CULLING -----
Cone stats
Total          0
First Distance  0
Second Distance 0
Entering Clip   0
Z Clip          0
Cone Reject     0
----- RENDERER -----
Polygon count 0
Model Time    0

Averages for 1 frames, 0 polygons and 22.379999 seconds
Polygons/sec 0.000000, Per Frame 0

Average fps   0.044683
Worst case    3167 (0.031576 fps)
Best case     3167 (0.031576 fps)
Currently     3167 (0.031576 fps)

Maximum Possible Performance
Average fps   0.032723
...
Remaining time = 600
My_Mech_Ptr = 0x21f99ac
Class_ID=0, Number=0, Thing_Flags=0x00000007
----- ROUTER -----
Maximum Traffic (1 second average) 0 (0)
Max TX Buff 0
----- EVENTS -----
Max Events  0
Max Timed   2
Max Network 0
----- PERIODIC -----
```

Several things fall out of one report.

**`My_Mech_Ptr` is entity 0.** `0x21f99ac` is the base of the arena, and
`Thing_Flags = 0x00000007` is the value the arena loop writes into entity 0's
`+0x0A` and no other entity's. So the pod's own mech is slot zero, reserved at
boot, which is why the boot bothers to build entity 0 differently from the
other 999.

**`Remaining time = 600`.** A mission clock, and 600 is the number a BattleTech
Center ran on - ten minutes, if the unit is seconds.

**The frame-rate maths pins the timebase.** `fps` is computed as `100.0`
divided by a tick count, so the free-running counter at `0x02000808` is
**hundredths of a second** - which makes the watchdog's `addi.l #$64` deadline
exactly one second.

**The culling pipeline is named**: a cone test with a total, two distance
rejections, an entering-clip count, a Z clip and a cone reject. That is six
named stages of a renderer this project has otherwise had to infer, and they
are counters, so once anything draws they can be read.

**The DUART reports on itself** - `ISR ff`, services, TX and RX counts, and
both init words - which is a cross-check on our model of it from the firmware's
own point of view rather than from the wire.

The numbers here are all zero or nonsense because nothing is running: one
frame, no polygons, 22 seconds. That is the point. **This is the measurement to
beat**, and it exists already.

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

### The pod does build a frame

With entity 0 a `Mech` in the thirty-slot table, both display-list emitters
run:

```
tap 0214465C hit 1     emit type 8, viewport
tap 02144724 hit 1     emit type 1, draw object
tap 0213A53A hit 1     the main loop's render call
tap 021444E8 hit 1     the list crosses into the renderer
tap 0214465C hit 2     and the next frame starts being built
```

and the buffer holds exactly what the format says it should:

```
0218AF14  00000048              count: 72 longwords
0218AF18  00000000 00000002 00000002 00000001    a type 0 record
0218AF28  FFFFFFFF              terminator
0218AF2C  00000008 0000000A     type 8, viewport, 10 longwords
0218AF34  00000000 00000000     x0, y0
0218AF3C  000001DF 00000167     x1 = 479, y1 = 359
0218AF44  000001E0 00000168     width 480, height 360
0218AF4C  000000EF 000000B3     centre 239, 179
0218AF5C  00000001 00000028     type 1, draw object, 40 longwords = 7n+33, n=1
0218AF64  3F800000 00000000 ...  the identity matrix
```

**480 x 360, one object, an identity transform.** The cockpit is drawing.

Two things stand between that and a picture.

**The list is double-buffered.** `0x0218AF04` is a descriptor, not the list:
`+0x00` and `+0x04` are two buffer pointers, `0x0218AF14` and `0x0218B024`,
`+0x08` is the 9000-byte size that command 2 allocated, and `+0x0C` is a
cursor. The first render posts the buffer the emitters were *not* filling,
which is why the list that reaches the renderer stub decodes as a type 0
record and a terminator with the real frame sitting after it.

**Only one frame is ever rendered.** In 900 million instructions the stub sees
exactly one command 6. The game builds the next frame and then waits, because
nothing tells it the last one finished - the stub acknowledges commands but
never completes a render. `Async_Render` itself is `0x0214D302`.

So the next move is not to decode anything. It is to make the renderer stub
**finish a frame**, and then read the list it is handed.

### The renderer's frame-complete interrupt

The board has its own interrupt and the firmware installs it as a **vectored**
one, which is why it was never among the autovectors:

```
0215B9C6  move.l #$214c708, $2000108.l    vector 66 = 0x42
0215B9D0  move.l #$215b69a, $200011c.l    vector 71 = 0x47, the DUART
0215B9E4  move.l #$215b69a, $2000068.l    autovector 2, also the DUART
0215B9EE  move.l #$215b69a, $200006c.l    autovector 3
```

`0x47` is the byte the boot writes to the DUART's interrupt vector register at
`0x11018`, so vector 71 is the DUART from both sides. **Vector 66 is the
renderer**, and its handler reads the cause out of a word:

```
0214C70C  move.w $3800001c.l, D0
0214C712  bclr   #$7, D0                acknowledge
0214C716  move.w D0, $3800001c.l
0214C71C  andi.w #$70, D0                the cause, bits 4-6
0214C720  cmpi.w #$50, D0   beq ...      frame complete
0214C726  cmpi.w #$60, D0   bne ...      a list of callbacks
```

and the frame-complete arm is three instructions:

```
0214C770  move.l $2000808.l, D0
0214C776  move.l D0, $217a326.l          stamp the timebase
0214C780  rte
```

**`0x0217A326` is the render-done flag**, and it closes a loop that was
previously only half visible: `Async_Render` clears it at `0x0214D3CE` on its
way out, `Render_Done` at `0x0214D45E` is a bare `tst.l` on it, and the
end-of-frame code at `0x0213A41A` computes the frame time as
`0x0217A326 - 0x021BB1A4`, the stamp minus the time the render started. So the
whole frame-timing story the status report prints comes from this one
interrupt.

`--rirq` raises it after every render: write `0x00D0` into the CSR word - bit 7
pending, cause `0x50` - and assert the line at level 5 with vector `0x42`,
holding it until the handler clears bit 7. With that, **the frame-complete arm
runs**, which it never did before.

**It is not yet enough.** The pod still builds one frame and stops: the
end-of-frame code runs once, the render call runs once, and the interrupt
completes once. Whatever asks for frame two is upstream of all of it - the
end-of-frame function is reached through the event pump's handler hook rather
than by any direct call, so the next question is what re-arms that. `Max Timed
2` in the status report says the timed-event queue has two entries, which is
where to look.

### The frame loop is running; the render is not repeating

With `--rirq` the pod's own instrumentation says the game is alive. Typing `s`
with entity 0 a `Mech`:

```
Model Time    3                        was 0
Remaining time = 597                   was 600
Class_ID=1, Number=0, Thing_Flags=0x00000007
Averages for 1 frames, 0 polygons and 22.410000 seconds
```

**The mission clock is counting down.** And the event pump is turning over:
kind `0x10000` - the per-class frame update, which reads `My_Mech_Ptr`'s
`Class_ID` and calls a different routine for each class - runs again and again,
as does the pump's handler hook.

What runs exactly once is the **end-of-frame**, and knowing how it is scheduled
says why that matters:

```
02138BA4  pea   ($1874,PC); ($213a41a)      at startup
02138BAE  pea   $c.w
02138BB2  jsr   $2122658.l                  schedule it

0213A544  tst.l $3fffe168.l                 TI_ErrorNumber
0213A54A  bne   $213a566                    an error: do not reschedule
0213A54E  pea   (-$136,PC); ($213a41a)       otherwise, at the end of
0213A558  pea   $c.w                         every frame, schedule it
0213A55C  jsr   $2122658.l                   again
```

So the end-of-frame **re-arms itself**, and the render is inside it. It ran
once, it took the not-an-error branch, and it rescheduled - and the rescheduled
event never came back. The pump's hook is called repeatedly, so events are
being delivered; this particular one is not.

`(-$8a,A6)` in the pump is **`+0x14` of the event buffer**, not a separate
variable: an event carries its own handler, and the pump calls it instead of
switching on the kind. That is how a scheduled routine gets run, and it is why
the end-of-frame appears in no call site anywhere in the ROM - it is only ever
reached through `0x02122658`.

**So the open question is narrow**: what `0x02122658` does with `(0x0C, 0, 0,
0, handler, 0)`, and why the second call does not produce an event the way the
first did.

### Why one frame: the stub was too fast

`0x02122658` turns out not to be a general scheduler. It special-cases two
kinds into **single dedicated slots**:

```
02122664  cmpi.l #$c, ($8,A6)          kind 0x0C
0212266E  move.w #$1, $21bb116.l       one slot, one flag
02122676  move.l ($8,A6), $21bb0f2.l   ... and six more longwords
021226BC  cmpi.l #$2, ($8,A6)          kind 2, likewise at 0x021BB118
0212270A  lea    $21b7566.l, A0        everything else goes in a queue
```

and `Get_Event` delivers the kind-`0x0C` slot **only when the render has
finished**:

```
0212218A  tst.w $21bb116.l      a frame event pending?
02122192  jsr   $214d45e.l      Render_Done
021221A0  beq   $21221fe        not done: nothing to deliver
021221B6  move.l $21bb0f2.l, (A3)   deliver it, handler and all
```

The handler travels in the event: `(A3+0x14)` gets the fifth argument, which is
the pointer the end-of-frame passed to the scheduler, and `+0x14` of the event
buffer is the `(-$8a,A6)` the pump calls.

So the loop is: **end-of-frame renders, reschedules itself, and its event is
released by the render completing.** Which makes the completion interrupt
load-bearing, and shows why a stub that is *too fast* breaks it:

```
0214D3BE  move.l #$1, (A0)              ring the doorbell
0214D3C4  move.l $2000808.l, $21bb1a4.l
0214D3CE  clr.l  $217a326.l             clear the render-done flag
```

`Async_Render` clears the flag **two instructions after** ringing the doorbell.
An interrupt taken at the doorbell sets the flag and then the clear wipes it,
and the pod waits for ever for a frame it has already finished. A real board
took milliseconds. `--rirq` now counts down `RIRQ_DELAY` instructions before
raising the line, and `--rirq LEVEL:DELAY` makes it a knob rather than a
constant.

**With that, frames flow.** Six renderer commands in a run become **400** - the
logger's cap - all of them opcode 6.

### The frame, decoded

The list the renderer receives was the right one all along; the stub's walker
was wrong about one longword. `0xFFFFFFFF` is a **separator**, not the end: a
real frame has one after the leading record and carries straight on. Reading it
as a record type is what made every display list in this project look empty.

With that fixed, and with entity 0 placed by an `0xEC` packet at X 100, Y 200,
Z 5.4 with Course 1.0:

```
display list at TI 100007D0: 104 longwords
  type 0, 4 longwords
  ----
  viewport  (0,0)-(479,359)  480x360  centre (239,179)
  object    1 picks, 42 longwords, viewport 1, items from record 2, screen 480x360
       0.9998    0.0000   -0.0175
       0.0000    1.0000    0.0000
       0.0175    0.0000    0.9998
     100.0000    8.2000 -200.0000
      pick (16,16) -> entity 0 part 0
  type 6, 5 longwords
  items     22 longwords
      item $0E0, 1 longwords      a vector
      item $100, 3 longwords
      item $280, 1 longwords
      item $240, 2 longwords      draw polygon
      item $2A0, 1 longwords
      item $0C0, 1 longwords      a run of vertices
      ...
```

Three things to read off it.

**The transform is built from the position we sent.** The translation row is
`(100.0, 8.2, -200.0)` for a packet carrying X 100, Y 200, Z 5.4 - that is
**(X, Z + 2.8, -Y)**. The renderer's world is Y-up with the sign of the third
axis flipped, and `2.8` is an eye height added on top of the mech's own Z.

**Course is in degrees.** The rotation is `cos 1 deg = 0.9998` and
`sin 1 deg = 0.0175`, from a packet that carried Course `1.0`.

**The item stream is real geometry.** `$0E0`, `$0C0`, `$100`, `$240`, `$280`,
`$2A0` are the model interpreter's own opcodes - vectors, vertex runs, draw
polygon, the markers - the same language `tools/model.py` already runs.

So the chain is complete end to end: **a packet arrives at the wire, moves an
entity, and shows up as the transform of a frame the pod builds for its
renderer.**

### What the items say, now that they print their payloads

The item lengths were known and the meanings were not, which is a gap a log
line can close: printing each item's payload makes a shape id or a field of
view recognisable where a bare length is not.

A frame's first type 7 record is **the scene**:

```
item $2C0  93  10000.0000  1.0000  60.0000  0.0940  0.0620  0.0940  0  0  0
item $000
```

**`$2C0` sets the camera**: a far plane of 10000, a near plane of 1.0, a
**60-degree field of view**, and a colour triple of `(0.094, 0.062, 0.094)` -
a very dark violet, which is the ground or the sky. The leading `93` is not
identified.

The second type 7 record is **the head-up display**:

```
item $0E0
item $100  16  16      position
item $280
item $240  72          draw 72
item $2A0
item $0C0
item $280
item $100  0  0
item $240  96
item $100  0  0
item $240  95
item $2A0
item $000
```

`$100` takes a screen position and `$240` a number, so this is *move here,
draw that* - a HUD glyph or symbol per pair. The object record names which type
7 record to run through its `+0x58`, and it names record 2: the pod is drawing
its instruments.

**There is no mech geometry in the frame, and there should not be.** The only
entity in the world is the player's own, and you do not see your own cockpit
from inside it. Giving a second entity a class, a number, flags and a slot in
the thirty-strong mech table is not enough to make it appear - the per-class
draw operation, one of the seven class dispatchers, wants more than that.

### The draw pass, and why it only ever sees one entity

The frame is built by `0x0212DB70`, and how it is reached matters more than
what it does. Event **kind 2** dispatches on `My_Mech_Ptr`'s `Class_ID` and
calls a different builder per class:

```
0213912E  jsr $213eea4.l      one class
02139140  jsr $212db70.l      class 1, a Mech
02139152  jsr $2104374.l
02139164  jsr $210b9ca.l
```

each with `My_Mech_Ptr` as its only argument. **Rendering is per-viewer, not
per-entity**: the pod draws the world *from* its own mech, and what kind of
thing you are flying decides which builder runs - the same shape as the
in-game console's dispatch and the seven class-dispatched operations.

The builder opens by clearing six longwords at `0x02194054`-`0x02194068`, which
identifies them: they are the **`Cone stats`** the status report prints -
`Total`, `First Distance`, `Second Distance`, `Entering Clip`, `Z Clip`,
`Cone Reject`. Then it gates on the viewer:

```
0212DBA4  btst #$0, ($bb,A3)    the viewer's +0xBB, bit 0
0212DBAE  btst #$2, ($ba,A3)    +0xBA, bit 2
0212DBB6  lea  ($2e,A3), A0     Z, against -10.0
```

and `+0xBB` is the byte **message `0xE0` writes** - which the field sweep found
without knowing what it was for.

The list itself is built through the descriptor:

```
0212DC7C  pea $218af14.l        the buffer
0212DC78  pea $2328.w           its size, the 9000 bytes command 2 allocated
0212DC72  pea $218af04.l        the descriptor
0212DC82  jsr $2144592.l        start a list
0212DC92  jsr $21445fa.l        (descriptor, 2)
0212DC98  movea.l $218af10.l, A0   the cursor, descriptor+0x0C
0212DC9E  addq.l #4, $218af10.l    every record is written through it
```

So `0x0218AF04` is `{buffer, second buffer, size, cursor}` and the two buffers
alternate, which is what the earlier reading called double buffering and got
right.

**Making another entity draw needs more than we have.** Giving entity 1 a
class, a number, flags, a mech-table slot, the `+0xBB` draw bit and a position
from the wire changes nothing: tapping the builder shows it called sixteen
times and **always with entity 0**. Whatever enumerates the world for drawing
is inside the builder and is not reached, so the missing ingredient is
something the builder looks for rather than something the entity lacks.

### Inside the frame builder

Reading `0x0212DB70` forward gives the frame's construction in order.

**The leading record is written by hand**, not by an emitter: `1` and then
`0xFFFFFFFF` through the cursor, which is the `{0, 2, 2, 1}` and the separator
every frame opens with. Then the viewport emitter is called with
`(0, 0, 479, 359, 0x100, 0x100)` - the 480x360 extent, straight from
constants.

**The view heading is `Course + a twist`:**

```
0212DCEC  lea    ($f8,A3), A0        Course
0212DCF0  lea    ($fc,A3), A1        and the field after it
0212DCF8  fadd.s (A1), FP0
0212DD08  fcmp.s #$43b40000, FP0     360.0
0212DD1A  fadd.s #$c3b40000, FP0     wrap by -360
0212DD38  fadd.s #$43b40000, FP0     or by +360
```

The wrap at 360 settles the units from the code rather than from an
observation, and it names **`+0xFC` as something added to Course to get where
the pilot is looking** - a torso twist is what a BattleTech pod has that a
heading alone does not.

The two matrix builders it calls confirm it again:

```
0213F35E  fmul.d #$3f91df46, FP0     pi / 180
02133F366 fsincos.x FP0, FP2
```

`0x0213F30C` and `0x0213F350` each take an angle in **degrees**, convert,
`fsincos` it and fill a 3x3 - one about one axis, one about another.

**The scene's colours come from the game definition.** After the object record
the builder reads six longwords from `[0x02193BB4]+0x30`..`+0x44` and pushes
them with `60.0` and `10000.0`, which is the `$2C0` camera item: the field of
view and the far plane are constants, the colour is per-game.
`0x02193BB4` is set at startup from `0x02179A10 + id * 0x84`, so each game -
BattleTech, Red Planet - has a 132-byte definition record and this is where
part of it is used.

**And the builder never touches the entity table or the mech table.** Neither
`0x02189F10` nor `0x021943DA` appears anywhere in its 0x1466 bytes. So the
world is not enumerated here, which rules out a whole family of guesses about
why a second mech does not appear: it is not that the builder skips it, it is
that the builder was never going to look.

### The display-list API, and who uses it

The list is not written by hand; there is a small API, and finding it makes
every emitter in the ROM readable at a glance.

| | |
|---|---|
| `0x02144592(buffer, size, desc)` | start a list: `desc[0]` is the buffer, the cursor goes to `buffer+8`, `desc[+8]` is the size |
| `0x021445FA(desc, type)` | begin a record: remember the start, advance the cursor by 8, write the type |
| `0x02144632(desc)` | end it: `(cursor - start)/4 - 2` into the record's second longword |
| `0x0214465C(desc, ...)` | emit a type 8, a viewport |
| `0x02144724(desc, ...)` | emit a type 1, a draw object |
| `0x02144978(desc, ...)` | emit a type 3, `0x88` bytes |

`0x02144632` is worth pausing on: it computes the length as **the longwords
written minus two**, which is the `2 + len` rule this project had inferred from
the renderer's side, now proved from the writer's.

**`record_begin` has 41 call sites**, and three types are passed to it as
constants - 2, 6 and **7**, the item stream. There are **21 type 7 emitters**,
in pairs around the item-writing code.

Only four of them run: `0x0212F108`/`0x0212F17C` and
`0x0213F074`/`0x0213F0C8` - the scene record with its `$2C0` camera, and the
head-up display. The other seventeen sit inside **other viewers' frame
builders**:

```
0x0214FB1A   <- 0x02139198
0x0211C802   <- 0x021176CA
0x0210645C   <- 0x021391A8
```

and `0x02139198` and `0x021391A8` are further arms of the same kind 2 class
dispatch that reaches `0x0212DB70`. So **every viewer class has its own frame
builder**, each with its own item records, and the one that runs is chosen by
what the pilot is flying. Ours is the Mech's.

Which sharpens the open question rather than answering it. The Mech builder has
**four** draw-object emitter calls - `0x0212DDD2`, `0x0212DFC6`, `0x0212E096`,
`0x0212E1C8` - and only the first runs. Whatever puts another thing in the
world is behind one of the other three.

### What the draw bit actually opens

The three unused draw-object emitters are not skipped by a failing test. After
the scene's camera item the builder jumps straight past them:

```
0212DE66  jsr $21453a8.l       emit the $2C0 camera item
0212DE74  bra $212e286         and over everything else
```

so `0x0212DE78`-`0x0212E1C8`, the block that would emit the second, third and
fourth object records, is reached only by a branch back into it. Its own head
tests a global: `btst #$0, $2193c13.l`.

What `entity+0xBB` bit 0 does open is further on:

```
0212E2E0  btst #$0, ($bb,A3)
0212E2E8  beq  $212e358        clear: skip
0212E2EE  pea  $3a.w
0212E2FA  jsr  $2144978.l      emit a type 3 record
0212E312  move.l (A0), (A1)    its +0x3C from the entity's X
0212E31E  move.l #$0, (A0)         +0x40 zero
0212E33E  fmove.s FP0, (A0)        +0x44 the negated Y
```

With the bit set, that block runs sixteen times in a run where it ran none
before. So **`+0xBB` bit 0 places the viewer's own type 3 record** at
`(X, 0, -Y)` - the same axis flip the object transform uses - and `0x3A` is a
tag it carries.

**And that is the honest limit of what hand-setting fields can do.** The world
is empty not because the builder refuses to look at entity 1 but because
nothing ever *created* anything: `Create_Thing` has never run in any of these
sessions. Writing a class, a number and flags into an entity's memory is not
the same as the game making a thing, and the difference is everything the
constructor does that we have not seen. The next move is to make
`Create_Thing` run.

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

What follows the object's own header is **not** geometry, which is what an
earlier reading of this said. It is a list of **pick queries** — `n` of them at
`+0x88`, seven longwords each, and `n` is capped at 32 because that is the size
of the slot array the renderer allocates at `0xFE00C1B0`.

| longword | direction | contents |
|---|---|---|
| `lw0` | in | screen **X** |
| `lw1` | in | screen **Y** |
| `lw2` | out | the entity drawn at that pixel; **0 means nothing was hit** |
| `lw3` | out | the sub-part tag, set by model opcode `$480` |
| `lw4`–`lw6` | out | its position, through the object's rotation and translation |

`0xFE019BE0` packs `lw0` and `lw1` into an XY address with `MOVY` and files it;
`0xFE01A280` reads the frame buffer at that address while drawing, records what
it found and paints a marker; `0xFE01A5D0` restores the pixel afterwards; and
`0xFE019D50` copies the answers back into the list for the 68020 to read. It is
how the cockpit knows what the pilot has under the crosshairs.

The geometry lives in the archive, not in the display list — see the model
format in RENDERING.md.

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
`main game loop (SecCom 674 bytes).` — and **that 674 is hexadecimal**. The
code at `0x02138BB8` pushes `$674` against a `%x` format, so the shared
communication block is **0x674 = 1,652 bytes**, not 674. Every prose mention of
it in this project said 674 until now.

**The block is at `0x4007E000`.** The code that sets it up sits immediately
before the handshake call, in the game-start path:

```
02138B52  move.l  #$4007E000, $2194452.l    the block's base, cached here
02138B5C  clr.l   (-$70,A6)                 a counter
02138B6E  movea.l (-$a6,A6), A0             loop:
          addq.l  #1, (-$a6,A6)
          clr.b   (A0)                      zero a byte
          addq.l  #1, (-$70,A6)
          cmpi.l  #$674, (-$70,A6)
          bcs     $2138B6E                  0x674 bytes of it
02138B86  jsr     $214DA26                  then the handshake
```

So the 68020 clears 1,652 bytes at `0x4007E000` and only then asks the Amiga
whether it is ready. In the Amiga's own address space that is offset
`0x7E000` - far above the program, which ends at `0xF6A4`.

That is also why watching `0x40000000`-`0x4000FFFF` found nothing but the
handshake word: **the block is in a different 64K**. It is set up on a game
start rather than by the monitor's `p`, so the pointer at `0x02194452` is still
zero after `Secondary Started`, and the block itself cannot be watched until a
game runs.

### What is in the block: a 32-slot message ring

The block is not opaque. `0x0212C1EC` is the enqueue and it gives up the whole
layout:

```
0212C1F4  movea.l $2194452.l, A0        the block
0212C1FA  move.l  ($12A,A0), D0         the write index
0212C1FE  addq.l  #1, D0
0212C200  andi.l  #$1F, D0              32 slots
0212C20C  cmp.l   ($12E,A0), D0         against the read index
0212C210  beq     $212C252              full: return 0
          ... i*4 + i = 5i, <<2 = 20i, +i = 21i, <<1 = 42i
0212C22E  add.l   $2194452.l, D0
0212C234  addi.l  #$132, D0             the slot array
0212C242  move.l  ($8,A6), (A0)         the caller's word into the slot
```

and `0x0212C256` is the commit, which advances the write index by one modulo 32
once the slot is filled.

```
+0x000 .. +0x129   298 bytes, not yet identified
+0x12A             write index, long
+0x12E             read index, long
+0x132             32 slots of 42 bytes
```

**The arithmetic closes the block.** `0x132 + 32 x 42 = 0x672`, against a block
of `0x674` - two bytes of slack and nothing unaccounted for. That is the second
independent confirmation of the size, after the loop bound and the printf.

It is also **set up during an ordinary boot**, not only on a game start: after a
normal run the pointer at `0x02194452` holds `0x4007E000`, and the firmware
reaches `main game loop (SecCom 674 bytes).` The only traffic a boot generates
is three reads of `+0x12A` and one of `+0x12E` - the producer checking whether
the ring is full and finding nothing to send.

**It has now been driven to completion.** The firmware's own diagnostic menu
has `p - Start Secondary`, and with the ready word supplied it gets past the
wait and says so:

```
--duart-in 'p' --set 40000100=1234567

  Starting Secondary
  Secondary Started
```

Without it, `0x40000100` is read **12,112 times** in one run while the console
prints `Waiting for Secondary to become ready 0` — the handshake is a spin, and
the number it reports is the word it read.

Two things that follow. **The `0x400` is not arbitrary**: the load script puts
`AMIGA3_0` at `0x400003E4`, its 601A header is 28 bytes, so the Amiga program's
text begins at `0x40000400` - window offset `0x400`, exactly what the 68020
hands over. The handshake tells the other board where its code is.

And **nothing touches the Amiga window during an ordinary boot at all** - the
watch comes back empty over `0x40000000`-`0x4000FFFF` until the secondary is
started. It is brought up on demand, which is why this never appeared before.

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
That second check is `[base] & 0xFF0000FF >= 0x55000001` at `0x021492BA`, so
the board is expected to raise the signature's **low** byte once the download
lands.

### Standing in for the board

`--astub` models the board rather than poking a constant over it. Two lines do
the whole thing:

- whatever the 68020 writes to the head at `+0x04` is written to the tail at
  `+0x08` as well - a board that drains the ring as fast as it is filled, which
  is the fastest a real one could be;
- and the first push sets the low byte of the signature, which is what the
  ROM's second check wants: `[base] & 0xFF0000FF` must be **at least
  `0x55000001`**, not merely `0x55......`.

With that the ROM stops saying `Audio subsystem is NOT properly downloaded!`
and takes the branch at `0x021492D8` for the first time. All four of its
subsystem checks now pass.

It also cleans up the bus log, which matters more than it sounds. Answering
`0x50001000` with a poke made every access to the board open bus, so the
download of `btAudio.dld` showed up as **1,236,274 unmapped accesses** and
buried everything else in the report. With the ring as real memory it is zero,
and what remains in the log is what the pod is actually waiting on.

**This is a stub and it is listed as one.** Nothing plays a sound; the DSP is
not emulated; `btAudio.dld` goes through the FIFO and is thrown away. What is
now true is only that the ROM believes its audio board is there, which is what
it needs to believe to get on with anything else.

### The device at `0x00010000`: a watchdog and two control ports

With the audio download no longer burying the bus log, what is left of the
unmapped traffic is small enough to read line by line. It resolves into two
things.

**`0x00010000` is strobed, and the strobe is a watchdog kick.** The routine is
three instructions:

```
0215BA8A  move.b #$80, $10000.l
0215BA92  move.b #$0,  $10000.l
0215BA9A  rts
```

a pulse on bit 7 and nothing else. It is called from **exactly one place**, and
that place is the top of `Get_Event` - the event pump every frame goes through:

```
02122164  move.l $21bb13e.l, D0        the deadline
0212216A  cmp.l  $2000808.l, D0        against the free-running timebase
02122170  bge    $212218a              not yet
02122178  addi.l #$64, D0              next one, 100 ticks on
0212217E  move.l D0, $21bb13e.l
02122184  jsr    $215ba8a.l            kick
```

A pulse on a deadline, from the one function that cannot stop running while the
pod is alive. That is what a watchdog is for and where one belongs. In a boot
it fires **453 times**.

**`0x00010007`-`0x00010015` are two four-register control ports.** Eight
instructions in 534 KB of ROM touch them and nothing else does:

```
02123336  ori.b  #$40, $10007.l        after installing 56 exception vectors
0212333E  andi.b #$bf, $1000f.l
02123346  andi.b #$bf, $1000b.l
0212334E  ori.b  #$40, $10013.l

0215B9F8  ori.b  #$84, $10009.l        after installing autovectors 2 and 3
0215BA00  andi.b #$7b, $1000d.l
0215BA08  andi.b #$7b, $10011.l
0215BA10  ori.b  #$84, $10015.l
```

Two ports interleaved at a stride of 4, four registers each, and each group
does **set, clear, clear, set of one mask** - `0x40` for the first, `0x84` for
the second. Both runs happen immediately after the code installs the interrupt
vectors they go with, which is what makes this interrupt routing rather than
anything else. The **part** is still unidentified; what it is *for* is not.

**The catch-all vector handler.** The first of those two sites fills 56
exception vectors with one routine at `0x02123358`, which reads the vector
offset from the stack frame at `(0x1A,A7)` and the PC at `(0x16,A7)`, formats
them as `VVVV PPPPPPPP` and writes them straight out of the console port - then
loops forever re-printing, **except** for vector offset `0x138`, which it
returns from. So an unexpected exception in this cockpit announces itself and
hangs, and exactly one interrupt is expected and ignored.

## Open questions

- Which *part* sits at `0x00010007..0x00010015`? What the ROM does with
  it is above; the chip is still unnamed.
- The UART receive register — needed to drive the ROM's built-in diagnostic
  menu, which can start the renderer, the Secondary and a test game on demand.
- Resource type semantics (1, 2, 4, 7).
- ARCNET has still not been touched; the boot reaches the main loop without it.
  The controller is reported to be an **SMC COM90C66**, on the CPU board.
- After the audio download the ROM jumps through a null pointer. Expected while
  three boards are stubs, but worth revisiting once any of them is real.
