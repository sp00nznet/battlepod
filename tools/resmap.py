#!/usr/bin/env python3
"""Walk a cockpit resource archive.

The firmware builds its resource map by reading a flat sequence of 16-byte
headers, each optionally followed by its data, terminated by a header whose id
is -1. The layout below is taken from that parser (ROM3_0 at 0x0214D0AC), not
guessed:

    +0x00  u32   resource id      - the numbers the firmware prints per type
    +0x04  u32   type class       - 1, 2, 4 or 7 in the 13.1.8 archives
    +0x08  u32   flags            - bit 4 of its low byte marks an alias
    +0x0C  u32   count, or the id this resource is an alias for

When bit 4 is set the resource carries no data of its own and +0x0C names
another resource instead; otherwise +0x0C is a count and count*4 bytes of data
follow the header.

usage:
  resmap.py <resource file>              summary by type
  resmap.py <resource file> --list       every resource
  resmap.py <resource file> --dump ID    hex and float view of one resource
"""
import struct
import sys

HEADER = 16
ALIAS = 0x10                # bit 4 of the flags byte at +0x0B


def walk(blob):
    """Yield (offset, id, type, flags, count, data) for every resource."""
    at = 0
    while at + HEADER <= len(blob):
        rid, rtype, flags, count = struct.unpack(">IIII", blob[at:at + HEADER])
        if rid == 0xFFFFFFFF:
            return
        inline = 0 if (flags & 0xFF) & ALIAS else count * 4
        yield at, rid, rtype, flags, count, blob[at + HEADER:at + HEADER + inline]
        at += HEADER + inline


def aliases(items):
    """Resolve every alias and report what it points at."""
    by_id = {rid: (rtype, len(d)) for _, rid, rtype, _, _, d in items}
    rows = [(rid, count) for _, rid, _, flags, count, _ in items if (flags & 0xFF) & ALIAS]
    if not rows:
        return
    bad = [r for r, tgt in rows if tgt not in by_id]
    print("\naliases: %d, %d resolve" % (len(rows), len(rows) - len(bad)))
    seen = {}
    for _, tgt in rows:
        if tgt in by_id:
            seen[by_id[tgt][0]] = seen.get(by_id[tgt][0], 0) + 1
    print("  they point at: %s" % ", ".join("type %d x%d" % kv for kv in sorted(seen.items())))
    for rid, tgt in rows[:6]:
        t = by_id.get(tgt)
        print("  id %-4d -> id %-4d %s" %
              (rid, tgt, "(type %d, %d bytes)" % t if t else "MISSING"))


def bounds(items):
    """Type 1 carries an axis-aligned box and a bounding sphere; check them."""
    box = sphere = n = 0
    for _, _, rtype, _, _, d in items:
        if rtype != 1 or len(d) < 0x44:
            continue
        v = struct.unpack(">7f", d[0x24:0x40])
        n += 1
        if v[0] <= v[1] and v[2] <= v[3] and v[4] <= v[5]:
            box += 1
        corner = sum(max(abs(v[i]), abs(v[i + 1])) ** 2 for i in (0, 2, 4)) ** 0.5
        if v[6] <= corner * 1.005:
            sphere += 1
    if n:
        print("\ntype 1 geometry header (floats at +0x24):")
        print("  min <= max on all three axes: %d of %d" % (box, n))
        print("  7th float <= box-corner distance: %d of %d  (a bounding sphere)"
              % (sphere, n))


def summary(items):
    by_type = {}
    for _, rid, rtype, _, count, data in items:
        t = by_type.setdefault(rtype, {"n": 0, "ids": [], "bytes": 0, "counts": []})
        t["n"] += 1
        t["ids"].append(rid)
        t["bytes"] += len(data)
        t["counts"].append(count)
    print("%5s %6s %10s %10s  %s" % ("type", "count", "bytes", "avg", "id range"))
    for rtype in sorted(by_type):
        t = by_type[rtype]
        ids = sorted(t["ids"])
        print("%5d %6d %10d %10d  %d-%d" %
              (rtype, t["n"], t["bytes"], t["bytes"] // max(1, t["n"]),
               ids[0], ids[-1]))
    return by_type


def looks_like_floats(data):
    """Fraction of longwords that read as plausible model-scale floats."""
    if len(data) < 64:
        return 0.0
    ok = n = 0
    for i in range(0, min(len(data), 4096) - 3, 4):
        v = struct.unpack(">f", data[i:i + 4])[0]
        n += 1
        if v == v and abs(v) != float("inf") and (v == 0.0 or 1e-4 < abs(v) < 1e6):
            ok += 1
    return ok / max(1, n)


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    blob = open(argv[1], "rb").read()
    items = list(walk(blob))
    consumed = sum(HEADER + len(d) for *_, d in items) + HEADER
    print("%s: %d bytes, %d resources, %d accounted for\n"
          % (argv[1].split("/")[-1], len(blob), len(items), consumed))

    if "--dump" in argv:
        want = int(argv[argv.index("--dump") + 1])
        for at, rid, rtype, flags, count, data in items:
            if rid != want:
                continue
            print("id %d type %d flags %08X count %d, %d bytes at +%06X"
                  % (rid, rtype, flags, count, len(data), at))
            for i in range(0, min(len(data), 128), 16):
                row = data[i:i + 16]
                fl = " ".join("%9.3f" % struct.unpack(">f", row[j:j + 4])[0]
                              for j in range(0, len(row) - 3, 4))
                print("  %04X  %-32s  %s" % (i, row.hex(), fl))
            return
        print("no resource %d" % want)
        return

    if "--list" in argv:
        print("%6s %5s %10s %8s %6s" % ("id", "type", "flags", "count", "bytes"))
        for _, rid, rtype, flags, count, data in items:
            print("%6d %5d %10X %8d %6d" % (rid, rtype, flags, count, len(data)))
        return

    by_type = summary(items)
    aliases(items)
    bounds(items)
    print("\nhow much of each type reads as plausible floats:")
    for rtype in sorted(by_type):
        samples = [d for _, _, t, _, _, d in items if t == rtype and len(d) > 64][:12]
        if not samples:
            print("  type %d: no inline data" % rtype)
            continue
        avg = sum(looks_like_floats(d) for d in samples) / len(samples)
        print("  type %d: %.0f%%" % (rtype, avg * 100))


if __name__ == "__main__":
    main(sys.argv)
