#!/usr/bin/env python3
"""A TMS340x0 disassembler, for reading the cockpit's renderer.

The 68020 never reads inside a model - it only walks the 16-byte resource
headers - so the geometry format is parsed entirely by the TMS340 code in
R.BIN. That code is 28 KB and is the only route to it.

The renderer is a **TMS34020**, not the TMS34010 first assumed. R.BIN uses
instructions that exist only on the '20 - SETCDP ($0273), SETCSP ($0251),
SETCMP ($02FB), RPIX ($0280), VLCOL ($0A00), VFILL ($0A57), CLIP ($08F2) - and
it drives a coprocessor through the CMOVGC/CMOVCG group at $0600-$06FF, which
on this board can only be a TMS34082 floating-point unit. That is where the
renderer's 3D maths goes.

Encodings follow the TMS34020 User's Guide (Texas Instruments, August 1990),
whose summary table gives every instruction word bit by bit. The processor is
little-endian in 16-bit words and its addresses are *bit* addresses, so a byte
at file offset n sits at bit address n*8.

Not every instruction is implemented; anything unrecognised prints as `.word`,
which keeps the stream in sync because an unknown opcode is still one word long.

The image holds data as well as code, so a linear disassembly can never reach
100%; the reported figures separate zero fill from genuine unknowns.

usage:
  tms340dis.py <file> [--base BITADDR] [--at BITADDR] [--count N] [--skip N]
"""
import struct
import sys


def segments(blob):
    """R.BIN is a scatter-load image: records of (target offset, longword
    count) big-endian, each followed by its data. Only the first segment is
    code; the rest are data the 68020 places elsewhere in the renderer's
    memory. Disassembling the file as one flat block counts all of that as
    instructions, which is why it used to look so unrecognisable."""
    at = 0
    while at + 8 <= len(blob):
        tgt, cnt = struct.unpack(">II", blob[at:at + 8])
        if cnt == 0 or cnt > 0x100000:
            return
        yield ((0x1FC00000 + tgt) * 8) & 0xFFFFFFFF, cnt, at + 8
        at += 8 + cnt * 4

REG = ["A%d" % i for i in range(15)] + ["SP"]
REGB = ["B%d" % i for i in range(16)]


def regname(f, r):
    return (REGB if f else REG)[r]


# Relative branch and call targets are PC-relative in words; they only become
# real addresses once the image's load base is added. main() sets this.
LOAD_BASE = 0


# base opcode -> (mnemonic, class). Classes describe how the operands are
# packed into the low bits and what extension words follow.
NOARG = {
    0x0040: "IDLE", 0x0080: "MWAIT", 0x0100: "EMU", 0x01C0: "POPST",
    0x01E0: "PUSHST", 0x0300: "NOP", 0x0320: "CLRC", 0x0360: "DINT",
    0x0940: "RETI", 0x0D60: "EINT", 0x0DE0: "SETC",
    # TMS34020 only. SETCDP/SETCSP/SETCMP recompute the cached pitch
    # conversions from DPTCH/SPTCH/MPTCH, which is why they carry no operand
    # even though their encodings look like they hold a register number.
    0x0251: "SETCSP", 0x0273: "SETCDP", 0x02FB: "SETCMP",
    0x0860: "RETM", 0x080F: "TRAPL", 0x08F2: "CLIP", 0x0C57: "LINIT",
    0x0A00: "VLCOL", 0x0A37: "PFILL  XY", 0x0A57: "VFILL", 0x0857: "VBLT",
    0x0EFA: "TFILL  XY",
}
ONEREG = {
    0x0020: "REV", 0x0120: "EXGPC", 0x0140: "GETPC", 0x0180: "GETST",
    0x01A0: "PUTST", 0x0380: "ABS", 0x03A0: "NEG", 0x03C0: "NEGB",
    0x03E0: "NOT", 0x1020: "INC", 0x1420: "DEC",
    0x0500: "SEXT", 0x0520: "ZEXT",        # field 0; field 1 adds 0x0200
    0x0700: "SEXT", 0x0720: "ZEXT",
    0x0280: "RPIX", 0x0A60: "CVMXYL", 0x0A80: "CVDXYL",     # '20 only
}
TWOREG = {
    0x4000: "ADD", 0x4200: "ADDC", 0x4400: "SUB", 0x4600: "SUBB",
    0x4800: "CMP", 0x4C00: "MOVE", 0x4E00: "MOVE", 0x5000: "AND",
    0x5200: "ANDN", 0x5400: "OR", 0x5600: "XOR", 0x5800: "DIVS",
    0x5A00: "DIVU", 0x5C00: "MPYS", 0x5E00: "MPYU", 0x6A00: "LMO",
    0x6C00: "MODS", 0x6E00: "MODU", 0x1C00: "BTST", 0xE000: "ADDXY",
    0xE200: "SUBXY", 0xE400: "CMPXY", 0xE600: "CPW", 0xE800: "CVXYL",
    0xEC00: "MOVX", 0xEE00: "MOVY", 0xF600: "DRAV", 0xEA00: "CVSXYL",
}
# immediate forms: long takes two extension words, short takes one
IMM_LONG = {0x09E0: "MOVI", 0x0B20: "ADDI", 0x0B60: "CMPI", 0x0D00: "SUBI",
            0x0C00: "ADDXYI"}
