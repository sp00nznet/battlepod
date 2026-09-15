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
        self.touched = {}       # region -> access count, for the report
        self.setf = 0           # field-parameter writes this model ignores

    # ---- memory -------------------------------------------------------
    def note(self, addr):
        self.touched[addr >> 24] = self.touched.get(addr >> 24, 0) + 1

    def rw(self, addr):
        self.note(addr)
        return self.mem.get(addr & ~0xF, 0)

    def ww(self, addr, v):
        self.note(addr)
        self.mem[addr & ~0xF] = v & 0xFFFF

    def rl(self, addr):
        return self.rw(addr) | (self.rw(addr + WORD) << 16)

    def wl(self, addr, v):
        self.ww(addr, v & 0xFFFF)
        self.ww(addr + WORD, (v >> 16) & 0xFFFF)

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

    def flags(self, v):
        v &= 0xFFFFFFFF
        self.z = 1 if v == 0 else 0
        self.n = 1 if v & 0x80000000 else 0
        return v


def s32(v):
    return v - 0x100000000 if v & 0x80000000 else v


def run(m, steps, trace):
    """Execute until something unimplemented turns up, and say what it was."""
    executed = 0
    while executed < steps:
        here = m.pc
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
            m.setreg(f, rd, m.rl(m.fetchl()))
            continue

        # register indirect, the forms this code actually uses
        if op & 0xFC00 == 0x8000:                               # MOVE Rs,*Rd
            m.wl(m.reg(f, rd), m.reg(f, rs))
            continue
        if op & 0xFC00 == 0x8400:                               # MOVE *Rs,Rd
            m.setreg(f, rd, m.rl(m.reg(f, rs)))
            continue
        if op & 0xFC00 == 0x9000:                               # MOVE Rs,*Rd+
            a = m.reg(f, rd)
            m.wl(a, m.reg(f, rs))
            m.setreg(f, rd, a + 32)
            continue
        if op & 0xFC00 == 0x9400:                               # MOVE *Rs+,Rd
            a = m.reg(f, rs)
            m.setreg(f, rd, m.rl(a))
            m.setreg(f, rs, a + 32)
            continue
        if op & 0xFC00 == 0xB400:                               # MOVE *Rs(o),Rd
            o = m.fetch()
            m.setreg(f, rd, m.rl(m.reg(f, rs) + (o - 0x10000 if o & 0x8000 else o)))
            continue
        if op & 0xFC00 == 0xB000:                               # MOVE Rs,*Rd(o)
            o = m.fetch()
            m.wl(m.reg(f, rd) + (o - 0x10000 if o & 0x8000 else o), m.reg(f, rs))
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

        # Field-parameter setup. 0x0540 and 0x0740 differ by exactly the
        # field-select bit, which is SETF for field 0 and field 1; 0x0620 and
        # 0x0660 behave the same way - all four are one word and are followed
        # by ordinary instructions, never by an address. This model always
        # moves 32 bits, so they have no effect here beyond letting the stream
        # continue. Anything that depends on a real field size will be wrong.
        if 0x0540 <= op <= 0x077F and (op & 0xFFE0) not in (0x0580, 0x05A0,
                                                            0x0780, 0x07A0):
            m.setf += 1
            continue

        m.halted = "unimplemented opcode %04X at %08X" % (op, here)
        return executed
    return executed


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
    for i in range((len(blob) - skip) // 2):
        m.mem[base + i * WORD] = struct.unpack("<H", blob[skip + i * 2:skip + i * 2 + 2])[0]
    # file offset `skip` is TI 0xFE000000, which is also the entry point
    print("loaded %d words at $%08X" % (len(m.mem), base))

    n = run(m, steps, opt("--trace", 0))
    print("\nexecuted %d instructions" % n)
    print("stopped: %s" % (m.halted or "step limit reached"))
    print("pc $%08X  sp $%08X" % (m.pc, m.a[15]))
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
