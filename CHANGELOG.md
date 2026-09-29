# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **A centre: several pods, CPU pilots, one hub.** `tools/hub.py` launches
  pods as separate processes joined over UDP, starts the game on each as the
  console does, relays their traffic, and flies bots through the panel's own
  input reports - steer at the nearest Mech, close, and hold the trigger
  while pointing at it. Two bots on BadLands close from 240 apart to under
  100, facing each other.
- **`--net HOST:PORT`**, **`--net-node N`** and **`--realtime`** in the
  emulator; the packet queue grows while a pod runs.
- **Every pod in a game carries the game's address.** A receiver forwards
  anything not stamped with it, so pods with addresses of their own relay
  each other's traffic without end.
- **Frames are paced in real time** to at least 3 hundredths, about what the
  board managed; an instant renderer otherwise runs a pod's frame loop, and
  its broadcasts, thousands of times a second.
- Heading h walks along (sin h, -cos h). Scenario 4S.
- **Open**: nobody dies yet. Networked pods fire at each other, but damage to
  a Mech is decided on the pod that owns it, and how it learns of a hit is
  not read.
- **Two pods talk.** A pod transmits once it has an address at `0x0218AEB0`,
  a hub node in `0x0218AEB3` and a game identity at `0x02179D32`: the sender
  reaches the boot monitor's `+0x24` with node, length and buffer. A driving
  pod sends `0xEC` and `0xE7` in pairs. Fed to a second pod that has the same
  Mechs from the console, they move its copy of the first pod's Mech to
  where the first pod put it.
- **`--send-log FILE`** writes every packet the pod transmits, in the form
  `--packet-file` reads, and the report counts them.
- Scenario 4R. **282/282.**
- **It can be played.** `cockpit.exe --live-pod` draws the pod's own frames
  in the main view and turns the keyboard into the panel's input reports -
  W/S throttle, A/D stick, space fire, T target select, L searchlight - and
  `tools/play.sh [scenario] [vehicle]` starts a game on it the way the
  console does: range, your Mech at a drop point, a Loki ahead, the map,
  `PLAYER_LINK`.
- **The timebase is paced to the wall clock in live play.** The emulator runs
  about four million instructions a second even while drawing; left to tick
  on instructions the game would run many times real speed.
- **The stick steers** in advanced mode with "stick turns" (buttons `33` and
  `31`): `A1` and `A2` turn the Mech opposite ways.
- `frame_draw` is shared by `--frame-out` and the live view, and caches each
  model it decodes. `BATTLEPOD_NO_HOLD=1` lets a headless live run exit.
- Scenario 4Q plays a game headless and checks the frame and the clock.
  **279/279.**
- **The buttons, and a fight.** The Mech's button switch at `0x02132536`
  names its own arms on the head-up display - radar, map and damage displays,
  torso twist, view up and down, the searchlight, target select, forward
  observer, basic and advanced control. `A5`-`A7` are the **triggers**. One
  `B1 A5` from a MadCat with a Loki 100 units ahead fires shots out of the
  arena, puts the fire on the wire, and **destroys the Loki**: `0x0213424E`
  sets off its explosions and tears it down.
- Buttons `30`/`31` choose whether the stick moves the crosshairs or the
  torso, which is why the stick alone seemed to do nothing.
- **`--frame-at N`** draws display list N rather than the last one that
  placed a model, and `--frame-out` reports which list it drew of how many.
- **`BATTLEPOD_UNBUFFERED=1`** makes stdout unbuffered, so a run that dies
  keeps its output.
- **Fixed**: the top-of-arena allocator `0x0214C61E` was written up as never
  used. It has no direct callers, but a fight fills it with class 5 hit
  effects.
- Scenario 4P. **277/277.**
- **The controls work.** The panel's input reports, named by the firmware's
  own input viewer: `B0`/`B1 id` a button up and down, `C0 id hi lo` an
  analog value, `D0 key` a keypad key. Analog `A0`-`A4` are filed into the
  pilot's Mech at `+0x84`-`+0x8C`; `A0` is the throttle and `A4` turns it.
  Full throttle, `0x340`, is exactly the chassis' top speed.
- **The timebase counts hundredths of a second**, not milliseconds: a MadCat
  Prime at full throttle moves 0.26944 a tick, its 97 kph in metres per
  hundredth.
- **`--rio-late N`** holds the panel's input back until the packet queue has
  gone and the wire has been polled N more times, because a Mech still
  dropping in ignores its controls. The end-of-run report says how many times
  the wire was polled.
- **`--peek` refuses to go past its limit**, now 32, instead of being read as
  an unknown option.
- Scenario 4O. **275/275.**
- **A game started the way the console starts one, with nothing written into
  memory by hand**: `0xE5` for the range, `0xE4` MECH_CLASS for each vehicle,
  the map as `0xE4`s, `0xED` PLAYER_LINK. The pod flies its MadCat from a
  cockpit 8.2 up and draws a Loki standing in BadLands in front of it.
- **`0xE4` is the console's create message** - `Reset world` (class -1),
  `MECH_CLASS` (class 1) and `Downloading Map` (classes 2, 3 and 6) are all
  it. `0x0213CF5E` switches on the class at `+0x0E` and builds into the arena
  slot `+0x12` names. MECH_CLASS carries the vehicle record at `+0x4A`, the
  heading at `+0x50`, the name at `+0x22`; map objects the shape at `+0x22`
  and scale and heading after it.
- **`tools/mapsend.py`** turns a scenario file into those packets, and
  **`--packet-file`** feeds them - a map is hundreds; `--packet` held eight.
  All 882 of BadLands-16's objects go in without one `Create unknown thing`.
- `--frame-out` now captures past the 400th renderer command, silently, so it
  sees the latest frame.
- **Fixed**: the class-to-draw-routine table in DEVICES.md had classes 2, 3
  and 6 on the wrong routines; class 3 is `0x0214C228`.
- Scenarios 4K-4N. **272/272.**
- **`--frame-out FILE` draws what the pod put on screen**: the camera and every
  placed model from the last display list the firmware posted, with skeletons
  assembled into whole mechs. The first one is a MadCat, 224 polygons, feet on
  the ground, seen from 40 units off.
- **The chassis is `0xF8`'s `+0x08`**, an index into the ROM's 38 vehicle
  records in the order `tools/vehicles.py` reads them. The pod agrees on all
  six skeletons: 0 MadCat 452, 4 Vulture 453, 8 Loki 451, 12 Thor 454,
  30 Sunder 455, 34 Avatar 456.
- **A pilot with nothing written by hand.** `0xED` is `PLAYER_LINK`: it
  switches on the class of the entity `+0x32` names, and for a Mech makes it
  `My_Mech_Ptr` when `+0x08`/`+0x09` are this pod's node. `0xE5`, `0xF8`,
  `0xED` and the pod is flying the Mech it was given - the order the console's
  own log starts a game in.
- `0x02134F06` is the **game-over reset**, reached only once the mission clock
  is negative - not the start of a game. `0xE8` is a class-dispatched
  **destroy**.
- **A type 3's layout**: entity, model, a 3x3, the position, 21 joint pairs
  and 16 node matrices. A MadCat's and a Loki's differ only in the model id.
- **The `$2C0` scene item's third value is the heading**, not a near plane.
- Scenarios 4I (the Avatar) and 4J (the linked pilot), and the frame drawn in
  4H. **264/264.**
- **The created Mech is drawn**: a MadCat, as the firmware's own type 3 record
  naming model `0x1C4` (452), with a type 4 on the ground under it and a
  type 5 searchlight at 8.2 up, colour (1.0, 0.8, 0.4), cone cos 20°/10°. The
  frame goes from 132 longwords to 446.
- **What stood in the way was the pod's visibility range**, not the renderer
  and not the Mech. The culler `0x02111636` passes a thing only within its
  radius plus `min(its range, the view limit)`, and the view limit is
  `0x02193C24 + 0x02193C28` - written in exactly one place, `0xE5`'s handler,
  from packet `+0x44` and `+0x48`. Every `0xE5` sent so far had zeros there.
- **The culler, read by hand past the disassembler's misdecoded FPU
  branches**: it returns 1 for out of range, 2 for outside the view cone and 0
  for visible, and the cone's width is `tan` of the viewer's `+0x118`, a half
  field of view the Mech constructor sets to 30.0 and a hand-classed slot 0
  never gets.
- **The world pass**: `0x0212E650` walks all 1000 slots and dispatches on
  `Class_ID` through a 13-entry table at `0x0212E944`; the Mech's routine is
  `0x0212F2C2`. Classes 0 and 7 draw nothing.
- **Correction to the entry below: the 357 draw-model items are the head-up
  display.** Model `0x48` is a targeting reticle animated through `0x4F`,
  `0x5F`/`0x60` sit at screen coordinates, and the block also prints a `%4.0f`
  range. The viewer's `+0x67C` is its target record.
- **Unrecognised display-list records are printed raw** instead of as a bare
  length; the Mech was a type 3 nobody could see inside.
- **`--tap` stops with an error past its limit**, which is now 32, rather than
  dropping the ninth tap in silence and making its address look unreached.
- Scenario 4G (which draw-model call sites run), scenario 4H (the Mech seen)
  with a no-range control. **260/260.**
- **`--vmtrace` now logs the interpreter's own program counter** alongside the
  opcode. It is a pointer in the interpreter's frame at `(-$10e,A6)` - the cell
  every operand-taking arm steps with `addq.l #1` - and it turns an opcode
  stream into an instruction map: consecutive entries give the exact length of
  every instruction the pod executed.
- **`mission_dis.py --trace`** holds the inferred operand lengths up against
  that map. On an 8192-instruction run it confirms **all 7612 straight-line
  steps** and contradicts none.
- **Operand readers are now read out of the ROM instead of listed.** An arm
  that hands the program counter to a reader consumes its operand in there, and
  only one reader had been recognised. There are three: `0x0211995C` takes two
  bytes (a 16-bit operand), `0x021199A8` takes four (16.14 fixed point,
  `hi + lo/16384`, via two calls to the first), and `0x0211A80C` takes an
  `$FF`-terminated byte list. So **`0x60` pushes a fixed-point constant** and
  takes four operand bytes, not zero, and **`0x09` takes a terminated list**
  whose length is in the stream.
- **`0x64` pushes a string literal**: a length byte, that many bytes of
  NUL-terminated text, then execution resumes after them. Twenty-one literals
  appear across the thirteen routines - `'exitScreen'`, `'VGL Universe 34933'`,
  `'STATS (kills/deaths)'`, `'Transition at T - %0t'`, `'Speed %1d'`,
  `"('NoseCam')"`. The resume address agrees with the trace **127 times out of
  127**.
- **`0x0A` is the interpreter's `printf`** - it follows a `0x64` in 70 cases out
  of 70, and `0x0211A89A` has the `%` test, the `*` test, a ctype table at
  `0x0218247F` and a 39-byte buffer at `0x021827BC`. **`0x0B` takes a pushed
  name**: `B1_BattleTech_1` pushes `'exitScreen'` and then runs `0x0B`, which is
  why the routine name table exists.
- **`xref.py --calls`** finds every site that calls or jumps to an address,
  across all four call forms - `bsr.b` included, which is two bytes where the
  others are four and which a word-stepping scanner walks straight over. An
  under-reported caller list reads as a finding.
- **The slot allocator** at `0x0211E15E`: 16 slots of stride 0x6C0 from a base
  the caller passes, free bit at `+0x0D` bit 0, and on a free slot it writes the
  class to `+0x02`, the index to `+0x06` and `7` to `+0x0A`. Both constructors
  use it, each has exactly one caller, and both callers are unused mission
  opcodes. `0x20`'s handler is the matching reset.
- **The ROM carries two games.** `0x0211786C` tests `[0x021B74B2]` and writes
  one of two script-table addresses into `[0x0216F49C]`. The one nobody had
  read is **Red Planet and Martian Football** - `R1_Red_Planet_1`,
  `F1_Martian_Footb`, `mfExit`, `lockExit` and thirteen more, eighteen routines
  in the same bytecode. A write trap on the pointer is what found it.
- **`--wtrap BASE[:LEN]`** logs every write into a range with the pc that made
  it. `--watch` only ever reported reads - a write to mapped memory takes the
  fast path and returns before anything is noted - so the question "where did
  this value come from" had no answer short of reading 231 references by hand.
- **`mission_dis.py --reach`**, and the claim it makes is now sound: the
  successor rule accounts for **every jump in an 8192-instruction trace**, and
  all 979 executed addresses fall inside the 2329 it reaches.

| | routines | instructions | opcodes | creation opcodes |
|---|---|---|---|---|
| BattleTech | 13 | 2329 | 70 | **0** |
| Red Planet | 18 | 4688 | 68 | **0** |

- **`mission_dis.py --strings`**, and with it what the other game is. **Red
  Planet** is a scored race - `Score %1d`, `Scoring zones: %1d`, `%1d KPH`,
  `Leader Board`, `Leader is %0n %0L`, `*Winner-Cam*` and `*Loser-Cam*`, all
  captioned `Live from Red Planet`. **Martian Football** is a team sport in the
  same vehicles: `(No team)` / `Red Team` / `Blue Team`, a `Position` that is
  `Runner`, `Blocker`, `Crusher` or `?`, counts of `Blockers` and `Crushers`,
  and the caption `Martian Football: live from Red Planet`. Its title line is
  `Red Planet / Martian Football` and its build string `VGL Universe 34934a`
  against Red Planet's `34934` - a mode of Red Planet, not a separate title.
- **BattleTech's own HUD text**, from the same source: `Shoulder view`,
  `Ground cam`, `Map view`, `STATS (kills/deaths)`, `%1d kills`, `%1d deaths`,
  `Speed %1d`, `%2d/%3d`.
- **The interpreter's `printf` conversions.** `%` then an optional `*` then a
  digit then a letter; the digit is a slot number, `*` takes the slot number
  from the float argument at that index. `N`/`n` first name, `V`/`v` vehicle,
  `L`/`l` last name, `D`/`d` integer, `F`/`f` float, `T`/`t` time.
- **The roster**: 20 slots of 30 bytes at mission record `+0x1CE4`, first name
  at `+0x08`, vehicle at `+0x0C`, last name at `+0x10`, with the float
  arguments at `+0x1CB8` and the output buffer at `0x021827BC`. Mission opcodes
  `0x10`-`0x16` and `0x8D` maintain it. On a booted pod it is entirely zero, as
  is the 60 x 64-byte table at `0x02182816` that `0x10` indexes - which is why
  `%1d deaths` formats to `" "` and `"deaths"` with nothing between them.
- **What gives an entity its class.** Three routines write it, all indexing the
  arena at `0x021F99AC` with stride `0x6B4` and all writing the same three
  fields - class to `+0x02`, slot index to `+0x06`, `7` to `+0x0A`.
  `0x0214C57E` is the workhorse with **nine callers, one per class**, including
  `0x0212D060` for **class 1, the Mech**; `0x0214C4FC` has four (class 4 three
  times, class 9 Camship); `0x0214C61E` allocates from slot 950 upward and
  nothing calls it.
- **The class numbering**, from `Create_Thing`'s own 19-way switch: 1 Mech,
  6 and 8 Escape pod, 9 Camship, 10 and 18 Hovercraft, 12 VTV, 16 Copter.
- **`Create_Thing` does not build into the arena.** Opcode `0x24` passes the
  mission's own record, and `0x0211E15E` allocates 16 slots of `0x6C0` inside
  it. That is why its stride never matched the arena's - it is a different
  table, and the two only look alike because both carry class, number and flags
  at the same offsets.
- **The gate in front of the whole game.** `0x02134F06` decides whether
  `My_Mech_Ptr` is a real Mech or arena slot 0: it wants the game length
  positive and bit 1 of `0x02193C13`, and both arrive in an `0xE5` packet
  (`+0x3C` and `+0x30`, copied by `0x0210E212`). But it is only reachable
  through a **dispatch on `My_Mech_Ptr`'s own class**, and a fresh pod's
  `My_Mech_Ptr` is slot 0 with class 0. Forcing slot 0 to class 1 breaks the
  circle: the class 1 arm runs every frame and a mission run goes from 400
  renderer commands to 42300, the count a pod reaches with no mission at all.
- **`0xF8` is the other way in.** `0xF6`-`0xFF` dispatch to `0x02103702`, which
  switches on the same byte again; `0xF8`'s arm destroys whatever `0x0215DD0A`
  names and, on payload selector 1, builds a class 1 Mech straight into
  `My_Mech_Ptr`. Injecting it reaches the arm but not the selector - the
  payload is a buffer at `0x02183716`, not the bytes on the wire.
- **The first entity this project has created.** `0xF8` with the create
  selector at `+0x02` set to 1 builds a class 1 Mech through the arena
  allocator: entity 1 comes back with `Class_ID` 1, `Number` 1, `Thing_Flags`
  7, and the arena cursor at `0x021A5DB8` moved on. It is not drawn yet.
- **The pod draws.** A viewer whose class is 0 posts a display list with **no
  draw-model items at all**; give arena slot 0 a class of 1 and the same run,
  step for step, posts **357**, naming models **72, 73, 95 and 96**. What was
  missing was never the renderer - it was a viewer with a class.
- **`0x0212DB70` is the per-frame cull entry**: it clears the six counters the
  firmware's own `----- CULLING -----` report prints (`0x02194054` Total
  through `0x02194068` Cone Reject) and tests bit 0 of the viewing entity's
  `+0xBB`. Its one caller is `0x02139140`. With a viewer class and a created
  Mech the report goes from `Total 0` to **`Total 1`**, with `Model Time`
  non-zero - the Mech is a candidate the culler tests.
