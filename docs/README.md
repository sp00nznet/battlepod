# Documentation

Reviving a 1996 arcade cabinet means most of the work is reading, not writing,
and the reading is worth more than the code. These are the findings, kept
separate from the project's own front page.

## What is here

| | |
|---|---|
| [DEVICES.md](DEVICES.md) | The hardware, board by board: the address map, the DUART, the interrupts, the boot monitor, the resource archive, the renderer's command protocol, the network and the secondary display. The longest document and the one everything else rests on. |
| [RENDERING.md](RENDERING.md) | How the pod drew a picture, and how this project draws it back: the display list, the model programs, materials, the chassis, the rest pose, whole maps. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Where this is going - the windows, the seams, the networking, and which decisions evidence has already settled. Also answers how the game actually played. |
| [FALSE-TRAILS.md](FALSE-TRAILS.md) | **Every wrong turn that cost real time, and what killed it.** |
| [UNRESOLVED.md](UNRESOLVED.md) | **What is assumed, what is measured and unexplained, and what is papered over.** |
| [DEVICES.md](DEVICES.md) also carries the **mission interpreter**: the 162-opcode bytecode machine the pod runs its scenarios on. |
| [SOURCES.md](SOURCES.md) | **The paper trail: what the published manuals and patents contain, and what they do not.** |
| [PLAN.md](PLAN.md) | The original field notes, kept as written. |

The [changelog](../CHANGELOG.md) is the narrative in order; the
[roadmap](../ROADMAP.md) is what is next.

## Why the last two files exist

A project like this generates two kinds of knowledge that normally evaporate.

The first is **negative results**. Six ways of reaching the operator console's
message strings, all empty, is a day's work whose only product is knowing not to
try those six again. Written down it is worth something; left in a terminal
scrollback it gets paid for twice.

The second is **the difference between knowing and assuming**. Almost everything
here was recovered by inference, and inference that goes unlabelled hardens into
fact by repetition. `SecCom 674 bytes` sat in four documents as a decimal byte
count for months because it read plausibly; it is hexadecimal, and 1,652.
UNRESOLVED.md exists so that every load-bearing assumption has to say out loud
what it is and what would settle it.

## House rules for these documents

- **Say which it is.** Measured, inferred, or assumed - and if inferred, from
  what.
- **Keep the negative results.** "Looked for X, it is not there" is a finding.
- **Quote the machine.** The firmware's own strings, the console's own log, the
  manual's own words. They outrank any reasoning here.
- **When a claim turns out wrong, correct it in place and say so**, rather than
  quietly editing. The commit log and FALSE-TRAILS.md carry the record.
- **Nothing from the release is committed** - no code, no data, no assets, no
  renders. See the repository rules.
