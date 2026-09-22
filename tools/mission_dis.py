#!/usr/bin/env python3
"""Disassemble the cockpit's mission bytecode.

The missions are programs for a 162-opcode interpreter in the ROM (see
`tools/missions.py` for the routine table and DEVICES.md for the machine). To
read one you need two things: where a routine starts, and how many operand
bytes each opcode takes.

Both come out of the ROM rather than out of a guess, and the second is then
held up against a run of the real interpreter (`--trace`).

**Where a routine starts.** `0x021186FC` walks the table comparing names, and
on a match reads the entry's 16-bit value and *adds the table's own address*.
So the program counter is `table + offset`, and the name table sits at the
front of the blob it indexes.

**How long an instruction is.** Every handler that takes an operand begins by
stepping the interpreter's program counter, and that step is one instruction:
`addq.l #1,(-$10e,A6)`. Counting those in a handler, up to the `bra` back to
the fetch loop, gives the operand length - measured from the handler rather
than assumed from a table someone typed in. Handlers that pass the program
counter to a reader instead have their reader counted the same way.

usage: mission_dis.py <ROM3_0> [NAME] [--base HEX] [--limit N]
       mission_dis.py <ROM3_0> --lengths
       mission_dis.py <ROM3_0> --trace <battlepod --vmtrace output>
       mission_dis.py <ROM3_0> --reach
       mission_dis.py <ROM3_0> --strings
       mission_dis.py --selftest
"""
import re
import struct
import sys

BASE = 0x020FFFE4
TABLE = 0x0216B378          # the routine table, and the bytecode's own base
DISPATCH = 0x02119762       # the 162-entry jump table
JUMP_ORIGIN = 0x021198BA    # what its offsets are relative to
BAD_OPCODE = 0x0211972E     # the arm that reports an unknown opcode
NOPCODE = 162

FRAME_PC = 0xFEF2               # (-$10e,A6), the interpreter's program counter
STEP_PC = b"\x52\xae\xfe\xf2"   # addq.l #1,(-$10e,A6)
PUSH_PC = b"\x48\x6e\xfe\xf2"   # pea (-$10e,A6)
PASS_PC = b"\x2f\x2e\xfe\xf2"   # move.l (-$10e,A6),-(A7)
BRA_W = 0x6000                  # bra with a 16-bit displacement

# An arm that hands the program counter to a helper consumes its operand inside
# that helper. There are several such helpers, and hardcoding the one we first
# met (`0x0211995C`) left two opcodes short, which desynchronised any walk that
# reached them. So read the helper instead: a reader steps *its own* copy of the
# pointer with `addq.l #1,(-$4,A6)` once per byte, and may call other readers.
#
#   0211995C  two steps               - a big-endian 16-bit operand
#   021199A8  two calls to 0211995C   - 16.14 fixed point, `hi + lo/16384`
#   0211A80C  a loop                  - an $FF-terminated byte list
#
# A reader with a backward branch consumes a number of bytes that depends on
# the data, and is reported as such rather than guessed at.
#
# A reader steps whatever frame cell its pointer argument lives in, and that is
# not always the same one: `0x0211995C` keeps it in `(-$4,A6)` and steps
# `52AE FFFC`, while `0x0211A650` - which `0x07` feeds - works on the caller's
# argument in place and steps `52AE 000C`. Matching only the first spelling
# read `0x07` and `0x08` as zero-length, and since their handlers also write
# the program counter back they were taken for jumps. They are ordinary
# instructions with eight and six operand bytes.
STEP_ANY = b"\x52\xae"          # addq.l #1,(d16,A6)
RTS = 0x4E75
VARIABLE = None


def handlers(data, base=BASE, dispatch=DISPATCH):
    """opcode -> handler address, or None for the unknown-opcode arm."""
    out = []
    at = dispatch - base
    for k in range(NOPCODE):
        v = struct.unpack(">h", data[at + 2 * k:at + 2 * k + 2])[0]
        t = JUMP_ORIGIN + v
        out.append(None if t == BAD_OPCODE else t)
    return out


