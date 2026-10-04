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

### Six chassis

The mech ids are not a jumble. They fall into blocks, and the blocks say what
they are:

| ids | what |
|---|---|
| `451`–`456` | six **skeletons** — 32 nodes each, box `4.00 x 9.00 x 4.00` to the float, no polygons at all |
| `461`–`466` | six **torsos**, one per skeleton |
| `470`–`480` | limbs, in mirrored pairs — `471`/`474`, `472`/`475`, `473`/`476`, `477`/`478`, `479`/`480` |
| `490`–`496` | a leg set: a centre piece and three mirrored pairs |
| `501`–`505`, `511`–`515` | two five-part limbs, assembled by `516` and `517` |

A skeleton is nothing but structure. Model 451 is ten `$040`s, eight
`$060`/`$080` push and pop pairs, nineteen single vertices and nine plane
records — and not one polygon or material between them. Its stream opens

```
$40  1 0 1 0 $BF4CCCCD 0    $40  2 1 2 0 $3FC00000 0    $40  3 ...
```

which is a chain of node compositions carrying inline floats — `-0.8`, `1.5` —
at a regular stride of seven longwords. That stride is also the independent
confirmation that `$040` takes six operands, which had only been settled by
sweeping it against the archive's checks.

**So there were six chassis**, and the release says which. `Game Files/
Vehicle_List` is 568 bytes of plain text listing 38 vehicles:

```
0 MP-MadCat Prime    4 VP-Vulture Prime   8 LP-Loki Prime
12 TP-Thor Prime     24 Drone             30 SP-Sunder Prime
34 AP-Avatar Prime   170 Director
```

Four Clan OmniMechs, two Inner Sphere ones, a drone and the referee's camera.
Six chassis against six skeletons is not a coincidence, and the cockpit ROM
closes it: `ROM3_0` holds those same 38 vehicles as records of **958 bytes at
`0x70582`**, the name in ASCII at `+0` and a halfword at `+0x28` that is the
only field in the whole 958 bytes landing anywhere near a model id. It
partitions all 38 configurations into exactly six groups:

| id | chassis | configurations |
|---|---|---|
| `451` | **Loki** | Prime, V1-V6, plus the **Drone**, which rides the Loki rig |
| `452` | **MadCat** | Prime, V1-V5 |
| `453` | **Vulture** | Prime, V1-V5, and an "Explo Vulture" |
| `454` | **Thor** | Prime, V1-V7 |
| `455` | **Sunder** | Prime, V1-V3 |
| `456` | **Avatar** | Prime, V1-V3 |

`model.py` labels them, so the tools stop talking in bare numbers.

### Telling them apart

Two things about a part can be measured rather than eyeballed. Mirroring the
vertices and taking the mean distance to the nearest original vertex gives how
symmetric it is; binning them across the width and taking the highest point in
each bin gives the shoulder profile. `model.py --shape` prints both for every
model in the archive.

Which axis to mirror in is itself a measurement, not an assumption — over
`461`-`466` the x plane gives 0.004-0.055 and the y and z planes 0.085-0.18, so
x is the left-right axis and the box centre sits on the origin there.

| id | chassis | symmetry error | height profile across the width | polygons |
|---|---|---|---|---|
| `461` | Loki | **0.037** | `0.94 0.94 0.90 1.00 1.00` | 282 |
| `462` | MadCat | **0.055** | `1.00 1.00 0.58 0.84 0.84` | 248 |
| `463` | Vulture | 0.006 | `1.00 1.00 0.81 1.00 1.00` | 386 |
| `464` | Thor | 0.008 | `1.00 1.00 0.84 1.00 1.00` | 331 |
| `465` | Sunder | 0.005 | `0.96 1.00 0.99 1.00 0.96` | 71 |
| `466` | Avatar | 0.004 | `0.75 1.00 1.00 1.00 0.75` | 66 |

