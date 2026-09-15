# Rendering a cockpit

A BattleTech pod is not one screen. It is three display surfaces and a physical
control panel, each driven by different hardware over a different interface.
Reproducing "the pod" means reproducing all four, and they are at very different
stages — so it is worth being explicit about which is which.

The part numbers below come from VWE's own cockpit patent, WO 97/00106
(PCT/US96/10431, filed June 1996), which describes the 3.0 cockpit in detail.

---

## What it is supposed to look like

Worth settling early, because it sets the target and the obvious guess is
wrong. **It is not wireframe.** Three independent lines say so.

**The renderer's own code.** Disassembling the code segment and tallying what
it calls:

| instruction | count |
|---|---|
| `LINE` | **0** |
| `FILL` | 1 |
| `PIXBLT` | 1 |
| `PIXT` | 8 |
| `CEXEC` (coprocessor) | **517** |

Zero `LINE` instructions in six thousand words of renderer. A wireframe engine
is nothing *but* line draws. And with only ten of the '20's own block
primitives in the whole image, the rasteriser is not using them either — the
spans are written by hand, which is what you have to do for anything shaded,
because `FILL` only does one flat colour. The work is in the 517 coprocessor
operations.

**The frame buffer.** `PSIZE` reads 16, so the pod runs **480x360 at 16 bits
per pixel**. Nobody spends 16 bits a pixel on lines.

**The footage.** Two period videos carry real screen capture, and they settle
what the manuals cannot:

- *Virtual World Entertainment BattleTech 3.0 Dooley Trainer* — YouTube
  `MHSmuBxqlG4`. Game footage at roughly 164 s, 188 s, 199 s and 281 s.
- *The Next Step: "Virtual Worlds and Battletech"* — YouTube `qu0KkyH1jVw`,
  a Discovery Channel piece. Game footage around 126 s, 150 s, 240–258 s, and
  the post-game debrief at 303 s.

What they show, consistently:

- **Flat-shaded solid polygons.** The facets are plainly distinct — you can
  count the quads down a mech's leg, each a single flat tone. Not Gouraud, and
  certainly not wireframe.
- **No texture at all** on mechs or terrain.
- **Cast shadows**, drawn as dark polygons on the ground beneath each mech.
- A sky that is a vertical gradient, and **distance haze** washing the horizon
  out to a pale band.
- A tight palette — sand, tan, and a purple-brown for faces turned away.
- Projectiles as small bright polygons; explosions and burning wrecks as
  clusters of flame-coloured polygons with scattered debris points.
- The 150 s frame is *Red Planet* on the same hardware: same flat-shaded style,
  grey tunnel palette, and a text HUD along the bottom edge.

One frame at 258 s is shot over a pilot's shoulder inside a pod and shows all
four surfaces at once: the main monitor with a shadowed mech on the plain, the
secondary display below it running a green radar grid, a column of lit
pushbuttons to the left and a strip of lamps to the right. That is the machine
this repo has been taking apart, in one photograph.

The debrief screen at 303 s *is* drawn in outline — mech silhouettes per pilot,
green where intact and red where damaged, with callsign and score. So wireframe
does appear in this product, in the post-game UI, and nowhere in the world view.

**A correction.** An earlier reading of this said the target was texture-mapped,
on the strength of VWE's 1994 press kit:

> we look forward to introducing a new cockpit, which utilizes **texture mapped
> graphics** (for greater realism) in the first half of 1995.

That was a *plan* for a next cockpit, not a description of this one, and the
footage shows no texturing. The archive agrees, and this is the part that
should have been checked first: `battletech_ti_res` holds **six type 2 bitmaps,
22,632 bytes between them**, against 130 models and 131 type 7 payloads. Six
small bitmaps is a font and some HUD furniture. It is not a texture library.

The asset patent (US 5,710,878) does name texture, bump and environment mapping
among the material kinds its tool could author — but it describes the authoring
pipeline across VWE's products, not what this release's renderer does with it.