def call_target(data, at, base=BASE):
    """(target, next offset) for a jsr/bsr at `at`, or None if it is not one."""
    w = (data[at] << 8) | data[at + 1]
    if w == 0x4EB9:                                     # jsr abs.l
        return struct.unpack(">I", data[at + 2:at + 6])[0], at + 6
    if w in (0x4EBA, 0x6100):                           # jsr (d16,PC) / bsr.w
        return base + at + 2 + struct.unpack(">h", data[at + 2:at + 4])[0], at + 4
    if (w >> 8) == 0x61 and (w & 0xFF) not in (0x00, 0xFF):     # bsr.b
        return base + at + 2 + struct.unpack(">b", data[at + 1:at + 2])[0], at + 2
    return None


def call_near(data, at, base=BASE, span=12):
    """The first call within a few words of `at` - the reader a `pea` feeds.

    The call does not always follow the `pea` immediately: `0x09`'s arm pushes
    a second argument in between, and requiring adjacency read its operand as
    zero bytes long.
    """
    for j in range(at, at + span, 2):
        c = call_target(data, j, base)
        if c:
            return c
    return None


# A word-by-word scan cannot tell an instruction from the middle of one, and
# the 68881's extension words alias as branches: `fmove.s FP0,(-$4,A6)` is
# `F22E 6400 FFFC`, whose middle word reads as a `bcc.w` with a negative
# displacement - so every reader that stored a float was declared a loop. The
# coprocessor instructions are the only multi-word forms in these helpers, so
# skipping them by their real length is enough to keep the scan aligned.
FSIZE = {0: 4, 1: 4, 2: 12, 3: 12, 4: 2, 5: 8, 6: 2}    # source specifier

BCC_W = (0x6000, 0x6200, 0x6300, 0x6400, 0x6500, 0x6600,
         0x6700, 0x6C00, 0x6D00, 0x6E00, 0x6F00)


def fpu_len(data, at):
    """Length of the coprocessor instruction at `at`, or 0 if it is not one."""
    w = (data[at] << 8) | data[at + 1]
    if (w & 0xFF00) != 0xF200:
        return 0
    n = 4
    mode, reg = (w >> 3) & 7, w & 7
    if mode in (5, 6):
        n += 2
    elif mode == 7:
        if reg in (0, 2, 3):
            n += 2
        elif reg == 1:
            n += 4
        elif reg == 4:
            ext = (data[at + 2] << 8) | data[at + 3]
            n += FSIZE.get((ext >> 10) & 7, 2)
    return n


PUSH_CELL = (b"\x2f\x2e", b"\x48\x6e")      # move.l (d16,A6),-(A7) / pea (d16,A6)


def handed_pointer(data, at, back=8):
    """Was a frame cell pushed as an argument just before the call at `at`?

    A reader takes the stream pointer as an argument and gives back how far it
    got; a routine called with anything else - a string, a register - is not
    reading the stream and must not be charged for the `addq.l`s inside it.
    """
    for j in range(max(0, at - back), at, 2):
        if data[j:j + 2] in PUSH_CELL:
            return True
    return False


def reader_cost(data, addr, base=BASE, span=0x200, seen=()):
    """How many operand bytes a stream reader consumes, or VARIABLE."""
    if addr in seen or len(seen) > 4:
        return VARIABLE
    seen = seen + (addr,)
    at = addr - base
    if not (0 <= at < len(data) - 4):
        return VARIABLE
    n = 0
    i = at
    end = min(at + span, len(data) - 6)
    while i < end:
        if data[i:i + 2] == STEP_ANY and \
           ((data[i + 2] << 8) | data[i + 3]) != FRAME_PC:
            n += 1
            i += 4
            continue
        f = fpu_len(data, i)
        if f:
            i += f
            continue
        w = (data[i] << 8) | data[i + 1]
        if w == RTS:
            return n
        if (w & 0xFF00) == 0x6000 and w != 0x6000:          # bcc.b
            if struct.unpack(">b", data[i + 1:i + 2])[0] < 0:
                return VARIABLE                              # a loop: data
        if w in BCC_W and struct.unpack(">h", data[i + 2:i + 4])[0] < 0:
            return VARIABLE
        c = call_target(data, i, base)
        if c:
            # Only a call that is *handed the pointer* is another reader.
            # `0x0211A650` calls the firmware's printf on its bad-operand path,
            # and following that into a routine that happens to contain an
            # `addq.l` charged `0x07` an operand byte it does not have.
            if handed_pointer(data, i):
                sub = reader_cost(data, c[0], base, span, seen)
                if sub is VARIABLE:
                    return VARIABLE
                n += sub
            i = c[1]
            continue
        i += 2
    return VARIABLE


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
        if data[i:i + 4] == PUSH_PC or data[i:i + 4] == PASS_PC:
            # An arm that hands the program counter to a reader consumes its
            # operand in there. Counting only the byte steps missed those, and
            # the disassembly ran off the rails at the first one. It hands it
            # over by address (`pea`) or by value (`move.l ... ,-(A7)`), and
            # only the first spelling was recognised.
            c = call_near(data, i + 4, base)
            if c:
                sub = reader_cost(data, c[0], base)
                if sub is VARIABLE:
                    return VARIABLE
                n += sub
                i = c[1]
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