The names on this second table are **inherited**, not measured: `461`-`466`
is a block of six ten ids above a block of six, so it is read as the same six
chassis in the same order. What corroborates it is the polygon counts — the
four Clan chassis come in at 248-386 and the two Inner Sphere ones at 71 and
66, and that split falls exactly where the ROM puts the Clan/Inner Sphere
boundary, at `455`. There is no part table anywhere in the cockpit software to
confirm it outright: `461`, `463`, `465` and `501` do not occur in `ROM3_0` at
all, in either width. Parts are bound by whoever builds the display list, which
is the game server, which is the standing blocker.

An earlier draft of this section guessed `462` was the Thor from its deep
one-sided notch. That was wrong, and wrong in an instructive way. **Thor's
torso is symmetric (0.008).** Its famous one-shoulder missile pod is not part
of the torso mesh at all — it hangs off the rig as a separate part, which is
the same thing the bounding boxes and the instruction stream already said:
the archive holds rigs, not poses, and a configuration is a choice of what to
hang on one.

The same two columns over the skeletons are worth a look on their own: five of
the six place their 19 nodes symmetrically and `456`, the Avatar, does not
(0.0169) — so chassis asymmetry can live in the frame as well as in the load.

### The skeletons are a rest pose, and it stands up

`$040` was on the measured-but-not-interpreted list for a long time: six
operands, one of which was obviously a float. It is a **node composition**, and
the six operands are a node, its parent, a transform slot, and **three floats
that are the node's offset from its parent**. A skeleton is a chain of them and
nothing else, so running the chain gives positions. `model.py --nodes` does:

```
451 Loki
   node  1 <-  0  slot  1  offset   0.00  -0.80   0.00   stands at   0.00  -0.80   0.00
   node  2 <-  1  slot  2  offset   0.00   1.50   0.00   stands at   0.00   0.70   0.00
   node  3 <-  1  slot  7  offset  -1.18   1.00  -0.20   stands at  -1.18   0.20  -0.20
   node  4 <-  3  slot  8  offset   0.08  -2.75   0.26   stands at  -1.10  -2.55   0.06
   node  5 <-  4  slot  9  offset   0.00  -2.00   0.02   stands at  -1.10  -4.55   0.08
   node  9 <-  2  slot  5  offset   1.49   2.20  -0.50   stands at   1.49   2.90  -0.50
```

Hips, torso, a hip/knee/foot down each side, a shoulder out each way, mirrored
to the third decimal. Feet at y −4.55 and shoulders at +2.90 inside a stated
box of −5.00 to +4.00. **That is a BattleMech standing up**, and the check that
says so is not ours: every node has to land inside the bounding box the model
states for itself, and across the six chassis the worst node pokes out by 5.6%
of the model size with three of them at zero.

There are exactly **two leg designs** in the release. Loki, Thor and Sunder put
the knee straight under the hip. MadCat, Vulture and Avatar throw it 2.15 units
backwards and bring the foot forward again — a reverse-jointed, digitigrade
leg, which is what a Clan OmniMech looks like and what makes a Mad Cat
recognisable at a glance.

### Hanging the parts on it

Parts are authored **in the space of the node they hang on**, reaching from
that node down to the next one. Model 471's box runs y −2.75 to +0.24 and the
Loki's hip-to-knee offset is −2.75 exactly. So the part that belongs on a node
is the one whose own bounding box *contains the offset of that node's child*,
and where several do, the smallest. Nothing is placed by hand.

Left and right are separate resources holding the same geometry reflected in
x — 471 and 474 are vertex-for-vertex mirrors — and **which way round they go
is settled by making the part touch what it hangs from**. An earlier version of
this settled it by which way a part's own vertices lean against which way the
node does, and that was wrong: the Loki's thigh straddles its own origin while
the MadCat's sits entirely to one side of it, so a rule about leaning gets one
family right and the other wrong, and the MadCat came out with its legs hanging
in the air beside its hips.