The mech line art in the operations manuals and data supplements is print
illustration, not screen capture; it is good reference for *shape* — MadCat,
Vulture, Loki, Thor and the rest — and no guide at all to how they were drawn.

**So the target is flat-shaded, untextured, shadowed solid polygons at 480x360
in 16-bit colour.** That is simpler than texture mapping in the way that
matters: one colour per face, no per-pixel interpolation, which is a span
rasteriser a first implementation can actually reach.

---

## 1. The primary monitor — the 3D view

**Hardware.** The 68020 builds a display list; a **TMS34020** rasterises it
into the primary monitor (part 82), which is magnified by the pod's optics
rather than being a large panel. The '20 does not do the 3D arithmetic itself —
it hands that to a **TMS34082 floating-point coprocessor** over the coprocessor
bus, 419 instructions' worth in R.BIN, starting five instructions after reset.
DEVICES.md shows how both parts were identified from the instruction stream. The firmware calls the list a "Dlist" and has
dedicated errors for it: `Pre Dlist overflow!`, `Post Dlist Overflow`,
`Render List Overflow`.

**What we have.** The renderer's whole address space is mapped into the 68020 at
`0x20000000`, its command protocol is decoded, and `battlepod` already stands in
for it and logs every command. The renderer's own diagnostics name the primitive
types: `Out of Solids...`, `Weird solid direction %f... shape %d`,
`Suspect ARES data... shape %d`, `Suspect cylinder data... shape %d`. So the
display list is built from **solids, cylinders and "ARES"** primitives, not raw
triangles.

**What we have of the geometry.** The resource archive is decoded — see
DEVICES.md. Type 1 is 3D models, 130 of them, each with a verified axis-aligned
bounding box and bounding sphere; type 4 is an alias table; type 7 holds the
bulk payloads; type 2 is six compressed bitmaps.

**What we have of the model format.** A type 1 resource is **not a mesh**. It is
a threaded program of 45 opcodes, run by the renderer's own interpreter at
`0xFE00EDB0` against a table at `0xFE00EEA0` — the same design as the display
list. `tools/model.py` runs one and collects what it draws.

| what | where |
|---|---|
| header | 22 longwords; counts at `+0x00`, `+0x04`, `+0x08`, `+0x18` are vertices, normals, faces and materials, confirmed against the interpreter's own allocation strides |
| stream | starts at `+0x58` — a valid opcode in **130 of 130** models |
| vertices | `$0A0` one, `$0C0` a run: IEEE float triples carried inline |
| polygons | `$240`/`$260`: face, vertex count, indices, material |
| materials | `$4C0` flat and `$4E0` lit, six longwords: index, three floats of colour, and a fourth that is `0.5` in every record so far |
| culling | the sign of a dot product, stored in the plane record by `$180` |

**The branches carry a language of their own.** `$320`, `$360` and `$420` do
not carry a target, they carry a *predicate program*, evaluated by a second
threaded interpreter at `0xFE018910` through a 24-entry table at `0xFE018A00`.
It is postfix on a small stack: five push forms taking one operand each
(`$020`–`$0A0`), then NOT, OR, AND, XOR, NEG, ADD, SUB, five comparisons and
two short-circuit forms taking none, terminated by `$000`, which pops the
result and returns to the branch.

So this, out of model 30:

```
$320  $080 $000  $040 $00C8  $260  $000  $1440
```

reads as *"if value(0) >= 200, jump 0x1440 bits on"* — a distance test choosing
a level of detail. **That is where most models keep their geometry**, which is
why the first version of this walked straight past the polygons and came back
with nothing but a material table. `$2C0` is the unconditional form of the same
jump.

The checks `model.py --stats` reports over the whole archive:

```
  header +0x58 is a known opcode : 130 / 130
  stream walks to a return       : 130 / 130
  vertex count matches the header: 120 / 130
  vertices reproduce the box     :  84 / 130
  and the same with x mirrored   :   5 / 130
  material count matches         :  56 / 130
  face and material indices sane : 128 / 130
```

