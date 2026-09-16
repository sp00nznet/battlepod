#!/usr/bin/env python3
"""Read the cockpit ROM's vehicle and weapon tables.

`Game Files/Vehicle_List` names 38 vehicles and numbers them. The cockpit ROM
carries the same 38 as fixed records, and each one is a complete statement of
what a BattleMech is to this game: which skeleton to draw it on, what every
hit location is called and how much armour it has, and what it is carrying.

The layout was read off the records themselves - the names are in ASCII, so
the string fields locate the array, and the array's stride locates everything
else - and then checked against something outside the ROM. A spreadsheet in the
release, `New mechs and VTV`, lists the loadouts of MadCat V4, MadCat V5 and
Thor V7 in words. Decoding those three records has to produce those three
loadouts, weapon for weapon and round for round, and it does. `--selftest`
keeps it that way.

  vehicle record, 958 bytes
    +0x00  name, 40 bytes, NUL padded
    +0x28  u16   the skeleton's resource id in the TI archive
    +0x32  u16   how many hit locations follow
    +0x34  f32 x 12   the first is top speed in kph; the rest are not identified
    +0x64  the hit locations, 34 bytes each
             +0x00  name, 24 bytes
             +0x18  u16  armour
             +0x1a  u16  internal structure
             +0x1c  u16 x2  the two sub-part ids the pick query returns
    then twelve weapon slots of 12 bytes, ending exactly at the record's end
             +0x00  u16  index into the weapon table, or 0xFFFF for an empty bay
             +0x02  u16  unidentified, 2 throughout
             +0x04  u16  rounds carried, or 0xFFFF for an energy weapon
             +0x06  u16 x3  unidentified; the first pairs launchers off against
                            each other and the last tracks the ammo type

  weapon record, 60 bytes, 20 of them at 0x7D018
    +0x00  name, 24 bytes          +38  u32  range in metres
    +25    short name for the HUD  +46  f32  heat
    +34    u32  damage             +56  u32  1 direct fire, 2 missiles
  The numeric fields are not longword aligned, which the 68020 does not mind.

usage:
  vehicles.py <ROM3_0>              the roster, one line each
  vehicles.py <ROM3_0> --id N       one vehicle in full
  vehicles.py <ROM3_0> --weapons    the weapon table
  vehicles.py --selftest
"""
import struct
import sys

VEHICLES, VSTRIDE, NVEHICLES = 0x70582, 958, 38
WEAPONS, WSTRIDE, NWEAPONS = 0x7D018, 60, 20
LOCATIONS, LSTRIDE = 0x64, 34
NSLOTS, SSTRIDE = 12, 12
EMPTY = 0xFFFF


def text(b):
    return b.split(b"\0")[0].decode("latin1")


def weapons(rom):
    out = []
    for i in range(NWEAPONS):
        r = rom[WEAPONS + i * WSTRIDE:WEAPONS + (i + 1) * WSTRIDE]
        out.append((text(r[:24]), text(r[25:36]),
                    struct.unpack_from(">I", r, 34)[0],
                    struct.unpack_from(">I", r, 38)[0],
                    struct.unpack_from(">f", r, 46)[0],
                    struct.unpack_from(">I", r, 56)[0]))
    return out


class Vehicle(object):
    def __init__(self, rec):
        self.rec = rec
        self.name = text(rec[:40])
        self.skeleton = struct.unpack_from(">H", rec, 0x28)[0]
        self.nloc = struct.unpack_from(">H", rec, 0x32)[0]
        self.speed = struct.unpack_from(">f", rec, 0x34)[0]
        self.loc = []
        for i in range(self.nloc):
            o = LOCATIONS + i * LSTRIDE
            self.loc.append((text(rec[o:o + 24]),
                             struct.unpack_from(">H", rec, o + 0x18)[0],
                             struct.unpack_from(">H", rec, o + 0x1A)[0],
                             struct.unpack_from(">2H", rec, o + 0x1C)))
        self.slots = []
        base = LOCATIONS + self.nloc * LSTRIDE
        for i in range(NSLOTS):
            o = base + i * SSTRIDE
            if o + SSTRIDE > len(rec):
                break
            f = struct.unpack_from(">6H", rec, o)
            if f[0] != EMPTY:
                self.slots.append(f)

    def sane(self):
        """A record we have read correctly: the locations fit inside it with
        room for the slots, and every one of them is named."""
        base = LOCATIONS + self.nloc * LSTRIDE
        return (self.name != "" and 400 <= self.skeleton <= 600
                and base + NSLOTS * SSTRIDE == len(self.rec)
                and all(n for n, _, _, _ in self.loc))


def roster(rom):
    return [Vehicle(rom[VEHICLES + i * VSTRIDE:VEHICLES + (i + 1) * VSTRIDE])
            for i in range(NVEHICLES)]


def carries(v, wt):
    """What a vehicle is armed with, as the release's own spreadsheet writes
    it: a weapon name and, for anything that needs reloading, a round count."""
    out = []
    for f in v.slots:
        name = wt[f[0]][0]
        out.append(name if f[2] == EMPTY else "%s (%d)" % (name, f[2]))
    return sorted(out)


def show(v, wt):
    print("%s" % v.name)
    print("  skeleton %d, top speed %.0f kph, %d hit locations"
          % (v.skeleton, v.speed, v.nloc))
    for name, armour, struc, parts in v.loc:
        print("    %-24s armour %-6d structure %-6d sub-parts %d,%d"
              % (name, armour, struc, parts[0], parts[1]))
    for f in v.slots:
        print("    %-26s %-10s %s"
              % (wt[f[0]][0], "-" if f[2] == EMPTY else "%d rounds" % f[2],
                 " ".join("%d" % x for x in (f[1], f[3], f[4], f[5]))))