What holds for both is adjacency. Of the two orientations, exactly one lands
the thigh's inner edge **on** the pelvis's outer edge:

```
Loki    hips 470 spans x -0.90..0.90
        node 3 at x -1.18   part 474 -> -2.30..-0.90   gap 0.00  overlap 0.00
                            part 471 -> -1.46..-0.06   gap 0.00  overlap 2.22
MadCat  hips 490 spans x -1.00..1.00
        node 3 at x -1.95   part 494 -> -1.87..-1.00   gap 0.00  overlap 0.00
                            part 491 -> -2.90..-2.03   gap 1.03  overlap 0.00
```

Across the six chassis **all 42 limb joints meet**, the worst by 0.004 units on
a machine nine units tall, which is float noise in the authoring rather than a
gap. The harness guards the count.

Two nodes get their part another way, and both say so in the code. The **torso**
always hangs on node 2: on a chassis with no shoulder nodes at all there is no
child offset to match against, and where there is one, several parts contain it
and the smallest is not the torso — so it comes from the part block ten ids
above the skeleton. A **foot** hangs on a node with nothing below it, so again
there is no offset; it is whatever is left unused in the seven-id block the
rest of that leg came from.

`render.py --mechs` runs it over the archive:

```
 451  Loki     8 parts,  206 polygons: 461 470 474 475 471 472 476 473
 452  MadCat   8 parts,  224 polygons: 462 490 491 492 494 495 496 493
 453  Vulture  8 parts,  242 polygons: 463 490 491 492 494 495 496 493
 454  Thor     8 parts,  211 polygons: 464 470 474 475 471 472 476 473
 455  Sunder   8 parts,  189 polygons: 465 470 474 475 471 472 476 473
 456  Avatar   8 parts,  219 polygons: 466 490 491 492 494 495 496 493
```

Six for six, and the leg families fall out on their own along exactly the split
the node geometry already drew: `470`-`476` for the straight-legged three,
`490`-`496` for the reverse-jointed three. `render.py --mech 452` draws one.

**The feet are not settled.** The rule that decides every other joint cannot
decide these: a foot hangs on a node with nothing below it, and both
orientations of the pair score identically — gap 0.00, overlap 0.42 either way.
Worse, the reverse-jointed chassis come out **7.50 units wide** against the
4.00 their own rig declares, because `493`/`496` are 3.60 across and hang at
ankles 3.90 apart. Either those are not the feet or they do not hang at the
ankle; the parts left in that block fit no better, so this is recorded as open
rather than guessed at. The straight-legged three come out 4.60 wide, which is
close enough to 4.00 to be the same kind of rounding everything else here has.

**The arms were missing here, and are found below** (*The arms*). The vehicle records list a Left and
Right Arm and a Left and Right Weapon Pod among their 21 hit locations, and the
archive holds candidates — `477`-`480`, and `516`/`517`, which are a left/right
pair whose x signs match the shoulder nodes. But the MadCat skeleton has no
shoulder nodes at all, which it plainly needs, so at least one arm mount is
supplied rather than stored. That is the same boundary everything else runs
into: the pose beyond the rest pose, and the choice of what to hang, come from
the game server.

### What a BattleMech is to this game

The chassis names came out of the cockpit ROM, and they came out of a record
that has a great deal more in it. `ROM3_0` carries 38 vehicle records of 958
bytes at `0x70582` — the same 38 `Vehicle_List` numbers — and each one is a
complete statement of a machine:

```
+0x00  name, 40 bytes
+0x28  u16  the skeleton's resource id in the TI archive
+0x32  u16  hit locations to follow, 21 on every vehicle in the release
+0x34  f32 x 12, the first of which is top speed in kph
+0x64  the hit locations, 34 bytes each
         +0x00 name, 24 bytes   +0x18 armour   +0x1a structure
         +0x1c two sub-part ids
       then twelve weapon slots of 12 bytes, ending exactly at the record end
         +0x00 index into the weapon table, 0xFFFF for an empty bay
         +0x04 rounds carried, 0xFFFF for an energy weapon
```