**Every model in the archive walks to a return.** All 45 opcodes are measured.
Most came off the handlers: count every `MOVE *A7+` as one longword and every
`ADDI #n, A7` as `n/32` more, with the handler's bounds taken from the next
entry in the table. Four of them — `$200`, `$220`, `$280`, `$2A0` — save the
stream pointer in `A8` on entry and end `MOVE A8, A7 / ADDI #n, A7`, and that
`n` is the true advance whatever the body does in between.

Two would not yield to reading, `$040` and `$520`, because both open with calls
that consume operands of their own. Those were settled by **sweeping the pair
against the archive's own checks**, and the answer is sharp: 6 and 5 take every
model to a clean return where 5 or 7 for `$040` drop twenty of them. `$520 = 5`
also matches an independent reading of its handler as *(destination, near, far,
source A, source B)*. Worth being plain that those two are measured by
consequence rather than read off the code.

**Five models are mirrored.** They span their stated box only with x negated,
which is how a left and a right part share one set of vertices — and why pairs
like 491 and 494 state boxes identical to the float. `--stats` counts those on
their own line rather than folding them into the pass, because a mirrored match
is a different claim from a plain one.

What remains is the gap between counts: 120 models decode the right number of
vertices but only 84 reproduce their box, and two still have an index out of
range. The failures have a shape, though — the stated box is consistently a
little *larger* than what we decode, `-7.80..10.50` against a header of
`-8.00..11.00` — which is what you would see if a few vertices come from an
opcode whose operands we skip without reading. `$200`, `$220`, `$280` and
`$2A0` are measured but never interpreted, and they are the obvious suspects.

## Drawing it

`tools/render.py` takes a model and draws it: z-buffered flat-shaded triangles,
one directional light, a graded sky and a hazed ground, at the pod's own
480x360. It writes a PNG using nothing but the standard library.

Three things it does that the checks do not care about:

- **Pick one level of detail.** Walking every branch stacks the near and far
  versions of a model in the same frame, which renders as a lump. Which side of
  a branch carries the detail differs per model, so it walks both ways and
  keeps whichever drew more.
- **Frame on the vertices actually decoded**, not on the stated bounding
  sphere. That sphere has to contain the origin as well, so framing on it
  leaves the model small in the middle of the picture.
- **Draw the cast shadow**, by flattening the model onto the ground plane and
  drawing that before the model itself. The footage has a hard-edged dark
  shadow under every mech and it is most of what sits a model on the ground.

At a 55-degree field of view rather than the 90 it started with, the result
reads the way the footage does: hard facets, one flat tone each, a hard shadow,
haze taking the ground out to the horizon. Model 30 is one of the terrain
mesas; 463 is a mech's head and canopy, the dark viewport slot clearly cut into
the red armour; 133 is one of the flared towers.

One correction worth making here: solids, cylinders and ARES turned out **not**
to be the drawing primitives. They live in the *68020's* own archive, keyed by
the same ids as the visual models but far coarser — a handful of elements per
object where the model has thousands of bytes. They are how the pod reasons
about shape in software, not how the TI puts pixels on the screen. See
DEVICES.md.

**The strategy is not to emulate the TMS340.** It is to intercept the display
list the 68020 already builds and draw it with a modern renderer. Emulating the
graphics processor would mean reproducing its video timing, shift registers and
VRAM to get the same pixels a different way — and, now that the coprocessor is
known to be there, a TMS34082 as well.

`tools/tms340run.py` exists anyway, because running the renderer's own code is
the only way to read a format nothing else documents. It currently boots the
'20 through hardware initialisation, clears both frame buffers, takes the
display interrupt, sets up double buffering and reaches boot stage 5, where it
stops in the routine that uploads the coprocessor's tables. That is the
boundary: **past this point the renderer's behaviour depends on floating-point
results the '82 produces**, so the next real step for the interpreter is the
'82's instruction set, not more of the '20's.

