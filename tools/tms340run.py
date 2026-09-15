#!/usr/bin/env python3
"""Run the cockpit renderer's TMS34010 code, to find out what it needs.

If R.BIN executes, it draws its own frames - the geometry format stops being
something that has to be decoded and becomes something the renderer reads for
us. This is the same method that worked on the 68020: run it, watch where it
stops, and let the firmware say what is missing.

Memory is bit-addressed. Everything here works in bit addresses and the backing
store is a sparse dict of 16-bit words, so a word at bit address a lives at
a >> 4 when a is word-aligned, which in this code it always is.

--render hands the renderer a display list and watches it walk it, which is the
only way to see it draw: the 68020 only ever builds one once a game has started,
and starting a game needs a network. The list is built here from the format in
DEVICES.md, so it is also a test of that format being right.

usage:
  tms340run.py <R.BIN> [--steps N] [--irq VEC:PERIOD] [--trace N] [--pchist]
  tms340run.py <R.BIN> --boot N --render [LIST] [--fb OUT.pgm]
  tms340run.py --selftest
"""
import struct
import sys

WORD = 16                       # bits per word
FB_BASE = 0xA0000000            # frame buffer, per the renderer's own init
IO_BASE = 0xC0000000            # TMS34020 on-chip I/O registers
PSIZE_REG = IO_BASE + 0x0150    # pixel size in bits


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
        self.hist = None        # PC -> execution count, when asked for
        self.ints = 0           # interrupts enabled, as EINT/DINT leave it
        self.stop_at = None
        self.blits = 0
        self.pixels = 0
        self.unknown = {}
        self.skip_unknown = 0
        self.fpu = [0] * 32     # the TMS34082's register file
        self.fpu_ran = {}       # coprocessor routines this run executed
        self.fpu_missing = {}   # and the ones it could not
        self.copcmds = {}       # which commands the run actually issued
        self.copn = 0
        self.conv = {}          # what SETCSP/SETCDP/SETCMP last latched
        self._psize = 8         # until the firmware writes PSIZE
        self.irq_every = 0
        self.irq_vector = 0
        self.irqs = 0

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

    @property
    def psize(self):
        """Pixel size in bits, from the on-chip register once it is set."""
        return self.mem.get(PSIZE_REG, 0) or self._psize

    def xy_linear(self, v):
        """XY address to bit address: OFFSET + Y*DPTCH + X*PSIZE.

        The hardware does this with CONVDP, a shift count SETCDP derives from
        DPTCH, because DPTCH is always a power of two. The arithmetic is the
        same and needs no cached register."""
        return (self.b[4] + (v >> 16) * self.b[3]
                + (v & 0xFFFF) * self.psize) & 0xFFFFFFFF

    # The B file is the graphics instructions' operand set: B0 SADDR, B1 SPTCH,
    # B2 DADDR, B3 DPTCH, B4 OFFSET, B5 WSTART, B6 WEND, B7 DYDX, B8 COLOR0,
    # B9 COLOR1. PIXBLT and FILL take everything from there and carry no
    # operands of their own, which is why they encode as bare opcodes.
    SADDR, SPTCH, DADDR, DPTCH, OFFSET, DYDX = 0, 1, 2, 3, 4, 7
    COLOR0, COLOR1 = 8, 9

    def row(self, reg, pitch, y, xy):
        """Bit address of row y of a source or destination."""
        if xy:
            return self.xy_linear((self.b[reg] + (y << 16)) & 0xFFFFFFFF)
        return (self.b[reg] + y * self.b[pitch]) & 0xFFFFFFFF

    def blit(self, op):
        """PIXBLT and FILL.

        ponytail: replace only. The pixel-processing operation and the plane
        mask in CONTROL are not applied, and neither is window clipping - the
        firmware sets W to 0 for the frame it draws into. Transparency is, and
        has to be, because that is how a binary source draws text.
        """
        ps = self.psize
        dy, dx = self.b[self.DYDX] >> 16, self.b[self.DYDX] & 0xFFFF
        transparent = (self.field_read(IO_BASE + 0xB0, 16) >> 5) & 1
        dxy, sxy = op in (0x0F20, 0x0F60, 0x0FA0, 0x0FE0), op in (0x0F40, 0x0F60)
        fill, binary = op in (0x0FC0, 0x0FE0), op in (0x0F80, 0x0FA0)
        colour, back = self.b[self.COLOR1], self.b[self.COLOR0]
        for y in range(dy):
            d = self.row(self.DADDR, self.DPTCH, y, dxy)
            s = self.row(self.SADDR, self.SPTCH, y, sxy) if not fill else 0
            for x in range(dx):
                if fill:
                    v = colour
                elif binary:
                    # one bit per pixel, expanded to COLOR1 and COLOR0
                    if self.field_read(s + x, 1):
                        v = colour
                    elif transparent:
                        continue
                    else:
                        v = back
                else:
                    v = self.field_read(s + x * ps, ps)
                    if transparent and v == 0:
                        continue
                self.field_write(d + x * ps, ps, v)
        self.blits += 1
        self.pixels += dy * dx

    def fpu_exec(self, cmd):
        """Run a coprocessor operation, or say which one is missing.

        Mode 3 names a routine in the '82's internal ROM, so this is ordinary
        floating-point arithmetic and not microcode somebody would have to
        emulate. Only the routines actually identified are run; anything else
        is counted and named, because faking one would put numbers on the
        screen that no cockpit ever produced.
        """
        md, fpuop = (cmd >> 14) & 3, (cmd >> 8) & 0x3F
        if md == MD_ROM and fpuop in FPU_ROM:
            FPU_ROM[fpuop][1](self.fpu)
            self.fpu_ran[fpuop] = self.fpu_ran.get(fpuop, 0) + 1
        else:
            self.fpu_missing[(md, fpuop)] = self.fpu_missing.get((md, fpuop), 0) + 1

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