IMM_SHORT = {0x09C0: "MOVI", 0x0B00: "ADDI", 0x0B40: "CMPI", 0x0BE0: "SUBI"}
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
# The '20 manual gives these as `0000 01F1 100R SSSS` for a store and
# `0000 01F1 101R DDDD` for a load, with bit 9 selecting which of the two
# field-size registers applies. Reading both as stores was wrong and it broke
# the display interrupt, whose handler read-modify-writes INTPEND.
#   base -> (mnemonic, direction, field)
ABS_ONE = {
    0x0580: ("MOVE", "store", 0), 0x05A0: ("MOVE", "load", 0),
    0x0780: ("MOVE", "store", 1), 0x07A0: ("MOVE", "load", 1),
    0x05E0: ("MOVB", "store", None), 0x07E0: ("MOVB", "load", None),
}

# The coprocessor group: a 32-bit command word follows each, so three words.
COPROC = {
    0x0600: "CEXEC", 0x0620: "CMOVGC", 0x0640: "CMOVGC", 0x0660: "CMOVCG",
    0x0680: "CMOVMC", 0x06A0: "CMOVCM", 0x06C0: "CMOVCS", 0x06E0: "CMOVMC",
    0x0820: "CMOVMC",
}

ABS_TWO = {0x0340: "MOVB", 0x05C0: "MOVE", 0x07C0: "MOVE"}
                                    # absolute to absolute, two addresses

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
        elif m in ("SRA", "SRL", "RL"):
            k = (32 - k) & 0x1F     # right shifts encode 32 minus the count
        return done("%-7s #%d, %s" % (m, k, regname(f, rd)))
    if op == 0x0D5F:
        return done("%-7s $%08X" % ("CALLA", s.long()))
    if op == 0x0D3F:
        d = s.word()
        off = d - 0x10000 if d & 0x8000 else d
        return done("%-7s $%08X" % ("CALLR", LOAD_BASE + (start + 2 + off) * 16))
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
        return done("%-7s $%08X" % (m, LOAD_BASE + (s.at + off) * 16))
    if op & 0xFFE0 in ABS_ONE:
        m, dirn, fld = ABS_ONE[op & 0xFFE0]
        a = s.long()
        tail = "" if fld is None else ", %d" % fld
        if dirn == "store":
            return done("%-7s %s, @$%08X%s" % (m, regname(f, rd), a, tail))
        return done("%-7s @$%08X, %s%s" % (m, a, regname(f, rd), tail))
    if op & 0xFFE0 in COPROC:
        return done("%-7s %s, $%08X" % (COPROC[op & 0xFFE0], regname(f, rd), s.long()))
    if (op & 0xFDC0) == 0x0540:                 # SETF FS, FE, F
        return done("%-7s %d, %d, %d"
                    % ("SETF", (op & 0x1F) or 32, (op >> 5) & 1, (op >> 9) & 1))
    if op & 0xFFE0 in DSJ:
        d = s.word()
        off = d - 0x10000 if d & 0x8000 else d
        return done("%-7s %s, $%08X"
                    % (DSJ[op & 0xFFE0], regname(f, rd), (start + 2 + off) * 16))
    if op & 0xF800 == 0x3800:
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
    if "--segments" in argv:
        for ti, cnt, at in segments(blob):
            print("  TI $%08X  %6d longs  file +%06X" % (ti, cnt, at))
        return
    if "--code" in argv:                     # just the first segment, in place
        for ti, cnt, at in segments(blob):
            blob, skip = blob[:at + cnt * 4], at
            break
    base = opt("--base", 0)                  # bit address the code is loaded at
    count = opt("--count", 48)
    at = opt("--at", None)

    global LOAD_BASE
    # The 68020 uploads from file offset 8 to TI 0xFE000000 - its own log says
    # "68K src 2ae0008 ... TI fe000000" - so the header is not part of the image
    # and addresses must be measured from there, not from the start of the file.
    LOAD_BASE = base - skip * 8
    start_word = skip // 2 if at is None else (at - LOAD_BASE) // 16
    quiet = "--validate" in argv
    limit = base + (len(blob) - skip) * 8   # one past the image, as a bit address

    s = Stream(blob, start_word)
    decoded = unknown = zeros = targets = inrange = 0
    for _ in range(count):
        here = LOAD_BASE + (s.at * 16)
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
        if text.startswith(("CALLA", "CALLR", "JA", "JR", "DSJ")) and "$" in text:
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
        print("%d of %d call and branch targets land inside the image (%.0f%%)"
              % (inrange, targets, 100.0 * inrange / targets))


if __name__ == "__main__":
    main(sys.argv)
