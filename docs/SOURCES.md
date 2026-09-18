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

## The Mech Damage Heat Chart, and what it settles

`mech-damage-heat-chart` is three pages VWE printed for players: a weapon table
with damage, heat and a range ladder; one row per configuration with a count
per weapon; and the totals at 300, 600, 900 and 1200 metres. It is the only
account of this roster that did not come out of a cockpit, which is exactly
what makes it worth holding the ROM against.

**Every name on it is in the ROM.** All 33 configurations and all 20 weapons,
checked by the harness. And the five configurations the ROM has that the chart
does not are, by their own names, the ones that would not have been printed:

```
Explo Vulture, Loki Test DNU, MadCat V4, Madcat V5, THOR V7
```

- `Loki Test DNU` says so outright.
- `MadCat V4`, `Madcat V5` and `THOR V7` are the three the release's own
  `New mechs and VTV` spreadsheet writes out in words - that is, additions
  documented separately from the chart.

**It also names the ROM's `Drone`.** The chart has a `Loki V7` the ROM does
not, and the ROM has a `Drone` the chart does not. The chart's own arithmetic
settles it without needing to read a faint cell: `Loki V7` does 8.0 damage and
3.0 heat at 300 m but 4.0 damage and 1.0 heat at 600 m, and the only weapon in
the chart that is worth exactly 4.0/1.0 and still reaches 600 m is the `SRM 2`.
The 300 m difference, 4.0 damage and 2.0 heat, is two `LASER SM`. So `Loki V7`
carries one SRM 2 and two small lasers - which is precisely and uniquely what
the ROM's `Drone` carries.

### The numbers, though, are not this build's

The loadouts agree. The weapon values do not, and not by a scale factor:

| | chart damage | ROM | chart heat | ROM | chart range | ROM |
|---|---|---|---|---|---|---|
| `LASER MD` | 5.0 | 25 | 3.0 | 2.0 | 600 | 350 |
| `LASER LG` | 8.0 | 50 | 8.0 | 6.0 | 900 | 600 |
| `E PPC` | 17.0 | 75 | 15.0 | 16.0 | 1500 | 950 |
| `AFC 25` | 5.0 | 25 | 7.0 | 0.8 | 1200 | 900 |
| `LRM 15` | 15.0 | 75 | 5.0 | 6.5 | 6000 | 6000 |

Seven of the twenty are exactly five times the chart's damage and the rest are
not, so it is not a units difference. The missile ranges match and the energy
and ballistic ranges do not. **`ROM2_0`, `ROM2_5` and `ROM3_0` carry byte-for-byte
the same weapon table**, so the chart does not belong to an older cockpit in
this dump either. It is a different balance pass than any ROM here, and the
chart is evidence about the roster rather than about the numbers.

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
