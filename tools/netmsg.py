#!/usr/bin/env python3
"""The wire format of the cockpit's network messages, read off the senders.

The operator console's log gives every message a name and a field list, but a
`printf` cannot say how wide a field goes out or in what order. The senders
can: each builds its packet in a stack buffer with a run of `move` stores, then
hands (destination, length, buffer, priority) to the packet sender at
`0x021468A4`. Reading those stores back out gives the layout.

This finds every call site, walks backwards to the function's opcode byte, and
reports the payload length and each store into the buffer as an offset, a width
and where the value came from.

usage: netmsg.py <ROM3_0> [--base HEX] [--send HEX]
       netmsg.py --selftest
"""
import struct
import sys

SEND = 0x021468A4
BASE = 0x020FFFE4
RECV = 0x0213CF2C      # the game's byte-0 dispatch

# move.<sz> <src>, (d16,A6), by the two opcode bytes that precede the
# displacements. The A6 destination is what makes it a buffer store.
SIZE = {0x1D: 1, 0x3D: 2, 0x2D: 4}
SRC = {
    0x7C: "imm",       # move.<sz> #imm, (d16,A6)
    0x68: "(d16,A0)",  # move.<sz> (d16,A0), (d16,A6)
    0x50: "(A0)",
    0x40: "D0",
    0x41: "D1",
    0x6E: "(d16,A6)",
    0x51: "(A1)",
    0x69: "(d16,A1)",
}


def stores(data, base, start, end, buf):
    """Buffer stores in [start,end), as (offset, width, source).

    A store of `(A0)` says nothing on its own: the compiler loads the
    function's argument into A0 and then walks it with `adda.l #imm`, so the
    field it means is the running displacement. Both are tracked here, which
    turns most of a message body into offsets in the caller's structure.
    """
    out = []
    a0 = None                       # running (name, displacement) for A0
    i = start - base
    while i < end - base:
        hi, lo = data[i], data[i + 1]
        w16 = (hi << 8) | lo
        if w16 == 0x206E:           # movea.l (d16,A6), A0
            a0 = ("arg%+d" % struct.unpack(">h", data[i + 2:i + 4])[0], 0)
            i += 4
            continue
        if w16 == 0xD1FC:           # adda.l #imm, A0
            if a0:
                a0 = (a0[0], a0[1] + struct.unpack(">I", data[i + 2:i + 6])[0])
            i += 6
            continue
        if w16 in (0x2050, 0x2068, 0x2248, 0x2448):
            pass                    # other A0 uses; leave the tracking alone
        if hi in SIZE and lo in SRC:
            w = SIZE[hi]
            j = i + 2
            if lo == 0x7C:
                imm = 2 if w < 4 else 4
                val = int.from_bytes(data[j:j + imm], "big")
                src = "#%0*X" % (w * 2, val & ((1 << (w * 8)) - 1))
                j += imm
            elif lo in (0x68, 0x6E, 0x69):
                reg = {0x68: "A0", 0x6E: "A6", 0x69: "A1"}[lo]
                d16 = struct.unpack(">h", data[j:j + 2])[0]
                if lo == 0x68 and a0:
                    src = "%s+%X" % (a0[0], a0[1] + d16)
                else:
                    src = "(%+d,%s)" % (d16, reg)
                j += 2
            else:
                src = SRC[lo]
                if lo == 0x50 and a0:
                    src = "%s+%X" % a0
            d = struct.unpack(">h", data[j:j + 2])[0]
            j += 2
            if buf is not None and d >= buf:
                out.append((d - buf, w, src))
            i = j
            continue
        i += 2
    return out


def sites(data, base, send=SEND):
    out = []
    for i in range(0, len(data) - 5, 2):
        op = (data[i] << 8) | data[i + 1]
        if op == 0x4EB9 and struct.unpack(">I", data[i + 2:i + 6])[0] == send:
            out.append(base + i)
        elif op == 0x4EBA and base + i + 2 + struct.unpack(">h", data[i + 2:i + 4])[0] == send:
            out.append(base + i)
    return out


