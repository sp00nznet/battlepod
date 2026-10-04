# Contributing

Issues and pull requests are welcome: a decode that is wrong, a device that
behaves differently from what [DEVICES.md](docs/DEVICES.md) says, a scenario
that doesn't start, or a fix to any of it.

## Before you open a pull request

- `make && make test` passes. If you have the release, so does
  `make conformance VWE_GAME_FILES=...`, and the pass count in the README
  and the CHANGELOG's `Unreleased` section moves with your change.
- Say how you know. This project runs on evidence: a bus trace, the
  firmware's own console output, a routine you followed. A claim that rests
  on an assumption goes in [UNRESOLVED.md](docs/UNRESOLVED.md) as one, and a
  trail that turned out wrong goes in [FALSE-TRAILS.md](docs/FALSE-TRAILS.md).
- One change per pull request, with a commit message that says why.

## No VWE material

Nothing from the release goes in the repository, in any form: no ROM or
resource bytes, no extracted models, images or sounds, no disassembly
listings, no dumps, and no test fixtures built from any of them. Short
sequences quoted in the docs as evidence for a specific claim are the
exception, and only that. If your change needs the release to test, it reads
it from `VWE_GAME_FILES` at run time and skips with a message without it.

## Where your code comes from

battlepod is MIT. Contributions must be your own work or under a licence
compatible with MIT, and you need to be able to say which.

The live risk is a fix carried over from a GPL project, which would relicense
this one by accident and is very hard to untangle afterwards. The projects
you are most likely to have open alongside this one are GPL:

- **MAME** (GPL-2.0-or-later for the project as a whole), including its
  68000-family, TMS340x0 and ADSP-21xx cores
- **[WarlockD/Battletech-VME-3.0-Decompile](https://github.com/WarlockD/Battletech-VME-3.0-Decompile)**
  (GPL-3.0), the other public work on this hardware

Reading them to understand a part is fine; part numbers and facts are not
copyrightable, and the README credits that repository for the ones it found
first. Copying or closely translating their code is not. If something you
want to submit came from anywhere other than your own head, say where in the
pull request.

[Musashi](https://github.com/kstenerud/Musashi), the 68k core this builds
on, is MIT and is fetched by `make deps`, not vendored.

## A note on AI-assisted contributions

Pull requests written with an AI assistant are welcome, on the same terms as
any other: a human has read the change, understands it, has run it, and can
answer for it. "The model said so" is not evidence for a hardware claim.