# `0x64` is the one arm that hands the program counter to a helper *by value*
# and takes a new one back, so counting the arm's own steps sees neither its
# operand nor its target. Its helper `0x02119CC4` reads one length byte, pushes
# the address of the bytes *after* it onto the typed stack as a type 0 value
# (via `0x02119AA8`, which is the push itself: stack pointer at `[0x021B74B6]`,
# frame 0x4C, type at +0 and payload at +4), and returns that address plus the
# length.
#
# So `0x64` **pushes a string literal**: one length byte, that many bytes of
# NUL-terminated text, and execution resumes after them. `exitScreen`,
# `STATS (kills/deaths)`, `Speed %1d` and `VGL Universe 34933` all arrive this
# way, and `0x0A` - which follows a `0x64` in 70 cases out of 70 - is the
# interpreter's printf: a `%` test, a `*` test, a ctype table at `0x0218247F`
# and a 39-byte output buffer at `0x021827BC`.
#
# The skipped bytes are *data*. Walking them as code is how the reading that
# they were inline routines survived as long as it did: `0x25` is `%` and
# `0x20` is a space, so every format string disassembles into what look like
# object-creating opcodes. The trace agrees with the resume address 127 times
# out of 127.
NUL = bytes(1)
STRING_PUSH = 0x64
EXTRA_OPERAND = {STRING_PUSH: 1}

# `0x09`'s reader `0x0211A80C` loops until it reads `$FF`, storing each byte as
# a longword into the mission record at `+0x1CA0` and padding the rest of a
# two-entry array with `$FFFFFFFF`. The count is data, not a constant, so the
# handler cannot say how long the operand is - but the stream can, and reading
# it there is not a guess. The trace shows two- and three-byte operands.
TERMINATED = {0x09: 0xFF}

# `0x42` is a call, not a jump: `0x44` returns to the instruction after it. The
# trace shows the pair - a `0x44` at `0x0216B4CA` lands on `0x0216BA8C`, which
# is exactly where the `0x42` at `0x0216BA89` came from. So a call's
# fall-through is reachable code, which `successors` already says, and a
# return has no successor of its own worth naming.
RETURN = 0x44


def lengths(data, base=BASE):
    hs = handlers(data, base)
    out = [operand_len(data, h, base) for h in hs]
    for op, n in EXTRA_OPERAND.items():
        if hs[op] is not None and out[op] is not VARIABLE:
            out[op] += n
    return out, hs


def inst_len(data, pc, lens, base=BASE):
    """Total bytes of the instruction at `pc`, or None if it cannot be read."""
    op = data[pc - base]
    if op in TERMINATED:
        end = data.find(bytes([TERMINATED[op]]), pc + 1 - base)
        return None if end < 0 else end + 1 - (pc - base)
    return None if lens[op] is VARIABLE else 1 + lens[op]


def successors(data, pc, lens, hs, base=BASE):
    """Where execution can go from the instruction at `pc`."""
    op = data[pc - base]
    n = inst_len(data, pc, lens, base)
    if n is None:
        return []
    if op == STRING_PUSH:
        return [pc + 2 + data[pc + 1 - base]]     # the bytes between are text
    if op == RETURN:
        return []
    out = [pc + n]
    if touches_pc(data, hs[op], base) and lens[op] == 2:
        d16 = struct.unpack(">h", data[pc + 1 - base:pc + 3 - base])[0]
        out.append(pc + n + d16)
    return out


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
        total = inst_len(data, pc, lens, base)
        if total is None:
            print("  %08X  %02X  <operand cannot be read>" % (pc, op))
            return
        args = data[o + 1:o + total]
        note = ""
        if op == STRING_PUSH:
            n = args[0]
            text = data[o + 2:o + 2 + n].split(NUL)[0].decode("latin-1")
            print("  %08X  %02X  %02X   push %r" % (pc, op, n, text))
            pc += 2 + n
            continue
        if touches_pc(data, hs[op], base):
            note = "   jump"
            if lens[op] == 2:
                d16 = struct.unpack(">h", args[:2])[0]
                note = "   jump %+d -> %08X" % (d16, pc + total + d16)
        print("  %08X  %02X%s%s" %
              (pc, op, "  " + " ".join("%02X" % b for b in args) if args else "",
               note))
        pc += total


