# The games this cabinet ran

The pod is remembered as a BattleTech machine, and the release is labelled
BattleTech, but the ROM carries the scripts for **three game modes across two
titles** and picks between them at boot.

Everything below is read out of the firmware. Nothing here is from a magazine
or a memory; the source for each claim is the code or the strings, and
`tools/mission_dis.py --strings` reprints the strings from any copy of the
release.

## How the choice is made

Missions are bytecode routines behind a table of named entry points, and the
name lookup walks whatever table `[0x0216F49C]` holds. That word is written
exactly once per boot, by `0x0211786C`:

```
02117874  tst.l  $21b74b2.l
0211787C  lea    $216c8ea.l, A0      Red Planet / Martian Football
02117882  move.l A0, $216f49c.l
0211788A  lea    $216b378.l, A0      BattleTech
02117890  move.l A0, $216f49c.l
```

So `[0x021B74B2]` is the title selector, and the two tables are:

| | address | routines |
|---|---|---|
| BattleTech | `0x0216B378` | 13 |
| Red Planet / Martian Football | `0x0216C8EA` | 18 |

Both are read by the same interpreter, in the same bytecode, with the same
instruction set. A pod is not built for one game; it is told which one to be.

Each mode stamps a build string into its own title screen, and the three are
consecutive:

| mode | build string |
|---|---|
| BattleTech | `VGL Universe 34933` |
| Red Planet | `VGL Universe 34934` |
| Martian Football | `VGL Universe 34934a` |

Martian Football's is a *suffix* of Red Planet's, and its title line is
`Red Planet / Martian Football` rather than a name of its own - so it is a mode
of Red Planet, not a third title.

---

## BattleTech

Table `0x0216B378`. Thirteen routines: two scenarios, eight follow-cockpit
cameras, three displays.

```
B1_BattleTech_1  B2_BattleTech_2  exitScreen
FC1..FC8_Follow_Cockp
T1_Nose_Only_1   T2_Camera_Only_1
```

A deathmatch. The scoreboard counts `%1d kills` and `%1d deaths`, the summary
screen is headed `STATS (kills/deaths)`, and the running score prints as
`%2d/%3d`.

Views the script can name:

```
Cockpit view   Shoulder view   Ground cam   Rear quadrant   Map view
('NoseCam')    (Cameras only)
```

Other text: `Pilot`, `Vehicle`, `Speed %1d`, `Transition at T - %0t`.

## Red Planet

Table `0x0216C8EA`, routines `R1_Red_Planet_1` and `R2_Red_Planet_2` with
their exits `rp1Exit` and `rp2Exit`.

A scored race, not a fight. The HUD carries `Score %1d`,
`Scoring zones: %1d`, `%1d KPH` and a `Leader Board`; the exit screens print
`Leader is %0n %0L` and `%0n %0L is last`.

The two scenarios differ in which end of the field they celebrate:

| routine | exit camera |
|---|---|
| `R1_Red_Planet_1` | `*Winner-Cam*` |
| `R2_Red_Planet_2` | `*Loser-Cam*` |

The whole thing is dressed as a broadcast: `Live from Red Planet`.

## Martian Football

Table `0x0216C8EA`, routines `F1_Martian_Footb` and `F2_Martian_Footb` with
`mfExit`. Same vehicles, same speed readout, same camera set as Red Planet -
and a team sport on top of it.

```
(No team)   Red Team   Blue Team
Position:   Runner   Blocker   Crusher   ?
Blockers    Crushers
```

Two teams, three roles. `Runner` is the one who scores; `Blocker` and
`Crusher` are the two ways of stopping them, and the HUD shows how many of each
are on the field. A player's line reads `%*1n (%*1v)` - name and vehicle - with
`(No team)` for anyone unassigned and `???` on the exit screen for a position
it cannot name.

Caption: `Martian Football: live from Red Planet`.

---

## Where the text comes out

All of it is printed by one routine, `0x0211A89A`, which mission opcode `0x0A`
calls with a format string it pops off the typed stack. A conversion is `%`,
an optional `*`, a digit and a letter:

* the digit is a **slot number** into the roster, clamped to 0..19;
* `*` means take the slot number from the float argument at that index instead,
  truncated to an integer;
* the letter chooses the field.

| letter | prints |
|---|---|
| `N` `n` | the slot's first name |
| `V` `v` | the slot's vehicle |
| `L` `l` | the slot's last name |
| `D` `d` | an integer |
| `F` `f` | a float |
| `T` `t` | a time |

So `%*0n %*0L` is "the first and last name of whoever argument 0 names", which
is how one script serves every seat in a linked cabinet.

The roster is **20 slots of 30 bytes** at mission record `+0x1CE4`, with the
first name at `+0x08`, the vehicle at `+0x0C` and the last name at `+0x10`.
Twenty is the clamp, and twenty is how many players these games were built to
carry.

On a pod booted by this project the roster is entirely zero - which is why
`%1d deaths` formats into a space and the word `deaths` with nothing between
them. See [UNRESOLVED.md](UNRESOLVED.md).