# The coprocessor group, all three words wide (TMS34020 User's Guide, 13.2).
# PIXBLT source and destination forms, and FILL. All bare - see Machine.blit.
BLIT = (0x0F00, 0x0F20, 0x0F40, 0x0F60, 0x0F80, 0x0FA0, 0x0FC0, 0x0FE0)
PIXT = (0xF000, 0xF200, 0xF400, 0xF800, 0xFA00, 0xFC00)

# ---------------------------------------------------------------------------
# The TMS34082 floating-point coprocessor.
#
# Its command word is the 32 bits following the '20's CMOV*/CEXEC opcode:
#
#   31-29 ID   28-25 ra   24-21 rb   20-16 rd   15-14 md   13-8 fpuop   7-0 ...
#
# The md field is the part that matters and it is not guesswork: every one of
# the nine commands R.BIN issues during a render agrees with it - the three
# CMOVGCs read 01, the four memory moves read 10, the two CEXECs read 11, and
# those are exactly the modes the TMS34020 instructions they belong to imply.
# The low byte carries the other GSP register the '20 opcode had no room for.
#
# Register file, from the handbook's Table 4-3.
FPU_REGS = (["RA%d" % i for i in range(10)] + ["C", "CT", "STATUS", "CONFIG",
            "COUNTX", "COUNTY"] + ["RB%d" % i for i in range(10)] +
            ["VECTOR", "MCADDR", "SUBADD0", "SUBADD1"])
RA0, C_REG, CT_REG, RB0 = 0, 10, 11, 16

MD_EXEC, MD_REG, MD_MEM, MD_ROM = 0, 1, 2, 3


