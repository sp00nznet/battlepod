#!/usr/bin/env python3
"""Disassemble the cockpit's mission bytecode.

The missions are programs for a 162-opcode interpreter in the ROM (see
`tools/missions.py` for the routine table and DEVICES.md for the machine). To
read one you need two things: where a routine starts, and how many operand
bytes each opcode takes.

Both come out of the ROM rather than out of a guess.

**Where a routine starts.** `0x021186FC` walks the table comparing names, and
on a match reads the entry's 16-bit value and *adds the table's own address*.
So the program counter is `table + offset`, and the name table sits at the
front of the blob it indexes.

**How long an instruction is.** Every handler that takes an operand begins by
stepping the interpreter's program counter, and that step is one instruction:
`addq.l #1,(-$10e,A6)`. Counting those in a handler, up to the `bra` back to
the fetch loop, gives the operand length - measured from the handler rather
than assumed from a table someone typed in.

usage: mission_dis.py <ROM3_0> [NAME] [--base HEX] [--limit N]
       mission_dis.py --lengths <ROM3_0>
       mission_dis.py --selftest
"""
import struct
import sys

BASE = 0x020FFFE4
TABLE = 0x0216B378          # the routine table, and the bytecode's own base
DISPATCH = 0x02119762       # the 162-entry jump table
JUMP_ORIGIN = 0x021198BA    # what its offsets are relative to
BAD_OPCODE = 0x0211972E     # the arm that reports an unknown opcode
NOPCODE = 162

STEP_PC = b"\x52\xae\xfe\xf2"   # addq.l #1,(-$10e,A6)
PUSH_PC = b"\x48\x6e\xfe\xf2"   # pea (-$10e,A6)
READ16 = 0x0211995C             # reads a big-endian 16-bit operand, advancing
BRA_W = 0x6000                  # bra with a 16-bit displacement


def handlers(data, base=BASE, dispatch=DISPATCH):
    """opcode -> handler address, or None for the unknown-opcode arm."""
    out = []
    at = dispatch - base
    for k in range(NOPCODE):
        v = struct.unpack(">h", data[at + 2 * k:at + 2 * k + 2])[0]
        t = JUMP_ORIGIN + v
        out.append(None if t == BAD_OPCODE else t)
    return out


def operand_len(data, handler, base=BASE, span=0x80):
    """How many operand bytes an opcode takes, counted from its handler."""
    if handler is None:
        return 0
    at = handler - base
    end = min(at + span, len(data) - 4)
    n = 0
    i = at
    while i < end:
        if data[i:i + 4] == STEP_PC:
            n += 1                      # one byte, stepped by hand
            i += 4
            continue
        if data[i:i + 4] == PUSH_PC:
            # An arm that hands the program counter to the 16-bit reader takes
            # a two-byte operand. Counting only the byte steps missed those,
            # and the disassembly ran off the rails at the first one.
            j = i + 4
            w = (data[j] << 8) | data[j + 1]
            if w == 0x4EB9 and struct.unpack(">I", data[j + 2:j + 6])[0] == READ16:
                n += 2
                i = j + 6
                continue
            if w == 0x4EBA and \
               base + j + 2 + struct.unpack(">h", data[j + 2:j + 4])[0] == READ16:
                n += 2
                i = j + 4
                continue
        # the arm ends with a branch back to the fetch loop
        if (data[i] << 8 | data[i + 1]) == BRA_W:
            break
        i += 2
    return n


def touches_pc(data, handler, base=BASE, span=0x80):
    """Does this arm change the program counter by something it read?

    Stepping it by one is how an operand is consumed; anything else is control
    flow. `0x42` turned out to be a jump whose two-byte operand is a signed
    displacement, and nothing in the operand-length rule could have told us.
    """
    if handler is None:
        return False
    at = handler - base
    for i in range(at, min(at + span, len(data) - 4), 2):
        if data[i:i + 4] == STEP_PC:
            continue                    # consuming an operand, not jumping
        if data[i + 2] == 0xFE and data[i + 3] == 0xF2:
            w = (data[i] << 8) | data[i + 1]
            # Only a *write* to the program counter is control flow. Reading it
            # - `movea.l (-$10e,A6),A0`, `pea (-$10e,A6)` - is how every
            # ordinary operand-taking arm starts, and counting those as jumps
            # marked three quarters of the instruction set as branches.
            if (w & 0xFF00) == 0x2D00 or (w & 0xF0FF) == 0x50AE or \
               (w & 0xF1FF) in (0xD1AE, 0x91AE):
                return True
        if (data[i] << 8 | data[i + 1]) == BRA_W:
            break
    return False


def lengths(data, base=BASE):
    hs = handlers(data, base)
    return [operand_len(data, h, base) for h in hs], hs


def disassemble(data, entry, base=BASE, table=TABLE, limit=200):
    """Walk a routine from its entry offset, printing one line per opcode."""
    lens, hs = lengths(data, base)
    pc = table + entry
    for _ in range(limit):
        o = pc - base
        if not (0 <= o < len(data)):
            print("  %08X  out of the image" % pc)
            return
        op = data[o]
        if op >= NOPCODE or hs[op] is None:
            print("  %08X  %02X  <unknown>" % (pc, op))
            return
        n = lens[op]
        args = data[o + 1:o + 1 + n]
        note = ""
        if touches_pc(data, hs[op], base):
            note = "   jump"
            if n == 2:
                d16 = struct.unpack(">h", args)[0]
                note = "   jump %+d -> %08X" % (d16, pc + 1 + n + d16)
        print("  %08X  %02X%s%s" %
              (pc, op, "  " + " ".join("%02X" % b for b in args) if n else "",
               note))
        pc += 1 + n


def selftest():
    # a fabricated handler: two pc steps then a branch back
    blob = bytearray(0x200)
    blob[0x100:0x108] = STEP_PC + STEP_PC
    blob[0x108:0x10A] = b"\x60\x00"
    assert operand_len(bytes(blob), 0x100, 0) == 2
    blob[0x100:0x104] = b"\x60\x00"          # branch straight away
    assert operand_len(bytes(blob), 0x100, 0) == 0
    assert operand_len(bytes(blob), None, 0) == 0
    print("mission_dis selftest ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2:
        sys.exit(__doc__)
    base, table = BASE, TABLE
    if "--base" in argv:
        base = int(argv[argv.index("--base") + 1], 16)
    data = open(argv[1], "rb").read()
    if "--lengths" in argv:
        lens, hs = lengths(data, base)
        named = sum(1 for h in hs if h is not None)
        print("opcodes with a handler: %d" % named)
        print("opcodes that are control flow: %d" %
              sum(1 for h in hs if touches_pc(data, h, base)))
        for n in range(max(lens) + 1):
            print("  taking %d operand bytes: %d" %
                  (n, sum(1 for k, h in enumerate(hs) if h is not None and lens[k] == n)))
        return
    sys.path.insert(0, "tools")
    import missions
    rs = dict(missions.routines(data, base, table))
    want = [a for a in argv[2:] if not a.startswith("--")]
    name = want[0] if want else "B1_BattleTech_1"
    if name not in rs:
        sys.exit("no routine called %s; have %s" % (name, ", ".join(rs)))
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 40
    print("%s at %04X:" % (name, rs[name]))
    disassemble(data, rs[name], base, table, limit)


if __name__ == "__main__":
    main(sys.argv)