Worth knowing: VWE patented its asset pipeline too — US 5,710,878, "Method for
facilitating material application for a group of objects of a computer graphic"
(McCoy and Albertson, filed June 1995). It describes a tool that collects
models, materials, sounds and joint animation sequences and "produces a resource
for use by a simulation program" — which is to say, it describes the authoring
side of the very archive we are trying to read. It names the media types the
resource holds: polygon-mesh models with vertex normals, materials (Gouraud and
Phong shading, texture, bump and environment mapping), sounds, and joint
animations. Four kinds of thing; the archive has four type classes.

## 2. The auxiliary displays — the secondary screen

**Hardware.** An actual Amiga 500 motherboard on a VWE carrier card, driving the
auxiliary display (part 80) in the lower display portion (75). It does not run
the game; it draws the cockpit's secondary information display.

**What we have.** Its program is in the release — `AMIGA3_0`, 61 KB of Manx
Aztec C, plus `btsecond3_0` — and it is loaded through a window at
`0x40000000`. The handshake is decoded: it writes `0x01234567`, the 68020
answers `0x76543210`, and they agree on a 674-byte shared communication block
the firmware calls SecCom.

**What is missing.** The SecCom protocol. Two routes: HLE it from the 68020
side, or run the 61 KB Amiga program on a second CPU core — `battlepod` already
carries a 68000 core, and Musashi supports multiple contexts.

## 3. The panel — lamps, bar graphs and soft labels

This is the one the patent is clearest about, and the one that is **already
reproducible**.

The patent is explicit that the cockpit deliberately avoided LED and LCD matrix
message displays:

> The displays of the controls within the cockpit use CRT monitors, with lighted
> momentary push buttons located above and below, rather than the conventional
> LED or LCD matrix message displays.

So the panel is a set of small CRTs showing **soft labels**, ringed by
**individually lit momentary pushbuttons** (part 104) — closer to an airliner's
line-select keys than to a row of idiot lights. Each lamp is separately
addressable *with a brightness*, which is why the firmware's diagnostic asks for
one.

**What we have: all of it.** The panel is driven entirely over the Remote I/O
serial link, which is decoded end to end:

| opcode | device | payload |
|---|---|---|
| `0xD1` | display | id, then 8 ASCII characters |
| `0xD2` | bar graph | id, then the number of bars to light |
| `0xD3` | lamp | id, then brightness |
| `0xD5` | — | none; sent once at boot |

framed as `01 <node> <len> <node+len> <payload> <sum(payload)>`, with both
checksums verified. And the id ranges come from the firmware's own prompts:

| device | ids |
|---|---|
| lamps | `0x00`–`0x3B`, `0x50`–`0x53`, `0x60` |
| displays | `0x80`–`0x91` |
| bar graphs | `0x80`–`0x91` except `0x8C`, `0x8D`, `0x8F` |

`battlepod` decodes the captured stream into panel state — which lamp is lit and
how brightly, where each bar graph stands, what each display reads. Drawing that
is a presentation problem, not a reverse-engineering one.

**What is missing** is only the *labelling*: which id is the heat scale, which is
the weapons panel, which pushbutton is which. That is a question for the
operations manuals and the patent figures, not for the firmware — and it can be
answered incrementally, because the pod will happily light any lamp you ask it
to from its own diagnostic menu.

## 4. The controls — inputs on the same wire

Joystick (60), pedals (61), throttle (62), buttons (104) and keypads (85, 134)
all report over the same Remote I/O link, inbound. The firmware's diagnostic
menu has `RIO protocol loopback test` and `Read/display data from RIO_A protocol
handler`, so the inbound direction can be exercised from the pod side before any
of it is wired to a real control.

---

## Order of work

The panel first, because it is done apart from drawing it and it makes the
emulator visibly a cockpit. Then the resource archive, because that is where
the 3D view has to come from and it depends on nothing else — no network, no
Macintosh, no relocations. The secondary screen and the controls after that,
and the network last, since a pod that never joins a game still boots, lights
its panel and renders its view.
