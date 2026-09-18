#!/usr/bin/env python3
"""What strings does a function in the cockpit ROM mention?

Naming an unknown handler is mostly a matter of reading what it prints. The
firmware narrates itself, so a function's string references are usually enough
to say what it is for. This walks a function from its entry to its last `rts`
and reports every string it points at, by either form the compiler emits:
a PC-relative `pea`/`lea`, or an absolute long operand.

usage: fnstr.py <image> <text-base-hex> ADDR[:LIMIT] ...
       fnstr.py --selftest
"""
import struct
import sys

PCREL = {0x487A: "pea"}
for _r in range(8):
    PCREL[0x41FA | (_r << 9)] = "lea A%d" % _r

# The compiler ends a function with `unlk A6; rts` or a bare `rts`; the scan
# stops at the first `rts` that is not inside a jump table.
RTS = 0x4E75


def text_at(data, off, limit=120):
    """The C string at off, if it looks like one."""
    if off < 0 or off >= len(data):
        return None
    end = data.find(b"\0", off, off + limit)
    if end < 0:
        return None
    s = data[off:end]
    if len(s) < 3:
        return None
    if any(c < 0x20 or c > 0x7E for c in s):
        return None
    return s.decode("ascii")


def scan(data, base, start, limit=0x400):
    """String references in [start, start+limit), stopping at the first rts."""
    out = []
    off = start - base
    end = min(off + limit, len(data) - 4)
    i = off
    while i < end:
        op = (data[i] << 8) | data[i + 1]
        if op in PCREL:
            disp = struct.unpack(">h", data[i + 2:i + 4])[0]
            s = text_at(data, i + 2 + disp)
            if s:
                out.append((base + i, PCREL[op], s))
            i += 4
            continue
        if op == RTS:
            break
        val = struct.unpack(">I", data[i:i + 4])[0]
        s = text_at(data, val - base)
        if s:
            out.append((base + i, "long", s))
        i += 2
    return out


def calls(data, base, start, limit=0x400):
    """Absolute and PC-relative jsr targets in the same range."""
    out = []
    off = start - base
    end = min(off + limit, len(data) - 6)
    i = off
    while i < end:
        op = (data[i] << 8) | data[i + 1]
        if op == 0x4EB9:
            out.append(struct.unpack(">I", data[i + 2:i + 6])[0])
            i += 6
            continue
        if op == 0x4EBA:
            disp = struct.unpack(">h", data[i + 2:i + 4])[0]
            out.append(base + i + 2 + disp)
            i += 4
            continue
        if op == RTS:
            break
        i += 2
    return out


def selftest():
    # a tiny image: pea (d16,PC) pointing at a string, then rts
    body = bytearray(b"\x48\x7a\x00\x06" b"\x4e\x71" b"\x4e\x75")
    body += b"hello\0"
    data = bytes(body)
    got = scan(data, 0x1000, 0x1000)
    assert got == [(0x1000, "pea", "hello")], got
    assert calls(data, 0x1000, 0x1000) == []
    # a jsr absolute is picked up, and the scan stops at the rts
    data = b"\x4e\xb9\x00\x12\x34\x56" b"\x4e\x75"
    assert calls(data, 0, 0) == [0x123456]
    print("fnstr selftest ok")


def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        return selftest()
    if len(argv) < 4:
        sys.exit(__doc__)
    data = open(argv[1], "rb").read()
    base = int(argv[2], 16)
    for spec in argv[3:]:
        addr, _, lim = spec.partition(":")
        addr = int(addr, 16)
        lim = int(lim, 16) if lim else 0x400
        print("%08X" % addr)
        for a, how, s in scan(data, base, addr, lim):
            print("    %08X  %-6s %r" % (a, how, s))
        cs = calls(data, base, addr, lim)
        if cs:
            print("    calls: " + " ".join("%08X" % c for c in cs))


if __name__ == "__main__":
    main(sys.argv)