- **What a created Mech contains**: position floats at `+0x26`/`+0x2A`/`+0x2E`,
  an orientation block to `+0x50`, hit-location records from `+0x2C0` carrying
  `PPC`, `E LAS MD`, `LASER MD` and `LRM 1524`, forty damage tables from
  `+0x490`. The constructor does the whole job.
- Fifteen checkpoints, three scenarios, and the check helpers hoisted out of
  the model-archive block so later sections can use them. **250/250.**

### Fixed

- **`--clock` was writing over every injected packet.** The monitor's
  received-packet buffer put the packet body at `0x02000804` and the firmware's
  millisecond timebase is at `0x02000808`, so bytes 4 through 7 of everything
  this project has ever put on the wire were a free-running counter. Nothing
  had needed those bytes - the fields exercised so far all sit at `+0x08` and
  beyond - until `0xF8`'s create selector turned out to be a longword at
  `+0x02`, which spans bytes 2 to 5 and so read half selector and half clock.
  The buffer has moved to `+0x600`, `mon_install` warns if the clock lands
  inside it, and the harness is unchanged at 246 with the move. Recorded in
  FALSE-TRAILS.md.

### Fixed

- **`0x07` and `0x08` are not jumps.** They take eight and six operand bytes.
  Their reader works on the caller's argument in place - `addq.l #1,($c,A6)` -
  where every other reader keeps its own copy in `(-$4,A6)`, so matching one
  spelling of the step read both as zero-length, and an arm that reads nothing
  and writes the program counter looks exactly like a jump. Their handlers also
  hand the counter over by value rather than by address.
- **`0x42` is a call, not a jump**: a `0x44` at `0x0216B4CA` returns to
  `0x0216BA8C`, which is where the `0x42` at `0x0216BA89` came from.
- **The operand counter followed a reader into `printf`** and charged `0x07`
  for an `addq.l` inside it. A call is another reader only if it is handed the
  pointer.

### Fixed

- **`0x24` was a false lead, and the premise under a week of work with it.** It
  is the ROM's only caller of `Create_Thing` and no mission runs it - but
  walking all thirteen routines from their entries, both arms of every branch,
  finds **no creation opcode at all in any mission script in the ROM**. "The
  mission never executes `0x24`" describes the design rather than a fault:
  scripts do not create the things in a world. The guard branch that was being
  searched for does not exist. DEVICES.md and UNRESOLVED.md corrected in place;
  recorded in FALSE-TRAILS.md.
- **The twenty-three candidate guard branches were all `printf`s.** `0x25` is
  `%` and `0x20` is a space, and both are opcodes, so every format string in
  the mission disassembled into what looked like object-creating instructions
  sitting in a branch that never ran. Reading `0x64`'s skipped bytes as text
  rather than as code removes every one of them: static reachability drops from
  an inflated 1034 to **986 instructions, with no creation opcode among them**.
- **The mission loop is not waiting for the renderer either.** Running the same
  script with and without `--rirq` - frames completing and frames never
  completing - gives an identical trace. It does respond to the script:
  `B2_BattleTech_2` diverges from `B1_BattleTech_1` at the 1418th opcode.
- A word-by-word scan read **68881 extension words as branches**
  (`fmove.s FP0,(-$4,A6)` is `F22E 6400 FFFC`), and **`bsr.b` was not decoded**
  at all. Both are recorded in FALSE-TRAILS.md.

### Added

- **`0xED`'s class 1 arm is the player-link path, and it is reachable**: entity
  1 a Mech, entity 2 the mission, three packets in order - a game length, an
  `0xED` naming the mech, an `0xED` naming the mission - and both arms run.
- **It changes nothing.** The mission executes **8192 opcodes using 65 distinct
  ones with and without a linked player, and the two traces are identical** -
  not similar in shape, the same opcodes in the same order. `0x24` runs neither
  time.
- So **the loop is not waiting for a player**, which was the obvious hypothesis.
  What remains is another pod on the wire, a renderer state the stub does not
  reach, or something in the mission record we have not learned to fill.
- One more checkpoint. **208/208.**

- **The control flow, named**, with a real mission's execution counts beside
  it: `0x41` **conditional branch** (114) - a 16-bit displacement, a popped
  condition; `0x42` **unconditional jump** (84); `0x44` **return** (84); `0x40`
  the other displacement branch (51); `0x07`/`0x08` a matched pair (60/59);
  `0x64` (127) a PC transform. `0x41` being the busiest branch, and `0x42` and
  `0x44` running the same number of times, is what a program full of small
  routines and one polling loop looks like.
- **One opcode defeats the operand-length rule**, and the exception is listed
  with its reason rather than hidden in a heuristic: `0x64` hands the program
  counter to its helper *by value* and takes a new one back, and the helper
  does the `addq.l #1` on its own copy.
- With it, `B1_BattleTech_1`'s body walks 55 instructions and stops at the same
  address as before. **The tool stopping in the same place under a different
  rule is the evidence that it is the routine ending rather than the rule being
  wrong.**
- Two more checkpoints. **207/207.**

- **The interpreter has six value types, and two type-dispatched
  instructions.** `0x73 t` **loads** a value of type `t` - its arms end in the
  push helper - and `0x70 t` **stores** one, its arms beginning with a pop.
  Type 0 is a **string**: `0x70`'s slot 0 pops and calls `strncpy`. Type 2 is
  the integer the plain push tags its frames with. Six of a possible eleven
  types exist.
- Which is why they are among the busiest instructions a mission runs: they
  are not calls out to the engine, they are **how the program reads and writes
  anything at all**.
- One more checkpoint. **206/206.**

### Fixed

