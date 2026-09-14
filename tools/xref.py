#!/usr/bin/env python3
"""Find where a 68k image references a string.

The cockpit ROM narrates itself, so the fastest way to find the code behind a
console message is to locate the message and then the instruction that points
at it. Handles the PC-relative forms a THINK/MPW-era compiler emits plus plain
absolute-long operands.

usage: xref.py <image> <load-address-hex> <text> [...]
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


def main(argv):
    if len(argv) < 4:
        sys.exit(__doc__)
    data = open(argv[1], "rb").read()
    base = int(argv[2], 16)
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
