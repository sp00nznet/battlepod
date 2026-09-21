#!/usr/bin/env python3
"""Find where a 68k image references a string, or calls a routine.

The cockpit ROM narrates itself, so the fastest way to find the code behind a
console message is to locate the message and then the instruction that points
at it. Handles the PC-relative forms a THINK/MPW-era compiler emits plus plain
absolute-long operands.

`--calls` answers the other question this project keeps asking: *who else does
this?* A routine with one caller is a routine whose behaviour is fully
explained by that caller; a routine with six is a shared service, and the six
are the list of ways into it. Both readings have mattered - `Create_Thing`
having exactly one caller is what pinned entity creation to the mission
interpreter, and that reading only survives if the search covered every way a
68k program can call something. It did not: a search that knows `jsr abs.l`
and forgets `bsr.b` under-reports, and under-reporting a caller list reads as
a finding.

usage: xref.py <image> <load-address-hex> <text> [...]
       xref.py <image> <load-address-hex> --calls <target-hex> [...]
       xref.py --selftest
"""
import struct
import sys

# opcode -> how it is written, for the (d16,PC) forms that carry a string pointer
PCREL = {0x487A: "pea (d16,PC)"}
for reg in range(8):
    PCREL[0x41FA | (reg << 9)] = "lea (d16,PC),A%d" % reg


def xrefs(data, base, target):
    hits = set()
    for i in range(0, len(data) - 4, 2):
        op = (data[i] << 8) | data[i + 1]
        if op in PCREL:
            disp = struct.unpack(">h", data[i + 2:i + 4])[0]
            if base + i + 2 + disp == target:
                hits.add((base + i, PCREL[op]))
    needle = struct.pack(">I", target)
    at = data.find(needle)
    while at >= 0:
        hits.add((base + at, "absolute long operand"))
        at = data.find(needle, at + 1)
    return sorted(hits)


# All four ways this compiler calls something, and the two ways it tail-jumps.
# `bsr.b` is the one that gets forgotten, because it is two bytes where the
# others are four and a scanner stepping by words walks straight over it.
def call_at(data, i, base):
    """(target, how) if a call or jump sits at offset `i`, else None."""
    if i + 4 > len(data):
        return None
    w = (data[i] << 8) | data[i + 1]
    if w in (0x4EB9, 0x4EF9):                               # jsr/jmp abs.l
        if i + 6 > len(data):
            return None
        return (struct.unpack(">I", data[i + 2:i + 6])[0],
                "jsr abs.l" if w == 0x4EB9 else "jmp abs.l")
    if w in (0x4EBA, 0x4EFA):                               # jsr/jmp (d16,PC)
        d = struct.unpack(">h", data[i + 2:i + 4])[0]
        return (base + i + 2 + d,
                "jsr (d16,PC)" if w == 0x4EBA else "jmp (d16,PC)")
    if w == 0x6100:                                         # bsr.w
        d = struct.unpack(">h", data[i + 2:i + 4])[0]
        return base + i + 2 + d, "bsr.w"
    if (w >> 8) == 0x61 and (w & 0xFF) not in (0x00, 0xFF):  # bsr.b
        d = struct.unpack(">b", data[i + 1:i + 2])[0]
        return base + i + 2 + d, "bsr.b"
    return None


def calls(data, base, target):
    """Every site that calls or jumps to `target`.

    This is a scan at every word boundary, not a disassembly, so a hit inside
    the middle of some other instruction is possible. Those are rare and loud -
    they sit nowhere near a routine's code - and the alternative is a full
    disassembly of half a megabyte to answer a question that takes a second.
    """
    hits = []
    for i in range(0, len(data) - 4, 2):
        c = call_at(data, i, base)
        if c and c[0] == target:
            hits.append((base + i, c[1]))
    return hits


def selftest():
    base = 0x1000
    # jsr abs.l, jsr (d16,PC), bsr.w and bsr.b all reaching 0x1000
    blob = (b"\x4e\xb9\x00\x00\x10\x00"          # 1000: jsr $1000
            b"\x4e\xba\xff\xf8"                  # 1006: jsr (-8,PC) -> 1000
            b"\x61\x00\xff\xf4"                  # 100A: bsr.w -> 1000
            b"\x61\xf0"                          # 100E: bsr.b -> 1000
            b"\x4e\x75\x00\x00")
    got = calls(blob, base, 0x1000)
    assert [a for a, _ in got] == [0x1000, 0x1006, 0x100A, 0x100E], got
    assert [h for _, h in got] == ["jsr abs.l", "jsr (d16,PC)", "bsr.w", "bsr.b"]
    assert calls(blob, base, 0x2000) == []
    # 0x6100 is bsr.w and 0x61FF is bsr.l; neither carries a byte displacement
    assert call_at(b"\x61\xff\x00\x00", 0, 0) is None
    assert call_at(b"\x4e\x75\x00\x00", 0, 0) is None
    # the string side still works
    s = b"\x41\xfa\x00\x04\x00\x00hello\x00"
    assert (base + 0, "lea (d16,PC),A0") in xrefs(s, base, base + 6)
    print("xref selftest ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 4:
        sys.exit(__doc__)
    data = open(argv[1], "rb").read()
    base = int(argv[2], 16)
    if argv[3] == "--calls":
        for t in argv[4:]:
            target = int(t, 16)
            hits = calls(data, base, target)
            print("%08X: %d call sites" % (target, len(hits)))
            for addr, how in hits:
                print("    %08X  %s" % (addr, how))
        return
    for text in argv[3:]:
        at = data.find(text.encode())
        if at < 0:
            print("%-44s not found" % text[:42])
            continue
        target = base + at
        print("%-44s file %06X  addr %08X" % (text[:42], at, target))
        for addr, how in xrefs(data, base, target):
            print("    %08X  %s" % (addr, how))


if __name__ == "__main__":
    main(sys.argv)