- **`0x70` and `0x73` are not families of built-in calls.** They dispatch on
  their operand byte eleven ways each, which looked like two tables of engine
  calls. `0x73`'s own error message settles it - `deref:Illegal value type
  %d!` - so the operand is a **value type**. Written up as built-ins for one
  commit on the strength of the shape alone; the string was a hundred bytes
  away.

- **`0x65 n` pushes local `n`** - its helper multiplies the operand by the
  frame size and adds `0x021B74BE`, so that pointer is a **frame base** and the
  script object's `+0x1C88` is where a routine's locals live, not a second
  stack in the loose sense. It is the second-busiest instruction a mission
  runs, which is what reading variables looks like.
- **`0x70` and `0x73` are multiplexed**: each takes an operand byte and
  dispatches on it again, **eleven ways each**. They are the third and fifth
  busiest instructions. No other one-operand opcode does this - for the rest
  the operand is data.
- So the effective instruction set is **94 opcodes plus 22 built-ins**, and a
  mission spends most of its time pushing constants, reading locals and calling
  into those two families.
- Three more checkpoints. **205/205.**

- **The interpreter's operand stack is typed.** Push writes a **type tag** at
  `+0x00` and the value at `+0x04` of a 0x4C-byte frame - which is why the
  readers return `+0x04`, and why there are separate ones for integers and
  floats. Pushing an integer writes tag `2`. The machine does floating-point
  arithmetic as well: one arm pops two values, `fadd`s them and pushes.
- **Five opcodes named**: `0x0B` schedule a routine at a time, `0x24` create a
  thing, **`0x44` return** (pop the program counter; a null one prints
  `Popped NULL return address, interpreter stopping.` and halts), `0x61` push a
  byte, `0x62` push a 16-bit word.
- `0x61` and `0x62` are over a third of everything a mission executes, which is
  what a stack machine looks like from the outside.
- Two more checkpoints. **202/202.**

- **`--vmtrace` - the exact opcode stream a mission runs.** It logs the
  interpreter's dispatch register, which is the only ground truth there is for
  a disassembler working from operand lengths it inferred.
- **A properly started `B1_BattleTech_1` executes 8192 opcodes using 65
  distinct ones**, beginning exactly as the disassembly says. The ten most
  used: `61:2416 65:1309 62:637 73:459 70:342 39:240 3C:222 33:221 72:144
  4B:130` - `0x61` alone is a third of everything, which is what a push looks
  like in a stack machine.
- **`0x0B` runs once and `0x24` never runs at all.** So the mission schedules
  one routine and, in eight thousand instructions, never creates a thing. It is
  not stuck - the mix is wide and changing - it is **waiting**, in a loop, for
  something that is false on a pod with one entity, no players and nothing else
  on the wire.
- One more checkpoint. **200/200.**

- **A thing is only ever made by a script.** `Create_Thing` is called from
  **exactly one place in the whole ROM**, and that place is a bytecode opcode
  handler: **`0x24`**, which takes four operands off the script's stack - two
  raw, two as integers - and calls it. The opcode before it calls a sibling
  constructor, so a script has more than one way to make something.
- That settles the shape of the system, and explains why an empty pod stays
  empty however much is written into its entity table by hand: **nothing has
  executed a `0x24`**. A scenario loader, a console broadcast, an entity flag -
  every route considered here was looking in the wrong place.
- `B1_BattleTech_1`'s body disassembles for 56 instructions before reaching an
  opcode with no handler, and there is no `0x24` among them, so whatever makes
  this mission's mechs is further in or in a routine it schedules.
- Two more checkpoints. **199/199.**

- **`--packet` takes up to eight, delivered in order.** A mission needs a
  *sequence* - a game length, then a mission, then a start - and one packet
  could never have expressed that.
- **`0xE5` carries the game length** at packet `+0x3C`, multiplied by a hundred
  into the mission clock at `0x02193C1C`. And the main loop **drains** that
  clock, so it counts down - which is why it is negative on an idle pod, for
  the plainest reason there is.
- With `0xE5` then `0xED`, all three landmarks fire in order: the forwarder,
  the clock write, the mission handler. The mission runs and its spawn opcode
  executes, and **still nothing is created**, so there is at least one more
  input. Said plainly rather than by forcing values into globals until
  something moves.
- One more checkpoint. **197/197.**

- **The first two bytecode opcodes with names**, from what they write rather
  than from reading their logic: **`0x0B` is *create this thing, at this time*
  ** - it writes the script object's `+0x1C94` and `+0x1C98`, popping the what
  and then the when and multiplying it by 100, which is a script saying
  *seconds*. **`0x02`** writes `+0x1C9C`, clamped to at least 1 and compared
  against 2.
- **And `0x0B` executes.** Running `B1_BattleTech_1` and watching its handler:
  one hit. The mission program reaches its spawn instruction unaided.
- **The last missing input is a game length.** The walker acts on a queued
  spawn only once its due time has passed, and the mission clock at
  `0x02193C1C` is negative on a pod nobody has told how long the game lasts.
  Forcing a value into it at the comparison makes things worse rather than
  better - the interpreter then runs once instead of twice - so the clock is
  load-bearing somewhere earlier too, and that is written down rather than
  worked around.
- One more checkpoint. **196/196.**

- **The disassembler follows jumps.** `0x42`'s two-byte operand is a signed
  displacement: `42 F9 DA` is `jump -1574 -> 0216B466`, the byte immediately
  after the name table ends - which is where a program's body would start.
  Disassembling from there gives `61 00, 65 FD, 72, 61 01` against a live trace
  of `61, 65, 72, 61`. **The two readings agree across a branch as well as
  along a straight line.**
- **Seven opcodes are control flow, and they are exactly the seven that take a
  16-bit operand** - so a two-byte operand is a jump displacement.
- Two more checkpoints. **195/195.**

### Fixed

- **Bytecode opcode `0x0B` is not a spawn.** It was named *create this thing,
  at this time* because the field it writes is read by the task that creates
  things - which is true, and not what it means. That task passes the field as
  the interpreter's **name** argument, walked to its NUL and truncated at
  sixteen characters. So `0x0B` is **at time T, enter this routine by name** -
  the same mechanism `0xED` uses to start a mission. A mission program
  schedules other script routines, and whatever creates a thing is inside one
  of them. Naming an instruction from what consumes its output, one step
  removed, got the shape right and the meaning wrong.

- **The operand-length rule missed 16-bit operands.** Some arms read one
  through `0x0211995C` instead of stepping the program counter twice, so
  counting only the byte steps ran the disassembly off the rails at the first
  jump. Six opcodes were being read a byte short.
- **And the first control-flow detector marked three quarters of the
  instruction set as branches**, by looking for any instruction touching
  `(-$10e,A6)`. *Reading* the program counter is how every operand-taking arm
  starts; only a write is a jump. Both were the tool's fault, not the
  firmware's.

- **`tools/mission_dis.py` - the mission bytecode disassembles.** Both things
  it needs come out of the ROM: the program counter is `table + offset`,
  because the name lookup adds the table's own address, and an instruction's
  operand length is **counted from its handler's own program-counter steps**
  rather than taken from a table anyone typed in.
- **It is a stack machine.** 94 opcodes have handlers; **81 take no operand**,
  12 take one byte, 1 takes two.
- **The disassembly matches the running pod.** `B1_BattleTech_1` begins
  `49 01, 49 01, 49 01, 4B 01, 4B 01, 47 01, 47 01, 47 01, 4A 08, 65 08, 45,
  42`, and tapping the interpreter's dispatch on a live mission gives exactly
  `49 49 49 4B 4B 47 47 47 4A 65 45 42`. Two independent readings of the same
  program, agreeing - which is the only check available on either.
- The walk stops after `42` because the program branches, and the tool says so
  rather than printing rubbish past the point where it stopped being right.
- Four more checkpoints. **193/193.**

- **A mission script runs.** `0xED` names the script at packet `+0x0A` and the
  entity at `+0x32`; class 19's arm starts the mission and enters the
  interpreter by that name. Put `B1_BattleTech_1` in the packet and the mission
  record takes the name, the program counter lands at `0x0216B7F1` in the ROM's
  bytecode, and the fetch-decode loop runs.
- **The script loops on a wait.** The spawner hands the interpreter an elapsed
  time every few ticks; the program sets a wait of `0x4C` hundredths - three
  quarters of a second - and the timer counts down by four per call and is set
  back again. So a named routine in the ROM, entered by a message off the wire,
  is executing on an interpreter driven by a scheduled task with its own timer
  counting down in real time.
- Nothing is created yet: the script waits, and what for is the next question.
- Two more checkpoints. **189/189.**

- **The missions are in the ROM.** `0x021186BC` enters the interpreter **by
  name**, looking a routine up in a table at `[0x0216F49C]`. `tools/missions.py`
  reads it - **thirteen routines**:

  ```
  B1_BattleTech_1  B2_BattleTech_2
  FC1..FC8_Follow_Cockp     exitScreen
  T1_Nose_Only_1   T2_Camera_Only_1
  ```

  Two scenarios, eight follow-a-cockpit cameras, an exit screen, a nose camera
  and a camera-only view - a BattleTech Center's whole repertoire, the game and
  the spectator displays that watched it.
- **`0xE4` is multiplexed**: packet `+0x0E` selects one of twenty sub-commands,
  `-1` to `18`. **Sub-command 13 builds a mission record** - a name copied out
  of the packet, two sub-objects of 31,142 bytes, and the interpreter
  initialised on the script object that follows them. About 70 KB in all.
- Four more checkpoints and a new tool. **187/187.**

### Fixed

- **`R1_Red_Planet_1` and `B1_BattleTech_1` are not side identifiers.** Found
  in the `0xED` handler beside chassis names, they were written up as plausibly
  an `R` side and a `B` side. They are **mission script names**, and `0xED`
  names the script to run. The guess was labelled as one, which is the only
  reason it cost nothing.

- **Missions are bytecode.** Following the spawner down reaches a **fetch,
  decode, dispatch** loop over **162 opcodes** - 94 of them with a handler, 93
  distinct - and the ROM names the machine in its own error messages:
  `Interpreter error, bad opcode %02xh at offset 0x%04lx!` and
  `Popped NULL return address, interpreter stopping.`
- **The script object at `0x021A5DBC`** holds a saved program counter at `+0`,
  an operand stack pointer at `+0x1C84`, a return stack pointer at `+0x1C88`, a
  wait timer at `+0x1C90`, and the pending spawn at `+0x1C94`/`+0x1C98`.
- The operand stack is a stack of **0x4C-byte frames** at `0x021B74B6`; one
  reader returns an integer and another multiplies by 100 and truncates, which
  is how a script says *seconds* and the engine stores hundredths.
- **Which is why nothing has ever appeared in a frame.** Not a missing flag or
  an unset entity field: a pod handed no mission has an empty spawn list -
  `+0x1C94` zero, `+0x1C98` `0xFFFFFFFF` - because the world is populated by
  running a program and there is no program.
- Three more checkpoints. **182/182.**

- **A mission starts.** `0xED` is dispatched on the class of the entity it
  names - and the id is at packet `+0x32`, not `+0x08`. Its eight arms cover
  classes 1, 7, 9, 10, 12, 13, 16 and **19**, and class 19's arm calls
  `0x0211786C`, which schedules the thing-creating task `0x02117788` as a kind
  `0x10000` event three ticks out. Send `0xED` to a class 19 entity and the
  spawner ticks - 16 times in a run where it had never run at all.
- **Class 19 is the mission itself**, not a vehicle. That is why
  `Create_Thing`'s table stops at 18 and refuses to build it, and why `0xE8`
  carries a teardown arm for a class no constructor makes - two loose ends from
  earlier, both explained by the same fact.
- **`0x02193C1C` is the mission clock in hundredths of a second**, negative on
  a pod with no mission; setting it to 60000 makes the spawner take its active
  branch instead of its idle one.
- What is still missing is the **script**: the spawner runs, takes the active
  branch and creates nothing, because what to create and when is scenario data
  the console sends. The same gap as the mission sequence, reached from the
  other end.
- Three more checkpoints. **179/179.**

- **The three unused draw-object emitters are not skipped by a failing test.**
  After the scene's camera item the builder jumps straight past them -
  `bra $212e286` - so that whole block is reached only by a branch back into
  it, and its head tests a global rather than anything about an entity.
- **What `entity+0xBB` bit 0 opens** is further on: a **type 3 record** tagged
  `0x3A` carrying the viewer's own `(X, 0, -Y)` - the same axis flip the object
  transform uses. Setting the bit makes that block run sixteen times in a run
  where it ran none.
- **And that is the limit of what hand-setting fields can do.** The world is
  empty not because the builder refuses to look at entity 1, but because
  nothing was ever created: `Create_Thing` has not run in any of these
  sessions. Writing a class, a number and flags into an entity's memory is not
  the same as the game making a thing, and the difference is everything the
  constructor does that we have not seen.
- Two more checkpoints. **176/176.**

- **The display-list API.** `0x02144592` starts a list, `0x021445FA(desc,
  type)` begins a record, `0x02144632` ends it, and `0x0214465C`, `0x02144724`,
  `0x02144978` emit types 8, 1 and 3. Finding it makes every emitter in the ROM
  readable at a glance.
- **`record_end` proves the `2 + len` rule** from the writing side: it computes
  the length as the longwords written **minus two**, which this project had
  only inferred from the renderer's walker.
- **41 `record_begin` call sites**, and **21 of them emit type 7**, the item
  stream. Only four run - the scene and the HUD. The other seventeen live in
  **other viewers' frame builders**, reached from further arms of the same kind
  2 class dispatch: every viewer class has its own builder, and the one that
  runs is chosen by what the pilot is flying.
- The open question is sharper for it: the Mech builder has **four**
  draw-object emitter calls and only the first runs, so whatever puts another
  thing in the world is behind `0x0212DFC6`, `0x0212E096` or `0x0212E1C8`.
- One more checkpoint. **174/174.**

- **The view heading is `Course + the field after it`**, wrapped at 360 -
  which settles the units from the code rather than from an observation, and
  names **`+0xFC`** as something added to Course to get where the pilot is
  looking. A torso twist is what a BattleTech pod has that a heading alone
  does not.
- The two matrix builders confirm it: `0x0213F30C` and `0x0213F350` each take
  an angle in **degrees**, multiply by pi/180, `fsincos` it and fill a 3x3.
- **The scene's colours come from the game definition.** The `$2C0` camera
  item's field of view and far plane are constants; its colour is six
  longwords from `[0x02193BB4]+0x30`. `0x02193BB4` is set at startup from
  `0x02179A10 + id * 0x84`, so each game has a 132-byte definition record.
- **The frame builder never touches the entity table or the mech table** -
  neither address appears in its 0x1466 bytes. The world is enumerated
  somewhere else entirely, which rules out a family of guesses about why a
  second mech does not appear: not that the builder skips it, but that the
  builder was never going to look.
- Two more checkpoints. **173/173.**

- **Rendering is per-viewer, not per-entity.** The frame builder is
  `0x0212DB70`, reached from event **kind 2**, which dispatches on
  `My_Mech_Ptr`'s `Class_ID` and calls a different builder per class - each
  with `My_Mech_Ptr` as its only argument. The pod draws the world *from* its
  own mech, and what you are flying decides which builder runs.
- **The six `Cone stats` globals are named**: the builder opens by clearing
  `0x02194054`-`0x02194068`, which are the `Total`, `First Distance`,
  `Second Distance`, `Entering Clip`, `Z Clip` and `Cone Reject` the status
  report prints.
- **`entity+0xBB` bit 0 gates drawing** - and `+0xBB` is the byte message
  `0xE0` writes, which the field sweep had found without knowing what it was
  for.
- **The display-list descriptor is confirmed** as `{buffer, second buffer,
  size, cursor}`: `0x02144592(buffer, 0x2328, descriptor)` starts a list and
  every record is written through the cursor at `descriptor+0x0C`.
- One more checkpoint. **171/171.**

- **Items print their payload, not their length.** The lengths were already
  known and the meanings were not, which is a gap a log line can close.
- **`$2C0` sets the camera**: `93, far 10000.0, near 1.0, FOV 60 degrees,
  colour (0.094, 0.062, 0.094)`. The first type 7 record in a frame is the
  scene.
- **The second type 7 record is the head-up display**: `$100` takes a screen
  position and `$240` a number, so the stream is *move here, draw that*, one
  pair per glyph. The object record names record 2 through its `+0x58` - the
  pod is drawing its instruments.
- **There is no mech geometry in the frame, and there should not be**: the only
  entity in the world is the player's own, and you do not see your own cockpit
  from inside it. Giving a second entity a class, a number, flags and a slot in
  the mech table is not enough to make it draw - written down as an open
  question rather than guessed at.
- One more checkpoint. **170/170.**

- **The frame decodes, and it has the mech in it.** With the walker fixed and
  entity 0 placed by an `0xEC` packet at X 100, Y 200, Z 5.4, Course 1.0:

  ```
  viewport  (0,0)-(479,359)  480x360  centre (239,179)
  object    1 picks, 42 longwords, screen 480x360
       0.9998    0.0000   -0.0175
       0.0000    1.0000    0.0000
       0.0175    0.0000    0.9998
     100.0000    8.2000 -200.0000
        pick (16,16) -> entity 0 part 0
  items     22 longwords
        item $0E0 ... $240 ... $2A0 ...
  ```
- **The transform is built from the position we sent**: the translation row is
  **(X, Z + 2.8, -Y)**, so the renderer's world is Y-up with the third axis
  negated and `2.8` is an eye height on top of the mech's own Z.
- **Course is in degrees** - `cos 1 deg` and `sin 1 deg` from a packet carrying
  `1.0`.
- **The item stream is real geometry**, in the model interpreter's own opcode
  language - the one `tools/model.py` already runs.
- Four more checkpoints. **169/169.**

### Fixed

- **`0xFFFFFFFF` in a display list is a separator, not the end.** The stub's
  walker treated it as a record type and stopped, so every display list this
  project ever decoded read as "a type 0 record and a terminator - nothing to
  draw" - and that sentence went into the documentation as a fact about the
  cockpit. One longword, misread, hid every frame the pod ever built.

- **Frames flow. Six renderer commands become 400.** `0x02122658` is not a
  general scheduler: it special-cases kinds `0x0C` and `2` into single
  dedicated slots, and `Get_Event` releases the kind-`0x0C` slot **only when
  the render has finished**. So the end-of-frame renders, reschedules itself,
  and its own event is released by the render completing - which makes the
  completion interrupt load-bearing.
- The handler travels in the event: `(A3+0x14)` gets the scheduler's fifth
  argument, and `+0x14` of the event buffer is the `(-$8a,A6)` the pump calls.
- **`--rirq LEVEL:DELAY`** - a calibration knob rather than a constant.

### Fixed

- **The renderer stub was completing a render too fast to be believed.**
  `Async_Render` clears the render-done flag **two instructions after** ringing
  the doorbell, so an interrupt taken at the doorbell set the flag and the
  clear immediately wiped it - and the pod waited for ever for a frame it had
  already finished. The stub now counts down before raising the line. The bug
  was ours, not the firmware's, and it is the reason the pod had appeared to
  render exactly once since the day the stub was written.

- **The game is running.** With `--rirq` the pod's own report says so:
  `Remaining time` counts **600 -> 597**, `Model Time` goes from 0 to 3, and
  the event pump turns over - kind `0x10000`, the per-class frame update, runs
  again and again.
- **The end-of-frame re-arms itself.** It is scheduled through `0x02122658`
  with `(0x0C, 0, 0, 0, handler, 0)` at startup and again at the end of every
  frame, unless `TI_ErrorNumber` is set. So the render is inside a routine that
  puts itself back on the queue - which is also why it appears in no call site
  anywhere in the ROM.
- **`(-$8a,A6)` in the event pump is `+0x14` of the event buffer**, not a
  separate variable: an event carries its own handler and the pump calls it
  instead of switching on the kind.
- The remaining question is now narrow and written down: what `0x02122658`
  does, and why the second scheduling does not produce an event the way the
  first did. **165/165.**

- **The renderer's frame-complete interrupt, and `--rirq` to raise it.** The
  board's interrupt is **vectored**, which is why it was never among the
  autovectors: vector 66 (`0x42`) at `0x0214C708`, cause in bits 4-6 of the
  word at `0x3800001C`, acknowledged by clearing bit 7. Cause `0x50` is frame
  complete and its arm stamps the timebase into **`0x0217A326`**.
- That flag closes a loop only half visible before: `Async_Render` clears it,
  `Render_Done` is a bare `tst.l` on it, and the end-of-frame code computes the
  frame time as the stamp minus the time the render started. All the frame
  timing the status report prints comes from this one interrupt.
- Vector 71 (`0x47`) is the DUART, confirmed from both sides - `0x47` is the
  byte the boot writes to its interrupt vector register at `0x11018`.
- With `--rirq`, **the frame-complete arm runs**, which it never did before.
  It is not yet enough: the pod still builds one frame and stops, and what
  re-arms the event pump's handler hook is the open question.
- One more checkpoint. **164/164.**

- **The pod does build a frame.** With entity 0 a `Mech` in the thirty-slot
  table, both display-list emitters run and the buffer holds a **480x360
  viewport** and a **type 1 draw-object with one item and an identity
  transform**. The cockpit is drawing; nothing was reading it.
- **The display list is double-buffered.** `0x0218AF04` is a descriptor, not
  the list: two buffer pointers at `+0x00` and `+0x04` (`0x0218AF14` and
  `0x0218B024`), the 9000-byte size at `+0x08`, a cursor at `+0x0C`. The first
  render posts the buffer the emitters were *not* filling, which is why the
  list reaching the stub decoded as a type 0 record and a terminator.
- **Only one frame is ever rendered.** In 900 million instructions the stub
  sees exactly one command 6: the game builds the next frame and waits, because
  the stub acknowledges commands but never *completes* a render.
  `Async_Render` is `0x0214D302`.
- Five more checkpoints. **163/163.**

- **A mech driven from the wire, reported by the pod.** Make entity 0 a `Mech`,
  send it an `0xEC` movement packet, type `d` at the in-game console:

  ```
  dMech 0
  Type 0, Color 0, Flags 7
  Course 1.00000, Speed 90.00000, X 100.00000, Y 200.00000, Z 5.40000
  ```

  Every step between the wire and that print is the cockpit's own code.
  **Speed comes back as 90 from a packet carrying 0.25**, because the dump
  scales `+0x114` by 360 - the field map and the argument order both right at
  once.
- **`tools/musashi_fpu.py`.** The moment an entity is a `Mech` the firmware
  reaches **FTAN**, opmode `0x0F`, which Musashi does not implement - it covers
  a subset of the 68881's transcendentals and calls `fatalerror()` on the rest.
  The script adds the missing sixteen as one-line libm calls in the shape the
  existing `FSIN` and `FCOS` cases use. It is a script rather than a patch
  because `third_party/musashi` is cloned by `make deps`; it is idempotent, and
  `make deps` runs it.
- Three more checkpoints. **158/158.**

- **The pod has an in-game console, and it answers.** Typing at the modelled
  serial port with nothing patched: `J` dumps the skeleton's joint angles, `Q`
  clears the profiler, `q` prints a hex dump, `s` prints the whole status
  report, and **`x` leaves the game for the diagnostic monitor**.
- **`x` is how the monitor is supposed to be reached.** Every monitor result in
  this project so far came from a cockpit with `RTS` patched over the game's
  entry, because the boot runs the game and never returns. It returns if you
  ask it to.
- `Post_Event` is `0x021228D6`, with **49 call sites** posting kinds 2, 3,
  `0x0A`, `0x64`, `0xB0`, `0xB1`, `0xC0`, `0xD0`, `0xFFFE`, `0xFFFF` - and kind
  `0x0A` from exactly one of them.
- Three more checkpoints. **155/155.**

- **Event kind `0x0A` is an in-game message**, and its arm routes by the class
  of the pod's own mech: a VTV handles them in its own code, a Copter ignores
  them, anything else takes them to the byte-`0x13` dispatch. So what happens
  to an in-game message depends on what the player is flying.
- That names both routes and keeps them apart: the byte-0 table is **kind 3**,
  a packet off the wire; the byte-`0x13` table is **kind `0x0A`**; and the
  `Post_Event(kind 0xB1, ...)` so many byte-0 handlers end with goes to
  neither - kinds `0xB0`, `0xB1`, `0xC0` and `0xD0` all land on `0x02139210`.
- Two more checkpoints. **153/153.**

- **`0xBE` names an owner.** The largest receive-only handler writes a key byte
  and a 40-character name into one of exactly **two** 42-byte records at
  `0x021B74C2`, and `0x0211EA58` looks a record up by matching its key against
  **the first byte of an entity** - the field the `TI ERROR!` dump calls
  `Last Object Owner`. Two owners, each with a name. In a BattleTech Center
  that is two sides, which fits the `R1_...` and `B1_...` strings in `0xED`'s
  handler. `SITELINK_NAME_MSG` is the candidate and is labelled as one.
- Three more checkpoints. **151/151.**

- **The cockpit firmware ships with an animation editor.** A state byte at
  `0x0215DCF7` subscripts a table of names at `0x021698EA`, and the names are
  `Rotate Camera`, `Move Camera`, `Move Focus`, `Rotate Object`, `Move Object`,
  `Rotate Joint`, `Move Joint`, `Frame Mode`, `Delete Frame?`, `Auto Play`,
  `Manual Play`, `Play Stopped`, `Loading File...`, `Saving File...`,
  `Appending File...`. The same function prints `Frame %02ld/%02ld` and two
  triples of floats.
- Which explains four loose things at once: **`ANIMATOR_CLASS`** in the
  console's taxonomy, **in-game message `0x4A`** dumping `Joint %d Angle %f`,
  **`0xF6`-`0xFF`** setting exactly the load/save/append states, and why the
  archive has posed skeletons with named joints at all - somebody posed them,
  on this hardware, with this tool.
- `0x021084E8` carries `Camera positions for map file`, so the editor is not
  the only authoring tool in the ROM - which also explains `CAMERA_POSITION`
  being one of the scenario grammars.
- Two more checkpoints. **149/149.**

- ROADMAP.md brought up to date: phases 8, 9 and 10 written down, and the
  quickstart in README.md is now a conformance scenario so the front page
  cannot rot again.

- **The whole entity map, across eight classes.** Sweeping 0, 1, 2, 9, 10, 12,
  16 and 18 and taking the union: **16 opcodes, 57 field slots, 467 of the
  1716 bytes** an entity occupies. Class 1, `Mech`, sees the most - 16 against
  12 to 14 - which is what one would expect of the class the pod itself is.
- **`0xEC` is the movement update**: X, Y, Z at `+0x26`, Course at `+0xF8`,
  Speed at `+0x114`, and a 24-byte block at `+0x694`. Position, heading and
  speed in one packet, and one of the 29 the pod both sends and receives.
- **`0xDE` configures a mech**: its 24-byte block at `+0x7E` begins exactly at
  **Type**, with **Color** at `+0x82` inside it. What a mech is and what colour
  it is drawn - what a console sends when a player picks a chassis.
- **Eleven entity fields now have names**, nine of them the firmware's own.

- **`+0x26`, `+0x2A` and `+0x2E` are X, Y and Z** - the firmware's own words,
  not an inference from the console's field lists. In-game message `0x64` dumps
  every mech with `Course %3.5f, Speed %3.5f, X %3.5f, Y %3.5f, Z %3.5f`, and
  its arguments are pushed right to left from `+0xF8`, `+0x114` (scaled by
  360), `+0x26`, `+0x2A`, `+0x2E`. The oldest assumption in the entity work
  leaves UNRESOLVED.md.
- With it, **`+0xF8` Course, `+0x114` Speed, `+0x7E` Type, `+0x82` Color**.
- **A second table: `0x021943DA` holds thirty entity pointers**, cleared at
  boot by the same routine that builds the arena. The thousand-slot arena holds
  everything in the world; this holds the **participants**, and thirty is the
  number of mechs a game can have.
- **Five more in-game messages with names**, from what their arms log: `0x4A`
  dumps the skeleton's joint angles, `0x51` clears the profiler, `0x64` dumps
  every mech, `0x71` is a hex dump, `0x73` the periodic report. All operator
  and developer commands, which is what a console sends a pod mid-game.
- Five more checkpoints. **147/147.**

- **The pod now reports on itself.** `0x021BB1A0` is a request flag the main
  loop tests, acts on and clears; setting it gets the firmware's whole status
  report out of a booted cockpit - the DUART's own view of itself, six named
  culling counters, frame-rate statistics, the router's traffic high-water
  marks and the event queues'.
- **In-game message `0x73` is what normally raises that flag** - its entire arm
  is `move.l #$1, $21bb1a0.l`. The first of the thirty-three in-game opcodes
  with a name, and it is a console asking a pod for its statistics.
- **`My_Mech_Ptr` is entity 0.** The report prints `0x21f99ac`, the base of the
  arena, with `Thing_Flags=0x00000007` - the value the boot writes into entity
  0's `+0x0A` and no other's. So the pod's own mech is slot zero, reserved at
  boot, which is why entity 0 is built differently from the other 999.
- **`Remaining time = 600`**, a mission clock - ten minutes, if the unit is
  seconds, which is what a BattleTech Center ran on.
- **The timebase is hundredths of a second**, pinned by the report's own
  arithmetic: fps is `100.0` divided by a tick count. Which makes the
  watchdog's `addi.l #$64` deadline exactly one second.
