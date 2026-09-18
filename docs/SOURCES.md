# The paper trail

What documentation exists for this machine, what each document actually
contains, and - the part that saves the most time - what it does **not**.

Everything here is on the Internet Archive, most of it under the
[BattleTech Pod Preservation Project](https://archive.org/details/@battletech_pod_preservation_project)
account. Nothing from any of it is copied into this repository.

## There is no board schematic

Checked, because it would settle several open questions at once and because it
is the obvious thing to hope for. **None of the published material is
board-level.** The three technical manuals are:

| | |
|---|---|
| `vwe-system-3.0-user-guide-and-technical-manual` (1995) | **Our machine.** Field service: which board to swap, what each front-plate connector is, cable labels, DIP switches, symptom tables. The "Parts List of Cockpit" is the mechanical assembly. No circuit diagrams, no part numbers for anything on a board. |
| `vwe-system-4.0-technical-manual` | **Not our machine.** System 4.0 is *Tesla* - "an Intel based Pentium PC equipped with cards to handle sound generation, network connection, and auxiliary video generation", with a Division graphics card. Its "Wire Schematics" section is cable runs between cabinets. |
| `virtual-world-battletech-system-1-operations-manual` (1990) | Operations, not hardware. |

The two patents on the account (`vwe-cockpit-patent-international-application`,
`vwe-polisher-patent`) are mechanical - the cockpit enclosure and a disc
polisher. The cockpit patent's text contains no occurrence of `68020`, `34020`,
`ADSP`, `Amiga`, `Arcnet` or `interrupt`.

So **the part at `0x00010007`-`0x00010015` cannot be named from the paper**.
Settling it needs a board photograph or a schematic that has not been scanned.

## What the System 3.0 manual *is* good for

It is a service manual written for someone standing in front of the cabinet,
and that turns out to be exactly the right altitude for questions about what
connects to what.

**The CPU board front plate** carries, top to bottom: an ejector handle, the
scan converter output (BNC, `Comm Main Video`, only present on cameraship
CPUs - the converter mounts on socket `J4`), an **8-position Node ID DIP
switch**, Main Video Out (DB9, VGA, drives the main screen), a **Reset
Button**, an **Interrupt Button**, the Remote I/O serial port, and the
**ARCNET BNC**.

Three of those are worth having in writing:

- **The node ID is a DIP switch**, switch 1 the least significant bit, and the
  manual is emphatic: "Without the proper DIP switch setting proper
  communication to and from this cockpit is rendered impossible." The firmware
  never writes `0x0218AEB0`/`B1` - 273,621 reads and no writes - so the node
  number reaches software from somewhere outside the game. The switch is the
  obvious candidate, read either by the boot monitor or by the ARCNET
  controller. **Which of the two is not settled here**; the `(net, node)` pair
  the game filters on is a logical address and an ARCNET node ID is a physical
  one, and nothing measured so far says they are the same number.
- **There is an interrupt button**, which "will force an interrupt on the CPU.
  This is used only under VWE supervision as a debugging tool." So one IRQ line
  on that board is a pushbutton.
- **The ARCNET controller is on the CPU board**, alongside the processor and
  the RAM - confirming where the LAN sits in the address map rather than
  leaving it to inference.

**The sound board** is "several Analog Devices ADSP's" with sample DRAM on
board, and it is also the amplifier, the mixer and the intercom. The manual
also says that when sound drops out, "sound is reestablished within 15 seconds
as the **software watchdog** will reactivate the audio channels" - which is the
manual's own word for a mechanism this project found independently in the
firmware, though the one found kicks a register every 100 ticks from
`Get_Event` and this one is about audio channels. They may or may not be the
same thing.

## Other material

- `vwe-release-13.1.8` - the software dump this whole project reads.
- `virtual-world-entertainment-press-kit-circa-1994` - marketing. Wrong about
  texture mapping; see FALSE-TRAILS.md.
- `vgl-battletech-3.0-data-supplement`, `mech-damage-heat-chart` - the game's
  own numbers as published to players, useful as an oracle against the ROM's
  vehicle table.
- `btc-brochure-lrg`, `battletech-center-north-pier-chicago`,
  `btc-japan-guide-book`, `battletech-center-posters` - period photographs,
  which is where cockpit interior reference comes from.
