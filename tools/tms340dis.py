#!/usr/bin/env python3
"""A TMS34010 disassembler, for reading the cockpit's renderer.

The 68020 never reads inside a model - it only walks the 16-byte resource
headers - so the geometry format is parsed entirely by the TMS340 code in
R.BIN. That code is 28 KB and is the only route to it.

Encodings follow the TMS34010 User's Guide (Texas Instruments, 1988). The
processor is little-endian in 16-bit words and its addresses are *bit*
addresses, so a byte at file offset n sits at bit address n*8.

Not every instruction is implemented; anything unrecognised prints as `.word`,
which keeps the stream in sync because an unknown opcode is still one word long.
The graphics group - PIXT, PIXBLT, FILL, LINE - and a few absolute MOVE forms
are the remaining gaps. They are left out rather than guessed: two opcodes were
tried as absolute moves, decoded to implausible addresses, and were removed.

The image holds data as well as code, so a linear disassembly can never reach
100%; the reported figures separate zero fill from genuine unknowns.

usage:
  tms340dis.py <file> [--base BITADDR] [--at BITADDR] [--count N] [--skip N]
"""
import struct
import sys

REG = ["A%d" % i for i in range(15)] + ["SP"]
REGB = ["B%d" % i for i in range(16)]


def regname(f, r):
    return (REGB if f else REG)[r]


# base opcode -> (mnemonic, class). Classes describe how the operands are
# packed into the low bits and what extension words follow.
NOARG = {
    0x0100: "EMU", 0x01C0: "POPST", 0x01E0: "PUSHST", 0x0300: "NOP",
    0x0320: "CLRC", 0x0360: "DINT", 0x0940: "RETI", 0x0D60: "EINT",
    0x0DE0: "SETC",
}
ONEREG = {
    0x0020: "REV", 0x0120: "EXGPC", 0x0140: "GETPC", 0x0180: "GETST",
    0x01A0: "PUTST", 0x0380: "ABS", 0x03A0: "NEG", 0x03C0: "NEGB",
    0x03E0: "NOT", 0x1020: "INC", 0x1420: "DEC", 0x0500: "SEXT",
    0x0520: "ZEXT",
}
TWOREG = {
    0x4000: "ADD", 0x4200: "ADDC", 0x4400: "SUB", 0x4600: "SUBB",
    0x4800: "CMP", 0x4C00: "MOVE", 0x4E00: "MOVE", 0x5000: "AND",
    0x5200: "ANDN", 0x5400: "OR", 0x5600: "XOR", 0x5800: "DIVS",
    0x5A00: "DIVU", 0x5C00: "MPYS", 0x5E00: "MPYU", 0x6A00: "LMO",
    0x6C00: "MODS", 0x6E00: "MODU", 0x1C00: "BTST", 0xE000: "ADDXY",
    0xE200: "SUBXY", 0xE400: "CMPXY", 0xE600: "CPW", 0xE800: "CVXYL",
    0xEC00: "MOVX", 0xEE00: "MOVY", 0xF600: "DRAV",
}
# immediate forms: long takes two extension words, short takes one
IMM_LONG = {0x09E0: "MOVI", 0x0B20: "ADDI", 0x0B60: "CMPI", 0x0D00: "SUBI"}
IMM_SHORT = {0x09C0: "MOVI", 0x0B00: "ADDI", 0x0B40: "CMPI", 0x0CE0: "SUBI"}
LIMREG = {0x0B80: "ANDNI", 0x0BA0: "ORI", 0x0BC0: "XORI"}
KREG = {0x1000: "ADDK", 0x1400: "SUBK", 0x1800: "MOVK",
        0x2000: "SLA", 0x2400: "SLL", 0x2800: "SRA", 0x2C00: "SRL",
        0x3000: "RL"}