- **The culling pipeline is named**: `Total`, `First Distance`,
  `Second Distance`, `Entering Clip`, `Z Clip`, `Cone Reject`. Six stages of a
  renderer this project has otherwise had to infer, and they are counters.
- Nine more checkpoints. **142/142.**

### Fixed

- **The "second dispatch over packet byte `0x13`" is the in-game keyboard.** It
  was found by looking for a network dispatch, so a network dispatch is what it
  was called. `(8,A6)` is the event buffer, the event is kind `0x0A`, kind
  `0x0A` is posted from one site - a one-byte console read - and byte `0x13` is
  the low byte of its longword parameter. The 33 "opcodes" are 33 keystrokes,
  and their values were shouting it: `0x4A` is `J`, `0x73` is `s`, `0x78` is
  `x`. Settled by typing them and watching the pod answer.

- **`0x0218AEE4` is not a message queue.** It was written up as one, with `+2`
  as a message type and `0x0C` as a type it "sends somewhere of its own". It is
  `My_Mech_Ptr`, `+2` is `Class_ID`, and `0x0C` and `0x10` are classes 12 and
  16. Three readings that were wrong together, because each propped up the
  others. Corrected in place.

- **`0xF6`-`0xFF` are not the console's setup messages.** They were written up
  as "the pod's mode machine... where `COCKPIT_CONFIG_MSG`, `PLAYER_CONFIG` and
  `SHADOW_ROM` have to land", on the strength of being receive-only, arriving
  in a block, and writing what looked like mode bytes. The numbers they write -
  `0x0D`, `0x0E`, `0x0F` - are subscripts into a table of state names, and the
  names are `Loading File...`, `Saving File...`, `Appending File...`. Corrected
  in place; where the console's setup messages land is open again.

- **The quickstart in README.md did not run.** It told the reader to pass
  `--tty 11016`, an option the binary does not have; the working flag is
  `--duart 11000`. Nobody noticed because everyone working on this had the real
  command in their shell history, and the harness was written against the flags
  rather than against the documentation. Fixed, and the documented command is
  now scenario 4r.
- **ROADMAP.md's account of what blocks a game was out of date and flattering
  in the wrong direction.** It said the byte encoding of each message was
  unknown and that the sender was behind THINK C's relocations. The encoding is
  mapped, from the pod's own two ends. What is actually missing is the
  *sequence* - which messages, in which order, take a booted pod to a mission.

- **A conformance checkpoint that begins with a dash was being read as a grep
  option**, so `----- PERIODIC -----` and its four siblings failed no matter
  what the output said. `grep -qF --` fixes it. A harness that can silently
  fail a checkpoint for a reason unrelated to the firmware is worse than no
  harness for that checkpoint.

- **The field sweep repeated as a `Mech`** - the pod's own class - raises the
  count from 14 opcodes to **16**, and every difference is a class-sensitive
  arm: `0xE0` writes one byte at `+0xBB` as a Mech where it wrote four at
  `+0xC4` as a Hovercraft, `0xEC` writes four more fields, and `0xDF` writes
  fewer because its extra arms are for classes 8 and 10.
- **`0xE7` is the clearest result in the sweep**: six consecutive longwords
  from packet `+0x0C`..`+0x20` into `+0x1E8`, `+0x200`, `+0x218`, `+0x230`,
  `+0x248`, `+0x260` - **six records `0x18` = 24 bytes apart**. That is a
  second array of 24-byte records, alongside the one `0xDD` broadcasts into at
  `+0x2E0`.
- Which is also a warning about the method: a sweep at one class reports a
  subset and gives no sign that it has.

- **Seven class dispatchers, not one.** `Create_Thing`'s five-instruction class
  switch appears identically at six more sites, all nineteen wide. Reading
  every table gives a class-by-operation matrix: `1`, `8`-`12`, `17` and `18`
  implement all seven; `2`-`6`, `14` and `15` implement the wide operations
  only; **`0`, `7` and `13` implement nothing anywhere**, which fits `0` being
  a free slot. So the entity system is class-polymorphic with nineteen slots
  and at least seven virtual operations.
- **Classes `4`, `5` and `15` are implemented elsewhere but rejected by
  `Create_Thing`**, so something other than `Create_Thing` makes them.
- Four more checkpoints, and the six new dispatch sites are now pinned so a
  change to any of them shows. **133/133.**

- **The class numbers, from the ROM's own create-thing dispatcher.** A dense
  switch over classes 0 to 18, six of whose arms push a name before they build
  anything: **1 `Mech`, 8 `Escape pod`, 9 `Camship`, 10 `Hovercraft`,
  12 `VTV`, 16 `Copter`.** Out of range logs
  `Create unknown thing %d, class %d received`.
- That joins the operator console's taxonomy to numbers: `MECH_CLASS` is 1,
  `HOVER_CLASS` 10, `VTV_CLASS` 12, `COPTER_CLASS` 16 by name, and `POD_CLASS`
  8 and `CAMERAMAN_CLASS` 9 on the strength of `Escape pod` and `Camship`
  being the only candidates. Seven more arms build something without naming it,
  and `EXPLOSION_CLASS` and `ANIMATOR_CLASS` have to be among them.
- It also explains the switches already found in the handlers: `0xDF` treats
  class 8 and 10 differently - an escape pod and a hovercraft - and `0xE8`'s
  teardown arms for 1, 9, 10, 11, 12, 13 and 19 are `Mech`, `Camship`,
  `Hovercraft`, `VTV` and three the creator does not build, including 19,
  which is past the end of the table.
- Eight more checkpoints. **129/129.**

- **The renderer's fixed error area, named by the ROM.** `TI ERROR!` dumps
  fifteen labelled longwords from `0x3FFFE164`: `TI_RoutineID`,
  `TI_ErrorNumber`, `TI_ProfileSP`, `TI_FPUStatus`, `TI_FPUPC`,
  `TI_VideoIntTimer`, `TI_LastShape`, `TI_LastZone`, `TI_LastCommand`,
  `TI_ShapePCOffset`, `TI_ProcPC`, `TI_ScanConv_Flag`, `TI_PolygonCount`,
  `TI_LastObject`, `TI_ProcSP`.
- **Which settles `0x3FFFE168` and `0x3FFFE174`**, listed until now as measured
  and unexplained: they are `TI_ErrorNumber` and `TI_FPUPC`, and the main loop
  puts them on Remote I/O displays `0x80` and `0x86` so an operator can read a
  crash code off a cabinet that will not start.
- **The entity header, in the firmware's own words.** The periodic report
  prints `Class_ID=%d, Number=%d, Thing_Flags=0x%08x` from `My_Mech_Ptr`, and
  the error dump prints `Last Object Owner` from `+0x00`. So `+0x00` is Owner,
  `+0x02` Class_ID, `+0x06` Number, `+0x0A` Thing_Flags - and `0x0218AEE4`
  holds `My_Mech_Ptr`, a pointer to this pod's own entity.
- **Eight opcodes with names**, from what their handlers log: `0xBA` damage
  (`old damage spreader`), `0xEB` burst damage, `0xEE` the router announcing
  itself, `0xED` a player's vehicle created and linked, `0xC4` the router's
  ready-and-timing report, `0xD3` camera selection, `0xE5` a player greeted by
  name - and **`0xC6` is `ROUTER_MODEM_COMMAND_MSG`**, on the same standard of
  evidence that named `0xC5`.

### Fixed

- **`fnstr.py` was rejecting every string that ended in a newline**, which is
  most of what the firmware logs. It had been reporting "no strings" for
  handler after handler and those silences were being read as findings - the
  sweep that named `0xC5` had already run with the broken filter. Allowing tab,
  newline and carriage return turned the same sweep into eight named opcodes.
  Recorded in FALSE-TRAILS.md: a filter that silently returns *fewer* results
  is the dangerous kind.

- **Class 0 is a free slot, and `0xE8` makes one.** `0xE8` switches seven ways
  on the class - 1, 9, 10, 11, 12, 13, 19, each a different teardown - and then
  every class, not only those seven, ends with the entity's class zeroed.
  Sweeping the class from 0 to 23 and injecting `0xE8` each time confirms it:
  every non-zero class loses its class byte and class 0 changes nothing. So the
  boot state is not a thousand blank objects, it is a thousand **free slots**.
- The class gate measured rather than assumed: **12 opcodes write the entity at
  class 0, 14 at class 10**. Only `0xDF` writes more of it at the higher class;
  `0xE0` and `0xE8` do nothing at all at class 0.
- The class numbers the firmware distinguishes so far: **1, 8, 9, 10, 11, 12,
  13, 19**, with 0 free.

### Fixed

- **A cleared byte is not a byte copied from the front of the packet.**
  `entityfields.py` attributed a changed run to the packet offset whose value
  it matched, which makes zero ambiguous - and `0xE8`, whose whole effect is to
  zero the class, came out as "from packet+00". An all-zero run is now reported
  as cleared and never attributed.

- **`tools/entityfields.py` - ask the firmware which bytes a message writes.**
  Boot and dump entity 1; boot again with one packet injected and dump it
  again; the difference is the message. The packet body is a ramp, byte `n`
  holding the value `n`, so a longword that lands in the entity carries its own
  packet offset with it. Both runs are deterministic, so nothing else moves.
- **`entity+0x02` is the class, and handlers switch on it.** `0xDF` copies the
  three position fields, reads `+0x02`, and takes one arm for class 8, another
  for class 10, and drops everything else. The arena loop clears `+0x02` at
  boot, so an unconfigured entity takes a do-nothing arm - which is why the
  first sweep saw less than the static reading, and the first thing the tool
  had to learn to do was write a class in first.
- **Fourteen opcodes write the entity they name**, 1 to 90 bytes each, now
  mapped byte for byte. Every field the static reading found is confirmed in
  place, and ten messages it could not follow - `B9 CA CC CD D7 D9 DC DE E0
  E8` - are mapped for the first time. `0xDD`'s broadcast of packet `+0x40`
  into six records `0x18` apart comes out of the dump exactly as the code said.
- **`entity+0x9C` is a sequence, and `0xD2` refuses to go backwards on it**:
  it compares a longword off the event against `+0x9C` and drops the whole
  message if it is not newer. First evidence that this is a state-replication
  protocol with an out-of-order guard, which is what a LAN simulation needs.

- **The published Mech Damage Heat Chart checked against the ROM.** All **33
  configurations and all 20 weapons** on it are in the vehicle table, and the
  five the ROM has that the chart does not are exactly the ones whose names say
  they would not have been printed: `Explo Vulture`, `Loki Test DNU`,
  `MadCat V4`, `Madcat V5`, `THOR V7`.
- **The ROM's `Drone` is the chart's `Loki V7`**, settled by the chart's own
  arithmetic rather than by reading a cell: 8.0 damage and 3.0 heat at 300 m
  but 4.0 and 1.0 at 600 m, which is one `SRM 2` plus two `LASER SM` and
  nothing else - and that is uniquely what `Drone` carries.
- Three more checkpoints. **114/114.**

### Fixed

- **The chart's weapon numbers are not this build's**, and saying otherwise
  would have been easy: the loadouts match exactly, so the values look like
  they should. They are not a scale factor apart - seven of twenty are exactly
  five times the chart's damage and the rest are not - the missile ranges match
  while the energy and ballistic ones do not, and `ROM2_0`, `ROM2_5` and
  `ROM3_0` all carry byte-for-byte the same weapon table, so it is not an older
  cockpit in this dump either. The chart is evidence about the roster, not
  about the numbers.

- **`docs/SOURCES.md` - the paper trail, and what is not in it.** There is **no
  board schematic** in any published material. Checked all of it: the System
  3.0 manual is field service, the System 4.0 manual is a different machine
  (Tesla, a Pentium PC with a Division graphics card), the System 1 manual is
  operations, and both VWE patents are mechanical. So the part at
  `0x00010007`-`0x00010015` cannot be named from the documents.
- The service manual pays anyway. **The node ID is an 8-position DIP switch on
  the CPU board front plate** - which matters, because the firmware never
  writes `0x0218AEB0`/`B1` and the number has to come from somewhere. Whether
  the boot monitor reads that switch or the ARCNET controller does is now an
  explicit open question rather than an unnoticed gap.
- Also from the front plate: an **Interrupt Button** that "will force an
  interrupt on the CPU... used only under VWE supervision as a debugging tool",
  and confirmation that the **ARCNET controller is on the CPU board**.
- And the manual's own words for something found independently in the firmware:
  "sound is reestablished within 15 seconds as the **software watchdog** will
  reactivate the audio channels."

- **The pod has a watchdog, and `Get_Event` kicks it.** `0x00010000` gets a
  `0x80`/`0x00` pulse from a three-instruction routine called from exactly one
  place: the top of the event pump, on a deadline 100 ticks of the free-running
  timebase apart. A pulse from the one function that cannot stop running while
  the pod is alive. It fires 453 times in a boot.
- **`0x00010007`-`0x00010015` is characterised**, if not named. Two
  four-register control ports at a stride of 4, touched by **eight instructions
  in 534 KB of ROM and nothing else**, each run doing set/clear/clear/set of
  one mask - immediately after installing the interrupt vectors it goes with.
  It was listed as "two interleaved 8-bit parts, probed once at init"; it is
  interrupt routing.
- **The catch-all exception handler**: 56 vectors point at `0x02123358`, which
  prints the vector offset and the faulting PC straight out of the console port
  and then loops forever re-printing - except vector offset `0x138`, which it
  returns from. One interrupt is expected and ignored; everything else
  announces itself and hangs.
- Four more checkpoints. **111/111.**

- **`--astub`, an audio board instead of a poke.** The board is a ring the
  68020 fills and the DSP drains; the stub writes the head index into the tail,
  so it drains as fast as it is filled, and raises the signature's low byte on
  the first push. The ROM's second audio check is
  `[base] & 0xFF0000FF >= 0x55000001` - it wants that low byte, which a
  constant `0x55000000` never gave it.
- **`Audio subsystem is NOT properly downloaded!` is gone**, and the branch at
  `0x021492D8` is taken for the first time. All four of the ROM's subsystem
  checks now pass.
- The bus log is legible again: the `btAudio.dld` download used to appear as
  **1,236,274 unmapped accesses** and bury everything else. With the ring as
  real memory it is zero. **107/107.**

- **A mech moved.** A packet injected at the wire - opcode `0xE1`, entity id 1,
  seven floats - comes back out of memory as seven entity fields at exactly the
  offsets the static reading predicted, including the two the sender writes out
  of order. Nothing on that path is patched or stubbed: the low-level dispatch,
  the router, the identity filter, `Post_Event`, the event pump, the byte-0
  table and the handler are all the cockpit's own code. First time anything
  here has made the game's own state move.
- **The world is built during an ordinary boot.** `0x0214C422` fills
  `0x02189F10` with pointers to **1000 entities of `0x6B4` = 1,716 bytes**,
  from `0x021F99AC` to `0x0239C8CC`, `cmpi.l #$3e8` in the loop. Entity 0 is
  built differently and gets class `7`. So the objects a mission would move
  already exist; what is missing is the mission.
- Four more checkpoints, including the injected packet's own arrival, read back
  out of the entity it named. **105/105.**

- **The entity table is at `0x02189F10`**, an array of pointers indexed by the
  entity id a packet carries, referenced from **231 sites** in the ROM. An id
  on the wire is a subscript, which is why the protocol names a thing in four
  bytes.
- **The receive handlers are the exact inverse of the senders**, field for
  field, and reading both gives a check nothing else here has. `netmsg.py
  --fields`: **44 field pairs confirmed by both ends, none disagreeing.** Two
  readings taken from different code by different methods, consistent to the
  byte.
- **46 distinct offsets in the entity structure**, recovered without running
  the game. Among them `0xDD` broadcasts one packet field across six sibling
  records **0x18 = 24 bytes apart**, which puts a stride on the record array
  that was previously only known to exist.
- Five more conformance checkpoints, one of them an exact-match rather than a
  floor: the two ends of the protocol must disagree on **zero** fields.
  **101/101.**

- **Both halves of the game protocol, side by side.** The receiving table gives
  71 opcodes; `tools/netmsg.py` reads the sending side and puts the two
  together. The sender at `0x021468A4` has **45 call sites**, each writing its
  own opcode into the first byte of the buffer it then passes - **38 distinct
  opcodes, `0xB9` to `0xED`**, every one inside the range the receiver covers.
- That split names things nothing else could: **29 opcodes are sent and
  received** (pod to pod, the simulation itself), **17 are received only**
  (`BE C4 C6 D3 E4 E5 EE` and `F6`-`FF` - commands the pod obeys) and **9 are
  sent only** (`C5 C8 CE D0 D4 D5 D6 E2 E6` - reports the pod files). The three
  receive-only handlers that carry strings agree: `0xC6` runs the modem `+++`,
  `0xC4` prints `Master router ready`, `0xE5` prints `WELCOME %s`.
- **The shape of a packet body.** An 8-byte header, then at `+0x08` the entity
  id from the entity's own `+0x06`, then three longwords from the entity's
  `+0x26`/`+0x2A`/`+0x2E`, then message-specific fields drawn from the same
  structure - `0xD2` takes sixteen of them from `+0xC4` to `+0x120`, `0xDD`
  nineteen from `+0x2A4` to `+0x2E0`. The entity structure can now be mapped
  from the messages that report it.
- **`0xF6`-`0xFF` is a dispatch inside the dispatch**, ten entries at
  `0x02104342` over the same byte. All ten are receive-only and all ten write
  the pod's own mode and configuration globals rather than anything in the
  world. This is where the console's setup messages land.
- `tools/fnstr.py`, which reports the strings a function in the ROM points at.
  The firmware narrates itself, so that is usually enough to say what an
  unnamed handler is for.