`100 + 21 x 34 + 12 x 12` is 958 to the byte, which is what says the record is
read right rather than merely read plausibly.

Every vehicle has the **same 21 hit locations**, in the same order, with the
same sub-part ids; only the armour and structure numbers change between
chassis:

```
Left/Right Foot        Left/Right Arm          Left/Center/Right Torso
Left/Right Lower Leg   Left/Right Weapon Pod   Lower Torso
Left/Right Upper Leg   Missile Pack            Rear Center/Lower/Left/Right Torso
Hips                   Searchlight
```

That is the mech, part by part, and the two ids on each line are the pair the
renderer's **pick query** hands back when a shot lands on it — the query whose
seven-longword groups this project spent a while calling geometry. They run
from 10 to 51 in consecutive pairs, so ids 0-9 belong to something else.

### Where a shot lands

`$480` pushes a tag over a run of polygons. On a mech part that tag is a **hit
location, one-based** — the same 21 the vehicle records list, in the same
order. Three things say so and none of them is the tag itself.

**Nothing anywhere exceeds 21.** Twenty-seven models in the archive use `$480`
and every tag in all of them falls in 1 to 21, which an arbitrary tag space
would not do.

**A torso tags exactly the torso.** The ten torso hit locations are Left,
Centre, Right, Lower, Rear Centre, Rear Lower, Rear Left, Rear Right, plus the
Missile Pack and Searchlight. Models 461 and 462 tag all ten and nothing else;
the other four tag nine or seven of them, dropping the Missile Pack and, on the
Thor, the rear quarters.

**And the sides agree with the geometry.** The assembly at `516`, whose
vertices all sit at positive x, tags Right Arm and Right Weapon Pod. `517`, its
mirror at negative x, tags the left pair. That is decided twice over — by which
way the model leans and by what the ROM calls the location — and the two agree.

```
 461 Loki     12 Left Torso, 13 Center Torso, 14 Right Torso, 15 Lower Torso,
              16 Rear Center Torso, 17 Missile Pack, 18 Searchlight,
              19 Rear Lower Torso, 20 Rear Left Torso, 21 Rear Right Torso
 501          9 Right Arm, 11 Right Weapon Pod
 511          8 Left Arm, 10 Left Weapon Pod
```

So the chain from a pixel to a damaged component is now complete on paper: the
renderer's pick query returns a sub-part id for whatever is under a point, the
vehicle record turns that into a named location with its own armour and
structure, and `$480` is where the geometry says which polygons are that
location. `model.py --zones` prints it.

Terrain and buildings use the same opcode to group their polygons and tag them
1 and 2. That is a zone number and nothing to do with anybody's left foot, so
only mech parts get their tags named.

**This is also what identifies the arms** (*The arms*, below, says where they go). `516` and `517` are the two arm
assemblies, each drawing five alternative sub-models — five loadouts, one
chosen at draw time. What is not settled is where they go. Hung on the shoulder
nodes they reach far outside the mech's own bounding box, and their geometry
runs six units along z where the whole machine is four deep, which reads as an
arm authored along an axis and rotated into place per frame. That would fit:
the parts that hold still between frames are authored where they sit, and the
ones that aim are not. The MadCat skeleton has no shoulder nodes at all, so at
least one arm mount is supplied rather than stored — the same boundary
everything else here runs into.

### The arms

They were never in the skeleton, and they are not chosen by chassis. Every
Mech draws the same two assemblies, `516` (right) and `517` (left), and the
pod's own display list says what they draw. A Mech's type 3 record carries,
from word 31, the variables its models' predicates test; read against
`516`'s program:

```
node 1 <- 0, instance 5, offset (1.38, 1.80, -1.50)   ; 517: instance 3, x -1.38
if var 44 is zero: draw nothing                         ; the Right Arm's intact value
if var 4 == 1..5: draw 501..505                         ; 517: var 46, var 6, 511..515
```