# The ROM carries two script tables and picks between them at boot:
# `0x0211786C` tests `[0x021B74B2]` and writes either `0x0216C8EA` or
# `0x0216B378` into `[0x0216F49C]`, which is what the name lookup walks. The
# first is BattleTech; the second is Red Planet and Martian Football, the other
# titles this cabinet ran. Only one of them had ever been read.
TABLES = {"BattleTech": 0x0216B378, "RedPlanet": 0x0216C8EA}

# The four opcodes that make something. `0x24` calls `Create_Thing`; `0x21`
# calls the class 4 constructor. Each constructor has exactly one caller and it
# is its mission opcode, so if no script reaches one of these, nothing a script
# does creates anything.
CREATION = (0x20, 0x21, 0x22, 0x23, 0x24, 0x25)


def reachable(data, table, base=BASE):
    """Every instruction any routine in `table` can reach, as pc -> opcode."""
    import missions
    lens, hs = lengths(data, base)
    seen = {}
    work = [table + e for _, e in missions.routines(data, base, table)]
    while work:
        pc = work.pop()
        if pc in seen or not (0 <= pc - base < len(data)):
            continue
        op = data[pc - base]
        if op >= NOPCODE or hs[op] is None:
            continue
        seen[pc] = op
        work += successors(data, pc, lens, hs, base)
    return seen


def report_reach(data, base=BASE):
    import missions
    for name, table in TABLES.items():
        seen = reachable(data, table, base)
        ops = set(seen.values())
        print("%s routines: %d" %
              (name, len(missions.routines(data, base, table))))
        print("%s instructions: %d" % (name, len(seen)))
        print("%s opcodes: %d" % (name, len(ops)))
        print("%s creation opcodes: %d" %
              (name, sum(1 for o in seen.values() if o in CREATION)))


def literals(data, table, base=BASE):
    """(routine, [string]) for every literal a routine can reach.

    The strings are the fastest description of what a script is *for*. Reading
    them is how `Martian Football` stopped being a name in a table: Red Team,
    Blue Team, Runner, Blocker, Crusher, and a broadcast caption.
    """
    import missions
    lens, hs = lengths(data, base)
    out = []
    for name, entry in missions.routines(data, base, table):
        seen = set()
        work = [table + entry]
        found = []
        while work:
            pc = work.pop()
            if pc in seen or not (0 <= pc - base < len(data)):
                continue
            op = data[pc - base]
            if op >= NOPCODE or hs[op] is None:
                continue
            seen.add(pc)
            if op == STRING_PUSH:
                n = data[pc + 1 - base]
                found.append(data[pc + 2 - base:pc + 2 + n - base]
                             .split(NUL)[0].decode("latin-1"))
            work += successors(data, pc, lens, hs, base)
        out.append((name, list(dict.fromkeys(found))))
    return out


def report_strings(data, base=BASE):
    for game, table in TABLES.items():
        print("%s:" % game)
        for name, texts in literals(data, table, base):
            if texts:
                print("  %-18s %s" % (name, " | ".join(texts)))


TRACE = re.compile(r"([0-9A-F]{8}):([0-9A-F]{2})")