- Four conformance checkpoints for the protocol and two for the second
  dispatch. **96/96.**

### Fixed

- **`0xC5` is `ROUTER_STATUS_MSG` by layout, not just by description**, and
  leaves UNRESOLVED.md. Its sender builds a 100-byte packet: `strncpy` of
  `0x50` bytes into `+0x08`, a longword at `+0x58`. That is
  `status string, status code long` on the wire, and no other message the pod
  sends has that shape.
- **The pod sends 38 opcodes, not 31, from 45 call sites, not 43.** The earlier
  count took the nearest preceding immediate byte store as the opcode, which
  misses a sender that writes its opcode before a branch. Requiring the store's
  displacement to match the buffer the call passes finds the rest. Corrected in
  place in DEVICES.md and recorded in FALSE-TRAILS.md.

### Fixed

- **`0x02146004` is the SiteLink modem, not the game's network receive.** Two
  entries below were written on that wrong reading. Its own strings settle it -
  `Modem in command mode`, `Answered at 115200...Syncing up.` - and the state
  at `0x0239DD9A` indexes eight connection states, with state 0 matching an
  `OK
` from a Hayes modem. That is the inter-centre link from `Dial_List`.
- So of the two receive paths, the one that posts events is the **modem**, and
  the one reaching the opcode dispatch - boot monitor service `+0x18` - is
  where ARCNET traffic arrives. **Where game opcodes `0x01`-`0x07` are handled
  is open again**: they reach `0x02122FBC` and it discards them.
- Both mechanisms are real and stand as described - `Post_Event` with its
  400-slot queue, and an identity the firmware only ever reads. Only the wire
  they belong to was wrong, and the identity gate turns out to gate the site
  link and the router filter rather than the game path.
- Nearly claimed a third thing and checked first: `pea $10012.l` in that code
  is a **lookup token** passed to a table search at `0x02122550`, not the
  unidentified device at `0x00010007`-`0x00010015`. That address range stays
  unidentified.

### Fixed

- **The map was drawing a fraction of its geometry, and the wrong models.**
  Caught by looking at the picture. Three separate faults:
- **The C decoder only walked the fall-through.** `tools/render.py` picks the
  best of three walks; `src/mesh.h` did not, so the terrain mesa came out at
  **9 polygons instead of 132**. `mesh_run_mode` now takes `ALL`/`FALL`/`TAKE`
  and `mesh_best` ports the heuristic - full walk unless the model rewrites
  vertex slots, otherwise whichever single arm drew more.
- **The wrong column named the model on nine-field records.** Column 1 holds a
  collision hull - 0 to 7 polygons, radii in the hundreds - and column 8 holds
  the real geometry. BadLands places 78 terrain mesas that way, so they were
  all being drawn as flat plates.
- **`scene.h` and `rig.h` were not in the Makefile's dependencies**, so a fixed
  decoder kept reporting the broken numbers. The same trap as `mesh.h` two
  commits ago; all the headers are now one `HDRS` variable.
- Together: **9,308 polygons to 53,792**, and from a low camera BadLands-16 is
  mesas and buildings receding into haze rather than scattered plates.
  `--scene-view turn pitch zoom` is new for getting down among them.

### Fixed

- **The SecCom block is 1,652 bytes, not 674.** The firmware prints
  `main game loop (SecCom 674 bytes).` and every piece of prose in this project
  took that at face value for months. The code at `0x02138BB8` pushes **`$674`**
  against a **`%x`** format, so the number is hexadecimal: **0x674 = 1,652**.
  Corrected in DEVICES.md, ROADMAP.md, ARCHITECTURE.md and README.md; the
  firmware's own line is left verbatim, because that is what it says.

### Added

- **The game's message table, found by following the injected packet.** The
  loop is an event pump - `Get_Event(0xFFFF)`, an optional hook, then a switch
  on the event's kind over `-2`, `-1`, `1`, `2`, **`3`**, `0xA`, `0xB0`, `0xB1`,
  `0xC0`, `0xD0`, `0x10000`, `0x10003`. **Kind 3, a network packet, goes to
  `0x0213B80A`**, which reads **packet byte 0** and branches into a jump table
  at `0x0213CE9E`: `subi.w #$B9`, bounds-check against `0x47`, **71 entries**.
- **Opcodes `0xB9` to `0xFF`, 46 with their own handler.** That is the same
  range the pod *sends* in - 31 opcodes `0xBA` to `0xED`, found earlier from its
  43 calls to the packet sender - so it is **one symmetric protocol**, and the
  operator console's messages live in it. Two new checkpoints; the harness is at
  **88/88**.
- Worth keeping straight: this is **not** the dispatch at `0x0213A332` that
  reads byte `0x13`. Both exist, reached by different routes; the byte-0 table
  is where a packet off the wire lands.
- **A packet injected from outside reaches the game's event queue** - the first
  time anything has. The path: a byte-0 opcode the low-level dispatch does not
  claim falls through to the router at `0x0212300A`, passes a second identity
  filter at `0x02123062` which accepts **two** addresses (`0x02179D32` and
  `0x0218AEB2`), and is handed to `Post_Event` at `0x021230C8` as an **event of
  kind 3**. Three taps, three hits. Three new checkpoints; the harness is at
  **86/86**.
- **This corrects "the low opcodes are discarded, so game messages cannot get
  in".** They are discarded, but a game message does not use one - byte 0 is a
  low-level type and the game's own opcode is at byte `0x13`. The dispatch knows
  only `0`, `1`-`7`, `0x20`, `0x21`, `0xC7`, `0xE4`; everything else is routed.
- What still does not happen is the draining: `0x02139E64` is never reached
  during a boot, so the event sits in the queue. **The message pump is part of a
  mission, not of coming up.**
- Also corrected: `--packet` takes the message **body**, not a framed packet -
  the stub writes the four-byte header itself. An hour went into a packet whose
  opcode was reading as `0` because of that.
- **The SecCom block is a 32-slot message ring, and the arithmetic closes it.**
  The enqueue at `0x0212C1EC` gives up the whole layout: a write index at
  `+0x12A`, a read index at `+0x12E`, `& 0x1F` for 32 slots, and a slot stride
  that works out to **42 bytes** (`i*5`, `<<2`, `+i`, `<<1`) from a base of
  `+0x132`. **`0x132 + 32 x 42 = 0x672` against a block of `0x674`** - two bytes
  of slack and nothing unaccounted for. Third independent confirmation of the
  size, after the loop bound and the printf.
- **It is set up during an ordinary boot, not only on a game start** - correcting
  what was written here last commit. After a normal run the pointer at
  `0x02194452` holds `0x4007E000` and the firmware reaches `main game loop`. The
  only traffic a boot generates is three reads of `+0x12A` and one of `+0x12E`:
  the producer checking whether the ring is full and finding nothing to send.
- Also tried and worth recording: **the monitor's `y - START TEST GAME` does
  nothing**, because reaching the monitor at all requires patching an `RTS` over
  the game init - the same code path the test game would use. Three new
  checkpoints; the harness is at **83/83**.
- **A `docs/` folder, and two documents this project should have had from the
  start.** The technical writing moved out of the root -
  `docs/DEVICES.md`, `docs/RENDERING.md`, `docs/ARCHITECTURE.md`,
  `docs/PLAN.md` - joined by an index explaining what is where.
- **`docs/FALSE-TRAILS.md`** records every wrong turn that cost real time and
  what killed it: the A5 model that does not apply, the modem mistaken for the
  game receive, "no second dispatch" when the opcode was simply at byte `0x13`,
  `674` read as decimal, the collision hulls drawn as terrain, the rig box that
  cannot settle placement, and the Makefile dependency trap that served a fixed
  decoder's old numbers twice.
- **`docs/UNRESOLVED.md`** separates what is *assumed* from what is *measured
  and unexplained* from what is *papered over*, because those fail differently.
  Every load-bearing assumption now has to say what would settle it - the
  `461`-`466` torso naming, `0xC5` as `ROUTER_STATUS_MSG`, the feet by
  elimination - and every fake is listed with what breaks if it is wrong.
- **The SecCom block is at `0x4007E000`.** Its location was never known. The
  code that sets it up sits immediately before the handshake call: a base
  written to a pointer at `0x02194452`, then **`0x674` bytes zeroed a byte at a
  time**, then `jsr $214DA26`. In the Amiga's own address space that is offset
  `0x7E000` - far above its program, which ends at `0xF6A4`.
- That also explains why watching `0x40000000`-`0x4000FFFF` turned up only the
  handshake word: **the block is in a different 64K**. Three new checkpoints
  read it straight out of the disassembly; the harness is at **80/80**.
- It is set up on a game start, not by the monitor's `p`, so the pointer is
  still zero after `Secondary Started` and the block cannot be watched live
  yet. The 0x674 appearing as both a printf argument and a loop bound is what
  settles the size beyond doubt.
- **The secondary display's handshake driven to completion.** The handshake
  itself was already recorded here from an earlier session; what is new is that
  the firmware's own `p - Start Secondary` now gets past it and says
  **`Secondary Started`**. Without the ready word, `0x40000100` is read
  **12,112 times** in one run while the console prints
  `Waiting for Secondary to become ready 0` - the wait is a spin, and the
  number it prints is the word it read.
- **The `0x400` the 68020 hands over is the Amiga program's text base.** The
  load script puts `AMIGA3_0` at `0x400003E4`, its 601A header is 28 bytes, so
  its text begins at `0x40000400` - window offset `0x400`, exactly the value
  written to `0x40000108`. The handshake tells the other board where its code
  is, which also explains the `--set 40000100=1234567` that has been in the
  harness since before anyone wrote down why.
- **Nothing touches the Amiga window during an ordinary boot.** Watching
  `0x40000000`-`0x4000FFFF` across a full boot comes back empty; the board is
  brought up on demand. Two new checkpoints; the harness is at **77/77**.
- **The secondary display's program runs for the first time.** `--amiga` loads
  `AMIGA3_0` - a plain **601A image**, text 56,704, data 4,720, bss 692, with
  `ABSFLAG = 1` meaning no relocation table - at address **0**, where its own
  `jmp $0000E112` says it expects to be. A bare-metal display board with no
  operating system.
- **It does not start, and the reason is now known.** The word at `0xE112` is
  zero in the file under either mapping, inside a hole of zeros at
  `0xE000`-`0xE400`; the trace runs `jmp $e112` straight into them. Something
  fills that word before the program runs, and it is not the image.
- The other board is the candidate and the evidence agrees: `ROM3_0` carries
  **208 distinct references into `0x40000000`-`0x40010000`**, the Amiga's memory
  window, `0x40000000` itself **137 times**. The boards share memory and the
  display is driven across it rather than booted - which makes the next
  question that interface, the 674-byte SecCom protocol the roadmap has carried
  since the start. Two new checkpoints; the harness is at **75/75**.
- **Standing where the pilot stood.** Every scenario opens with a block of
  five-column drop points - facing, position, height - which the console reads
  with the `%f %f %f %f %d` grammar. BadLands has **sixteen, one per pod**, and
  `--scene-drop N` puts the camera at one. The height is **5.4 on every drop in
  every map**, which is a cockpit on a machine nine units tall: eye level, not
  a number anyone picked.
- The camera orbits a centre, so standing somewhere means putting the centre
  one look-ahead in front and turning to match - a heading of h needs
  **turn = -h**. What comes out is the pod's own picture: BadLands is mesas and
  rock spires along the horizon over sand, and Urbana from its drop point is
  tower blocks and low buildings. Same code, same archive, different scenario.
  One new checkpoint; the harness is at **73/73**.
- **Whole maps, drawn.** The release ships **eleven scenario files in plain
  text**, and the grammar to read them came out of the operator console, which
  parses them with `scanf`: `GROUND_CLASS %d %d %f %f %f %f %f %d %d` and its
  eight-field neighbour. The columns are a class, a **model resource id**, a
  position, a heading in degrees and a scale - so a scenario is a list of
  models to place, and every one of them is a resource this project already
  decodes. **BadLands-16 places 882 objects using 19 models**, and
  `battlepod --scene` draws 9,308 polygons of it.
- `src/scene.h` reads the file; `ras_draw_at` places each object by its own
  heading and scale, so one decoded model is drawn hundreds of times rather
  than merged into a mesh the size of a map - which is also what the display
  list does. Three new checkpoints; the harness is at **72/72**.
- **It needs no game running**, which is why it was worth doing: it is the
  first thing here to draw a whole world rather than one object. Three of
  BadLands' nineteen models decode to no geometry, which is recorded and not
  yet explained.
- **The console's log strings are not statically referenced, and that is now
  measured rather than suspected.** Six ways of reaching them were tried and
  all came back empty: all **4,256** code fixups target `DATA` `0x0072`-
  `0x31CA` and none above; `DREL` slot contents stop at `0x7468`, just below
  the messages at `0x7572`; no `DATA` longword equals a message offset; no
  32-bit or 16-bit constant in any segment does either.
- The mechanism itself works - the same technique finds `CArray.c`,
  `CObject.c`, `CWindow.c` and an assertion message through `CREL` sites and
  `DREL` slots - and the extraction is faithful to the resource fork byte for
  byte. These particular strings are simply not on the end of it.
- Two leads written down rather than chased: **five of twenty segments carry no
  `CREL`** (`CODE_0`, `1`, `11`, `12`, `13`), and **`DATA` opens with a
  longword `600` then 600 words** while containing exactly 600 printable
  strings - a coincidence that survives, since read as offsets in three
  framings only 12 to 16 of the 600 land on a string start where an index would
  land on all.
- **The console's relocations are read, and the model was wrong.** THINK C's
  far model does not reach globals through A5: this application has **zero
  `lea (d16,A5),An` sites and eight `pea (d16,A5)` in 260 KB of code**. It puts
  absolute 32-bit `DATA` offsets inline and ships `CREL` to say where - a flat
  list of ascending 16-bit offsets per segment, each naming a longword holding
  one. Confirmed by those longwords landing on real string starts.
- That work went upstream into **`macrecomp/tools/relocs.py`**, since it is
  general THINK C support rather than anything to do with this cabinet.
- **It has not yielded the message opcodes.** The console's message strings sit
  high in `DATA`, above `0x67C3`, and no fixup site in any segment points at
  them. Five of the twenty segments carry no `CREL` at all, which is where to
  look next. Recorded as an unfinished thread rather than a solved one.
- **The first opcode with a name: `0xC5` is `ROUTER_STATUS_MSG`.**
  `0x02145E1C` builds it as an opcode, a `strncpy` of up to **0x50 bytes** of
  text, and a longword - and its callers are the SiteLink modem's own state
  arms, the ones printing `Modem in command mode`. The console logs exactly one
  message of that description: `ROUTER_STATUS_MSG from node %ld, status %s,
  status code %ld`. Three agreeing facts rather than a decode, and written down
  as inference - but it is the first named opcode in this protocol and it cost
  nothing.
- The console corroborates the shape: `CODE_18` compares a received packet's
  byte against `#$C5` and against nothing else in that form, which is what one
  special-cased message type looks like. **First opcode seen in both binaries.**
- **What the A5 cross-reference will cost, measured rather than guessed.**
  `DATA` holds no plain-offset pointers to the message strings - all 39,096
  bytes searched, nothing - so the pointers do not exist until the relocations
  are applied. `DREL` is two sections: ~2,486 32-bit offsets descending from
  `0xD4D2`, then ~290 16-bit ascending. Both ranges run past `DATA` at `0x98B8`
  and past `DATA`+`ZERO` at `0xA8C8`, which is what THINK C's far-data model
  looks like. Naming the other 30 opcodes goes through that.
- **The 33 opcodes are the in-game message set, not the setup sequence** - a
  guess checked before it was built on. The nine handlers from `0x64` to `0x70`
  line up in count with the nine `*_CLASS` records the map file carries, which
  looked convincing; the code refutes it. The arms that do more than queue an
  event operate on the local vehicle through a pointer at `0x0218AEE4`:
  `0x68` subtracts **5.0** from a float at `+0x2E` and compares it against
  -2.8, `0x3B` subtracts 2.0 from `+0x100`, `0x4A` walks 24-byte records from
  `+0x140`. Subtracting five from a float and checking a threshold is damage or
  heat, not a map record.
- First sight of the **vehicle state structure** as a result: a word flag at
  `+0x92`, floats at `+0x2E` and `+0x100`, an array of 24-byte records at
  `+0x140`, all off the pointer at `0x0218AEE4`.
- Naming individual opcodes needs the other end - the console's code writes the
  opcode that goes with each named message - which means the `DREL` fixups and
  an A5 cross-reference, the job `macrecomp`'s front end was picked for.
- **The game's own message dispatch, found from the sending side.** The packet
  sender at `0x021468A4` has **43 call sites**, 28 in one module, and each
  writes its own opcode first: **31 distinct opcodes from `0xBA` to `0xED`**.
  That said the game protocol lives nowhere near `0x01`-`0x07`, and the
  receiving half turned up in the same neighbourhood.
- **The opcode is at packet byte `0x13`, not byte 0.** `0x02139E64` reads
  `($13,A0)` and branches into a **33-arm dispatch** at `0x0213A332` covering
  `0x21` to `0x7A`. That one fact is what made the earlier reading wrong: byte
  0 is the low-level type the boot monitor switches on, and the game's type
  sits nineteen bytes in.
- Most arms translate the wire message into **`Post_Event(kind 0xB1, param N)`**
  and queue it, so a game message is not acted on where it arrives - the same
  shape the modem path has. The dispatch is reached from a message pump at
  `0x0213909E` fed from `0x0218AEE4`, with the firmware's own
  `Test Event, message# %d` sitting beside it.
