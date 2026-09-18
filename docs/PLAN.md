# battlepod — Virtual World Entertainment pod revival

Field notes + plan. Scratch document, not a deliverable. Nothing here goes into a public
repo before the licensing section is settled.

Source data: https://archive.org/details/vwe-release-13.1.8 (VWE Release 13.1.8, 1996)

---

## 1. What the dump actually is

Two `.sit` archives. **Identical contents** — 85 entries each; one is a StuffIt 4.5
re-stuff of the other for compatibility. Extracted with `unar` (The Unarchiver CLI,
Windows build) to `_dump/`; 398 files, 37 MB, resource forks preserved as AppleDouble
`.rsrc` sidecars.

```
VWE Release 13.1.8/
  VWE Center Kit/Mac Files/2.5-3.0 Related Files/VWE Release 13.1.8/
    BattleTech 13.1.8/     <- the current release
    Red Planet 13.1.8/     <- same engine, VWE-original IP
    BTMR 960312/           <- BattleTech Mission Review 6.0.15f1
    RPMR 2.4.1/            <- Red Planet Mission Review
    13.1.8 BT Notes        <- 317 KB of dev/ops release notes (Word)
  Server Archives/Outgoing Software/
    BattleTech 13.1.7/     <- previous release + Console 1.5.12.a01 (OpsCon app)
    Red Planet 13.1.5/
```