JUMP_REL = {
    0xC000: "JRUC", 0xC100: "JRP", 0xC200: "JRLS", 0xC300: "JRHI",
    0xC400: "JRLT", 0xC500: "JRGE", 0xC600: "JRLE", 0xC700: "JRGT",
    0xC800: "JRLO", 0xC900: "JRHS", 0xCA00: "JREQ", 0xCB00: "JRNE",
    0xCC00: "JRV", 0xCD00: "JRNV", 0xCE00: "JRN", 0xCF00: "JRNN",
}
JUMP_ABS = {b | 0x80: n.replace("JR", "JA") for b, n in JUMP_REL.items()}


# Absolute-addressing moves, where a 32-bit bit-address follows the opcode.
#
# The scanned manual's table for this group is the least legible part of it and
# its load/store split contradicts what the firmware actually does, so the
# entries kept here are the ones confirmed against observed behaviour instead:
#
#   0x0780  every one of the seven writes to 0xFFFFFDE0 uses it, and that word
#           is the renderer state the 68020 polls - so it is a store
#   0x07A0  same family, used on 0xFFFFFDA0
#   0x0580  writes 0xC0000080 and 0xC0000110, the TMS34010's own I/O registers
#
# 0x0700 and 0x0740 were tried as loads, decoded to implausible addresses, and
# are left unrecognised. The rest of the 0x0400-0x07FF group stays unknown
# rather than being filled in from an OCR reading that does not hold up.
ABS_ONE = {
    0x0580: ("MOVB", "store"), 0x05A0: ("MOVB", "store"),
    0x0780: ("MOVE", "store"), 0x07A0: ("MOVE", "store"),
    0x07E0: ("MOVB", "load"),
}
ABS_TWO = {0x0340: "MOVB"}          # absolute to absolute, two addresses

# Register-indirect moves. The User's Guide gives these as `oooo ooFS SSSR DDDD`
# for MOVE - six opcode bits then a field-select bit - and `oooo oooS SSSR DDDD`
# for MOVB, which has no field select. Both put the source in bits 8-5, the
# register file in bit 4 and the destination in bits 3-0.
#   key: (base, mask) -> (mnemonic, source form, dest form, extension words)
IND = [
    (0x8000, 0xFC00, "MOVE", "Rs", "*Rd", 0),
    (0x8400, 0xFC00, "MOVE", "*Rs", "Rd", 0),
    (0x8C00, 0xFE00, "MOVB", "Rs", "*Rd", 0),
    (0x8E00, 0xFE00, "MOVB", "*Rs", "Rd", 0),
    (0x9000, 0xFC00, "MOVE", "Rs", "*Rd+", 0),
    (0x9400, 0xFC00, "MOVE", "*Rs+", "Rd", 0),
    (0x9C00, 0xFE00, "MOVB", "*Rs", "*Rd", 0),
    (0xA000, 0xFC00, "MOVE", "Rs", "-*Rd", 0),
    (0xA400, 0xFC00, "MOVE", "-*Rs", "Rd", 0),
    (0xAC00, 0xFE00, "MOVB", "Rs", "*Rd(o)", 1),
    (0xAE00, 0xFE00, "MOVB", "*Rs(o)", "Rd", 1),
    (0xB000, 0xFC00, "MOVE", "Rs", "*Rd(o)", 1),
    (0xB400, 0xFC00, "MOVE", "*Rs(o)", "Rd", 1),
    (0xB800, 0xFC00, "MOVE", "*Rs(o)", "*Rd(o)", 2),
    (0xBC00, 0xFE00, "MOVB", "*Rs(o)", "*Rd(o)", 2),
]
DSJ = {0x0D80: "DSJ", 0x0DA0: "DSJEQ", 0x0DC0: "DSJNE"}