- **This supersedes "there is no second dispatch"** from two commits ago. There
  is one; it was being looked for on the wrong byte and in the wrong opcode
  range.
- **The pod's identity is something it is told, not something it works out.**
  `0x0218AEB0` is this cockpit's `(net, node)` and `0x02179D32` the game's, and
  across a whole boot they are read **273,621 times and written zero times**.
  The startup clears the bss they live in and they stay zero until the operator
  console puts an address there - which is why `Net_Configuration` carries a
  node number per cockpit.
- **While they are zero, no network packet can reach the game path at all.**
  The receive at `0x02146004` returns -1 on its first comparison, before
  touching a device, a buffer or a byte. Supplying an address once the pod is
  running gets past it and the receive body then runs every time round the main
  loop. Two new checkpoints; the harness is at **69/69**.
- It then sits in **state 0 of an eight-state machine** at `0x0239DD9A` and
  touches no hardware - no new address appears in the unmapped log - so the
  received data is software-buffered rather than read from the ARCNET
  controller at that point. States 1 to 7 are the next question.
- **`--peek ADDR:N`** reads memory when a run ends, which is how the zeros were
  found, and **`--set-at PC ADDR=HEX`** writes a longword the first time
  execution reaches an address - the only way to supply configuration that the
  firmware's own startup would otherwise wipe.
- **Nothing dispatches a game message at receive time, and that was the wrong
  question.** The dispatch at `0x02122FBC` discards opcodes `0x01`-`0x07`, so
  the plan was to find the other dispatch that handles them. There is no other
  dispatch: **there are two receive paths.** That chain serves the *boot
  monitor's* queue, which is why the opcodes it knows are identify, timebase
  and route. A packet that arrives off the network and matches this pod's game
  identity goes somewhere else entirely - it is **posted as an event**.
- **`Post_Event` and a 400-slot queue.** `0x021228D6` takes a kind and three
  longwords and files them, stamped with the timebase. Kinds `0x0C` and `2`
  have dedicated slots; everything else, network packets included, goes into a
  table at `0x021B7566` in records of `0x26` bytes up to `0x021BB0C6` -
  **exactly 400**. The firmware names the routine itself, in
  `In Post_Event, event queue full!`.
- So the low opcodes were never going to the wrong handler. They go to the
  right one, into a queue nobody is draining, because the game loop is not
  running. The same wall as everywhere else, but a more useful shape: it names
  where to look when a game does start, and it means writing the operator
  console does not need a second dispatch found first.
- It also confirms the packet header from the receiving side: `buf[6]` and
  `buf[7]` are matched against `0x02179D32`/`33`, which is exactly where the
  sender at `0x021468A4` writes the game identity. Both ends agree.
- **The Remote I/O link works in both directions now.** `--rio-in` drives the
  receiver nothing had ever driven, and the firmware confirms it without us
  interpreting anything: feed `01 00 03 03 D3 05 01 D9` and its own "display
  hex data from remote I/O" prints `[d3] [05] [01]` - the payload, with the
  header and checksum stripped by its own protocol handler. So inbound framing
  matches outbound and the transport for stick, throttle and pedals is done.
  Two new checkpoints; the harness is at **67/67**.
- What an input report *says* is still open. The receive interrupt at
  `0x0215B6CC` takes up to four bytes at a time and hands each to a state
  machine through a function pointer at `0x0217FBE4`, so the panel board's
  opcodes are a dig through those states - **feeding all 256 opcodes past the
  firmware's decoder produced nothing**, which is worth recording as a negative
  result rather than repeating.
- Also checked and worth writing down: **the display list a boot posts is
  empty.** It decodes as one type 0 record and then a `0xFFFFFFFF` terminator.
  There is nothing to draw until a game runs, so wiring the display list to the
  rasteriser cannot be tested against real content yet.
- **Whole mechs in C.** `src/rig.h` is `render.py`'s Assembly ported: eight
  parts hung on a skeleton's rest pose by the same rules - containment for the
  limbs, touch-the-parent for which way a mirrored pair goes, the id block for
  the feet. `cockpit.exe --live --rig 452` turns a whole MadCat, and
  `--rig-all` totals the six. `$040`'s node tree is now captured by `mesh.h`,
  which had been skipping it by length.
- **The two assemblers check each other too**, on the same numbers: **6 chassis
  whole, 48 parts placed, 1291 mech polygons**, identical either way, and every
  node, model and position matching across all six. Three new checkpoints; the
  harness is at **65/65**.
- One bug the comparison caught, worth recording because it is a trap the
  Python sets: a part has **two extents and they are not the same**. The box a
  model states for itself decides which node it belongs on; where its vertices
  actually are decides whether two placed parts touch. The C used the vertex
  extent for both, and the MadCat came out with six parts instead of eight -
  no thighs at all, and the shins hung on the ankles.
- **The main view draws itself.** `src/mesh.h` runs a model's own threaded
  program and `src/raster.h` draws the result, both in C inside the emulator's
  process - `cockpit.exe --live --mesh 463` turns a Vulture torso with no file
  in the path and no Python. The archive is already in the emulator's memory,
  so `mesh.h` walks it in place at `0x02B00000` rather than loading anything.
- **The two decoders check each other.** They are separate ports of one
  interpreter, so the harness holds both to the same floor: **130 models, 5578
  vertices, 2515 polygons, 1050 materials, identical either way**. Six new
  checkpoints; the harness is at **61/61**.
- That check earned its keep immediately. The first C version followed `$020`
  to its target and abandoned the continuation, where the Python hands the
  target to a work list and carries straight on - it came out with nine
  vertices and **no polygons at all**. A second bug hid behind a stale object
  file, because `mesh.h` was not in the Makefile's dependencies.
- **The pod answers.** Say `IDENTIFY_YOURSELF` to the booted cockpit and it
  replies `20 01 00 20` followed by `GAME RUNNING 3228 600 2 GAME_NAME` -
  exactly the reply the operator console logged in 1995, from the other side of
  the same wire. **The first message exchanged with the pod in either
  direction**, and the feedback loop step 3 of the plan needs. A new checkpoint
  guards it; the harness is at **55/55**.
- **`--tap ADDR`**, with `--tap-dump OFF N`. `--watch` says what touched a
  region of memory; a tap says what the registers held when execution arrived
  somewhere, and dumps N bytes at `A6+OFF`. The reply never reaches a device we
  model - it is a stack argument to the packet sender - so the only way to read
  it was to stand at the sender's door as it went out.
- **The packet handlers read from the pod rather than the Mac.** The plan was
  to lift the console's 68k code for the byte layouts; the pod's side is easier,
  already in the emulator, and a decoder specifies a format as well as an
  encoder does. The dispatch at `0x02122FBC`, the identity handler's four-byte
  header and `sprintf`, and the sender at `0x021468A4` writing a constant
  eight-byte header of opcode, priority and three `(net, node)` addresses drawn
  from the destination argument, our own address at `0x0218AEB0` and the game
  identity at `0x02179D32`.
- Worth knowing before building on it: **opcodes 1-7, 0x20 and 0x21 are thrown
  away** in this state - the handler releases the packet and returns to the main
  loop without looking at it. So whatever configures and starts a game is
  handled by something that is not running yet, and finding it is the next
  question rather than an assumption that this dispatch is the whole story.
- **The legs were hanging in the air beside the hips, and now they are not.**
  Which way round a mirrored pair goes was settled by which way a part's own
  vertices lean against which way the node does. That is wrong: the Loki's
  thigh straddles its own origin and the MadCat's sits entirely to one side of
  it, so the rule got one family right and the other visibly wrong.
- The rule that holds for both is **adjacency** - of the two orientations,
  exactly one lands the thigh's inner edge *on* the pelvis's outer edge, and it
  lands there to the hundredth. `Loki 474 -> -2.30..-0.90` against hips ending
  at `-0.90`; `MadCat 494 -> -1.87..-1.00` against hips ending at `-1.00`; the
  other way round overlaps by 2.22 or leaves a 1.03 gap. Across the six chassis
  **all 42 limb joints now meet**, the worst by 0.004 units on a machine nine
  units tall. A new checkpoint guards it; the harness is at **54/54**.
- **The feet stay open, and are now recorded as open.** A foot hangs on a node
  with nothing below it, so the adjacency rule has nothing to work against, and
  both orientations score identically. The reverse-jointed chassis come out
  7.50 units wide against the 4.00 their own rig declares, because `493`/`496`
  are 3.60 across and hang at ankles 3.90 apart - so either those are not the
  feet or they do not hang at the ankle.
- **The main view, in a window.** `make view` builds `build/view.exe` and
  `render.py --raw --spin N` feeds it: the pod's own 480x360, opened at double
  size, letterboxed rather than stretched when the window is dragged. Space
  plays and pauses, arrows step, escape quits. Sixty frames of a MadCat turning
  is one command.
- The frames are **plain RGB with no container** - the same bargain the panel
  makes with the Remote I/O stream. The rasteriser is Python today and will be
  C in the pod eventually; the window does not care, and swapping one for the
  other changes nothing. A file that does not divide evenly into frames is
  called out as a size mismatch rather than shown sheared by a row.
- **The cockpit panel, in windows you can move around.** `make panel` builds
  `build/panel.exe`: lamps, soft-label displays and bar graphs in three
  resizable SDL windows, driven from a Remote I/O capture that
  `battlepod --rio-dump` writes. Left and right scrub a frame at a time, which
  is the point - that is how which-lamp-is-which gets answered, by watching an
  id change against what the firmware says it just did.
- **The seam is the wire.** `src/rio.h` holds the frame walker and panel state
  and is all the emulator and the renderer share; the emulator does not know
  the panel exists. So the panel runs with no emulator present, is testable
  against captured bytes, and could one day drive a serial port with a
  salvaged cockpit on the end of it.
- The capture driving it is **real firmware output** - each frame from a
  separate run of the pod's own diagnostic monitor over the modelled serial
  port. Statically linked, so `panel.exe` needs no DLLs beside it, and its
  self-check builds without SDL at all so the harness runs it anywhere.
- Worth recording: **a boot emits exactly one Remote I/O frame.** The firmware
  sends a single `D5` at startup and nothing after, because it does not light
  the panel until a game runs. Until the operator console exists a rich capture
  has to be assembled a command at a time - the same blocker as everywhere
  else, showing up somewhere new.
- **`tools/opscon.py` - the console's protocol, read out of the console.** The
  plan was to lift its 68k code; in the end no lifting was needed. The console
  **logs every message it sends, by name and with its fields**, and those
  `printf` formats sit in one region of its `DATA` resource - so a format
  string is a field list written by the sender. **31 messages**, cross-checked
  against `logproto.py`, which recovers the same vocabulary from a real
  centre's 1995 log: the sender and its diary agree.
- The entity taxonomy came with it and is wider than the vehicle list showed -
  `VTV_CLASS`, `HOVER_CLASS`, `COPTER_CLASS`, `CAMERAMAN_CLASS`,
  `ANIMATOR_CLASS`, `POD_CLASS`, `EXPLOSION_CLASS`, three of which this build
  reports as unsupported - and so did the **packet header**: `ERROR: Orig. %d,
  Pri. %d, Num. %ld, Time %ld` says a packet carries an origin, a priority, a
  sequence number and a timestamp.
- **The map file format, for free.** The console parses the release's data
  files with `scanf` and those grammars are in the same region, each followed
  by the log line naming what the parsed line becomes, so `--formats` labels
  them: `GROUND_CLASS %d %d %f %f %f %f %f %d %d`, `DOOR_CLASS`, `LIGHT_CLASS`,
  `CAMERA_POSITION` and the rest, plus `Net_Configuration` and `Game_Setup`.
  Three new checkpoints; the harness is at **53/53**.
- **The panel decomposition, from the System 3.0 manual** - the right
  generation for this release. It names the panels as hardware: Weapons A,
  Weapons B, Keypad, Buttons, LCD in the card cage, and describes Player
  Interface Device, Advanced Function and Video Select Panel in words that
  match the firmware's status lines one for one. So the SDL windows follow the
  boards rather than a layout we invented. The manual also gives the analog
  ranges the input path needs: throttle and pedals `$0000` to `$0340`, joystick
  `$0000` centred and about ±`$80` at the stops, all optical encoders.

### Still open

- The message **byte layout on the wire**. Format strings give the fields and
  their C types, not their order and width. That does need the code - but it is
  now a narrow question about a few functions in `Start.c` and `Load.c` rather
  than an open one about a 260 KB application.
- **The cockpit's whole switch inventory, from the firmware.** The ROM prints a
  status line every time a control is thrown, so the panel is recoverable
  without seeing a pod: torso twist and centring, visible/infrared/searchlight,
  the three secondary-display modes, radar zoom and range, target select,
  indirect fire and forward observer, three stick modes, fine and regular
  pedals, inertia or instant stops, and a **difficulty ladder built into the
  cockpit** - `BASIC` / `STANDARD` / `VETERAN` / `MASTER MODE`, with
  `CROSSHAIR ON`/`OFF` and a `PANEL TRAINING MODE` for teaching the switches.
  The damage messages line up one-for-one with the 21 hit locations.
- Photographs of a surviving pod give the arrangement - five green MFDs, three
  above the viewport and two flanking the console, eight soft keys each - and
  their printed legends read against the ROM strings as the same switches.
  Noted in ARCHITECTURE.md with the caveat that the photographs are of a
  **later pod generation** than this release: texture-mapped view, colour LCD
  console, where 13.1.8 is flat-shaded on a mono CRT.
- **Which lamp is which turns out not to need a photograph.** Drive an input,
  watch which lamp id changes on the Remote I/O wire, read the status line
  printed in the same frame. An experiment in our own emulator rather than an
  archaeology problem.

### Changed

- **ARCHITECTURE.md's operator-console call, corrected with measurements.** It
  said *write it, do not emulate it*, dismissing the 68k Mac route on THINK C's
  relocations. The sibling `macrecomp` toolkit already does 68k Mac static
  recompilation and has HyperCard - a larger program - booting, so the honest
  answer needed numbers. Its `scan_traps.py --coverage` on the console:
  **920/1624 call sites (56%)**, the gap dominated by SANE, QuickDraw, TextEdit
  and the Print Manager. The binary names its own 53 source files and **36 are
  THINK Class Library**; only 17 are VWE's, of which `Start.c` and `Load.c` are
  what we want, with every message name in one string region at `0x76C8`.
  So: **lift it to read it, write it to run it** - use the toolkit's front end
  to recover the message byte layouts, which needs no Toolbox at all, then
  write the console because the rest of its job is reading plaintext files we
  have already parsed.
- **ARCHITECTURE.md** - the long view. What the finished thing is (a pod in
  SDL windows you can drag around, panels driven by the Remote I/O byte stream
  so one could later be real hardware, ARCNET encapsulated in UDP with a small
  centre server), what order to build it in, and which decisions evidence has
  already settled. Its strategic call: **write the operator console rather than
  emulate it** - everything it reads is plaintext in the release and its entire
  message vocabulary was transcribed from a `Console Log` a real centre kept
  for eight months of 1995 - because a game start is what unblocks the pose
  data, and the pose data unblocks everything downstream.
- It also answers how the thing plays, from the cockpit ROM's own strings:
  `SHUTDOWN IN %d SECONDS`, `TWISTING TORSO LEFT`, `AMMO BAY FIRE`,
  `Course %3.5f, Speed %3.5f`. **Real-time first-person, not turn-based** -
  but keeping the whole tabletop data model, separate armour and internal
  structure on each of 21 hit locations, heat as a float with a shutdown
  countdown you can `MANUAL OVERRIDE`, ammunition counted per bay.
- **`$480`'s tag is a hit location**, one-based, the same 21 the vehicle
  records list. Three things say so: **no tag anywhere in the archive falls
  outside 1 to 21** across the 27 models that use the opcode; a torso model
  tags exactly the ten torso locations and nothing else; and the assembly at
  `516`, whose vertices all sit at positive x, tags **Right** Arm and **Right**
  Weapon Pod while its mirror `517` tags the left pair - decided twice over,
  by geometry and by the ROM, agreeing. `model.py --zones` prints it, named
  against the record when given the ROM.
- That completes the chain from a pixel to a damaged component on paper: the
  pick query returns a sub-part id, the vehicle record turns it into a named
  location with its own armour and structure, and `$480` says which polygons
  are that location. Two new checkpoints, harness at **49/49**.
- It also identifies the arms - `516` right, `517` left, five alternative
  sub-models each - without placing them. Hung on the shoulder nodes they
  reach well outside the mech's own bounding box and run six units along z on
  a machine four deep, which reads as an arm authored along an axis and
  rotated per frame. Terrain and buildings use `$480` too, tagging 1 and 2;
  that is a zone number and nothing to do with anyone's left foot, so only
  mech parts get their tags named.
- **A mech stands up.** `$040` turned out to be a node composition - node,
  parent, transform slot, and **three floats that are the offset from the
  parent** - so a skeleton is a chain of them and running the chain is a rest
  pose. It comes out as hips, torso, a hip/knee/foot down each side and a
  shoulder out each way, mirrored to the third decimal, feet at y -4.55 inside
  a stated box of -5.00. The check is the model's own: **every node has to land
  inside the bounding box the model states**, and across the six chassis the
  worst pokes out by 5.6% with three at zero. `model.py --nodes`.
- Exactly **two leg designs** in the release: Loki, Thor and Sunder put the
  knee under the hip; MadCat, Vulture and Avatar throw it 2.15 units back and
  bring the foot forward again, which is a reverse-jointed Clan OmniMech.