def call_args(data, base, site):
    """The `pea $len.w` and `pea (d16,A6)` pushed just before the call."""
    length = bufd = None
    i = site - base
    for j in range(i, max(-2, i - 0x40), -2):
        op = (data[j] << 8) | data[j + 1]
        if op == 0x4878 and length is None:
            length = struct.unpack(">H", data[j + 2:j + 4])[0]
        elif op == 0x486E and bufd is None:
            bufd = struct.unpack(">h", data[j + 2:j + 4])[0]
    return length, bufd


def opcode_store(data, base, site, back=0x400):
    """The nearest preceding `move.b #imm,(d16,A6)`: the opcode into buf[0]."""
    i = site - base
    for j in range(i, max(-2, i - back), -2):
        if data[j] == 0x1D and data[j + 1] == 0x7C and data[j + 2] == 0x00:
            return data[j + 3], base + j, struct.unpack(">h", data[j + 4:j + 6])[0]
    return None, None, None


def report(data, base, send=SEND):
    for site in sites(data, base, send):
        length, bufd = call_args(data, base, site)
        op, at, opd = opcode_store(data, base, site)
        if op is None or bufd is None or opd != bufd:
            print("%08X  (no opcode store found)" % site)
            continue
        print("%02X  sender %08X..%08X  payload %s" %
              (op, at, site, "%d" % length if length else "?"))
        for off, w, src in stores(data, base, at, site, bufd):
            print("      +%02X  %s  %s" % (off, "bwl"[w >> 1], src))


def unpack(data, base, start, end):
    """Packet-to-structure copies in a receive handler.

    A handler holds the packet in one stack slot and the entity it names in
    another, and copies fields across with the same five-instruction idiom
    every time: load a slot into A0, walk it with `adda.l`, load the other slot
    into A1, walk that, `move` through both. Tracking the two registers turns
    the idiom back into a pair of offsets.

    Yields (src slot, src offset, dst slot, dst offset, width).
    """
    reg = {}                     # 0 -> A0, 1 -> A1, as (slot, offset)
    out = []
    i = start - base
    while i < end - base:
        w = (data[i] << 8) | data[i + 1]
        if w in (0x206E, 0x226E):            # movea.l (d16,A6), A0/A1
            reg[(w >> 9) & 1] = [struct.unpack(">h", data[i + 2:i + 4])[0], 0]
            i += 4
            continue
        if w in (0xD1FC, 0xD3FC):            # adda.l #imm, A0/A1
            r = 0 if w == 0xD1FC else 1
            if r in reg:
                reg[r][1] += struct.unpack(">I", data[i + 2:i + 6])[0]
            i += 6
            continue
        if w in (0x2290, 0x3290, 0x1290):    # move.<sz> (A0), (A1)
            if 0 in reg and 1 in reg:
                out.append(tuple(reg[0]) + tuple(reg[1]) +
                           ({0x2290: 4, 0x3290: 2, 0x1290: 1}[w],))
            i += 2
            continue
        if w in (0x2368, 0x3368, 0x1368):    # move.<sz> (d16,A0), (d16,A1)
            if 0 in reg and 1 in reg:
                ds = struct.unpack(">h", data[i + 2:i + 4])[0]
                dd = struct.unpack(">h", data[i + 4:i + 6])[0]
                out.append((reg[0][0], reg[0][1] + ds,
                            reg[1][0], reg[1][1] + dd,
                            {0x2368: 4, 0x3368: 2, 0x1368: 1}[w]))
            i += 6
            continue
        if w in (0x2088, 0x3089, 0x1089):    # move.<sz> A1/(A1), (A0)
            i += 2
            continue
        if w == 0x4E75:
            break
        i += 2
    return out