def check_trace(data, path, base=BASE):
    """Hold the instruction lengths up against a run of the real interpreter.

    `battlepod --vmtrace` logs the interpreter's own program counter and the
    opcode it dispatched, so consecutive entries give the exact length of every
    instruction the pod executed. That is the only ground truth there is for
    lengths inferred from handlers, and it is what caught `0x09` and `0x60`.

    The logged counter points one past the opcode, because the fetch has
    already happened by the time the dispatch is reached.
    """
    lens, hs = lengths(data, base)
    ev = [(int(a, 16) - 1, int(b, 16)) for a, b in TRACE.findall(open(path).read())]
    if not ev:
        sys.exit("no ADDRESS:OP entries in %s - is that a --vmtrace dump?" % path)
    ok = bad = jumps = 0
    unpredicted = {}
    for (pc, op), (nxt, _) in zip(ev, ev[1:]):
        if touches_pc(data, hs[op], base) and op not in (STRING_PUSH,):
            # A jump's target comes from the stream or from the stack; the
            # successor rule covers it where it can, and the rest is counted.
            jumps += 1
            if op != RETURN and nxt not in successors(data, pc, lens, hs, base):
                unpredicted[op] = unpredicted.get(op, 0) + 1
            continue
        n = inst_len(data, pc, lens, base)
        if op == STRING_PUSH:
            n = 2 + data[pc + 1 - base]
        if n == nxt - pc:
            ok += 1
        else:
            bad += 1
            if bad < 8:
                print("  %08X  %02X  length %s, the pod stepped %d" %
                      (pc, op, n, nxt - pc))
    print("trace entries: %d" % len(ev))
    print("distinct opcodes: %d" % len(set(o for _, o in ev)))
    print("straight-line lengths confirmed: %d" % ok)
    print("control flow skipped: %d" % jumps)
    print("lengths the trace contradicts: %d" % bad)
    print("jumps the successor rule misses: %d" % sum(unpredicted.values()))
    for op, k in sorted(unpredicted.items()):
        print("    %02X  %d" % (op, k))


def selftest():
    # a fabricated handler: two pc steps then a branch back
    blob = bytearray(0x200)
    blob[0x100:0x108] = STEP_PC + STEP_PC
    blob[0x108:0x10A] = b"\x60\x00"
    assert operand_len(bytes(blob), 0x100, 0) == 2
    blob[0x100:0x104] = b"\x60\x00"          # branch straight away
    assert operand_len(bytes(blob), 0x100, 0) == 0
    assert operand_len(bytes(blob), None, 0) == 0

    # a coprocessor store is not a backward branch: F22E 6400 FFFC
    assert fpu_len(b"\xf2\x2e\x64\x00\xff\xfc", 0) == 6
    assert fpu_len(b"\xf2\x3c\x54\x80" + bytes(8), 0) == 12      # fdiv.d #imm
    assert fpu_len(b"\x4e\x75\x00\x00", 0) == 0

    # bsr.b reaches backwards in two bytes; bsr.w and jsr are wider
    assert call_target(b"\x61\xa6", 0, 0x100) == (0x100 + 2 - 90, 2)
    assert call_target(b"\x61\x00\xff\xa4", 0, 0x100) == (0x100 + 2 - 92, 4)
    assert call_target(b"\x4e\x75", 0, 0) is None

    # a reader that only steps its own pointer costs one byte per step
    step = STEP_ANY + b"\xff\xfc"
    r = bytearray(step + step + b"\x4e\x75" + bytes(8))
    assert reader_cost(bytes(r), 0, 0) == 2
    r[0:4] = b"\x60\xfe\x00\x00"                                 # a loop
    assert reader_cost(bytes(r), 0, 0) is VARIABLE

    # a terminated operand is read from the stream, not from the handler
    assert inst_len(bytes([0x09, 1, 2, 0xFF, 0]), 0, {0x09: VARIABLE}, 0) == 4
    assert inst_len(bytes([0x09, 1]), 0, {0x09: VARIABLE}, 0) is None
    assert inst_len(bytes([0x05, 0xAA]), 0, {0x05: 1}, 0) == 2
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
    if "--strings" in argv:
        sys.path.insert(0, "tools")
        return report_strings(data, base)
    if "--reach" in argv:
        sys.path.insert(0, "tools")
        return report_reach(data, base)
    if "--trace" in argv:
        return check_trace(data, argv[argv.index("--trace") + 1], base)
    if "--lengths" in argv:
        lens, hs = lengths(data, base)
        named = sum(1 for h in hs if h is not None)
        print("opcodes with a handler: %d" % named)
        print("opcodes that are control flow: %d" %
              sum(1 for h in hs if touches_pc(data, h, base)))
        print("opcodes whose operand length depends on the stream: %d" %
              sum(1 for k, h in enumerate(hs)
                  if h is not None and lens[k] is VARIABLE))
        fixed = [n for n in lens if n is not VARIABLE]
        for n in range(max(fixed) + 1):
            print("  taking %d operand bytes: %d" %
                  (n, sum(1 for k, h in enumerate(hs)
                          if h is not None and lens[k] == n)))
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