- **`render.py --mech N` assembles a whole one, placing nothing by hand.**
  Parts are authored in the space of the node they hang on - model 471 spans
  y -2.75 and the Loki's hip-to-knee offset is -2.75 exactly - so a part
  belongs on the node whose *child offset its own bounding box contains*, the
  smallest such part winning. Left and right are vertex-for-vertex mirrors,
  settled by which way each leans. The torso and the feet have no child offset
  to match and are placed by the id-block rules instead, which the code says
  out loud. All **six chassis assemble to eight parts**, and the two leg
  families fall out on their own along the same split the node geometry drew.
  Two new checkpoints; the harness is at **47/47**.
- **`tools/vehicles.py` - the cockpit ROM's vehicle and weapon tables.** Each
  of the 38 records at `0x70582` is a complete statement of a BattleMech: the
  skeleton's resource id, twelve floats of which the first is top speed, **21
  hit locations** by name with armour, structure and the two sub-part ids the
  pick query returns, and **twelve weapon bays**. `100 + 21 x 34 + 12 x 12` is
  958 to the byte. Every vehicle in the release has the same 21 locations in
  the same order - Left/Right Foot, Lower Leg, Upper Leg, Hips, Arm, Weapon
  Pod, the five torso zones and their rear faces, Missile Pack, Searchlight -
  so that list is the mech, part by part, and the sub-part ids run 10 to 51.
- **A weapon table of 20 entries at `0x7D018`**: name, HUD abbreviation,
  damage, range in metres, heat as a float, and direct fire against missile.
- **Checked against something the ROM does not control.** `New mechs and VTV`,
  a spreadsheet in the release, writes out three loadouts in English. Decoding
  those three records reproduces all three: **24 weapons, right names, right
  counts**, and every ammunition figure but one - Thor V7's SRM 4 carries 25
  rounds in the shipped ROM against the spreadsheet's 24, a design document
  predating its build rather than a bad decode. Five new checkpoints guard it
  and the harness is at **45/45**.
- **The six chassis, named from the release rather than guessed.** `Game
  Files/Vehicle_List` lists 38 vehicles over six chassis - MadCat, Vulture,
  Loki, Thor, Sunder, Avatar - plus a Drone and the Director camera. `ROM3_0`
  holds the same 38 as records of **958 bytes at `0x70582`**, name at `+0`, and
  the halfword at `+0x28` is the skeleton's resource id: it partitions all 38
  into exactly six groups. **451 Loki, 452 MadCat, 453 Vulture, 454 Thor, 455
  Sunder, 456 Avatar**, and the Drone rides the Loki rig. Six chassis against
  six skeletons confirms the structural read rather than assuming it.
- **The id blocks.** `451`-`456` are skeletons - 32 nodes, box
  `4.00 x 9.00 x 4.00` to the float, and not one polygon - `461`-`466` torsos,
  `470`-`480` limbs in mirrored pairs, `490`-`496` a leg set,
  `501`-`505`/`511`-`515` two five-part limbs assembled by `516`/`517`. Model
  451's stream is `$040`s carrying inline floats at a stride of seven
  longwords, which independently confirms `$040` takes six operands.
- **`model.py --shape`**: mirror a model and measure how far the mirrored
  vertices land from the originals, and bin them across the width for a
  shoulder profile. The mirror axis is measured too - over the torsos x gives
  0.004-0.055 against 0.085-0.18 for y and z.
- **Thor's torso is symmetric (0.008), and an earlier guess here said it was
  not.** This file previously read `462`'s deep one-sided notch as the Thor's
  shoulder pod. The ROM says `462` is the MadCat and the Thor is `464`. The pod
  is not in the torso mesh at all - it hangs off the rig as a separate part,
  which is the third independent line of evidence that the archive holds rigs,
  not poses.
- The `461`-`466` naming is inherited from the `+10` block alignment, not
  measured, and is corroborated by polygon count: the four Clan chassis come in
  at 248-386 and the two Inner Sphere ones at 71 and 66, splitting exactly
  where the ROM puts the boundary. No part table exists in the cockpit software
  to settle it outright - `461`, `463`, `465` and `501` do not occur in `ROM3_0`
  in either width, so parts are bound by the game server.

- **Material `kind` decoded: 0 is emissive, 1 is a lit surface.** Across the
  archive, `kind 0` materials average twice the luminance of `kind 1` (0.655
  against 0.368), and **every one of the 212 lights and markers points at a
  `kind 0` material while not one points at a `kind 1`**. `render.py` now gives
  kind 0 no lighting term, so a lamp stays lit on the side facing away from the
  sun. This is what `$4C0` "flat" and `$4E0` "lit" were saying.
- **Checked the decode against something outside the project.** A
  self-consistent wrong decode can pass every internal test but cannot
  accidentally produce a shape the world already recognises. Rendered side-on,
  463 is a mech torso with a canopy slit and a flank aperture, 466 a weapon pod
  with a barrel, 465 a shoulder rack. Their material tables read as paint
  schemes - armour browns and reds, a blue-cast near-black for canopy glass, a
  green sensor, an emissive yellow.

- **The bounding-box gap measured properly, and both explanations for it were
  wrong.** The claim in ROADMAP.md was that the failures all sit *inside* the
  stated box, from an authoring tool computing it over a pre-decimation mesh.
  Across all 31 rather than the handful that had been eyeballed, **27 poke
  outside it**. Rounding the decoded box outward does not reproduce the header
  either, at any granularity from 0.05 to 1.0.
- What is true is that the misses are small. Allowing any of the eight
  reflections: **89 exact, 105 within 2% of the model's own size, 117 within
  10%**, with three worse than that. `--stats` reports the 2% and 10% figures
  beside the strict one and the harness guards the 2% number, which takes it to
  **39/39** checkpoints.

- **The four draw opcodes that are not polygons.** `$200` puts one pixel at a
  vertex through `PIXT`; `$220` fills a rectangle between two corners;
  `$280`/`$2A0` draw a marker whose size is a world measurement the handler
  streams to the coprocessor to be scaled by distance. `model.py` collects the
  point forms and `render.py` draws them, unlit and biased a hair toward the
  camera - a light is coplanar with the surface it sits on and loses a straight
  depth test.
- Model 112 is the evidence the operand reading is right: **92 `$200` points,
  every one on material 2** - `kind 0`, rgb `1.00, 0.80, 0.50`, a warm amber -
  against 25 polygons on a flat grey. A dark structure with ninety-two lights.
  Model 84 shows the sized form, eleven markers from 0.1 to 0.37.

- **`$460` draws another model by resource id** - models nest. Twenty-two use
  it, and `516`/`517` draw `501`-`505` and `511`-`515`, exactly the mech part
  sets the bounding boxes had already paired off, which makes them the only two
  models that both compose transforms and assemble parts. `516` goes from 7
  polygons to **1035** once its sub-models are resolved. `model.py` follows
  them when handed the archive; their geometry joins the mesh but not the
  `written` list the box check uses.
- **They arrive unplaced, and that is the answer rather than a gap.** `$040`
  reads three operands - two node indices and a one-based index into a 48-byte
  table of twelve floats - and composes *node i = node j x instance k*. That
  48-byte table is **not** allocated from the model's header: its seven counts
  allocate 28, 16, 36, 56, 40, 12 and 20 bytes an entry and none is 48. It is a
  global the caller sets before running the model. **The archive holds rigs,
  not poses** - a model names its parts and says how they compose, and the
  transforms that place them come from the 68020 per frame, which is what the
  part bounding boxes had already implied from the other side.
- `render.py` decides whether to walk every branch from the data rather than a
  rule of thumb: a model keeping levels of detail behind its branches rewrites
  the *same* vertex slots on each arm, while one using them as a sequence -
  one `$460` per arm - writes each slot once. Take the full walk when nothing
  was rewritten, otherwise the fuller single path.

- **`render.py` draws the cast shadow**, by flattening a model onto the ground
  plane and drawing that before the model itself. The footage has a hard-edged
  dark shadow under every mech and it is most of what sits a model on the
  ground rather than floating it.
- It also frames on the vertices actually decoded rather than the stated
  bounding sphere - that sphere has to contain the origin too, so framing on it
  left every model small in the middle of the picture - and narrows the field
  of view from 90 degrees to 55. Model 463 now reads plainly as a mech's head
  and canopy, with the dark viewport slot cut into the red armour.
- The section of RENDERING.md describing the renderer was lost to one of the
  multi-edit scripts that aborted part-written; it is restored.

- **The complement fix reconciles two halves of the project.** The renderer's
  resource loader tests its flag word with what read at face value as
  `BTST #27`; the archive format, decoded from the 68020 side long before and
  sitting in `resmap.py` ever since, says the flag is *bit 4*. Those could not
  both be right. Complemented, `~27 & 31` is 4, and they are the same statement.
- `model.py --stats` counts **mirrored** models on their own line: five span
  their stated box only with x negated, which is how a left and a right part
  share one set of vertices, and why pairs like 491 and 494 state identical
  boxes. A mirrored match is a different claim from a plain one.
- The remaining box failures have a shape worth recording: the stated box is
  consistently a little larger than what we decode, which is what a few
  vertices coming from an opcode we skip without reading would look like.
  `$200`, `$220`, `$280` and `$2A0` are measured but never interpreted.

- **Every model in the archive now walks to a return — 130 of 130.** All 45
  opcodes are measured. Most came off the handlers, counting `MOVE *A7+` as one
  longword and `ADDI #n, A7` as `n/32` more, with each handler's bounds taken
  from the next entry in the table rather than guessed; `$200`, `$220`, `$280`
  and `$2A0` save the stream pointer in A8 and end `MOVE A8, A7 / ADDI #n, A7`,
  which gives the true advance directly.
- `$040` and `$520` would not yield to reading - both open with calls that
  consume operands of their own - so they were settled by **sweeping the pair
  against the archive's own checks**. The peak is sharp: 6 and 5 take every
  model to a clean return where 5 or 7 for `$040` drop twenty. `$520 = 5` also
  matches an independent reading of its handler. Recorded as measured by
  consequence rather than read off the code.
- Clean walks 104 -> **130**, vertex counts matching the header 84 -> **120**,
  boxes reproduced 63 -> **84**. Conformance floors raised to match.

- **The model tools are in the conformance harness**, which now runs
  **38/38** rather than 30/30. Five of the new checkpoints are the model
  archive's own numbers - the header opcode, clean walks, vertex and material
  counts, and the bounding-box check - recorded as *floors* rather than
  equalities, since the decoder is meant to improve and a number going up
  should not fail a build while a number going down means something that used
  to decode no longer does. The other three run each tool's `--selftest`.
- README documents `model.py` and `render.py`, which it had not mentioned at
  all, and the disassembler's figure is corrected from 95% to 98%.

- **Found the mechs.** Rendering all 81 models that produce polygons puts three
  dozen chunky red-brown parts in the high ids, 463 to 514, and their bounding
  boxes give the game away: `491 == 494`, `492 == 495`, `493 == 496` exactly,
  and `516`/`517` occupy mirrored half-spaces. Left and right limbs, modelled
  once and used twice.
- **The parts carry no joints** - one transform node each and no transform
  opcode executed - so a part is rigid and authored about its own pivot, which
  is why its box has to include the origin. Drawing a set together piles them at
  the origin instead of assembling. What places them is the display list: each
  object record carries its own 3x3 and translation, so the 68020 emits one
  record per part per frame with the joint angles baked in. The TI holds rigid
  parts, the 68020 holds the skeleton.

- **`tools/render.py` — the first geometry drawn out of the archive.**
  Z-buffered flat-shaded triangles, one directional light, a graded sky and a
  hazed ground, at the pod's own 480x360, written as a PNG with nothing but the
  standard library. Model 30 comes out as a **terrain mesa**, recognisably one
  of the buttes standing behind the mechs in the reference footage - which is a
  better check than any count, because the thing that comes out looks like the
  thing the pod drew.
- A model has to be walked down **one** level of detail to be drawn: taking
  every branch stacks the near and far versions in one frame and renders as a
  lump. Which side carries the detail differs per model, so the renderer tries
  both and keeps the fuller one.
- **What the model's bounding box actually spans**: the vertices *and the
  origin* - several models bound an axis at exactly `0.0` where no vertex
  reaches, which is a part keeping its own pivot inside its box - and *every
  value ever written to a vertex slot*, not just the survivors, because each
  level of detail rewrites the same slots. Vertices alone matched 41 of 84;
  plus the origin, 55; every write plus the origin, **63**. Archive-wide the
  box check goes 41 -> **63** of 130.

- **`tools/model.py` — the model format, and a tool that runs it.** A type 1
  resource is not a mesh but a **threaded program** of 45 opcodes, the same
  design as the display list, run by the renderer at `0xFE00EDB0` against a
  table at `0xFE00EEA0`. Vertices are IEEE float triples carried inline;
  polygons are index lists with a material; materials are six longwords of
  which three are a colour. The stream starts at header `+0x58` and that is a
  valid opcode in **130 of 130** models.
- The model's own bounding box is the validator: where a walk completes it is
  demonstrably right, and model 24 decodes 246 vertices against a header that
  says 246, 29 materials against 29, and reproduces its stated box exactly.
- Branch and call targets are bit offsets; `$160` is `2 + 3n`; `$520`/`$540`
  take one operand each, not five.
- **The model branch predicate.** `$320`, `$360` and `$420` do not carry a
  target, they carry a *program*, run by a second threaded interpreter at
  `0xFE018910` through a 24-entry table at `0xFE018A00` - postfix, five
  one-operand push forms then operators taking none, terminated by `$000`.
  `$320 $080 $000 $040 $00C8 $260 $000 $1440` is "if value(0) >= 200, jump
  0x1440 bits on": a distance test choosing a level of detail, which is where
  most models keep their geometry. `$2C0` is the unconditional form.
  Clean walks went 38 -> **98** of 130, vertex counts matching the header
  31 -> **84**, boxes reproduced 17 -> **41**, materials 31 -> **55**.
- The box check still lags the count check and the gap is written down as the
  hypothesis it is, not as a finding: it is not transforms, and walking every
  branch mixing levels of detail explains part of it but not all.

- **Reference footage, and a correction.** Two period videos carry real screen
  capture - the BattleTech 3.0 Dooley Trainer and a Discovery Channel piece -
  and they show **flat-shaded, untextured solid polygons with cast shadows**,
  a gradient sky and distance haze. An earlier note here called the target
  texture-mapped on the strength of VWE's 1994 press kit; that press kit was
  describing a *plan* for a next cockpit, not this one. The archive says the
  same thing and should have been checked first: six type 2 bitmaps totalling
  22,632 bytes against 130 models is a font and some HUD furniture, not a
  texture library. One frame shows a pod interior with all four surfaces at
  once. Wireframe does appear in this product - in the post-game debrief
  screen, and nowhere in the world view. See RENDERING.md.
- **What the pod actually looked like, settled.** Not wireframe: the renderer's
  code segment contains **zero `LINE` instructions**, and only ten of the
  TMS34020's own block primitives against 517 coprocessor operations - so the
  spans are written by hand, which is what shading requires because `FILL` does
  one flat colour. The frame buffer is 480x360 at 16 bits per pixel. And VWE's
  1994 press kit describes the cockpit then in development - the Tesla pod,
  which is this release - as the one that "utilizes texture mapped graphics".
  The mech art in the operations manuals is print illustration, not screen
  capture. See RENDERING.md.

### Fixed

- **`CMPI`, `SUBI` and `BTST` store the one's complement of their immediate.**
  TI's assembler flips the value before encoding and the hardware flips it
  back, so reading the encoding at face value turns the renderer's command-loop
  bounds check into `CMPI #$FFFFFFEF` - minus seventeen, compared unsigned -
  where it means **16**, the size of its dispatch table. The resource
  decompressor's escape test likewise reads `#$000000FF`, a `0xFF` byte, and
  not `#$FFFFFF00`, which nothing could equal. `BTST`'s bit numbers were wrong
  for the same reason. Both tools corrected.

- **The object record's trailing groups are pick queries, not geometry**, and
  both the docs and `--rstub` said geometry. Seven longwords each, capped at 32:
  the 68020 writes a screen X and Y, and the renderer fills in what it drew at
  that pixel - entity, sub-part tag and position - while drawing, reading the
  frame buffer at `0xFE01A280` and restoring the pixel afterwards. It is how the
  cockpit knows what is under the crosshairs. `--rstub` now decodes them.
- **DEVICES.md contradicted itself on the renderer's command dispatch table**,
  listing it two rows off - opcodes 3 to 12 with 1 and 2 null. The command loop
  does `DEC A0` before indexing, entry 0 jumps to the reset code and entry 1
  writes error, handle and address, so entry *i* serves opcode *i+1*.

- `tools/tms340dis.py` printed the cross-file `MOVE` (`0x4E00`) with both
  operands in the same register file. Bit 4 is the *direction*: `FE01A150` is
  `MOVE A12, B0` and is followed by `CPW B0, B0`, and `FE013210` has to reach
  `B9`, the colour `VLCOL` latches. The interpreter already had this right.

- **`MOVE *Rs+, Rd` clobbered the value it loaded when the two registers were
  the same.** The renderer's item dispatch is exactly that instruction -
  `MOVE *A0+, A0`, fetching a handler address through the register it advances
  - so the interpreter was jumping into the middle of its own jump table. On
  the hardware the loaded value wins. Self-tested.
- **The item stream is not inside the object record.** The renderer reads the
  object's `+0x58` as a 1-based index into the list built from **type 7**
  records and hands that record's payload to the interpreter. What follows the
  object's own header is geometry - `+0x88` groups of seven longwords, which is
  what the emitter's `7n + 33` was saying - run through a *second* item
  interpreter with its own table at `0xFE018A00`. `--rstub` and `--render` both
  corrected.