# The three loadouts the release writes out in words, in `New mechs and VTV`.
ORACLE = {
    "MadCat V4": ["100 mm Auto Fire Cannon (15)", "Long Range Missile 5 pk (24)",
                  "Long Range Missile 5 pk (24)", "Machine Guns (300)",
                  "Medium Laser", "Short Range Missile 6 pk (15)",
                  "Short Range Missile 6 pk (15)"],
    "Madcat V5": ["ER Large Laser", "Gauss Rifle (16)",
                  "Long Range Missile 10 pk (24)", "Long Range Missile 10 pk (24)",
                  "Medium Laser", "Medium Laser"],
    "THOR V7": ["100 mm Auto Fire Cannon (15)", "ER Large Laser",
                "ER Medium Laser", "ER Medium Laser", "ER Small Laser",
                "Long Range Missile 5 pk (24)", "Medium Laser", "Medium Laser",
                "Short Range Missile 2 pk (50)", "Short Range Missile 4 pk (24)",
                "Small Laser"],
}


def check(rom):
    wt, rs = weapons(rom), roster(rom)
    ok = sum(v.sane() for v in rs)
    chassis = sorted(set(v.skeleton for v in rs))
    print("%d vehicle records, %d decode cleanly" % (len(rs), ok))
    print("%d chassis: %s" % (len(chassis), " ".join(str(c) for c in chassis)))
    print("%d weapons, %d named" % (len(wt), sum(1 for w in wt if w[0])))
    names = full = 0
    for v in rs:
        if v.name not in ORACLE:
            continue
        got, want = carries(v, wt), ORACLE[v.name]
        bare = lambda xs: sorted(x.split(" (")[0] for x in xs)
        names += bare(got) == bare(want)
        full += got == want
        print("  %-12s %2d weapons, names %s, rounds %s"
              % (v.name, len(got),
                 "match" if bare(got) == bare(want) else "DIFFER",
                 "match" if got == want else "differ"))
        for a, b in zip(got, want):
            if a != b:
                print("       rom says %-32s the spreadsheet says %s" % (a, b))
    print("")
    print("vehicle records that decode : %d" % ok)
    print("chassis in the vehicle table: %d" % len(chassis))
    print("weapons named               : %d" % sum(1 for w in wt if w[0]))
    print("loadouts matching by name   : %d" % names)
    print("loadouts matching in full   : %d" % full)
    return ok, len(chassis), names, full


def selftest():
    """Build a record here rather than only ever reading ones we are still
    learning to read."""
    nloc = 21                   # fixed: 100 + 21*34 + 12*12 is exactly 958
    rec = bytearray(VSTRIDE)
    rec[0:4] = b"Test"
    struct.pack_into(">H", rec, 0x28, 454)
    struct.pack_into(">H", rec, 0x32, nloc)
    struct.pack_into(">f", rec, 0x34, 97.0)
    for i in range(nloc):
        o = LOCATIONS + i * LSTRIDE
        name = (b"Left Foot", b"Hips")[i] if i < 2 else b"part %d" % i
        rec[o:o + len(name)] = name
        struct.pack_into(">2H2H", rec, o + 0x18, 5000, 3000, 2 * i, 2 * i + 1)
    base = LOCATIONS + nloc * LSTRIDE
    for i in range(NSLOTS):
        struct.pack_into(">6H", rec, base + i * SSTRIDE, EMPTY, 2, EMPTY, 0, 0, 0)
    struct.pack_into(">6H", rec, base, 19, 2, 16, 0, 0, 0)          # Gauss, 16
    struct.pack_into(">6H", rec, base + SSTRIDE, 2, 2, EMPTY, 0, 0, 0)

    v = Vehicle(bytes(rec))
    assert v.sane(), "a record we built has to decode"
    assert v.name == "Test" and v.skeleton == 454 and v.nloc == 21
    assert abs(v.speed - 97.0) < 1e-6
    assert v.loc[1] == ("Hips", 5000, 3000, (2, 3)), v.loc[1]
    assert len(v.slots) == 2, v.slots

    wt = [("w%d" % i, "", 0, 0, 0.0, 1) for i in range(NWEAPONS)]
    assert carries(v, wt) == ["w19 (16)", "w2"], carries(v, wt)

    # A record whose location count does not leave room for the slots is a
    # misread, not a vehicle, and has to say so rather than return junk.
    struct.pack_into(">H", rec, 0x32, 22)
    assert not Vehicle(bytes(rec)).sane()
    print("selftest: ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2:
        sys.exit(__doc__)
    rom = open(argv[1], "rb").read()
    wt = weapons(rom)
    if "--weapons" in argv:
        print("%-24s %-12s %6s %7s %6s  %s"
              % ("weapon", "on the hud", "damage", "range", "heat", "fire"))
        for name, short, dmg, rng, heat, kind in wt:
            print("%-24s %-12s %6d %7d %6.1f  %s"
                  % (name, short, dmg, rng, heat,
                     "missile" if kind == 2 else "direct"))
        return
    if "--id" in argv:
        want = int(argv[argv.index("--id") + 1])
        return show(roster(rom)[want], wt)
    if "--check" in argv:
        return check(rom)
    for i, v in enumerate(roster(rom)):
        print("%3d  %-18s skeleton %d  %3.0f kph  %2d locations  %s"
              % (i, v.name, v.skeleton, v.speed, v.nloc,
                 ", ".join(carries(v, wt))))


if __name__ == "__main__":
    main(sys.argv)