def f2b(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def b2f(v):
    return struct.unpack(">f", struct.pack(">I", v & 0xFFFFFFFF))[0]


def fpu_scale(r):
    """SCALE: the perspective divide and viewport transform, from the
    handbook's own algorithm listing.

        RA0 = (X1/W1) * Sx + Cx      with X1..W1 in RA0..RA3,
        RA1 = (Y1/W1) * Sy + Cy           Sx,Sy,Sz in RA7..RA9,
        RA2 = (Z1/W1) * Sz + Cz           Cx,Cy,Cz in RB7..RB9
    """
    w = b2f(r[RA0 + 3])
    if w == 0.0:
        return
    for i in range(3):
        v = b2f(r[RA0 + i]) / w
        r[RA0 + i] = f2b(v * b2f(r[RA0 + 7 + i]) + b2f(r[RB0 + 7 + i]))
    r[CT_REG] = r[RA0 + 3]


FPU_ROM = {0x018: ("SCALE", fpu_scale)}


COPNAME = {0x0600: "CEXEC", 0x0620: "CMOVGC", 0x0640: "CMOVGC", 0x0660: "CMOVCG",
           0x0680: "CMOVMC", 0x06A0: "CMOVCM", 0x06C0: "CMOVCS", 0x06E0: "CMOVMC",
           0x0820: "CMOVMC"}

COPROC = (0x0600, 0x0620, 0x0640, 0x0660, 0x0680, 0x06A0, 0x06C0, 0x06E0,
          0x0820)


def s32(v):
    return v - 0x100000000 if v & 0x80000000 else v


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def run(m, steps, trace, brk=None):
    """Execute until something unimplemented turns up, and say what it was."""
    executed = 0
    while executed < steps:
        here = m.pc
        if here == m.stop_at:
            m.halted = "returned to the sentinel at $%08X" % here
            return executed
        if brk is not None and here == brk and m.hits < 3:
            m.hits += 1
            print("  break at $%08X after %d instructions" % (here, executed))
            print("    A: %s" % " ".join("%08X" % v for v in m.a[:8]))
            print("       %s" % " ".join("%08X" % v for v in m.a[8:]))
            print("    B: %s" % " ".join("%08X" % v for v in m.b[:8]))
            print("       %s" % " ".join("%08X" % v for v in m.b[8:]))
            print("    fs %s fe %s" % (m.fs, m.fe))
        # A periodic interrupt through a vector the firmware installed. The
        # renderer waits on a flag that only its interrupt handler clears, and
        # times out back to hardware init if nobody does - which is exactly
        # what a display interrupt is for.
        if m.irq_every and m.ints and executed and executed % m.irq_every == 0:
            handler = m.rl(m.irq_vector)
            if handler:
                m.a[15] -= 32
                m.wl(m.a[15], m.status())
                m.a[15] -= 32
                m.wl(m.a[15], m.pc)
                m.pc = handler
                m.irqs += 1
                m.ints = 0                  # the handler runs with them off
        if m.hist is not None:
            m.hist[here] = m.hist.get(here, 0) + 1
        op = m.fetch()
        f, rd, rs = (op >> 4) & 1, op & 0xF, (op >> 5) & 0xF
        executed += 1
        if trace and executed <= trace:
            print("  %08X  %04X" % (here, op))

        # no operands
        if op == 0x0300:                                        # NOP
            continue
        if op == 0x0360:                                        # DINT
            m.ints = 0
            continue
        if op == 0x0D60:                                        # EINT
            m.ints = 1
            continue
        if op == 0x0940:                                        # RETI
            m.pc = m.rl(m.a[15])
            m.a[15] += 32
            m.setstatus(m.rl(m.a[15]))
            m.a[15] += 32
            m.ints = 1
            continue
        # The graphics group: bare opcodes, operands all in the B file.
        if op in BLIT:
            m.blit(op)
            continue
        if op & 0xFE00 in PIXT:                                 # single pixel
            base = op & 0xFE00
            src = m.reg(f, rs)
            v = src if base in (0xF000, 0xF800) else m.field_read(
                m.xy_linear(src) if base in (0xF200, 0xF400) else src, m.psize)
            dst = m.reg(f, rd)
            m.field_write(m.xy_linear(dst) if base in (0xF000, 0xF400, 0xF600)
                          else dst, m.psize, v)
            m.pixels += 1
            continue
        if op & 0xFFE0 == 0x0160:                               # JUMP Rs
            m.pc = m.reg(f, rd)
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
            if base in (0x4000, 0x4400, 0x4800):
                # carry and overflow, which JRHI/JRLS/JRLT and friends read
                sa, sb = s32(a), s32(bb)
                if base == 0x4000:
                    m.c = 1 if a + bb > 0xFFFFFFFF else 0
                    m.v = 1 if not -(1 << 31) <= sa + sb < (1 << 31) else 0
                else:
                    m.c = 1 if bb > a else 0
                    m.v = 1 if not -(1 << 31) <= sa - sb < (1 << 31) else 0
            if base == 0x4800:
                continue
            # MOVE Rs,Rd across register files encodes as 0x4E00, with the
            # destination's file bit flipped - the source keeps the opcode's.
            m.setreg(1 - f if base == 0x4E00 else f, rd, r)
            continue

        # The XY group. These registers hold a packed pair: Y in the top 16
        # bits, X in the bottom, and carries never cross the halves.
        if op & 0xFE00 in (0xE000, 0xE200, 0xE400, 0xEC00, 0xEE00):
            a, bb, base = m.reg(f, rd), m.reg(f, rs), op & 0xFE00
            (dy, dx), (sy, sx) = (a >> 16, a & 0xFFFF), (bb >> 16, bb & 0xFFFF)
            if base == 0xEC00:                                  # MOVX
                m.setreg(f, rd, (dy << 16) | sx)
                continue
            if base == 0xEE00:                                  # MOVY
                m.setreg(f, rd, (sy << 16) | dx)
                continue
            if base == 0xE000:                                  # ADDXY
                rx, ry = (dx + sx) & 0xFFFF, (dy + sy) & 0xFFFF
                m.n, m.v = (1 if rx == 0 else 0), (rx >> 15) & 1
                m.z, m.c = (1 if ry == 0 else 0), (ry >> 15) & 1
            else:                                               # SUBXY, CMPXY
                rx, ry = (dx - sx) & 0xFFFF, (dy - sy) & 0xFFFF
                m.n = 1 if sx == dx else 0
                m.z = 1 if sy == dy else 0
                m.c = 1 if s16(sy) > s16(dy) else 0
                m.v = 1 if s16(sx) > s16(dx) else 0
            if base != 0xE400:
                m.setreg(f, rd, (ry << 16) | rx)
            continue
        if op & 0xFE00 in (0xE800, 0xEA00):                     # CVXYL, CVSXYL
            v = m.reg(f, rs)
            m.setreg(f, rd, m.flags(m.xy_linear(v)))
            continue

        # Absolute moves. Bit 9 picks which field-size register applies and
        # bit 5 the direction, so 0x0580/0x0780 store and 0x05A0/0x07A0 load.
        # Reading both as stores is what broke the display interrupt: its
        # handler read-modify-writes INTPEND through the field-0 pair, and a
        # store where a load belongs leaves the pending bit set forever.
        if op & 0xFDC0 == 0x0580:                               # MOVE, absolute
            fld = 1 if op & 0x0200 else 0
            size, addr = m.fs[fld], m.fetchl()
            if op & 0x20:
                m.setreg(f, rd, m.flags(m.field_read(addr, size, m.fe[fld])))
            else:
                m.field_write(addr, size, m.reg(f, rd))
            continue
        if op & 0xFDE0 == 0x05E0:                               # MOVB, absolute
            addr = m.fetchl()
            if op & 0x0200:
                m.setreg(f, rd, m.flags(m.field_read(addr, 8, 1)))
            else:
                m.field_write(addr, 8, m.reg(f, rd))
            continue
        if op == 0x0340:                                        # MOVB @a,@b
            src, dst = m.fetchl(), m.fetchl()
            m.field_write(dst, 8, m.field_read(src, 8))
            continue

        # memory to memory, both postincrementing. The renderer's object draw
        # uses it to stream a transform through.
        if op & 0xFC00 == 0x9800:                       # MOVE *Rs+, *Rd+
            fld = (op >> 9) & 1
            size = m.fs[fld]
            src, dst = m.reg(f, rs), m.reg(f, rd)
            m.field_write(dst, size, m.field_read(src, size))
            m.setreg(f, rs, src + size)
            m.setreg(f, rd, dst + size)
            continue
        if op & 0xFC00 == 0xA800:                       # MOVE *-Rs, *-Rd
            fld = (op >> 9) & 1
            size = m.fs[fld]
            src, dst = m.reg(f, rs) - size, m.reg(f, rd) - size
            m.setreg(f, rs, src)
            m.setreg(f, rd, dst)
            m.field_write(dst, size, m.field_read(src, size))
            continue
        if op & 0xFC00 == 0xB800:                       # MOVE *Rs(o), *Rd(o)
            fld = (op >> 9) & 1
            size = m.fs[fld]
            w = m.fetch()
            so = w - 0x10000 if w & 0x8000 else w
            w = m.fetch()
            do = w - 0x10000 if w & 0x8000 else w
            m.field_write(m.reg(f, rd) + do, size,
                          m.field_read(m.reg(f, rs) + so, size))
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
        if op & 0xFFE0 in (0x0B20, 0x0B60, 0x0D00, 0x0B80, 0x0BA0, 0x0BC0,
                           0x0C00):
            imm = m.fetchl()
            a = m.reg(f, rd)
            base = op & 0xFFE0
            if base == 0x0C00:                                  # ADDXYI
                m.setreg(f, rd, (((a >> 16) + (imm >> 16)) & 0xFFFF) << 16
                         | ((a + imm) & 0xFFFF))
                continue
            r = {0x0B20: a + imm, 0x0B60: a - imm, 0x0D00: a - imm,
                 0x0B80: a & ~imm, 0x0BA0: a | imm, 0x0BC0: a ^ imm}[base]
            m.flags(r)
            if base in (0x0B20, 0x0B60, 0x0D00):
                sa, si = s32(a), s32(imm)
                if base == 0x0B20:
                    m.c = 1 if a + imm > 0xFFFFFFFF else 0
                    m.v = 1 if not -(1 << 31) <= sa + si < (1 << 31) else 0
                else:
                    m.c = 1 if imm > a else 0
                    m.v = 1 if not -(1 << 31) <= sa - si < (1 << 31) else 0
            if base != 0x0B60:                                  # CMPI: flags only
                m.setreg(f, rd, r)
            continue
        # The 16-bit immediate forms. SUBI IW is 0x0BE0, not the 0x0CE0 first
        # assumed - the '20 manual gives it as 0000 1011 111R DDDD.
        if op & 0xFFE0 in (0x0B00, 0x0B40, 0x0BE0):
            w = m.fetch()
            imm = w - 0x10000 if w & 0x8000 else w
            a = m.reg(f, rd)
            base = op & 0xFFE0
            r = a + imm if base == 0x0B00 else a - imm
            m.flags(r)
            m.c = (1 if a + imm > 0xFFFFFFFF else 0) if base == 0x0B00                 else (1 if (imm & 0xFFFFFFFF) > a else 0)
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
                # MMFM's mask is not MMTM's: the firmware's own matched pairs
                # are MMTM #$8000 / MMFM #$0001 and MMTM #$E000 / MMFM #$0007,
                # so bit 0 names A0 here where bit 15 named it above.
                for i in range(16):
                    if mask & (1 << i):
                        m.setreg(f, i, m.rl(m.a[15]))
                        m.a[15] += 32
            continue

        # single-register arithmetic
        if op & 0xFFE0 in (0x0380, 0x03A0, 0x03E0, 0x1020, 0x1420,
                           0x0500, 0x0520, 0x0700, 0x0720):
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
                if base in (0x0500, 0x0700) and size < 32 and r & (1 << (size - 1)):
                    r |= ~((1 << size) - 1)
            m.setreg(f, rd, m.flags(r))
            continue

        # two-register arithmetic that is not plain add or move
        # BTST K, Rd is 0001 11KK KKKR DDDD, so the whole 0x1C00-0x1FFF block
        # is one instruction with a five-bit constant - not a two-register form.
        if op & 0xFC00 == 0x1C00:
            m.z = 0 if m.reg(f, rd) & (1 << ((op >> 5) & 0x1F)) else 1
            continue
        if op & 0xFE00 in (0x4200, 0x4600, 0x5800, 0x5A00, 0x5C00, 0x5E00,
                           0x6C00, 0x6E00, 0x4A00):
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
            else:                                               # BTST Rs,Rd
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
            nv = m.n ^ m.v
            cond = {0xC0: 1,
                    0xC1: (not m.n) and (not m.z),      # P   positive
                    0xC2: m.c or m.z,                   # LS
                    0xC3: (not m.c) and (not m.z),      # HI
                    0xC4: nv,                           # LT
                    0xC5: not nv,                       # GE
                    0xC6: nv or m.z,                    # LE
                    0xC7: (not nv) and (not m.z),       # GT
                    0xC8: m.c, 0xC9: 1 - m.c,           # LO / HS
                    0xCA: m.z, 0xCB: 1 - m.z,           # EQ / NE
                    0xCC: m.v, 0xCD: 1 - m.v,           # V  / NV
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
        # The TMS34020's coprocessor interface. Every one of these is three
        # words: the opcode, then a 32-bit command that names the coprocessor
        # and what it should do. On this board the coprocessor can only be a
        # TMS34082 floating-point unit, which is where the renderer's 3D maths
        # lives - so CMOVCG reads back results we do not compute yet.
        # ponytail: registers recorded, arithmetic not modelled; the FPU goes
        # in when the geometry path is the thing being chased.
        if op & 0xFC00 == 0xD800:               # CEXEC, short form: two words
            cmd = (op & 0x3FF) << 16 | m.fetch()
            m.fpu_exec(cmd)
            m.copn += 1
            m.copcmds[(0x0600, cmd)] = m.copcmds.get((0x0600, cmd), 0) + 1
            continue
        if op & 0xFFE0 in COPROC:
            cmd = m.fetchl()
            base = op & 0xFFE0
            crd, other = (cmd >> 16) & 0x1F, cmd & 0x1F
            m.copn += 1
            m.copcmds[(base, cmd)] = m.copcmds.get((base, cmd), 0) + 1
            if base in (0x0620, 0x0640):                # GSP registers -> FPU
                m.fpu[crd] = m.reg(f, rd)
                if base == 0x0640:                      # the two-register form
                    m.fpu[(crd + 1) & 0x1F] = m.reg(f, other)
            elif base == 0x0660:                        # FPU -> GSP register
                m.setreg(f, rd, m.fpu[crd])
            elif base == 0x06A0:                        # FPU -> memory
                a = m.reg(f, rd)
                for i in range(max(1, other)):
                    m.wl(a + i * 32, m.fpu[(crd + i) & 0x1F])
                m.setreg(f, rd, a + max(1, other) * 32)
            elif base in (0x0680, 0x06E0, 0x0820):      # memory -> FPU
                count = op & 0x1F if base in (0x0680, 0x0820) else m.reg(f, rd)
                a = m.reg(f, other)
                for i in range(count):
                    m.fpu[(crd + i) & 0x1F] = m.rl(a + i * 32)
                m.setreg(f, other, a + count * 32)
            elif base == 0x0600:                        # CEXEC
                m.fpu_exec(cmd)
            continue

        # SETCDP/SETCSP/SETCMP recompute the cached pitch conversions the XY
        # addressing modes use, from DPTCH (B3), SPTCH (B1) and MPTCH.
        if op in (0x0251, 0x0273, 0x02FB):
            m.conv[op] = m.b[{0x0251: 1, 0x0273: 3, 0x02FB: 13}[op]]
            continue
        if op & 0xFFE0 == 0x0280:                               # RPIX
            v, ps = m.reg(f, rd), m.psize
            r = v & ((1 << ps) - 1)
            for i in range(ps, 32, ps):
                r |= (v & ((1 << ps) - 1)) << i
            m.setreg(f, rd, r)
            continue
        if op & 0xFDE0 == 0x05C0:                               # MOVE @a,@b
            fld = 1 if op & 0x0200 else 0
            src, dst = m.fetchl(), m.fetchl()
            m.field_write(dst, m.fs[fld], m.field_read(src, m.fs[fld]))
            continue

        # Unknown opcodes stop the run, because guessing at one silently
        # corrupts everything after it. --skip-unknown steps over them instead
        # and counts them, which is for answering "how much further would it
        # get" - never for claiming the run was faithful.
        m.unknown[op] = m.unknown.get(op, 0) + 1
        if not m.skip_unknown:
            m.halted = "unimplemented opcode %04X at %08X" % (op, here)
            return executed
        continue
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

    if "--pchist" in argv:
        m.hist = {}
    m.skip_unknown = "--skip-unknown" in argv
    if "--irq" in argv:
        spec = argv[argv.index("--irq") + 1]
        vec, _, per = spec.partition(":")
        m.irq_vector = int(vec, 0)
        m.irq_every = int(per or "20000", 0)
    # With --render the first run is only there to bring the hardware up, so it
    # gets its own budget and --steps belongs to the walk that follows.
    boot = opt("--boot", 0 if "--render" in argv else steps)
    n = run(m, boot, opt("--trace", 0),
            int(argv[argv.index("--break") + 1], 0) if "--break" in argv else None)
    print("\nexecuted %d instructions" % n)
    print("stopped: %s" % (m.halted or "step limit reached"))
    if m.irqs:
        print("delivered %d interrupts through $%08X" % (m.irqs, m.irq_vector))
    if m.unknown:
        print("unknown opcodes: %s"
              % " ".join("$%04X x%d" % kv for kv in sorted(m.unknown.items())))
    if m.blits or m.pixels:
        print("%d blits, %d pixels written" % (m.blits, m.pixels))
    if m.copn:
        print("%d coprocessor instructions" % m.copn)
    print("pc $%08X  sp $%08X" % (m.pc, m.a[15]))
    if m.hist:
        print("\nbusiest addresses:")
        for a in sorted(m.hist, key=lambda k: -m.hist[k])[:12]:
            print("   $%08X  %d" % (a, m.hist[a]))
    if m.ioacc:
        print("\non-chip I/O registers, busiest first:")
        for a in sorted(m.ioacc, key=lambda k: -m.ioacc[k])[:8]:
            print("   $%08X  %d accesses" % (a, m.ioacc[a]))
    # Drive the renderer straight at a display list, which is the only way to
    # see it draw: the 68020 only ever sends one once a game has started, and a
    # game needs a network this does not have.
    if "--render" in argv:
        arg = argv[argv.index("--render") + 1] if len(argv) > argv.index("--render") + 1 else ""
        words = ([int.from_bytes(open(arg, "rb").read()[i:i + 4], "big")
                  for i in range(0, len(open(arg, "rb").read()), 4)]
                 if arg and not arg.startswith("--") else demo_list())
        addr = load_list(m, words)
        print("display list: %d longwords at TI bit $%08X" % (len(words), addr))
        if m.hist is not None:
            m.hist = {}
        m.copcmds, m.blits, m.pixels = {}, 0, 0
        m.fpu_ran, m.fpu_missing = {}, {}
        m.halted = None
        m.a[15] = opt("--sp", 0xFE034DC0)
        m.a[15] -= 32
        m.wl(m.a[15], SENTINEL)                 # where the walker returns to
        m.a[0] = addr
        m.pc = opt("--entry", WALKER)
        m.stop_at = SENTINEL
        n = run(m, steps, opt("--trace", 0))
        print("\nwalked %d instructions" % n)
        print("stopped: %s" % (m.halted or "step limit reached"))
        if m.unknown:
            print("unknown opcodes: %s"
                  % " ".join("$%04X x%d" % kv for kv in sorted(m.unknown.items())))
        if m.blits or m.pixels:
            print("%d blits, %d pixels written" % (m.blits, m.pixels))
        if m.fpu_ran:
            print("coprocessor routines run: %s"
                  % " ".join("%s x%d" % (FPU_ROM[k][0], v)
                             for k, v in sorted(m.fpu_ran.items())))
        if m.fpu_missing:
            print("coprocessor routines still missing: %s"
                  % " ".join("mode %d fpuop $%02X x%d" % (k[0], k[1], v)
                             for k, v in sorted(m.fpu_missing.items())))
        if m.copcmds:
            print("coprocessor commands this walk needed: %d distinct, %d issued"
                  % (len(m.copcmds), sum(m.copcmds.values())))
            for (base, cmd), k in sorted(m.copcmds.items(), key=lambda kv: -kv[1]):
                print("   %-7s $%08X  x%d" % (COPNAME.get(base, "?"), cmd, k))
        if m.hist:
            print("busiest addresses:")
            for a in sorted(m.hist, key=lambda k: -m.hist[k])[:12]:
                print("   $%08X  %d" % (a, m.hist[a]))
        if "--fb" in argv:
            dump_fb(m, argv[argv.index("--fb") + 1])
        return

    if "--fb" in argv:
        dump_fb(m, argv[argv.index("--fb") + 1])
    print("\nmemory regions touched (by top byte of the bit address):")
    for r in sorted(m.touched):
        note = ""
        if r == FB_BASE >> 24:
            note = "  <- frame buffer"
        elif r == IO_BASE >> 24:
            note = "  <- on-chip I/O registers"
        print("   $%02X......  %d accesses%s" % (r, m.touched[r], note))


SCRATCH_BIT = 0x10000000        # somewhere the renderer's own map does not use
SENTINEL = 0x00000020           # a return address that means "the call finished"
WALKER = 0xFE009D80             # the display-list walker, from opcode 6's handler


def demo_list():
    """A display list in the format DEVICES.md describes: one viewport, one
    object with the identity transform and a string item. Built here rather
    than captured, because a cockpit that has not started a game never sends
    one - so this is the first list the renderer has ever been handed."""
    text = b"BATTLETECH"
    # Two header longwords: the walker skips 0x40 bits before its first record,
    # and the 68020's copy loop takes its length from the first of them.
    words = [0, 0]
    words += [8, 10, 0, 0, 479, 359, 480, 360, 239, 179, 0, 0]
    obj = [1, 0]                                # type, length - filled in
    obj += [0x3F800000, 0, 0, 0, 0x3F800000, 0, 0, 0, 0x3F800000, 0, 0, 0]
    obj += [0, 0x3F800000, 1, 0, 0, 479, 359] + [0] * 13 + [1]
    items = [0x1E0]
    pad = text + b"\0" * (4 - len(text) % 4)
    for i in range(0, len(pad), 4):             # bytes reversed per longword
        items.append(int.from_bytes(pad[i:i + 4][::-1], "big"))
    items.append(0)
    obj += items
    obj[1] = len(obj) - 2
    words += obj
    # A type 2 record is the draw order: 1-based indices into the objects the
    # type 1 records collected, ending at a negative one. Without it the
    # renderer collects the list and draws none of it.
    words += [2, 2, 1, 0xFFFFFFFF]
    words += [0xFFFFFFFF]
    words[0] = len(words)
    return words


def load_list(m, words):
    for i, v in enumerate(words):
        m.wl(SCRATCH_BIT + i * 32, v)
    return SCRATCH_BIT


def dump_fb(m, path):
    """Write what is in the frame buffer as a PGM, so a frame can be looked at.

    The geometry is the renderer's own: DPTCH (B3) bits per row and PSIZE bits
    per pixel, over the span between the two buffers the main loop sets up at
    $A0000000 and $A0400000 - which at 8192 bits a row and 8 bits a pixel is
    1024 by 512.
    """
    pitch, psize = m.b[3] or 0x2000, m.psize
    width, height = max(1, pitch // psize), max(1, 0x400000 // pitch)
    shift = max(0, psize - 8)                   # scale deeper pixels to 8 bits
    rows = [bytes((m.field_read(FB_BASE + y * pitch + x * psize, psize) >> shift)
                  & 0xFF for x in range(width)) for y in range(height)]
    with open(path, "wb") as fh:
        fh.write(("P5\n%d %d\n255\n" % (width, height)).encode())
        for r in rows:
            fh.write(r)
    print("frame buffer: %dx%d at %d bpp -> %s, %d non-zero pixels"
          % (width, height, psize, path,
             sum(1 for r in rows for v in r if v)))


def selftest():
    """The three decodings that were wrong, each pinned by an assertion.

    Every one of them cost a day: a store where a load belonged left the
    display interrupt's pending bit set forever; MMFM's mask read backwards
    popped the saved register into the stack pointer; and SUBXY's flags are not
    the flags of an ordinary subtract.
    """
    def machine(words, **regs):
        m = Machine(0)
        for i, w in enumerate(words):
            m.mem[i * WORD] = w
        for k, v in regs.items():
            (m.b if k[0] == "b" else m.a)[int(k[1:])] = v
        return m

    # MOVE @addr,Rd loads; MOVE Rs,@addr stores. Both at field 1 = 32 bits.
    m = machine([0x0740, 0x07A0, 0x8000, 0x0000, 0x0780, 0x9000, 0x0000])
    m.wl(0x8000, 0xDEADBEEF)
    run(m, 3, 0)
    assert m.a[0] == 0xDEADBEEF, "MOVE @addr,Rd must load"
    assert m.rl(0x9000) == 0xDEADBEEF, "MOVE Rs,@addr must store"

    # MMTM's mask names A0 in bit 15, MMFM's in bit 0. The firmware's own
    # matched pairs are #$8000/#$0001 and #$E000/#$0007.
    m = machine([0x098F, 0xE000, 0x09AF, 0x0007], a0=1, a1=2, a2=3, a15=0x40000)
    run(m, 1, 0)
    m.a[0] = m.a[1] = m.a[2] = 0
    run(m, 1, 0)
    assert (m.a[0], m.a[1], m.a[2]) == (1, 2, 3), "MMTM/MMFM must round-trip"
    assert m.a[15] == 0x40000, "and leave the stack where it found it"

    # SUBXY: N from the X halves being equal, Z from the Y halves.
    m = machine([0xE200 | (1 << 5) | 0], a0=(7 << 16) | 3, a1=(7 << 16) | 3)
    run(m, 1, 0)
    assert m.a[0] == 0 and m.n == 1 and m.z == 1
    m = machine([0xE200 | (1 << 5) | 0], a0=(7 << 16) | 3, a1=(7 << 16) | 9)
    run(m, 1, 0)
    assert m.a[0] == (0 << 16) | 0xFFFA, "X borrows without touching Y"
    assert m.n == 0 and m.z == 1 and m.v == 1

    # FILL takes everything from the B file and nothing from the opcode.
    m = machine([0x0FC0], b2=0x1000, b3=0x100, b7=(2 << 16) | 3, b9=0x1234)
    m.mem[PSIZE_REG] = 16
    run(m, 1, 0)
    for a in (0x1000, 0x1010, 0x1020, 0x1100, 0x1110, 0x1120):
        assert m.field_read(a, 16) == 0x1234, "FILL missed %04X" % a
    assert m.field_read(0x1030, 16) == 0, "FILL ran past DYDX"
    assert m.pixels == 6

    # A binary source expands one bit per pixel into COLOR1 and COLOR0, which
    # is how the cockpit draws text.
    m = machine([0x0F80], b0=0x2000, b1=8, b2=0x3000, b3=0x100,
                b7=(1 << 16) | 4, b8=0x1111, b9=0x7777)
    m.mem[PSIZE_REG] = 16
    m.field_write(0x2000, 4, 0b1101)            # bit 0 first: 1, 0, 1, 1
    run(m, 1, 0)
    assert [m.field_read(0x3000 + i * 16, 16) for i in range(4)] ==         [0x7777, 0x1111, 0x7777, 0x7777], "binary PIXBLT did not expand"

    # Field access is bit-addressed and must not disturb its neighbours.
    m = machine([])
    m.field_write(0x37, 5, 0x1F)
    assert m.field_read(0x37, 5) == 0x1F
    assert m.field_read(0x36, 1) == 0 and m.field_read(0x3C, 1) == 0
    print("selftest: ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main(sys.argv)