Archive.org's warning is wrong on one point: this is **68k**, not PPC. `Console
1.5.12.a01` is `APPL`/`VW02` with 20 `CODE` resources (228 KB), plus `DATA`/`CREL`/`DREL`
and THINK Class Library UI resources — no `cfrg`, so no PowerPC fork. The Read Me
confirms: "Modified for compilation with THINK 7.0.4." It ran under 68k emulation on the
PowerMacs.

## 2. The hardware, established

From the VWE System 3.0 Technical Manual (archive.org OCR) cross-checked against the
binaries. Per cockpit, in the card cage:

| Board | Job | Software in the dump |
|---|---|---|
| **CPU** | main screen render + ARCNET + game sim. 68020 + 68881/2 (`FMOVEM` at ROM entry) | `ROM3_0` (534 KB raw 68k), `battletech_68020_res` |
| **"TI"** renderer | separate graphics processor, reset and started by the CPU board. **Identity unknown — no docs** | `R.BIN3_0` (28 KB, likely microcode), `battletech_ti_res` (1.5 MB, big-endian IEEE floats = geometry) |
| **Sound** | creation, mixing, amplification | `btAudio.dld` (989 KB), `.no_icom` variant |
| **"Secondary"** | **an actual Amiga 500 motherboard** on a VWE carrier, driving the secondary MFD screen | `Amiga3_0` (61 KB, Manx **Aztec C** 68k), `btsecond3_0` (145 KB) |
| **Remote I/O** | stick, throttle, pedals, keypad, lamps, LCDs, heat scale, bargraphs — serial "RIO protocol" | in `ROM3_0` |
| Backplane | power + inter-board data | — |

Eight cockpits plus camera ships per "side" on an **ARCNET** RG62 star hub. Each side has
one **OpsCon Macintosh** (PowerMac 6100/7100) holding the **A/ROSE ARCNET NuBus card**;
the Macs talk to each other over Ethernet/EtherTalk. `Dial_List` holds modem numbers for
inter-center play (HOU/ATL/OAK/SAN/DFW/LAS/LAX/CSM/YYZ/SAC plus the Chicago lab).

### The boot recipe is in plaintext

`Full_Load_3_0` is the entire pod memory map, nine lines:

```
ROM3_0                020FFFE4     BattleTech_TI_Res   02B00000
BattleTech_68020_Res  02AC0000     btAudio.dld         02D00000
R.BIN3_0              02AE0000     AMIGA3_0            400003E4   <- board-local 0x3E4
DEVELOPMENT           02FFFF00     btsecond3_0         40010400   <- board-local 0x10400
Go_Address            02100000
```

Each image carries a 0x1C-byte header (`60 1A` = `BRA.S +0x1A`, then size / checksum /
load address, then `JMP abs.l` to the real entry). `0x40000000` is the host window onto
the Amiga board's local address space. OpsCon does nothing clever here — it pushes these
files over ARCNET and says go.

### The gift: ROM3_0 has a built-in diagnostic monitor

`ROM3_0` embeds a serial-console menu, "BattleTech 2 Test Program":

```
k - Send reset to renderer (must be loaded)      s - Test remote I/O devices
y - START TEST GAME (starts Secondary, TI and 68020 in tandem)
i - RIO protocol loopback test                   2 - Test Lamps
e/f - I/O board serial port A read/write         4 - Test Heat Scale
a..d - real time clock tests                     5 - Test Bargraphs
"Starting TI, screen should clear"  /  "Starting Secondary"
```

The original engineers shipped the bring-up harness inside the image. Each subsystem can
be exercised in isolation, with printed narration. That is worth more than schematics.

Other `ROM3_0` strings worth noting: `Pre Dlist overflow!` / `Post Dlist Overflow` /
`Render List Overflow` — there is an explicit **display list** handed to the renderer.
`Interpreter error, bad opcode %02xh at offset 0x%04lx!` — there is a **bytecode VM**,
almost certainly running the compiled `Scenarios/*` map scripts.

## 3. Answering the three questions

**"Shims all the way down — can it run on Windows now?"**

No, and nothing is close. The blocker the community names — A/ROSE + ARCNET card
emulation — is the *wrong* blocker. Emulating the A/ROSE card gets the OpsCon UI running
under Basilisk II talking to nothing. **The game is not in the Mac.** The Mac is a file
server with a launch button. The real blocker is an undocumented custom 68020 board with
an unidentified graphics processor, no schematics, and no dump of the pod's own boot
monitor.

The upside of that same fact: **you do not need the Mac at all for v1.** Everything
OpsCon supplies is plaintext in the dump (`Game_Setup`, `Team_List`, `Vehicle_List`,
`Scenario_List`, `Net_Configuration`, the Load scripts). Synthesize the launch, skip that
whole layer.

**"Recomp toolkit, or emulate?"**

Interpret. Not recompile — at least not first.

- Static recompilation needs a known memory map to know which loads and stores are MMIO.
  We do not have one. Interpretation *produces* the map.
- Performance is irrelevant. This is a ~1996 68020.
- A 68020+68881 core already exists and is proven: Musashi (MAME), or Moira. Don't write
  one.
- Recomp stays available later, once the map is known and a standalone binary is wanted.
  It is not a v1 concern.

And the strategy is not "emulate the pod". It is **emulate the 68020 and HLE everything
else**. Never emulate the TI renderer — intercept the display list the ROM already builds
and draw it with a modern renderer. Same for audio, the MFDs, the RIO protocol, and
ARCNET.

**"Is it already on GitHub? Stars? Any C&D?"**

**Correction.** The original answer here was "zero relevant repos" — that was wrong.
The searches used (`battletech pod`, `battlepod`, `arose arcnet`, `virtual world
entertainment`, `tms34010 recompiler`) do not match the one repository that exists:
[WarlockD/Battletech-VME-3.0-Decompile](https://github.com/WarlockD/Battletech-VME-3.0-Decompile),
June 2024, 3 stars, one day of commits, no activity since.

It contains no decompilation. It is a dossier: the release, board photographs, and
datasheets for the parts its author identified, plus notes. It reaches the same load
map and the same renderer uncertainty as this project, and it names the ADSP-21020
sound DSP and the SMC COM90C66 ARCNET controller. Its author invites others to
continue.

So: no emulator precedent, no C&D precedent, and one friendly predecessor whose
research is worth using. It is GPL-3.0 and it redistributes the VWE material, so
nothing is copied from it here.

## 4. Licensing — the honest position

- **The copyright holder is alive and reachable.** Virtual World Entertainment LLC,
  Kalamazoo MI, run by Nickolas "PropWash" Smith (acquired 100% in Dec 2005), still
  operating Tesla II pods, running open pod nights and a Patreon. `PropWash@MechJock.Com`.
- **Trademarks:** BattleTech and MechWarrior are Topps + Microsoft, licensed to VWE. Red
  Planet is VWE-original with no third-party marks attached — **Red Planet is the cleaner
  flagship for screenshots and for the first public post.**
- **The upload is an invitation, not a license.** The Battletech Pod Preservation Project
  says it was "only given permission to post, in order to find a solution to the first
  issue" — the first issue being exactly this emulator. They asked for someone to build
  it. That is goodwill, not a grant.
- **MIT is correct and honest — on our code only.** The emulator, loader, and decoders
  are ours. No MIT header goes anywhere near VWE material, and the README says plainly
  that the tool ships and the data does not.
- **Never committed** (REPO_RULES §3, at full strength): `ROM*`, `R.BIN*`, `*_res`,
  `*.dld`, `Amiga*`, `btsecond*`, `Scenarios/*`, the Console/BTMR/RPMR apps and their
  resource forks, the release notes, `Console Log`, and the `Dial_List` phone numbers.
  `.gitignore` covers `_dump/` and the generated output directory explicitly. The README
  points at the archive.org item; the tool takes a path to the user's own extraction.
- **Repo starts private** (§1). Flipping public is its own deliberate decision, after the
  §1 checklist.
- **Recommendation: email PropWash before going public.** Not legally required, costs
  nothing, and a hostile rightsholder is the only thing that can kill this. The community
  around the v3 pods is the audience, and they already asked for this.

### One REPO_RULES conflict to settle

§3 bans "generated headers, symbol maps, or struct definitions reconstructed from
proprietary binaries." A hardware MMIO map observed by running the image is arguably that
category — but an emulator without a device map is not an emulator, and hand-written
device documentation is how MAME, Dolphin, and every other emulator project works.

**Recommendation:** treat an independently written, human-authored device table (our
names, our prose, derived from observed bus behaviour) as in scope and in repo, and keep
machine-generated artifacts out — raw MMIO trace CSVs, disassembly listings, symbol
dumps, decoded `_res` contents. Your rule, your call; flagging it before it bites.

## 5. Plan

Repo name `battlepod`. It is an emulator with heavy HLE, not a recomp, so it sits
alongside the `*recomp` family rather than claiming §9 house style — but it borrows §8's
conformance-harness shape.

**Phase 0 — Ground truth.** *The only phase that matters right now.*
Parse `Full_Load_*` and the 0x1C image header, place the images in a flat 64 MB space,
set PC to `Go_Address`. Drop in Musashi (68020 + 68881). Log every access outside RAM:
PC, address, size, R/W, value. Wire a stub serial console to whatever the ROM's console
I/O turns out to be, and drive the diagnostic menu one letter at a time. The menu is the
oracle — it labels each subsystem as it touches it.
**Output:** the pod's device map, and an answer to *what is the TI?* (a TMS340x0 host
interface is unmistakable: HSTADRL / HSTADRH / HSTDATA / HSTCTL.)

**Phase 1 — Boot to the test menu.** Success = the diagnostic menu prints. The
conformance harness starts here (§8): a fixed corpus of checkpoints — instructions
retired, menu text reached, each subsystem test's expected output — with a pass/fail
count in the README and CI failing on regression.

**Phase 2 — Display list capture.** Run `y - START TEST GAME`. Stub the TI so the CPU
believes it is alive; capture the Dlist buffers; decode `battletech_ti_res` (floats start
at offset 0x30). First screenshot: a wireframe Mad Cat.

**Phase 3 — Render + input.** Draw the Dlist properly. HLE the RIO protocol so a keyboard
or HOTAS drives stick, throttle, and pedals, and the lamp / bargraph / heat-scale outputs
land somewhere visible. Playable single-player.

**Phase 4 — Secondary screen + audio.** MFDs: HLE the command protocol over the
`0x40000000` window, or drop a minimal 68000 + OCS core in for the 61 KB Aztec C program.
Audio: decode `btAudio.dld`.

**Phase 5 — Network + OpsCon.** Only now does A/ROSE matter. HLE ARCNET over UDP for
8-pod games; OpsCon either runs under Basilisk II against a fake A/ROSE driver, or gets
reimplemented from its plaintext inputs.

**Skipped, deliberately:** static recompilation, cycle accuracy, emulating the real
renderer silicon, the Mac side, inter-center modem linking, Mission Review (BTMR/RPMR).
Add each when a phase actually blocks on it.

## 6. What could kill it

- **The renderer may do transform and lighting, not just rasterize.** Then `R.BIN`'s
  28 KB *is* the renderer and its ISA has to be understood. 28 KB is small enough to
  disassemble by hand once the part is identified — but identify it first.
- **The pod's real boot monitor is not in the dump.** `Full_Load` downloads the game image
  into a pod that already has ROM. If `ROM3_0` depends on monitor services set up before
  `Go_Address`, they have to be synthesized. The self-contained diagnostic menu suggests
  it may not — unconfirmed.
- **`_res` formats are undocumented.** Solvable, tedious.
- **Node-ID / ARCNET-tied checks.** The `DEVELOPMENT` flag at `0x02FFFF00` is in the dump
  and probably helps.

## 7. Next step

Phase 0 is roughly a day's work for someone who has built a 68k emulator before, and it
is the only thing that turns "three months or three years?" into an answer. Do that
before naming a repo, before emailing anyone, and before writing a line of renderer.