# The graphics group. PIXT moves single pixels, in linear or XY addressing;
# PIXBLT and FILL take their operands from the B-file registers rather than the
# instruction, so they encode as bare opcodes.
PIXT = {
    0xF000: ("PIXT", "Rs", "*Rd.XY"), 0xF200: ("PIXT", "*Rs.XY", "Rd"),
    0xF400: ("PIXT", "*Rs.XY", "*Rd.XY"),
    0xF800: ("PIXT", "Rs", "*Rd"), 0xFA00: ("PIXT", "*Rs", "Rd"),
    0xFC00: ("PIXT", "*Rs", "*Rd"),
}
BARE = {
    0x0F00: "PIXBLT  L, L", 0x0F20: "PIXBLT  L, XY", 0x0F40: "PIXBLT  XY, L",
    0x0F60: "PIXBLT  XY, XY", 0x0F80: "PIXBLT  B, L", 0x0FA0: "PIXBLT  B, XY",
    0x0FC0: "FILL    L", 0x0FE0: "FILL    XY",
    0xDF1A: "LINE    0", 0xDF5A: "LINE    1",
}


class Stream:
    def __init__(self, blob, at):
        self.b = blob
        self.at = at            # word index

    def word(self):
        o = self.at * 2
        if o + 2 > len(self.b):
            raise IndexError
        self.at += 1
        return struct.unpack("<H", self.b[o:o + 2])[0]

    def long(self):
        lo = self.word()
        return lo | (self.word() << 16)