Vars 4 and 6 are the vehicle record's `+0x2C` and `+0x2E`, copied into the
entity: 3 and 3 for MadCat, Loki and Sunder Primes, 2 and 2 for Vulture,
Thor and Avatar, and some variants differ side to side (Loki V1 is 1 and 2).
That is the evidence for word 31: the same two numbers turn up in the
frame's words 35 and 37 for all six chassis, and on that alignment vars 44
and 46 land on per-location values that read 1.0 on an undamaged Mech.
Variant 5 decodes to nothing, which is a chassis with no arm; nothing in
this release's 38 records uses it.

Instances 5 and 3 are the skeleton's shoulder slots (nodes 9 and 11 on the
Loki), and in the frame both are identity at rest, so an arm hangs at its
offset from the Mech's root, authored pointing forward (+z, the way the toes
point). `frame_draw` adds the shoulder (516/517's own few polygons) and the
chosen arm to the assembled Mech: the Loki goes from 206 polygons to 320.

The arm models keep their forearm behind three kinds of branch - a distance
test for the level of detail, the weapon pod's intact value, and face-facing
groups - so neither single path the other parts use draws more than the
upper arm. `mesh.h`'s `MESH_NEAR` takes the near level, the intact branch
and both sides of every face group; it is C only and used only for the arms,
so the Python port and the harness's decoder totals are unchanged.

Still open: an arm that aims. The instance transforms are identity in every
frame captured so far, with nobody firing at anything; one more 3x3 follows
the fifteen of them in the record, and is not identified.

### The weapon table

Twenty weapons of 60 bytes at `0x7D018`, `--weapons` prints them:

```
+0    name, 24 bytes   +34  damage        +46  f32 heat
+25   short HUD name   +38  range, metres +56  1 direct fire, 2 missiles
```

The numeric fields are not longword aligned, which the 68020 does not mind and
which cost an hour of reading them two bytes early.

What says they are right is that the table is internally consistent in a way a
wrong offset could not fake. Ranges are round numbers in metres — 150 for
machine guns, 6000 for every LRM regardless of rack size. Heat runs from 0.0
for a machine gun to 16.0 for an ER PPC, with the Gauss rifle down at 4.0
where a mass driver belongs. And **every ER laser out-ranges its base weapon
at identical damage for more heat** — 350 to 500 metres and 2.0 to 3.5 heat
from Medium to ER Medium — which is exactly, and only, what extended range
means.

### Checked against the release's own spreadsheet

A decode that is wrong but self-consistent passes every test you build out of
the same bytes. So the vehicle table is checked against a spreadsheet that
shipped in the release. `New mechs and VTV` writes out three loadouts in
English — MadCat V4, MadCat V5 and Thor V7 — and decoding those three records
has to reproduce them.

It does. All three come out with the right weapons, the right number of each,
and the rounds to match:

```
MadCat V4    7 weapons, names match, rounds match
Madcat V5    6 weapons, names match, rounds match
THOR V7     11 weapons, names match, rounds differ
     rom says Short Range Missile 4 pk (25)    the spreadsheet says 24
```

One round of SRM ammunition on one configuration, out of 24 weapons and
fourteen ammunition counts across the three. That is a design document and a
shipped build disagreeing, not a decode that is wrong — the spreadsheet is
dated before the release it describes. The harness guards all of it:
`tools/vehicles.py --check`, five checkpoints.

The loadouts also read correctly as BattleTech. Loki V2 carries twin ER PPCs
and nothing else but lasers, which is the Hellbringer Prime; MadCat Prime
carries a PPC, two LRM 15 racks and four lasers. Nobody could have got those
by accident from a wrong table.

### Checking against something outside the project

BattleTech's mechs are among the most drawn machines in science fiction, which
makes them a check this project could not otherwise get: a self-consistent
wrong decode can satisfy every internal test, but it cannot accidentally
produce a shape the rest of the world already recognises.

Rendered side-on, the high-id parts are unmistakable. **463** is a mech torso —
a wedge with a dark slit across the front where the canopy goes and a second
aperture on the flank. **466** is a weapon pod with a barrel protruding from a
rounded housing. **465** is a boxy rack of the kind the Clan mechs in the data
supplement carry on their shoulders. Those are BattleTech components, drawn
from floats this project decoded out of an instruction stream.

Their material tables read like paint schemes rather than like noise. Model 463
declares nine: browns and reds for armour across 322 of its polygons, a dark
grey, a **near-black with a blue cast** (`0.009, 0.008, 0.041`) on 17 — canopy
glass — a **green** (`0.20, 0.60, 0.20`) on four, and a **bright yellow**
(`0.975, 0.938, 0.300`) on seven.

### Materials are lit or emissive, and the archive says which

That yellow is the only one of the nine declared `kind 0`; the other eight are
`kind 1`. Across the whole archive:

| | count | mean luminance | median |
|---|---|---|---|
| `kind 0` | 150 | 0.655 | 0.738 |
| `kind 1` | 1573 | 0.368 | 0.312 |

and **every one of the 212 lights and markers points at a `kind 0` material —
not one points at a `kind 1`.** So `kind 0` is emissive and `kind 1` is a lit
surface, which is what `$4C0` "flat" and `$4E0` "lit" were saying all along.
`render.py` gives kind 0 no lighting term, so a cockpit lamp stays lit on the
side facing away from the sun.

### Lights

Four opcodes draw something other than a polygon, and all four gate on
visibility first:

| opcode | what it draws |
|---|---|
| `$200` | one pixel at a vertex, via `PIXT` — gated on the face facing |
| `$220` | a rectangle filled between two corners — `RPIX` then `FILL` |
| `$280`, `$2A0` | a marker at a vertex, sized by a world measurement the handler streams to the coprocessor to scale by distance |

`$200` takes a face, a vertex and a material; `$280`/`$2A0` take a vertex, that
size as an inline float, and a material. Model 112 is the proof the reading is
right: **92 `$200` points, every one of them on material 2** — which is `kind 0`
and `1.00, 0.80, 0.50`, a warm amber — while its 25 polygons use material 1, a
flat grey. A dark structure with ninety-two lights on it. Model 84 shows the
other form, eleven markers at real sizes from 0.1 to 0.37 across five
materials.

`render.py` draws them unlit, since they are emissive, and biases them a hair
toward the camera: a light sits *on* the surface it belongs to, so it is
coplanar with the polygon underneath and loses a straight depth test.

### Models draw other models

`$460` takes a resource id and runs *that* model in place:

```
FE015E00  MOVE  *A7+, A0, 1        ; a resource id
FE015E10  MOVE  A7, -*SP, 1
FE015E20  CALLR $FE00DF90          ; run that model
FE015E40  MOVE  *SP+, A7, 1
```

Twenty-two models use it, and the two most interesting are `516` and `517`:
they draw `501`–`505` and `511`–`515`, which are exactly the mech part sets the
bounding boxes identified, and they are the only two models that compose
transforms with `$040`. **So assembly does happen inside the model format**, at
least for these — 516 goes from 7 polygons to 1035 once its sub-models are
pulled in.

`model.py` follows them when given the archive to resolve ids against. Their
geometry joins the mesh but not the `written` list the box check uses, because
the box a model states is over its own vertices — all 19 models that use `$460`
and have a correct vertex count already span their box without the sub-model's.

**They arrive unplaced, and that is the right answer rather than a gap.**
`$040` reads three operands and does this:

```
FE00F5D0  MOVE *A7+, A13      ; node i,  from the model's node table (56 bytes each)
FE00F600  MOVE *A7+, A13      ; node j,  same table
FE00F650  MOVE *A7+, A13      ; instance k
FE00F660  DEC  A13            ; one-based
FE00F670  MPYU #$180, A13     ; 48 bytes - twelve floats, a 3x3 and a translation
FE00F680  ADD  A13, A10       ; into the array at @$FE028C60
```

So a model says *node i becomes node j composed with instance transform k* —
the shape of a rig. But the 48-byte instance array is **not allocated from the
model's header**: the seven counts there allocate 28, 16, 36, 56, 40, 12 and 20
bytes an entry, and none of them is 48. `@$FE028C60` is a global the caller
sets before running the model.

**The archive holds rigs, not poses.** A model names its parts and says how
they compose; the transforms that actually place them are handed in from
outside, per frame, by the 68020 — which is the same conclusion the part
bounding boxes reached from the other direction. With no pose to supply, every
node composes to identity and 516's 1035 polygons pile up at the origin. That
is not our tooling failing; it is what the data says on its own.

### Whole maps, from the release's own scenario files

`Console Files/Game Files/Scenarios` holds eleven of them - BadLands, Nazca,
Twycross, Outreach, Arena and the rest - and they are **plain text**. The
grammar is not guessed: it came out of the operator console, which parses them
with `scanf` and logs what each line becomes, and `tools/opscon.py --formats`
recovers both:

```
GROUND_CLASS    %d %d %f %f %f %f %f %d %d
TERRAIN_CLASS   %d %d %f %f %f %f %f %d
```

Read against the console's own `thing, class, shape, x, y, z` log line, the
columns are a class, a **model resource id**, a position, a heading in degrees
and a scale. The id column is what makes this worth having: it names a type 1
resource, which this project already decodes and draws. **A scenario is a list
of models to place.**

```
scenario objects placed  : 882      BadLands-16, the largest
scenario models used     : 19
scenario models decoded  : 16
```

`battlepod --scene FILE --scene-out FILE.rgb` draws the lot - 9,308 polygons
for BadLands - with `src/scene.h` reading the file and `ras_draw_at` placing
each object by its own heading and scale. One decoded model is drawn hundreds
of times, which is what the display list does too, and is why the rasteriser
takes a placement rather than a merged mesh the size of a map.

**Which column names the model differs by record length, and getting it wrong
draws the collision hulls instead.** On a nine-field record, column 1 holds
shapes of 0 to 7 polygons with radii in the hundreds - a hull, not a model -
while column 8 holds the real geometry: 132 polygons for the terrain mesa, 151
for a building. An eight-field record has no column 8 and its column 1 is the
drawable one. That is what the console's `thing, class, shape` log line is
doing with three ids.

The maps are thousands of units across where a mech is nine tall, so from above
the objects are specks. `--scene-view turn pitch zoom` puts the camera down
among them, and from there BadLands is mesas and buildings receding into haze -
which is what the period footage shows. One of the seventeen models it names
decodes to no geometry, which is not yet explained.

This needs no game running, which is why it was worth doing now: it is the
first thing in this project to draw a whole world rather than one object.

### Standing where the pilot stood

Every scenario opens with a block of five-column drop points - a facing in
degrees, a position, a height - before the map records, terminated by
`-1 -1 -1 -1 -1`. BadLands has sixteen, one per pod. `--scene-drop N` puts the
camera at one of them:

```
./build/battlepod.exe "$GF/Full_Load_3_0"     --scene "$GF/Scenarios/BadLands-16" --scene-drop 0 --scene-out out/pod.rgb
```

The camera model orbits a centre, so standing somewhere means putting the
centre one look-ahead in front and turning to match. A heading of h needs
**turn = -h**, which is what makes the world direction `(sin h, 0, cos h)` come
out as straight ahead in view space.

The height column is 5.4 on every drop in every map, which is a cockpit on a
machine nine units tall - so this is eye level, not a camera position someone
chose.

What comes out is the picture the pod showed. BadLands is mesas and rock spires
strung along the horizon over sand; Urbana, from its own drop point, is tower
blocks and low buildings - a city. Same code, same archive, different scenario
file.

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
