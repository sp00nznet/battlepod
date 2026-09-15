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

### Inside a type 1 model — what is known and what is not

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

Reading the loader that turns resource bytes into solids is the next step, and
it is now practical: the disassembler decodes FPU instructions, without which
this whole layer read as `dc.w $f2xx`.

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

- Which parts sit at `0x00010007..0x00010015`, and what is `0x38000022`?
- The UART receive register — needed to drive the ROM's built-in diagnostic
  menu, which can start the renderer, the Secondary and a test game on demand.
- Resource type semantics (1, 2, 4, 7).
- 34010 or 34020.
- ARCNET has still not been touched; the boot reaches the main loop without it.
  The controller is reported to be an **SMC COM90C66**, on the CPU board.
- After the audio download the ROM jumps through a null pointer. Expected while
  three boards are stubs, but worth revisiting once any of them is real.
