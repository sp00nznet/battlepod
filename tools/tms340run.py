#!/usr/bin/env python3
"""Run the cockpit renderer's TMS34010 code, to find out what it needs.

If R.BIN executes, it draws its own frames - the geometry format stops being
something that has to be decoded and becomes something the renderer reads for
us. This is the same method that worked on the 68020: run it, watch where it
stops, and let the firmware say what is missing.

Memory is bit-addressed. Everything here works in bit addresses and the backing
store is a sparse dict of 16-bit words, so a word at bit address a lives at
a >> 4 when a is word-aligned, which in this code it always is.

usage: tms340run.py <R.BIN> [--base BITADDR] [--skip N] [--steps N] [--trace N]
"""
import struct
import sys

WORD = 16                       # bits per word
FB_BASE = 0xA0000000            # frame buffer, per the renderer's own init
IO_BASE = 0xC0000000            # TMS34010 on-chip I/O registers


class Machine:
    def __init__(self, base):
        self.mem = {}           # bit address (word aligned) -> 16-bit word
        self.a = [0] * 16       # A file; a[15] is SP
        self.b = [0] * 16       # B file
        self.pc = base
        self.st = 0
        self.n = self.c = self.z = self.v = 0
        self.halted = None
        self.io = {}
        self.ioacc = {}         # which on-chip registers get hammered
        self.touched = {}       # region -> access count, for the report
        # Field parameters, as SETF leaves them: size in bits and whether a
        # short field sign-extends when read into a register.
        self.fs = [32, 32]
        self.fe = [0, 0]
        self.setf = 0
        self.hits = 0

    # ---- memory -------------------------------------------------------
    #
    # The TMS34010 addresses memory by the bit. A field is `size` bits starting
    # at any bit address at all, so a read spans up to three 16-bit words and a
    # write is a read-modify-write of the same. Everything below works that way
    # rather than pretending accesses are word aligned - the renderer relies on
    # it, and the previous version of this model did pretend, which made every
    # field move silently wrong.
    def note(self, addr):
        self.touched[addr >> 24] = self.touched.get(addr >> 24, 0) + 1
        if addr >> 24 == IO_BASE >> 24:
            a = addr & ~0xF
            self.ioacc[a] = self.ioacc.get(a, 0) + 1

    def rw(self, addr):
        return self.mem.get(addr & ~0xF, 0)

    def ww(self, addr, v):
        self.mem[addr & ~0xF] = v & 0xFFFF

    def field_read(self, addr, size, extend=0):
        """Read `size` bits from bit address `addr`."""
        self.note(addr)
        base = addr & ~0xF
        shift = addr - base
        span = 0
        for i in range((shift + size + WORD - 1) // WORD):
            span |= self.rw(base + i * WORD) << (i * WORD)
        v = (span >> shift) & ((1 << size) - 1)
        if extend and size < 32 and v & (1 << (size - 1)):
            v |= ~((1 << size) - 1) & 0xFFFFFFFF
        return v

    def field_write(self, addr, size, value):
        """Write `size` bits at bit address `addr`, leaving neighbours alone."""
        self.note(addr)
        base = addr & ~0xF
        shift = addr - base
        words = (shift + size + WORD - 1) // WORD
        span = 0
        for i in range(words):
            span |= self.rw(base + i * WORD) << (i * WORD)
        mask = ((1 << size) - 1) << shift
        span = (span & ~mask) | ((value << shift) & mask)
        for i in range(words):
            self.ww(base + i * WORD, (span >> (i * WORD)) & 0xFFFF)

    def rl(self, addr):
        return self.field_read(addr, 32)

    def wl(self, addr, v):
        self.field_write(addr, 32, v & 0xFFFFFFFF)

    def fetch(self):
        w = self.mem.get(self.pc & ~0xF, 0)
        self.pc += WORD
        return w

    def fetchl(self):
        lo = self.fetch()
        return lo | (self.fetch() << 16)

    # ---- registers ----------------------------------------------------
    def reg(self, f, r):
        return (self.b if f else self.a)[r]

    def setreg(self, f, r, v):
        (self.b if f else self.a)[r] = v & 0xFFFFFFFF

    def status(self):
        return (self.n << 31) | (self.c << 30) | (self.z << 29) | (self.v << 28)             | (self.fe[1] << 26) | ((self.fs[1] & 0x1F) << 21)             | (self.fe[0] << 5) | (self.fs[0] & 0x1F)

    def setstatus(self, v):
        self.n, self.c = (v >> 31) & 1, (v >> 30) & 1
        self.z, self.v = (v >> 29) & 1, (v >> 28) & 1
        self.fe[1], self.fe[0] = (v >> 26) & 1, (v >> 5) & 1
        self.fs[1] = ((v >> 21) & 0x1F) or 32
        self.fs[0] = (v & 0x1F) or 32

    def flags(self, v):
        v &= 0xFFFFFFFF
        self.z = 1 if v == 0 else 0
        self.n = 1 if v & 0x80000000 else 0
        return v


def s32(v):
    return v - 0x100000000 if v & 0x80000000 else v


def run(m, steps, trace, brk=None):
    """Execute until something unimplemented turns up, and say what it was."""
    executed = 0
    while executed < steps:
        here = m.pc
        if brk is not None and here == brk and m.hits < 3:
            m.hits += 1
            print("  break at $%08X after %d instructions" % (here, executed))
            print("    A: %s" % " ".join("%08X" % v for v in m.a[:8]))
            print("       %s" % " ".join("%08X" % v for v in m.a[8:]))
            print("    B: %s" % " ".join("%08X" % v for v in m.b[:8]))
            print("       %s" % " ".join("%08X" % v for v in m.b[8:]))
            print("    fs %s fe %s" % (m.fs, m.fe))
        op = m.fetch()
        f, rd, rs = (op >> 4) & 1, op & 0xF, (op >> 5) & 0xF
        executed += 1
        if trace and executed <= trace:
            print("  %08X  %04X" % (here, op))

        # no operands
        if op == 0x0360 or op == 0x0D60 or op == 0x0300:        # DINT/EINT/NOP
            continue
        if op == 0x0DE0:                                        # SETC
            m.c = 1
            continue
        if op == 0x0320:                                        # CLRC
            m.c = 0
            continue

        # MOVI long / short
        if op & 0xFFE0 == 0x09E0:
            m.setreg(f, rd, m.fetchl())
            continue
        if op & 0xFFE0 == 0x09C0:
            v = m.fetch()
            m.setreg(f, rd, v - 0x10000 if v & 0x8000 else v)
            continue
        if op & 0xFC00 == 0x1800:                               # MOVK
            k = (op >> 5) & 0x1F
            m.setreg(f, rd, 32 if k == 0 else k)
            continue

        # register to register
        if op & 0xFE00 in (0x4000, 0x4400, 0x4800, 0x5000, 0x5200, 0x5400,
                           0x5600, 0x4C00, 0x4E00):
            a, bb = m.reg(f, rd), m.reg(f, rs)
            base = op & 0xFE00
            if base == 0x4000:
                r = a + bb
            elif base == 0x4400:
                r = a - bb
            elif base == 0x4800:
                r = a - bb                       # CMP: flags only
            elif base == 0x5000:
                r = a & bb
            elif base == 0x5200:
                r = a & ~bb
            elif base == 0x5400:
                r = a | bb
            elif base == 0x5600:
                r = a ^ bb
            else:
                r = bb                           # MOVE Rs,Rd
            m.flags(r)
            if base != 0x4800:
                m.setreg(f, rd, r)
            continue

        # absolute moves, the two forms confirmed against this firmware
        if op & 0xFFE0 in (0x0780, 0x07A0):                     # MOVE Rs,@addr
            m.wl(m.fetchl(), m.reg(f, rd))
            continue
        if op & 0xFFE0 in (0x0580, 0x05A0):                     # MOVB Rs,@addr
            m.wl(m.fetchl(), m.reg(f, rd))
            continue
        if op & 0xFFE0 == 0x07E0:                               # MOVB @addr,Rd
            m.setreg(f, rd, m.flags(m.field_read(m.fetchl(), 8, 1)))
            continue
        if op & 0xFFE0 == 0x05E0:                               # MOVB Rs,@addr
            m.field_write(m.fetchl(), 8, m.reg(f, rd))
            continue
        if op == 0x0340:                                        # MOVB @a,@b
            src, dst = m.fetchl(), m.fetchl()
            m.field_write(dst, 8, m.field_read(src, 8))
            continue

        # register indirect, the forms this code actually uses
        if op & 0xFC00 in (0x8000, 0x8400, 0x9000, 0x9400, 0xA000, 0xA400,
                           0xB000, 0xB400):
            fld = (op >> 9) & 1          # which field the move uses
            size, ext = m.fs[fld], m.fe[fld]
            base, o = op & 0xFC00, 0
            if base in (0xB000, 0xB400):
                w = m.fetch()
                o = w - 0x10000 if w & 0x8000 else w
            if base in (0x8000, 0x9000, 0xA000, 0xB000):        # to memory
                a = m.reg(f, rd)
                if base == 0xA000:
                    a -= size                                   # predecrement
                    m.setreg(f, rd, a)
                m.field_write(a + o, size, m.reg(f, rs))
                if base == 0x9000:
                    m.setreg(f, rd, a + size)                   # postincrement
            else:                                               # from memory
                a = m.reg(f, rs)
                if base == 0xA400:
                    a -= size
                    m.setreg(f, rs, a)
                m.setreg(f, rd, m.flags(m.field_read(a + o, size, ext)))
                if base == 0x9400:
                    m.setreg(f, rs, a + size)
            continue

        # MOVB: always eight bits, sign-extended into a register
        if op & 0xFE00 in (0x8C00, 0x8E00, 0xAC00, 0xAE00, 0x9C00, 0xBC00):
            base = op & 0xFE00
            so = do = 0
            if base in (0xAC00, 0xAE00):
                w = m.fetch()
                do = so = w - 0x10000 if w & 0x8000 else w
            elif base == 0xBC00:
                w = m.fetch()
                so = w - 0x10000 if w & 0x8000 else w
                w = m.fetch()
                do = w - 0x10000 if w & 0x8000 else w
            if base in (0x8C00, 0xAC00):                        # to memory
                m.field_write(m.reg(f, rd) + do, 8, m.reg(f, rs))
            elif base in (0x8E00, 0xAE00):                      # to register
                m.setreg(f, rd, m.flags(m.field_read(m.reg(f, rs) + so, 8, 1)))
            else:                                               # memory to memory
                m.field_write(m.reg(f, rd) + do, 8,
                              m.field_read(m.reg(f, rs) + so, 8))
            continue

        # immediate arithmetic
        if op & 0xFFE0 in (0x0B20, 0x0B60, 0x0D00, 0x0B80, 0x0BA0, 0x0BC0):
            imm = m.fetchl()
            a = m.reg(f, rd)
            base = op & 0xFFE0
            r = {0x0B20: a + imm, 0x0B60: a - imm, 0x0D00: a - imm,
                 0x0B80: a & ~imm, 0x0BA0: a | imm, 0x0BC0: a ^ imm}[base]
            m.flags(r)
            if base != 0x0B60:                                  # CMPI: flags only
                m.setreg(f, rd, r)
            continue
        if op & 0xFFE0 in (0x0B00, 0x0B40, 0x0CE0):             # 16-bit forms
            w = m.fetch()
            imm = w - 0x10000 if w & 0x8000 else w
            a = m.reg(f, rd)
            base = op & 0xFFE0
            r = a + imm if base == 0x0B00 else a - imm
            m.flags(r)
            if base != 0x0B40:
                m.setreg(f, rd, r)
            continue

        # ADDK / SUBK / INC / DEC
        if op & 0xFC00 in (0x1000, 0x1400):
            k = (op >> 5) & 0x1F or 32
            r = m.reg(f, rd) + (k if (op & 0xFC00) == 0x1000 else -k)
            m.setreg(f, rd, m.flags(r))
            continue

        # CALLR and the decrement-and-branch family
        if op == 0x0D3F:
            w = m.fetch()
            t = m.pc + (w - 0x10000 if w & 0x8000 else w) * WORD
            m.a[15] -= 32
            m.wl(m.a[15], m.pc)
            m.pc = t
            continue
        if op & 0xFFE0 in (0x0D80, 0x0DA0, 0x0DC0):
            w = m.fetch()
            off = w - 0x10000 if w & 0x8000 else w
            take = {0x0D80: True, 0x0DA0: m.z == 1, 0x0DC0: m.z == 0}[op & 0xFFE0]
            v = (m.reg(f, rd) - 1) & 0xFFFFFFFF
            m.setreg(f, rd, v)
            if take and v != 0:
                m.pc += off * WORD
            continue

        # DSJS, encoded 0011 10DK KKKR DDDD: a short decrement-and-branch with
        # the distance in the opcode and bit 10 choosing the direction. This is
        # what drives the renderer's frame-buffer clear.
        if op & 0xF800 == 0x3800:
            k = (op >> 5) & 0x1F
            back = (op >> 10) & 1
            v = (m.reg(f, rd) - 1) & 0xFFFFFFFF
            m.setreg(f, rd, v)
            if v != 0:
                m.pc += (-k if back else k) * WORD
            continue

        # status register and stack housekeeping
        if op == 0x01E0:                                        # PUSHST
            m.a[15] -= 32
            m.wl(m.a[15], m.status())
            continue
        if op == 0x01C0:                                        # POPST
            m.setstatus(m.rl(m.a[15]))
            m.a[15] += 32
            continue
        if op & 0xFFE0 == 0x0180:                               # GETST
            m.setreg(f, rd, m.status())
            continue
        if op & 0xFFE0 == 0x01A0:                               # PUTST
            m.setstatus(m.reg(f, rd))
            continue
        if op & 0xFFE0 in (0x0980, 0x09A0):                     # MMTM / MMFM
            mask = m.fetch()
            if (op & 0xFFE0) == 0x0980:                         # push
                for i in range(15, -1, -1):
                    if mask & (1 << (15 - i)):
                        m.a[15] -= 32
                        m.wl(m.a[15], m.reg(f, i))
            else:                                               # pop
                for i in range(16):
                    if mask & (1 << (15 - i)):
                        m.setreg(f, i, m.rl(m.a[15]))
                        m.a[15] += 32
            continue

        # single-register arithmetic
        if op & 0xFFE0 in (0x0380, 0x03A0, 0x03E0, 0x1020, 0x1420,
                           0x0500, 0x0520):
            v, base = m.reg(f, rd), op & 0xFFE0
            if base == 0x0380:
                r = abs(s32(v))
            elif base == 0x03A0:
                r = -s32(v)
            elif base == 0x03E0:
                r = ~v
            elif base == 0x1020:
                r = v + 1
            elif base == 0x1420:
                r = v - 1
            else:
                size = m.fs[(op >> 9) & 1]
                r = v & ((1 << size) - 1)
                if base == 0x0500 and size < 32 and r & (1 << (size - 1)):
                    r |= ~((1 << size) - 1)
            m.setreg(f, rd, m.flags(r))
            continue

        # two-register arithmetic that is not plain add or move
        if op & 0xFE00 in (0x4200, 0x4600, 0x5800, 0x5A00, 0x5C00, 0x5E00,
                           0x6C00, 0x6E00, 0x1C00):
            a, bb, base = m.reg(f, rd), m.reg(f, rs), op & 0xFE00
            if base == 0x4200:
                r = a + bb + m.c
            elif base == 0x4600:
                r = a - bb - m.c
            elif base in (0x5800, 0x5A00):
                r = 0 if bb == 0 else (s32(a) // s32(bb) if base == 0x5800 else a // bb)
            elif base in (0x5C00, 0x5E00):
                r = s32(a) * s32(bb) if base == 0x5C00 else a * bb
            elif base in (0x6C00, 0x6E00):
                r = 0 if bb == 0 else (s32(a) % s32(bb) if base == 0x6C00 else a % bb)
            else:                                               # BTST
                m.z = 0 if a & (1 << (bb & 31)) else 1
                continue
            m.setreg(f, rd, m.flags(r))
            continue

        if op & 0xFFE0 == 0x0920:                               # CALL Rd
            m.a[15] -= 32
            m.wl(m.a[15], m.pc)
            m.pc = m.reg(f, rd)
            continue

        # shifts
        if op & 0xFC00 in (0x2000, 0x2400, 0x2800, 0x2C00):
            k = (op >> 5) & 0x1F
            v = m.reg(f, rd)
            base = op & 0xFC00
            if base in (0x2000, 0x2400):
                r = v << k
            else:
                r = (s32(v) if base == 0x2800 else v) >> ((32 - k) & 0x1F)
            m.setreg(f, rd, m.flags(r))
            continue

        # calls and returns
        if op == 0x0D5F:                                        # CALLA
            t = m.fetchl()
            m.a[15] -= 32
            m.wl(m.a[15], m.pc)
            m.pc = t
            continue
        if op & 0xFFE0 == 0x0960:                               # RETS
            m.pc = m.rl(m.a[15])
            m.a[15] += 32 + ((op & 0x1F) * 32)
            continue

        # branches
        if op & 0xFF00 in range(0xC000, 0xD000, 0x100):
            cond = {0xC0: 1, 0xCA: m.z, 0xCB: 1 - m.z,
                    0xC8: m.c, 0xC9: 1 - m.c,
                    0xCE: m.n, 0xCF: 1 - m.n}.get(op >> 8, None)
            d = op & 0xFF
            if d == 0x80:
                t = m.fetchl()
            elif d == 0:
                w = m.fetch()
                t = m.pc + (w - 0x10000 if w & 0x8000 else w) * WORD
            else:
                t = m.pc + (d - 0x100 if d & 0x80 else d) * WORD
            if cond is None:
                m.halted = "unimplemented branch condition %04X at %08X" % (op, here)
                return executed
            if cond:
                m.pc = t
            continue

        # SETF, encoded 0000 01F1 01FE SSSSS: field select in bit 9, the
        # sign-extend flag in bit 5, and the size in the low five bits with
        # zero meaning 32.
        if (op & 0xFDC0) == 0x0540:
            fld = (op >> 9) & 1
            size = op & 0x1F
            m.fs[fld] = size if size else 32
            m.fe[fld] = (op >> 5) & 1
            continue
        # 0x0620 and 0x0660 take a 32-bit operand - that reading is what lands
        # execution on the stack-pointer setup, where treating them as one word
        # leaves an unexplained 0x000D mid-entry. Their *effect* is still
        # unknown: the operands look like a table of globals 32 bits apart, but
        # modelling them as absolute loads changed nothing observable, so there
        # is no evidence for it and the operand is simply consumed.
        if op & 0xFFE0 in (0x0620, 0x0660):
            m.fetchl()
            m.setf += 1
            continue

        m.halted = "unimplemented opcode %04X at %08X" % (op, here)
        return executed
    return executed


def segments(blob):
    """R.BIN is a scatter-load image, not one flat block.

    Records of (target offset, longword count) big-endian, each followed by its
    data, terminated by 0xFFFFFFFF. The 68020 logs exactly this when it uploads
    - "68K src 2ae649c ... TI ffff0000, Count 616" - and the target offset maps
    to a TI bit address as (0x1FC00000 + target) * 8. Loading the file as one
    flat block at 0xFE000000, which is what this did first, leaves the last two
    segments missing: the I/O register initialisation table and the processor's
    own trap vectors.
    """
    at = 0
    while at + 8 <= len(blob):
        tgt, cnt = struct.unpack(">II", blob[at:at + 8])
        if cnt == 0 or cnt > 0x100000:
            return
        yield tgt, cnt, at + 8
        at += 8 + cnt * 4


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)

    def opt(name, default):
        return int(argv[argv.index(name) + 1], 0) if name in argv else default

    blob = open(argv[1], "rb").read()
    skip = opt("--skip", 8)
    base = opt("--base", 0xFE000000)
    steps = opt("--steps", 200000)

    m = Machine(base)
    for tgt, cnt, at in segments(blob):
        ti = ((0x1FC00000 + tgt) * 8) & 0xFFFFFFFF
        for i in range(cnt * 2):
            m.mem[ti + i * WORD] = struct.unpack(
                "<H", blob[at + i * 2:at + i * 2 + 2])[0]
        print("  segment: %-6d longs -> TI $%08X" % (cnt, ti))
    print("loaded %d words" % len(m.mem))

    n = run(m, steps, opt("--trace", 0),
            int(argv[argv.index("--break") + 1], 0) if "--break" in argv else None)
    print("\nexecuted %d instructions" % n)
    print("stopped: %s" % (m.halted or "step limit reached"))
    print("pc $%08X  sp $%08X" % (m.pc, m.a[15]))
    if m.ioacc:
        print("\non-chip I/O registers, busiest first:")
        for a in sorted(m.ioacc, key=lambda k: -m.ioacc[k])[:8]:
            print("   $%08X  %d accesses" % (a, m.ioacc[a]))
    print("\nmemory regions touched (by top byte of the bit address):")
    for r in sorted(m.touched):
        note = ""
        if r == FB_BASE >> 24:
            note = "  <- frame buffer"
        elif r == IO_BASE >> 24:
            note = "  <- on-chip I/O registers"
        print("   $%02X......  %d accesses%s" % (r, m.touched[r], note))


if __name__ == "__main__":
    main(sys.argv)