def decode(s):
    """Return (text, words consumed). Raises IndexError past the end."""
    start = s.at
    op = s.word()
    f, rd, rs = (op >> 4) & 1, op & 0xF, (op >> 5) & 0xF

    def done(text):
        return text, s.at - start

    if op in NOARG:
        return done(NOARG[op])
    if op in BARE:
        return done(BARE[op])
    if op & 0xFE00 in PIXT:
        m, sf, df = PIXT[op & 0xFE00]
        return done("%-7s %s, %s" % (m, sf.replace("Rs", regname(f, rs)),
                                     df.replace("Rd", regname(f, rd))))
    if op & 0xFFE0 in ONEREG:
        return done("%-7s %s" % (ONEREG[op & 0xFFE0], regname(f, rd)))
    if op & 0xFE00 in TWOREG:
        m = TWOREG[op & 0xFE00]
        if m == "XOR" and rs == rd:
            return done("%-7s %s" % ("CLR", regname(f, rd)))
        return done("%-7s %s, %s" % (m, regname(f, rs), regname(f, rd)))
    if op & 0xFFE0 in IMM_LONG:
        return done("%-7s #$%08X, %s" % (IMM_LONG[op & 0xFFE0], s.long(), regname(f, rd)))
    if op & 0xFFE0 in IMM_SHORT:
        return done("%-7s #$%04X, %s" % (IMM_SHORT[op & 0xFFE0], s.word(), regname(f, rd)))
    if op & 0xFFE0 in LIMREG:
        return done("%-7s #$%08X, %s" % (LIMREG[op & 0xFFE0], s.long(), regname(f, rd)))
    if op & 0xFC00 in KREG:
        k = (op >> 5) & 0x1F
        m = KREG[op & 0xFC00]
        if m in ("ADDK", "SUBK") and k == 0:
            k = 32
        return done("%-7s #%d, %s" % (m, k, regname(f, rd)))
    if op == 0x0D5F:
        return done("%-7s $%08X" % ("CALLA", s.long()))
    if op == 0x0D3F:
        d = s.word()
        return done("%-7s $%08X" % ("CALLR", (start + 2 + (d - 0x10000 if d & 0x8000 else d)) * 16))
    if op & 0xFFE0 == 0x0920:
        return done("%-7s %s" % ("CALL", regname(f, rd)))
    if op & 0xFFE0 == 0x0960:
        return done("%-7s %d" % ("RETS", op & 0x1F))
    if op & 0xFFE0 == 0x0900:
        return done("%-7s %d" % ("TRAP", op & 0x1F))
    if op & 0xFFE0 in (0x0980, 0x09A0):
        m = "MMTM" if (op & 0xFFE0) == 0x0980 else "MMFM"
        return done("%-7s %s, #$%04X" % (m, regname(f, rd), s.word()))
    if op & 0xFF00 in JUMP_ABS:
        return done("%-7s $%08X" % (JUMP_ABS[op & 0xFF00], s.long()))
    if op & 0xFF00 in JUMP_REL:
        m = JUMP_REL[op & 0xFF00]
        d = op & 0xFF
        if d == 0:
            d = s.word()
            off = d - 0x10000 if d & 0x8000 else d
        elif d == 0x80:
            return done("%-7s $%08X" % (m, s.long()))
        else:
            off = d - 0x100 if d & 0x80 else d
        return done("%-7s $%08X" % (m, (start + (s.at - start) + off) * 16))
    if op & 0xFFE0 in ABS_ONE:
        m, dirn = ABS_ONE[op & 0xFFE0]
        a = s.long()
        if dirn == "store":
            return done("%-7s %s, @$%08X" % (m, regname(f, rd), a))
        return done("%-7s @$%08X, %s" % (m, a, regname(f, rd)))
    if op & 0xFFE0 in DSJ:
        d = s.word()
        off = d - 0x10000 if d & 0x8000 else d
        return done("%-7s %s, $%08X"
                    % (DSJ[op & 0xFFE0], regname(f, rd), (start + 2 + off) * 16))
    if op & 0xFC00 == 0x3800:
        k = (op >> 5) & 0x1F
        back = (op >> 10) & 1
        return done("%-7s %s, $%08X"
                    % ("DSJS", regname(f, rd), (start + (-k if back else k)) * 16))
    for base, mask, m, sf, df, ext in IND:
        if op & mask != base:
            continue
        offs = [s.word() for _ in range(ext)]
        fld = (op >> 9) & 1 if mask == 0xFC00 else None
        sn, dn = regname(f, rs), regname(f, rd)

        def fmt(form, reg, o):
            return (form.replace("Rs", reg).replace("Rd", reg)
                    .replace("(o)", "(%d)" % o if o is not None else ""))

        so = offs[0] if ext and sf.endswith("(o)") else None
        do = offs[-1] if ext and df.endswith("(o)") else None
        text = "%-7s %s, %s" % (m, fmt(sf, sn, so), fmt(df, dn, do))
        if fld is not None:
            text += ", %d" % fld
        return done(text)
    if op in ABS_TWO:
        src, dst = s.long(), s.long()
        return done("%-7s @$%08X, @$%08X" % (ABS_TWO[op], src, dst))
    return done(".word   $%04X" % op)


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)

    def opt(name, default):
        return int(argv[argv.index(name) + 1], 0) if name in argv else default

    blob = open(argv[1], "rb").read()
    skip = opt("--skip", 0)                  # bytes of file header to ignore
    base = opt("--base", 0)                  # bit address the code is loaded at
    count = opt("--count", 48)
    at = opt("--at", None)

    start_word = skip // 2 if at is None else (at - base) // 16
    quiet = "--validate" in argv
    limit = base + len(blob) * 8            # one past the image, as a bit address

    s = Stream(blob, start_word)
    decoded = unknown = zeros = targets = inrange = 0
    for _ in range(count):
        here = base + (s.at * 16)
        try:
            text, _ = decode(s)
        except IndexError:
            break
        if text.startswith(".word"):
            unknown += 1
            if text.endswith("$0000"):
                zeros += 1          # padding and tables, not instructions
        else:
            decoded += 1
        if text.startswith(("CALLA", "JA")):
            targets += 1
            if base <= int(text.rsplit("$", 1)[1], 16) < limit:
                inrange += 1
        if not quiet:
            print("  %08X  %s" % (here, text))

    print("\n%d decoded, %d unknown of which %d are zero words" % (decoded, unknown, zeros))
    print("%.0f%% of all words recognised, %.0f%% ignoring zero fill"
          % (100.0 * decoded / max(1, decoded + unknown),
             100.0 * decoded / max(1, decoded + unknown - zeros)))
    if targets:
        print("%d of %d absolute call and jump targets land inside the image (%.0f%%)"
              % (inrange, targets, 100.0 * inrange / targets))


if __name__ == "__main__":
    main(sys.argv)