def packet_slot(data, base, start):
    """The stack slot a handler keeps the packet in.

    Every handler opens the same way: the event is the argument, and the packet
    is the longword at its `+0x10`. A handler that copies between two different
    objects has more than one slot in play, so knowing which one is the packet
    is what keeps their fields apart.
    """
    i = start - base
    for j in range(i, i + 0x20, 2):
        if (data[j] << 8 | data[j + 1]) == 0x2D68 and            struct.unpack(">h", data[j + 2:j + 4])[0] == 0x10:
            return struct.unpack(">h", data[j + 4:j + 6])[0]
    return None


def recv_fields(data, base, start, end):
    """(packet offset, structure offset, width) for one handler."""
    slot = packet_slot(data, base, start)
    if slot is None:
        return []
    return [(o0, o1, w) for s0, o0, s1, o1, w in unpack(data, base, start, end)
            if s0 == slot]


def table(data, base, send=SEND):
    """opcode -> [(sender head, payload length)]."""
    out = {}
    for site in sites(data, base, send):
        length, bufd = call_args(data, base, site)
        op, at, opd = opcode_store(data, base, site)
        if op is None or bufd is None or opd != bufd:
            continue
        out.setdefault(op, []).append((at, length))
    return out


def receivers(data, base, at=RECV):
    """opcode -> handler address, read out of the dispatch rather than typed in.

    The dispatch is the compiler's standard dense switch: subtract the first
    case, reject anything past the count, double, index a table of 16-bit
    offsets and jump relative to the instruction after the index. Every operand
    it needs is in those seven instructions.
    """
    i = at - base
    assert data[i] == 0x04 and data[i + 1] == 0x40, "not a subi.w at %08X" % at
    first = struct.unpack(">H", data[i + 2:i + 4])[0]
    assert data[i + 4] == 0x0C and data[i + 5] == 0x40, "not a cmpi.w"
    count = struct.unpack(">H", data[i + 6:i + 8])[0]
    j = i + 8
    while not (data[j] == 0x41 and data[j + 1] == 0xFA):   # lea (d16,PC), A0
        j += 2
    tbl = base + j + 2 + struct.unpack(">h", data[j + 2:j + 4])[0]
    while not (data[j] == 0x4E and data[j + 1] == 0xFB):   # jmp (PC,D0.w)
        j += 2
    origin = base + j + 2
    out = {}
    for k in range(count):
        v = struct.unpack(">h", data[tbl - base + 2 * k:tbl - base + 2 * k + 2])[0]
        t = origin + v
        if t != base + i + 0x18:                   # the shared "drop it" exit
            out[first + k] = t
    return out


def fields(data, base, send=SEND, recv=RECV, quiet=False):
    """Every message's fields, from both ends, and the structure behind them."""
    r = receivers(data, base, recv)
    heads = sorted(set(r.values()))
    snd = table(data, base, send)
    st = sites(data, base, send)
    agree = disagree = extra = 0
    ent = {}
    for op in sorted(r):
        h = r[op]
        k = heads.index(h)
        end = heads[k + 1] if k + 1 < len(heads) else h + 0x300
        fs = recv_fields(data, base, h, end)
        if not fs:
            continue
        want = {}
        if op in snd:
            at, _ = snd[op][0]
            site = [x for x in st if x > at][0]
            bd = call_args(data, base, site)[1]
            for off, _w, src in stores(data, base, at, site, bd):
                if src.startswith("arg+8+"):
                    want[off] = int(src.rsplit("+", 1)[1], 16)
        parts = []
        seen = set()
        for o0, o1, w in fs:
            ent.setdefault(o1, set()).add(op)
            mark = ""
            if o0 in want:
                if want[o0] == o1:
                    agree += 1
                    seen.add(o0)
                    mark = "="
                elif o0 in seen:
                    # The same packet field written to a second place. The
                    # sender only reads one of them, so this is a broadcast
                    # into sibling records, not a contradiction: `0xDD` puts
                    # packet+0x40 into six fields 0x18 apart.
                    extra += 1
                    mark = "*"
                else:
                    disagree += 1
                    mark = "!"
            parts.append("+%02X>%X%s" % (o0, o1, mark))
        if not quiet:
            print("%02X  %s" % (op, " ".join(parts)))
    if not quiet:
        print()
    print("field pairs confirmed by both ends: %d" % agree)
    print("packet fields broadcast to sibling records: %d" % extra)
    print("field pairs the two ends disagree on: %d" % disagree)
    print("distinct structure offsets: %d" % len(ent))
    if not quiet:
        print("  " + " ".join("%X" % o for o in sorted(ent)))


