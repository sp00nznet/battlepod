#!/usr/bin/env python3
"""The mission scripts, which are bytecode routines in the ROM.

The cockpit runs its missions on an interpreter - 162 opcodes, a fetch-decode
loop at `0x021188BE`, its own error messages naming it - and the programs are
not sent by the operator console. They are in the ROM's data, behind a table of
named entry points that `0x021186BC` looks a routine up in by name, truncating
the name at 16 characters.

The table is at `[0x0216F49C]`, and an entry is a NUL-terminated name followed
by a **big-endian 16-bit entry offset**. There is no count: the table simply
stops, which is why this reads until a name is not a name.

usage: missions.py <ROM3_0> [--base HEX] [--table HEX]
       missions.py --selftest
"""
import re
import struct
import sys

BASE = 0x020FFFE4
TABLE = 0x0216B378          # the value [0x0216F49C] holds on a booted pod

NAME = re.compile(rb"[A-Za-z0-9_]{2,16}\Z")


def routines(data, base=BASE, table=TABLE):
    """(name, entry offset) until the table stops looking like one."""
    out = []
    at = table - base
    while 0 <= at < len(data) - 3:
        end = data.find(b"\0", at)
        if end < 0 or end - at > 16:
            break
        name = data[at:end]
        if not NAME.match(name):
            break
        out.append((name.decode(), struct.unpack(">H", data[end + 1:end + 3])[0]))
        at = end + 3
    return out


def check(data, base=BASE, table=TABLE):
    rs = routines(data, base, table)
    print("mission routines named: %d" % len(rs))
    print("entry offsets ascending: %d" %
          all(rs[i][1] <= rs[i + 1][1] for i in range(len(rs) - 1)))
    names = [n for n, _ in rs]
    print("BattleTech scenarios: %d" % sum(1 for n in names if n.startswith("B")
                                           and "BattleTech" in n))
    print("follow-cockpit cameras: %d" % sum(1 for n in names
                                             if n.startswith("FC")))


def selftest():
    body = (b"A_One\0\x01\x23" b"B_Two\0\x04\x56" b"\x80\x81not a name\0")
    got = routines(body, 0, 0)
    assert got == [("A_One", 0x0123), ("B_Two", 0x0456)], got
    # a name longer than the interpreter's own 16-character limit ends it
    long = b"X" * 17 + b"\0\x00\x01"
    assert routines(long, 0, 0) == []
    assert routines(b"", 0, 0) == []
    print("missions selftest ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2:
        sys.exit(__doc__)
    base, table = BASE, TABLE
    if "--base" in argv:
        base = int(argv[argv.index("--base") + 1], 16)
    if "--table" in argv:
        table = int(argv[argv.index("--table") + 1], 16)
    data = open(argv[1], "rb").read()
    if "--check" in argv:
        return check(data, base, table)
    for name, off in routines(data, base, table):
        print("  %-18s %04X" % (name, off))


if __name__ == "__main__":
    main(sys.argv)
