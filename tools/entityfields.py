#!/usr/bin/env python3
"""Which bytes of an entity does each network message write?

The senders and the handlers were read statically, which covers the messages
that unpack with the compiler's plain copy idiom and misses the ones that do
arithmetic on the way in. This asks the firmware instead.

The method is a difference of two whole runs. Boot the cockpit once and dump
entity 1; boot it again with one packet injected at the wire and dump entity 1
again; whatever differs is what that message wrote. Both runs are
deterministic, so the difference is the message and nothing else.

The packet's body is a ramp - byte `n` holds the value `n` - so a longword that
lands in the entity carries its own packet offset with it, and the map comes
out of the dump rather than out of a reading of the code. The entity id has to
be real or the handler indexes the table with nonsense, so `+0x08` is forced to
1 in one variant and `+0x0C` in the other: those are the only two places a
message puts it.

usage: entityfields.py <Load_script> [--bin PATH] [--op HEX[,HEX...]]
                             [--class N]
       entityfields.py --selftest
"""
import re
import subprocess
import sys

ENTITY1 = 0x021FA060        # the arena is 0x021F99AC, stride 0x6B4
ESIZE = 0x6B4
PKTLEN = 0x60

BOOT = ["--duart", "11000", "--rstub", "3FF00000", "--monitor", "--astub",
        "--clock", "2000808", "--set", "40000100=1234567",
        "--steps", "60000000", "--top", "0"]

# Several handlers copy the three position fields and then switch on the
# entity's `+0x02`, so an entity left at the class the boot clears it to takes
# a do-nothing arm and the sweep sees almost nothing. `--class` writes a class
# in first. It has to be written while the pod runs, because the arena loop
# clears `+0x02` during init, and it has to be written at a PC *both* runs
# reach - `Get_Event`, not the packet dispatch - or the baseline and the
# injected run differ by the class itself.
CLASS_AT = "02122154"       # Get_Event, called every frame

ROW = re.compile(r"^  ([0-9A-F]{4})  ((?:[0-9A-F]{2} ?)+)\s*$")


def parse(text, at):
    """The bytes of a `--peek` block, as a list."""
    out = []
    want = "peek %08X:" % at
    seen = False
    for line in text.splitlines():
        if line.startswith(want):
            seen = True
            continue
        if not seen:
            continue
        m = ROW.match(line)
        if not m:
            break
        out += [int(x, 16) for x in m.group(2).split()]
    return out


def packet(op, idat):
    """A ramp body with the opcode in front and the entity id where it goes."""
    p = bytearray(range(PKTLEN))
    p[0] = op
    p[idat:idat + 4] = b"\x00\x00\x00\x01"
    return " ".join("%02X" % b for b in p)


def ranges(a, b):
    """Contiguous runs where two dumps differ, as (start, bytes)."""
    out = []
    i = 0
    while i < min(len(a), len(b)):
        if a[i] != b[i]:
            j = i
            while j < min(len(a), len(b)) and a[j] != b[j]:
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


CLEARED = -1


def source(b, off, n):
    """Where a changed run came from: a packet offset, CLEARED, or unknown.

    Zero is ambiguous - a byte the handler cleared and a byte copied from
    packet offset 0 look identical - so an all-zero run is reported as cleared
    and never attributed to the packet. `0xE8` is the case that matters: it
    zeroes the entity's class, which is a message that removes a thing, and
    reading that as "copied from packet+00" would have been wrong twice over.
    """
    if n < 1:
        return None
    if all(b[off + k] == 0 for k in range(n)):
        return CLEARED
    if b[off] >= PKTLEN:
        return None
    for k in range(1, n):
        if b[off + k] != b[off] + k:
            return None
    return b[off]


def run(binary, script, extra):
    p = subprocess.run([binary, script] + BOOT + extra,
                       capture_output=True, text=True)
    return p.stdout + p.stderr


def sweep(binary, script, ops, klass=None):
    pre = []
    if klass is not None:
        pre = ["--set-at", CLASS_AT, "%X=%08X" % (ENTITY1 + 2, klass)]
    base = parse(run(binary, script,
                     pre + ["--peek", "%08X:%d" % (ENTITY1, ESIZE)]),
                 ENTITY1)
    if len(base) != ESIZE:
        sys.exit("baseline dump is %d bytes, wanted %d" % (len(base), ESIZE))
    hits = 0
    for op in ops:
        best = []
        for idat in (8, 0x0C):
            out = run(binary, script,
                      pre + ["--packet", packet(op, idat),
                             "--peek", "%08X:%d" % (ENTITY1, ESIZE)])
            got = parse(out, ENTITY1)
            if len(got) != ESIZE:
                continue
            rs = ranges(base, got)
            if len(rs) > len(best):
                best, body = rs, got
        if not best:
            continue
        hits += 1
        total = sum(n for _, n in best)
        print("%02X  %d runs, %d bytes" % (op, len(best), total))
        for off, n in best:
            src = source(body, off, n)
            how = ("cleared" if src == CLEARED else
                   "from packet+%02X" % src if src is not None else "computed")
            print("      +%03X  %2d  %s" % (off, n, how))
    print("")
    print("opcodes that write the entity they name: %d" % hits)


def selftest():
    text = ("peek 021FA060:\n"
            "  0000  01 02 03 04\n"
            "  0010  05 06\n"
            "\n")
    assert parse(text, ENTITY1) == [1, 2, 3, 4, 5, 6], parse(text, ENTITY1)
    assert parse(text, 0x1234) == []
    assert ranges([1, 2, 3, 4], [1, 9, 9, 4]) == [(1, 2)]
    assert ranges([1, 2], [1, 2]) == []
    # a verbatim longword carries the offset it came from
    assert source([0, 0x0C, 0x0D, 0x0E, 0x0F], 1, 4) == 0x0C
    assert source([0, 0x0C, 0x0D, 0x00, 0x0F], 1, 4) is None
    # a cleared byte is not a byte copied from the front of the packet
    assert source([0x11, 0x00], 1, 1) == CLEARED
    assert source([0x11, 0x00, 0x00, 0x00, 0x00], 1, 4) == CLEARED
    p = packet(0xE1, 8).split()
    assert p[0] == "E1" and p[8:12] == ["00", "00", "00", "01"]
    assert p[0x0C] == "0C" and len(p) == PKTLEN
    print("entityfields selftest ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2:
        sys.exit(__doc__)
    binary = "./build/battlepod.exe"
    if "--bin" in argv:
        binary = argv[argv.index("--bin") + 1]
    if "--op" in argv:
        ops = [int(x, 16) for x in argv[argv.index("--op") + 1].split(",")]
    else:
        ops = list(range(0xB9, 0x100))
    klass = int(argv[argv.index("--class") + 1], 0) if "--class" in argv else None
    if klass is not None:
        print("entity 1 given class %d at its +0x02" % klass)
    sweep(binary, argv[1], ops, klass)


if __name__ == "__main__":
    main(sys.argv)
