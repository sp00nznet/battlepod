#!/usr/bin/env python3
"""Turn a scenario file into the packets the console would send to build it.

The console's log starts a game with "Reset world", "Creating vehicles" and
"Downloading Map", and the pod receives all three through one message: `0xE4`
in the game's byte-0 table, whose handler at `0x0213CF5E` switches on the class
at packet `+0x0E` (class -1 resets the arena) and writes the thing it builds
into the arena slot named by `+0x12`. The fields each class reads, from its arm
and the initialiser it calls:

    +0x08  word   owner
    +0x0A  long   OR'd into Thing_Flags
    +0x0E  long   class
    +0x12  long   thing number, the arena slot
    +0x16  float  x        +0x1A  float  y        +0x1E  float  z
    +0x22  long   shape: a type 1 model id

    class 2   +0x26 long, +0x2A scale, +0x2E heading   (0x02115BE6)
    class 3   +0x26 scale, +0x2A heading               (0x0214BF0E)
    class 6   +0x2A heading                            (0x0212BBDE)

A scenario line is `class shape x y z heading scale` and then one integer for
classes 3 and 6, two for class 2. Where those trailing integers go is a guess:
the last one is sent as the flags, and class 2's first as its +0x26 long.

usage: mapsend.py <scenario> [--first N] [--range R] [--limit N]
         [--near X Y RADIUS]

Prints one packet per line, hex, for battlepod's --packet-file: an 0xE5 that
gives the pod a visibility range of R (default 500) in each half, then one
0xE4 per map object numbered from N (default 11 - things 1 to 10 are the
vehicles in the console's log). --near keeps only objects within RADIUS of
(X, Y), which keeps a run short.
"""
import struct
import sys

GROUND, TERRAIN_A, TERRAIN_B = 2, 3, 6


def objects(path):
    """Yield (class, shape, x, y, z, heading, scale, extras) for each object."""
    text = open(path, "rb").read().decode("mac-roman", "replace")
    for line in text.replace("\r", "\n").split("\n"):
        f = line.split()
        if len(f) < 8:
            continue
        try:
            cls = int(f[0])
        except ValueError:
            continue
        if cls not in (GROUND, TERRAIN_A, TERRAIN_B):
            continue
        yield (cls, int(f[1]), float(f[2]), float(f[3]), float(f[4]),
               float(f[5]), float(f[6]), [int(v) for v in f[7:]])


def packet(op, length, fields):
    b = bytearray(length)
    b[0] = op
    for off, fmt, val in fields:
        struct.pack_into(fmt, b, off, val)
    return " ".join("%02X" % x for x in b)


def welcome(visibility):
    return packet(0xE5, 0x60, [(0x3C, ">l", 600000),
                               (0x44, ">l", visibility),
                               (0x48, ">l", visibility)])


def reset_world():
    """The console's "Reset world": an 0xE4 of class -1, sent after the welcome
    and before any vehicle. Its arm (0x0213CF72) clears the game's state and
    picks the environment - sky, haze, light - from the table at 0x02179A10
    (or 0x02179B9C under a 600 range), indexed by the welcome's +0x40. Without
    it the pod keeps the bay's environment, whose sky is not in the archive."""
    return packet(0xE4, 0x40, [(0x0E, ">l", -1)])


def create(thing, cls, shape, x, y, z, heading, scale, extras):
    f = [(0x0A, ">l", extras[-1] if extras else 0),
         (0x0E, ">l", cls), (0x12, ">l", thing),
         (0x16, ">f", x), (0x1A, ">f", y), (0x1E, ">f", z),
         (0x22, ">l", shape)]
    if cls == GROUND:
        f += [(0x26, ">l", extras[0] if len(extras) > 1 else 0),
              (0x2A, ">f", scale), (0x2E, ">f", heading)]
    elif cls == TERRAIN_A:
        f += [(0x26, ">f", scale), (0x2A, ">f", heading)]
    else:
        f += [(0x2A, ">f", heading)]
    return packet(0xE4, 0x40, f)


def selftest():
    p = create(20, 3, 132, 8000.0, 8060.0, 0.0, 180.0, 1.0, [8]).split()
    assert p[0] == "E4" and len(p) == 0x40
    assert p[0x0E:0x12] == ["00", "00", "00", "03"]
    assert p[0x12:0x16] == ["00", "00", "00", "14"]
    assert p[0x16:0x1A] == ["45", "FA", "00", "00"]
    assert p[0x22:0x26] == ["00", "00", "00", "84"]
    assert p[0x26:0x2A] == ["3F", "80", "00", "00"]      # scale
    assert p[0x2A:0x2E] == ["43", "34", "00", "00"]      # heading 180
    r = reset_world().split()
    assert r[0] == "E4" and r[0x0E:0x12] == ["FF", "FF", "FF", "FF"]
    w = welcome(500).split()
    assert w[0x44:0x48] == ["00", "00", "01", "F4"]
    print("mapsend selftest OK")


def main(argv):
    if len(argv) > 1 and argv[1] == "--selftest":
        selftest()
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 1
    first, visibility, limit, near = 11, 500, None, None
    i = 2
    while i < len(argv):
        if argv[i] == "--first":
            first = int(argv[i + 1]); i += 2
        elif argv[i] == "--range":
            visibility = int(argv[i + 1]); i += 2
        elif argv[i] == "--limit":
            limit = int(argv[i + 1]); i += 2
        elif argv[i] == "--near":
            near = tuple(float(v) for v in argv[i + 1:i + 4]); i += 4
        else:
            print("unknown option %s" % argv[i], file=sys.stderr)
            return 1
    print("# " + argv[1].replace("\\", "/").split("/")[-1])
    print(welcome(visibility))
    print(reset_world())
    thing = first
    for o in objects(argv[1]):
        if near and (o[2] - near[0]) ** 2 + (o[3] - near[1]) ** 2 > near[2] ** 2:
            continue
        if limit is not None and thing - first >= limit:
            break
        print(create(thing, *o))
        thing += 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