def check(data, base, send=SEND):
    """Countable facts, for the conformance harness."""
    t = table(data, base, send)
    r = receivers(data, base)
    print("call sites found: %d" % len(sites(data, base, send)))
    print("opcodes the dispatch handles: %d" % len(r))
    print("distinct handlers: %d" % len(set(r.values())))
    print("opcodes the pod sends: %d" % len(t))
    print("senders with a payload length: %d" %
          sum(1 for v in t.values() for _, ln in v if ln))
    # Every message the pod sends is one of the 71 the receiver's table covers.
    print("sent opcodes inside B9..FF: %d" %
          sum(1 for op in t if 0xB9 <= op <= 0xFF))
    # ROUTER_STATUS_MSG: a 100-byte packet whose body is an 80-byte string
    # followed by a longword. No other message the pod sends has that shape.
    fields(data, base, send, quiet=True)
    c5 = t.get(0xC5, [])
    st = []
    if c5:
        at, ln = c5[0]
        site = [s for s in sites(data, base, send) if s > at][0]
        st = stores(data, base, at, site, -0x64)
        print("C5 payload bytes: %d" % ln)
        print("C5 stores after the string: %s" %
              " ".join("+%02X" % o for o, _, _ in st if o))


def selftest():
    # move.b #$e1,(-$28,A6); move.l (6,A0),(-$20,A6); pea $28.w; pea (-$28,A6);
    # jsr SEND
    code = (b"\x1d\x7c\x00\xe1\xff\xd8"
            b"\x2d\x68\x00\x06\xff\xe0"
            b"\x48\x78\x00\x28"
            b"\x48\x6e\xff\xd8"
            b"\x4e\xb9" + struct.pack(">I", SEND))
    base = 0x1000
    s = sites(code, base)
    assert s == [base + 20], s
    assert call_args(code, base, s[0]) == (0x28, -0x28)
    op, at, opd = opcode_store(code, base, s[0])
    assert (op, at, opd) == (0xE1, base, -0x28)
    st = stores(code, base, at, s[0], -0x28)
    assert st == [(0, 1, "#E1"), (8, 4, "(+6,A0)")], st  # no A0 loaded yet
    # A0 tracking: movea.l (8,A6),A0; adda.l #$26,A0; move.l (A0),(-$20,A6)
    code2 = bytes([0x20, 0x6E, 0x00, 0x08,
                   0xD1, 0xFC, 0x00, 0x00, 0x00, 0x26,
                   0x2D, 0x50, 0xFF, 0xE0])
    got = stores(code2, 0, 0, len(code2), -0x28)
    assert got == [(8, 4, "arg+8+26")], got
    print("netmsg selftest ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2:
        sys.exit(__doc__)
    base, send = BASE, SEND
    if "--base" in argv:
        base = int(argv[argv.index("--base") + 1], 16)
    if "--send" in argv:
        send = int(argv[argv.index("--send") + 1], 16)
    data = open(argv[1], "rb").read()
    if "--check" in argv:
        return check(data, base, send)
    if "--fields" in argv:
        return fields(data, base, send)
    report(data, base, send)


if __name__ == "__main__":
    main(sys.argv)