### Added

- **The TMS34082's command word, and the first coprocessor routine running.**
  The 32 bits after a `CMOV*`/`CEXEC` opcode are the coprocessor's instruction:
  `ID | ra | rb | rd | md | fpuop`. The `md` field needs no guessing - all nine
  commands R.BIN issues during a render agree with it, each matching the mode
  its TMS34020 instruction implies. **Mode 3 selects a routine from the '82's
  internal ROM**, about 160 of them documented, which is what changes the size
  of this job: the arithmetic is documented silicon, not microcode to reverse.
- Short-form `CEXEC` is recorded and **not executed**: it splits its command
  between two words and the scanned handbook's diagram of that split is not
  legible enough to settle, so a run reports how many it met rather than
  running them wrongly.
- `CEXEC $D800` decodes as `SCALE` - the perspective divide and viewport
  transform - and now runs. A render walk reports one routine executed and
  **one still unidentified**, named rather than guessed.
- `MCADDR` is written before the draw, so the renderer points the coprocessor
  at something first.

- **The renderer accepts a display list and walks it.** `tms340run.py --render`
  builds one from the format in DEVICES.md and drives R.BIN at it directly,
  which is the only way to see the renderer draw: the 68020 only builds a list
  once a game has started. It is also a test of the format, and it found two
  things missing from it - the list header is **two** longwords, not one, and a
  **type 2 record is not optional**: with no draw order the renderer collects
  every object and iterates an empty list.
- **Why nothing draws yet, measured rather than assumed.** The whole object
  path runs - 236 instructions, no unimplemented opcode - and culls the object
  before its item stream, because its transform at `0xFE0220F0` is
  `CEXEC`/`CMOVGC`/`CMOVCM` and nothing else. The walk needs **ten distinct
  coprocessor commands, twelve issued**, of which eight are register and memory
  transfers and only two are operations: `CEXEC $E000` and `CEXEC $D800`. That
  is the size of the TMS34082 work standing between here and a first frame.
- PIXBLT, FILL and PIXT in the interpreter, taking their operands from the B
  file the way the hardware does, including the binary-source form that expands
  one bit per pixel into COLOR1 and COLOR0 - which is how the cockpit draws
  text. Self-tested.
- `MOVE *Rs+, *Rd+`, `MOVE *-Rs, *-Rd` and `MOVE *Rs(o), *Rd(o)`, which the
  object draw uses to stream a transform through. Code segment recognition
  95% -> **97%**.
- `--boot N` to give the hardware bring-up its own budget, and a coprocessor
  command log so a run says exactly which commands it needed.

- **The display list format**, read off the two emitters in ROM3_0 that build
  it rather than off the wire. It is a flat array of big-endian longwords with
  a leading count, copied verbatim into the renderer's memory. Record type 8 is
  a viewport - its width, height and centre are derived from its corners by the
  emitter, which is what identifies it. Record type 1 draws an object and
  carries twelve IEEE single-precision floats that read as the identity only
  as four rows of three: a 3x3 rotation and a translation row. So the 68020
  sends a *matrix*, and the coprocessor does the transform. The renderer
  confirms the shape: it takes two pointers into the object, one at the start
  of the twelve and one at the start of the fourth row. Record `[+4]` is the
  length of what follows the type and length words, which is why the emitter
  writes `7n + 33` for a record 35 longwords long.
- **The pod's screen resolution: 480 x 360.** The object record carries `479`
  and `359` as the screen extent, and running R.BIN leaves the renderer's own
  WEND register holding `$016701DF` - 359 by 479. Two sides of the machine,
  same number.
- The renderer's full command set. There are ten opcodes, not four: 4 is
  compact, 6 is render, 7 follows every render with the constant 5, and 10
  loads a palette. A request record is 12 bytes, not 8 - 20 for allocate.
  Rendering goes through `Async_Render` at `0x0214D302`, not through the
  opcode 6 wrapper, which is dead code.
- **The renderer's side of the same list**, which agrees with it. Its command
  dispatch is a ten-entry table at `0xFE028460` where entry *i* serves opcode
  *i+1*, so opcode 6 is `0xFE007630`, which converts its argument from a byte
  to a bit address and calls the walker at `0xFE009D80`. The record dispatch
  table at `0xFE00A160` has **nine record types, 0 to 8**, and every handler
  only files the record into a bucket; a second pass walks record type 2, which
  is the **draw order** - 1-based indices into the objects - and is what the
  firmware's `Render List Overflow` counts.
- **The item stream and its 25 opcodes.** After an object record's 35-longword
  header come items whose opcodes step by `0x20` because the renderer uses the
  opcode *directly* as a bit offset into its table at `0xFE0229E0` and then
  `JUMP`s - a threaded interpreter. Twenty-five entries there, and the 68020
  has an emitter for every one, which is where each item's length comes from.
  Two of them carry a C string copied with the bytes reversed per longword.
- `battlepod --rstub` now decodes a display list when a render command posts
  one - records, matrix, item stream and strings - and `--selftest` walks a
  synthetic one, since nothing in the release sends a render command until a
  game starts.
- `JUMP Rs` (`0x0160`), which the item interpreter uses and both tools were
  missing.

- The renderer's processor is identified: a **TMS34020**, not the TMS34010 it
  had been read as, driving a **TMS34082 floating-point coprocessor**. R.BIN
  executes `SETCDP`, `SETCSP`, `SETCMP`, `RPIX`, `VLCOL`, `VFILL` and `CLIP`,
  none of which exist on a '10, and 419 `CEXEC`/`CMOV*` coprocessor
  instructions - the first of them five instructions after reset. Both tools
  now follow the TMS34020 User's Guide (August 1990) instead of the '10's.
- `tools/tms340run.py --selftest`: assertions pinning the three decodings that
  had been wrong - absolute load versus store, the MMTM/MMFM mask order, and
  SUBXY's flags.
- `tools/tms340run.py --fb FILE`: write the renderer's frame buffer out as a
  PGM. Its geometry comes from the renderer itself - DPTCH bits a row, PSIZE
  bits a pixel - and reads 512x512 at 16 bits per pixel. Nothing is drawn into
  it yet; the point is that "did it render" is now a question with an answer.
- `tools/tms340run.py --skip-unknown`: step over unrecognised opcodes and count
  them, for measuring how much further a run would get. A diagnostic, never a
  claim that the run was faithful.
- The XY instruction group (ADDXY, SUBXY, CMPXY, MOVX, MOVY, CVXYL, CVSXYL,
  ADDXYI), the coprocessor group including CEXEC's two-word short form at
  `0xD800`, RPIX, the SETC*P family, the field-1 SEXT and ZEXT forms, and
  absolute memory-to-memory MOVE. Recognition of the code segment goes from
  72% to **95%**, and branch targets landing inside the image from 98% to 99%.
- The full branch condition table. Only 7 of the 16 conditions were evaluated;
  the arithmetic never set carry or overflow at all, so LT/GE/LE/GT/HI/LS could
  not have worked.

- `tools/tms340run.py`: an interpreter for the renderer's TMS34020 code. If
  R.BIN executes it draws its own frames, which would make the model format
  something the renderer reads rather than something that has to be decoded.
  It runs 3,000,000 instructions without meeting an unknown opcode, brings up
  the hardware, writes the on-chip I/O registers and clears the frame buffer -
  262,144 writes to 0xA0000000.
- A real bit-addressed memory model: fields are read and written at arbitrary
  bit addresses across word boundaries, and SETF sets the size and
  sign-extension per field. Every move uses the field its opcode selects.
- Instruction coverage for MOVB, the immediate arithmetic forms, ADDK/SUBK,
  CALLR, DSJ and DSJS, PUSHST/POPST/GETST/PUTST, MMTM/MMFM, the
  single-register arithmetic, multiply, divide, modulo, BTST and CALL Rd.

### Fixed

- **The display interrupt now runs, and with it the whole vertical-blank path.**
  Two decoding errors kept it dead. `0x05A0`/`0x07A0` are absolute *loads*, not
  stores - the manual gives the group as `0000 01F1 100R SSSS` for a store and
  `0000 01F1 101R DDDD` for a load - so the handler's read-modify-write of
  `INTPEND` never read anything and never cleared the pending bit. And `MMFM`'s
  register mask is `MMTM`'s reversed: bit 15 names A0 in one and bit 0 names it
  in the other, which every one of the 25 matched pairs in the image confirms.
  Reading both the same way popped the saved register into the stack pointer and
  sent `RETI` to address zero.

  With both fixed the renderer stops timing out of its frame wait - 1,142,192
  spins down to 5,078 - and gets through double-buffer setup to boot stage 5.
  Execution reaches 570,000 instructions before the first unknown opcode, up
  from 20,000.
- `0x38000022` is the renderer's reset line, not an open question: the
  monitor's `n - Start TI` prints "Starting TI, screen should clear" and writes
  a word to it.
- Reaching the diagnostic monitor by patching an `RTS` over the game
  initialisation also disabled menu item `y - START TEST GAME`, which calls
  that same function. Patching the call site instead leaves both working.
- `BTST K, Rd` occupies the whole of `0x1C00`-`0x1FFF`, five bits of constant -
  it was decoded as a two-register form, so a quarter of the block was
  unrecognised. Code segment recognition 97% -> **98%**.
- `SUBI IW` is `0x0BE0`, not `0x0CE0`.
- `DSJ` and `DSJS` printed targets with no load base, and `DSJS` measured its
  displacement from its own address rather than the next instruction. Branch
  targets landing inside the image went from 94% to 99%.
- `MOVE Rs, Rd` across register files (`0x4E00`) wrote the destination in the
  source's file.
- Every TI instruction address the disassembler printed was 0x40 bits too high:
  the 8-byte file header was being counted as part of the image, when the
  68020's upload log says file offset 8 is TI 0xFE000000. Building the
  interpreter is what exposed it. `CALLA $FE000780` now lands on the first
  instruction of the hardware-init routine instead of mid-data.

- Relative branch and call targets were missing the image's load base, so every
  `JR`, `CALLR` and `DSJ` target the disassembler printed was wrong. Validation
  now covers relative branches as well as absolute ones, which takes the check
  from 164 targets to 982: 938 of them land inside the image.

### Added

- `tools/tms340dis.py`: a TMS340 disassembler, written from the encodings in
  the User's Guide. 36% of `R.BIN` is recognised - the
  register-indirect MOVE family and the graphics group are the gaps - but 164 of
  164 absolute call and jump targets land inside the image on all three renderer
  binaries, which is what shows it is in sync. Now 49% of all words, 70%
  ignoring zero fill, and 100% over the renderer's hardware init.
- `--watch BASE:LEN` logs accesses inside a mapped region, which the unmapped
  log cannot see. Pointed at a loaded resource it shows exactly which offsets
  the firmware reads and from where.
- The disassembler now decodes FPU instructions, following `--cpu`. The
  cockpit's geometry and physics code is dense in them and previously read as
  `dc.w $f2xx`.
- `tools/resmap.py`: walks a cockpit resource archive. The format comes from the
  firmware's own parser, and the walk accounts for every byte of the file and
  reproduces the firmware's printed index exactly.
- `RENDERING.md`: what it would take to reproduce all four of a cockpit's
  surfaces - the 3D view, the secondary screen, the panel and the controls -
  and which are blocked on what.
- The captured Remote I/O stream is decoded back into cockpit panel state:
  which lamp is lit and how brightly, where each bar graph stands, what each
  soft-label display reads. That is what a panel renderer consumes.
- `tools/macres.py`: lists and extracts Macintosh resources, from a raw fork or
  the AppleDouble sidecar `unar` writes. Gets at the operator console's 20 CODE
  segments.
- `tools/logproto.py`: recovers the cockpit network protocol from an operator
  console log. The console logged every message it exchanged with the pods by
  name, so a surviving log specifies the protocol directly.
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

- R.BIN is a scatter-load image: records of a big-endian target offset and a
  longword count, each followed by its data, which the 68020 places at five
  different TI addresses. The records account for all but the four-byte
  terminator. Only the first segment is code; the fourth is the I/O register
  initialisation table at 0xFFFF0000 and the fifth the processor's trap
  vectors.
- Loading it flat, which is what both tools did, left those segments absent -
  so the renderer's I/O setup loop read zeroes and spun forever writing to
  0xC0000000. Placed properly it programs eight distinct video registers.
- Disassembling only the code segment gives 72% recognised rather than the 49%
  previously reported across the whole file; the earlier figure counted data
  segments as code.
- SETF is encoded 0000 01F1 01FE SSSSS - field select in bit 9, sign-extend in
  bit 5, size in the low five bits with zero meaning 32. 0x0550 and 0x0740 are
  SETF; that much of the earlier reading holds.
- 0x0620 and 0x0660 are three words, not one: that reading lands execution on
  the stack-pointer setup, where treating them as one word leaves an
  unexplained 0x000D mid-entry. Their effect is still unknown. Their operands
  look like a table of globals 32 bits apart, but modelling them as absolute
  loads changed nothing observable, so that guess was withdrawn rather than
  kept.
- The renderer's dispatch table base and indexing are confirmed independently:
  the only places in the image holding handler addresses are exactly
  0xFE028460 + (opcode - 1) * 32 for opcodes 3, 4 and 5. Opcode 4's handler
  branches to itself - an unused slot - and 0xFE0072E0 jumps back into the entry
  sequence, which is the reset path.
- The renderer's main command loop at 0xFE006D80 decodes with no unknown words,
  and is the same protocol already read off the 68020: status word four bytes
  into the comm block, queue eight bytes in, 0xFFFFFFFF terminator, pi as the
  ready signal. Its command dispatch table is at 0xFE028460, indexed by
  opcode - 1, with handlers for opcodes 3 to 12; opcode 5 is load resource map.
- Right shifts encode 32 minus the count, which the disassembler now accounts
  for - it was printing SRL #29 where the firmware means SRL #3, the bit-address
  to byte-address conversion.
- The manual's absolute-move table is the least legible part of the scan and its
  load/store split contradicts the firmware. Settled from the data instead: all
  seven writes to the renderer state word use 0x0780, and 0x0580 writes the
  TMS34020's own I/O registers, so both are stores. The rest of that opcode
  group is left unrecognised rather than guessed.
- The renderer's hardware init reads cleanly: it writes three registers in the
  TMS34020's documented I/O block at 0xC0000000, enables interrupts, then clears
  0x40000 bits of frame buffer at bit address 0xA0000000. That the addresses land
  on the processor's own register block is a semantic check on the disassembler.
- The renderer kernel is engine code, not game content: `R.BIN3_0` and
  `R.BIN2_5` are byte-identical between BattleTech and Red Planet.
- The 68020 never reads inside a model. Watching the whole archive across a
  complete boot shows reads only at offsets 0, 4, 8, 0x0B and 0x0C - the 16-byte
  header - with every reading PC inside the resource-map builder. The model body
  is parsed by the TMS340 code in R.BIN, so reading it means reading TMS340 code.
- The 68020-side archive format: a kind directory, then per kind a binary-searched
  table of 16-byte records, with the record chain verifying to the last byte of
  the file. Kinds 0 and 1 hold shapes - a count then 26-byte elements of six
  floats and a word - which `size == 4 + 26*count` confirms for 228 of 244
  records.
- Shapes are keyed by the same ids as the visual models: 64 of Red Planet's 65
  shape ids are also type 1 model ids. The TI holds the visual geometry and the
  68020 keeps a far coarser solid-and-cylinder version of the same object.
- Corrects an assumption recorded earlier: solids, cylinders and ARES are not
  the drawing primitives. They are the 68020's own representation.
- The renderer keeps a pool of up to 1500 "solids" of 32 bytes each, built from
  three validated primitive kinds: solids, cylinders and ARES, each with a
  direction the firmware sanity-checks.
- A type 1 model's body is variable-length: no relation of the form
  `a*field + b*field + c` explains the resource size for even half the models,
  so the header fields are not counts of fixed-stride records.
- The resource archive format: 16-byte headers, `-1` terminated, with an alias
  bit that makes `+0x0C` name another resource instead of counting data.
- Type 1 is 3D models - bounding box valid in 130 of 130, bounding sphere in
  127 of 130. Type 4 is an alias table, all 136 aliases resolving. Type 7 holds
  the payloads they point at. Type 2 is six compressed bitmaps, two of them
  identical across BattleTech and Red Planet.
- Corrects an earlier miscount: the archive holds 418 resources (130/6/151/131),
  not 467. The earlier figures were eyeballed from the console listing; the
  parser now agrees with the firmware id for id.

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
- The protocol's message vocabulary and the order of a game start, recovered
  from the operator console log in the release: IDENTIFY_YOURSELF, SHADOW_ROM,
  per-image Load, Set Go_Address, GO, COCKPIT_CONFIG_MSG, PLAYER_CONFIG,
  MECH_CLASS with Drop Location, GAME_OVER.
- `MECH_CLASS`'s type field is the vehicle id from `Vehicle_List`, which is also
  the last column of `Game_Setup` - those plaintext files map onto the wire.
- Remote I/O opcode `0xD5`, no payload, sent once during boot.
- A packet that passes the address checks is queued into a 100-slot ring at
  `0x02183716` for a consumer that only runs during a game. Sweeping all 256
  opcodes with a minimal body changes nothing except `0xC6`, which the modem
  router logs - so a single packet cannot start a game.
- The operator console is THINK C far model with `CREL`/`DREL` relocations, so
  its string references are placeholders on disk. Reading the sender needs those
  relocation tables implemented first.

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
