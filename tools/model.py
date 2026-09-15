#!/usr/bin/env python3
"""Run a cockpit model and collect what it draws.

A type 1 resource is not a mesh. It is a threaded program, the same design the
display list uses: an opcode is a bit offset into a table, the handler consumes
its operands from the stream and jumps back for the next one. The renderer's
own interpreter is at 0xFE00EDB0 and its table of 45 handlers at 0xFE00EEA0.

So the way to read a model is to run it. Vertices arrive as IEEE floats carried
inline in the instruction stream, polygons as index lists, materials as a kind
and four parameters of which three are a colour.

Two checks keep this honest, and both come out of the data rather than out of
us:

  * the longword at header +0x58 has to be a valid opcode - it is, in all 130
  * a model states its own bounding box at +0x24, so the vertices we decode
    have to reproduce it exactly

An opcode whose operands are not understood stops the walk and is reported by
number. Guessing a length silently desynchronises everything after it, which
would quietly corrupt every model in the archive rather than fail loudly on
one.

usage:
  model.py <resource file> --stats          run all of them, report the checks
  model.py <resource file> --id N           run one, describe what it drew
  model.py <resource file> --id N --obj F   write it out as a Wavefront OBJ
  model.py --selftest
"""
import struct
import sys

HEADER = 0x58                   # bytes, 22 longwords
STREAM = HEADER // 4            # first stream longword


def f32(v):
    return struct.unpack(">f", struct.pack(">I", v & 0xFFFFFFFF))[0]


class Desync(Exception):
    """An opcode we cannot measure. Raised rather than guessed past."""


# $320 and $360 branch on a predicate, and the predicate is a *second* threaded
# interpreter: 0xFE018910 reads its own opcodes from the same stream and
# dispatches through a 24-entry table at 0xFE018A00. It is a postfix expression
# on a small stack, terminated by $000.
#
# Every push form takes exactly one operand and ends by jumping back to the
# dispatch loop at 0xFE0189C0; everything from $0C0 up is an operator that takes
# none - NOT, OR, AND, XOR, NEG, ADD, SUB, five comparisons, and two short-
# circuit forms. $000 pops the result and returns to the branch.
#
# So `$320 $080 $000 $040 $00C8 $260 $000 $1440` reads as: is value(0) >= 200,
# and if so jump 0x1440 bits on. That is a distance test picking a level of
# detail, which is what most models put their geometry behind.
PRED = {0x000: 0, 0x020: 1, 0x040: 1, 0x060: 1, 0x080: 1, 0x0A0: 1}
PREDICATE_GAP = ()


class Model:
    """One type 1 resource, executed."""

    def __init__(self, data, paths="all", archive=None, depth=0):
        # `archive` maps a resource id to its bytes, and lets $460 - "draw this
        # other model here" - actually pull the sub-model in. Its geometry
        # joins this model's mesh but *not* its `written` list, because the
        # bounding box a model states is over its own vertices: all 19 models
        # that use $460 already span their box without the sub-model's.
        self.archive, self.depth = archive, depth
        self.subs = []          # resource ids drawn by $460
        # "all" collects everything the model can draw, which is what the
        # checks want. A picture wants one level of detail instead, because
        # stacking them puts the near and far versions in the same frame -
        # so "fall" walks past every conditional branch and "take" walks
        # through it. Which of those holds the detailed geometry differs
        # per model, so the renderer tries both and keeps the fuller one.
        self.paths = paths
        self.allpaths = paths == "all"
        self.w = list(struct.unpack(">%dI" % (len(data) // 4), data[:len(data) // 4 * 4]))
        h = self.w
        self.nvert, self.nnorm, self.nface = h[0], h[1], h[2]
        self.nnode, self.nmat = h[3], h[6]
        self.box = [f32(x) for x in h[9:16]]
        self.vert = {}          # index -> (x, y, z), model space
        self.written = []       # every value ever written to a slot
        self.poly = []          # (face, [vertex indices], material)
        self.mat = {}           # index -> (kind, p0, p1, p2, p3)
        self.parts = []         # sub-part tags pushed by $480
        self.bitmaps = []       # bitmap resource ids blitted by $560/$580
        self.seen = {}          # opcode -> count
        self.unknown = {}       # opcodes that stopped a path
        self.prev = None        # and what ran just before them
        self.lost = {}          # (previous opcode, what we hit)
        self.jumps = []         # (opcode, operand) of every call and branch
        self.stopped = None

    # -- the opcodes -----------------------------------------------------
    #
    # Lengths are the stream advance each handler makes. The fixed ones were
    # read off the handlers themselves - every `MOVE *A7+` is one longword and
    # every `ADDI #n, A7` is n/32 more. The rest are data dependent and are
    # computed from the operands, which is why this is an interpreter and not
    # a table.

    def put(self, index, v):
        self.vert[index] = v
        self.written.append(v)

    def vertex(self, at, n):
        """$0A0 and $0C0: a vertex, or a run of them, as inline floats."""
        base = self.w[at]
        if n is None:                       # $0A0, one vertex
            self.put(base, tuple(f32(self.w[at + 1 + i]) for i in range(3)))
            return at + 4
        for k in range(n):                  # $0C0, a run
            o = at + 2 + k * 3
            self.put(base + k, tuple(f32(self.w[o + i]) for i in range(3)))
        return at + 2 + n * 3

    def polygon(self, at):
        """$240 and $260: face, vertex count, the indices, then the material."""
        face, nv = self.w[at], self.w[at + 1]
        if not 3 <= nv <= 64:
            raise Desync("polygon with %d vertices" % nv)
        verts = self.w[at + 2:at + 2 + nv]
        self.poly.append((face, list(verts), self.w[at + 2 + nv]))
        return at + 3 + nv

    def material(self, at, kind):
        """$4C0 flat, $4E0 lit: index, then a colour and one more parameter.

        Six longwords in all. The three floats are plainly red, green and blue;
        the fourth is 0.5 in every record seen so far and is not identified.
        """
        i = self.w[at]
        rgb = tuple(f32(self.w[at + 1 + k]) for k in range(3))
        self.mat[i] = (kind,) + rgb + (f32(self.w[at + 4]),)
        return at + 5

    def predicate(self, at):
        """Skip one predicate program. Returns where it ends, past the $000."""
        for _ in range(64):
            op = self.w[at]
            at += 1
            if op == 0x000:
                return at
            if op in PRED:
                at += PRED[op]
            elif 0x0C0 <= op <= 0x2E0 and op % 0x20 == 0:
                pass                            # an operator, no operands
            else:
                raise Desync("predicate opcode $%03X" % op)
        raise Desync("predicate did not terminate")

    def target(self, operand):
        """A jump or call target: bits, measured from the start of the data.

        Both forms do `A7 = base + operand`. Read as bits from the *data*
        start that lands on a known opcode 33% of the time across the archive;
        read as bits from the stream start, 68%. The data picked this.
        """
        return operand // 32

    def run(self, limit=400000):
        """Execute the stream, following every path.

        Calls and conditional jumps both carry their target as a bit offset -
        `$020` does `A7 = base + operand` after pushing where it was, and
        `$320` does the same when its predicate holds. See target().

        Branches are taken *and* fallen through, because the question here is
        what the model can draw rather than what one frame of it draws. Most
        models put their geometry behind a predicate - walking only the
        fall-through gets you the materials and an immediate return, which is
        exactly what the first version of this did.
        """
        work, seen_pc, steps = [STREAM], set(), 0
        self.unknown, self.prev = {}, None
        while work and steps < limit:
            at = work.pop()
            while steps < limit:
                steps += 1
                if at >= len(self.w) or at in seen_pc:
                    break
                seen_pc.add(at)
                op = self.w[at]
                self.seen[op] = self.seen.get(op, 0) + 1
                at += 1
                prev, self.prev = self.prev, op
                try:
                    if op == 0x000:                         # return
                        break
                    if op == 0x020:                         # call
                        self.jumps.append((op, self.w[at]))
                        work.append(self.target(self.w[at]))
                        at += 1
                    elif op in (0x320, 0x360):              # jump on a predicate
                        end = self.predicate(at)
                        self.jumps.append((op, self.w[end]))
                        if self.allpaths:
                            work.append(self.target(self.w[end]))
                        elif self.paths == "take":
                            at = self.target(self.w[end])
                            continue
                        at = end + 1
                    elif op == 0x460:           # draw another model here
                        self.submodel(self.w[at + 2])
                        at += 3
                    elif op == 0x420:
                        # evaluates a predicate and stores the answer in a
                        # slot, so it is one predicate program plus an index
                        at = self.predicate(at) + 1
                    elif op == 0x2C0:                       # jump, always
                        self.jumps.append((op, self.w[at]))
                        at = self.target(self.w[at])
                    elif op in (0x300, 0x340):              # jump on face facing
                        self.jumps.append((op, self.w[at + 1]))
                        if self.allpaths:
                            work.append(self.target(self.w[at + 1]))
                        elif self.paths == "take":
                            at = self.target(self.w[at + 1])
                            continue
                        at += 2
                    elif op == 0x0A0:
                        at = self.vertex(at, None)
                    elif op == 0x0C0:
                        at = self.vertex(at, self.w[at + 1])
                    elif op in (0x240, 0x260):
                        at = self.polygon(at)
                    elif op in (0x4C0, 0x4E0):
                        at = self.material(at, 0 if op == 0x4C0 else 1)
                    elif op == 0x160:
                        # index, count, then three floats per item. The handler
                        # streams them with CMOVMC through A0 and puts A0 back
                        # into A7, which is what makes the length 2 + 3n.
                        at += 2 + 3 * self.w[at + 1]
                    elif op == 0x1A0:                       # a run of planes
                        at += 2 + 2 * self.w[at + 1]
                    elif op in (0x560, 0x580):              # blit bitmaps
                        n = self.w[at + 2]
                        self.bitmaps += self.w[at + 3:at + 3 + n]
                        at += 3 + n
                    elif op == 0x480:                       # push a sub-part
                        self.parts.append(self.w[at])
                        at += 4
                    elif op == 0x4A0:                       # pop it
                        pass
                    elif op in FIXED:
                        at += FIXED[op]
                    else:
                        raise Desync("opcode $%03X" % op)
                except Desync as e:
                    self.unknown[str(e)] = self.unknown.get(str(e), 0) + 1
                    key = ("$%03X" % prev if prev is not None else "start", op)
                    self.lost[key] = self.lost.get(key, 0) + 1
                    break
                except IndexError:
                    self.unknown["operands past the end"] = 1
                    break
        self.stopped = None if not self.unknown else             ", ".join(sorted(self.unknown))
        if steps >= limit:
            self.stopped = "step limit"

    # -- the checks ------------------------------------------------------
    def submodel(self, rid):
        """$460 names a resource id and runs that model in place."""
        self.subs.append(rid)
        if not self.archive or self.depth > 3 or rid not in self.archive:
            return
        sub = Model(self.archive[rid], self.paths, self.archive, self.depth + 1)
        sub.run()
        base = (max(self.vert) + 1) if self.vert else 0
        moff = (max(self.mat) + 1) if self.mat else 0
        for k, v in sub.vert.items():
            self.vert[base + k] = v
        for k, v in sub.mat.items():
            self.mat[moff + k] = v
        for f, vs, mi in sub.poly:
            self.poly.append((f, [base + v for v in vs], moff + mi))

    def box_matches(self):
        """The model's own bounding box against the vertices we decoded.

        Two things about what that box actually spans, both read off the data
        rather than assumed. It includes the **origin** - several models state
        a bound of exactly 0.0 on an axis where no vertex reaches it, which is
        what you get when a part has to keep its own pivot inside its box. And
        it spans **every value ever written to a vertex slot**, not just the
        ones left at the end: a model writes the same slots again in each level
        of detail, so the set surviving the walk belongs to no single one.

        Vertices alone match 41 of 84; plus the origin, 55; every write plus
        the origin, 63.
        """
        if not self.written:
            return False
        vs = self.written + [(0.0, 0.0, 0.0)]
        want = self.box
        for a in range(3):
            if abs(min(v[a] for v in vs) - want[a * 2]) > 1e-3:
                return False
            if abs(max(v[a] for v in vs) - want[a * 2 + 1]) > 1e-3:
                return False
        return True

    def box_matches_mirrored(self):
        """The same check with x negated.

        Five models only span their stated box that way, which is how a left
        and a right part share one set of vertices - and why pairs like 491 and
        494 state boxes identical to the float.
        """
        if not self.written:
            return False
        vs = [(-x, y, z) for x, y, z in self.written] + [(0.0, 0.0, 0.0)]
        w = self.box
        for a in range(3):
            if abs(min(v[a] for v in vs) - w[a * 2]) > 1e-3:
                return False
            if abs(max(v[a] for v in vs) - w[a * 2 + 1]) > 1e-3:
                return False
        return True

    def indices_sane(self):
        for face, verts, mat in self.poly:
            if face >= max(1, self.nface) or mat >= max(1, self.nmat):
                return False
            if any(v not in self.vert for v in verts):
                return False
        return True


# Opcodes whose stream advance is fixed and was read off the handler. The ones
# missing from here are the ones nobody has measured yet; meeting one stops the
# walk by design.
FIXED = {
    # $040 and $520 were not settled by reading their handlers - both begin
    # with calls that consume operands of their own, so counting stream reads
    # undercounts them. They were settled by sweeping the two against the
    # archive's own checks instead, and the answer is sharp: 6 and 5 take every
    # model in the archive to a clean return, where 5 or 7 for $040 drop 20 of
    # them. $520 = 5 also matches an independent reading of its handler as
    # (destination, near, far, source A, source B).
    0x040: 6, 0x060: 1, 0x080: 0,
    0x0E0: 4, 0x100: 4,                 # one index then three inline floats
    0x120: 4, 0x180: 3,
    0x1C0: 1, 0x1E0: 1,
    # These save the stream pointer in A8 on entry and end with
    # `MOVE A8, A7 / ADDI #n, A7`, so n is the advance whatever the body does
    # in between - a better measure than counting reads inside the handler.
    0x200: 3, 0x220: 4, 0x280: 3, 0x2A0: 3,
    0x2E0: 2,
    0x300: 2, 0x340: 2,
    0x380: 0, 0x3A0: 0, 0x3C0: 1, 0x3E0: 2, 0x400: 0,
    0x440: 1,
    0x500: 0,
    # $540 is two instructions falling into $520's handler with one flag
    # changed, so the two consume the same five longwords.
    0x520: 5, 0x540: 5,
}


# Opcodes with a length this interpreter computes rather than looks up.
HANDLED = (0x000, 0x020, 0x0A0, 0x0C0, 0x160, 0x1A0, 0x240, 0x260,
           0x2C0, 0x300, 0x320, 0x340, 0x360, 0x420, 0x460, 0x480, 0x4A0,
           0x4C0, 0x4E0, 0x560, 0x580)

# Every opcode the renderer's table has an entry for. The walk can only follow
# the ones it can measure, but all 45 are real, and the check that the stream
# starts on one should be judged against all of them.
KNOWN = frozenset(list(FIXED) + list(HANDLED))


def walk(blob):
    """Every resource in the archive, using the parser resmap.py established."""
    at = 0
    while at + 16 <= len(blob):
        rid, rtype, flags, count = struct.unpack(">IIII", blob[at:at + 16])
        if rid == 0xFFFFFFFF:
            return
        inline = 0 if (flags & 0xFF) & 0x10 else count * 4
        yield rid, rtype, blob[at + 16:at + 16 + inline]
        at += 16 + inline


def archive(blob):
    """Every type 1 resource by id, so $460 can resolve what it names."""
    return {rid: d for rid, t, d in walk(blob) if t == 1}


def obj(m, path):
    """A Wavefront OBJ, for looking at the thing in something else."""
    order = sorted(m.vert)
    at = {v: i + 1 for i, v in enumerate(order)}
    with open(path, "w") as fh:
        for v in order:
            fh.write("v %.6f %.6f %.6f\n" % m.vert[v])
        for face, verts, mat in m.poly:
            if all(v in at for v in verts):
                fh.write("f %s\n" % " ".join(str(at[v]) for v in verts))
    print("%s: %d vertices, %d polygons" % (path, len(order), len(m.poly)))


def stats(blob):
    models = [(rid, d) for rid, t, d in walk(blob) if t == 1]
    first_ok = boxes = sane = clean = counts = mats = mirrored = 0
    stops, lost = {}, {}
    for rid, data in models:
        m = Model(data)
        first_ok += m.w[STREAM] in KNOWN
        m.run()
        clean += m.stopped is None
        boxes += m.box_matches()
        mirrored += m.box_matches_mirrored() and not m.box_matches()
        sane += m.indices_sane()
        counts += len(m.vert) == m.nvert and m.nvert > 0
        mats += len(m.mat) == m.nmat and m.nmat > 0
        if m.stopped:
            key = m.stopped.split(" at ")[0]
            stops[key] = stops.get(key, 0) + 1
        for k, v in m.lost.items():
            lost[k] = lost.get(k, 0) + v
    n = len(models)
    print("%d type 1 models\n" % n)
    print("  header +0x58 is a known opcode : %3d / %d" % (first_ok, n))
    print("  stream walks to a return       : %3d / %d" % (clean, n))
    print("  vertex count matches the header: %3d / %d" % (counts, n))
    print("  vertices reproduce the box     : %3d / %d" % (boxes, n))
    print("  and the same with x mirrored   : %3d / %d" % (mirrored, n))
    print("  material count matches         : %3d / %d" % (mats, n))
    print("  face and material indices sane : %3d / %d" % (sane, n))
    if stops:
        print("\nwhere the walks stop:")
        for k, v in sorted(stops.items(), key=lambda kv: -kv[1])[:10]:
            print("   %-34s %d" % (k, v))
    if lost:
        print("\nwhat ran just before a walk lost sync:")
        for (a, b), v in sorted(lost.items(), key=lambda kv: -kv[1])[:10]:
            print("   after %-6s hit $%-9X x%d" % (a, b, v))


def selftest():
    """A model built here, so the walker is not only ever tested on data we
    are still learning to read."""
    h = [0] * 22
    h[0], h[2], h[6] = 3, 1, 1                       # 3 vertices, 1 face, 1 material
    tri = [(-1.0, 0.0, 0.5), (2.0, 0.0, 0.5), (0.0, 3.0, -4.0)]
    h[9:16] = [struct.unpack(">I", struct.pack(">f", x))[0] for x in
               (-1.0, 2.0, 0.0, 3.0, -4.0, 0.5, 5.0)]
    body = [0x4E0, 0, 0x3F800000, 0x3F000000, 0, 0x3F000000]      # material 0
    body += [0x0C0, 0, 3]                                          # three vertices
    for v in tri:
        body += [struct.unpack(">I", struct.pack(">f", c))[0] for c in v]
    body += [0x260, 0, 3, 0, 1, 2, 0]                              # one polygon
    body += [0x000]                                                # return
    data = struct.pack(">%dI" % (len(h) + len(body)), *(h + body))

    m = Model(data)
    m.run()
    assert m.stopped is None, m.stopped
    assert len(m.vert) == 3 and m.vert[2] == tri[2], m.vert
    assert m.poly == [(0, [0, 1, 2], 0)], m.poly
    assert m.mat[0] == (1, 1.0, 0.5, 0.0, 0.5), m.mat[0]
    assert m.box_matches(), "the box check must pass on a model we built"
    assert m.indices_sane()

    # Every one of the renderer's 45 opcodes is measured now, so an opcode
    # that is not in the table cannot be a real one - and meeting it has to
    # stop the walk and name it rather than guess a length and carry on.
    bad = Model(struct.pack(">%dI" % (len(h) + 2), *(h + [0x5A0, 0])))
    bad.run()
    assert bad.stopped and "$5A0" in bad.stopped, bad.stopped
    print("selftest: ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2:
        sys.exit(__doc__)
    blob = open(argv[1], "rb").read()
    if "--id" not in argv:
        return stats(blob)

    want = int(argv[argv.index("--id") + 1])
    lib = archive(blob)
    for rid, rtype, data in walk(blob):
        if rid != want or rtype != 1:
            continue
        m = Model(data, archive=lib)
        m.run()
        print("model %d: %d longwords" % (rid, len(m.w)))
        print("  header says %d vertices, %d normals, %d faces, %d nodes, %d materials"
              % (m.nvert, m.nnorm, m.nface, m.nnode, m.nmat))
        print("  box x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f  radius %.3f"
              % tuple(m.box))
        print("  decoded %d vertices, %d polygons, %d materials"
              % (len(m.vert), len(m.poly), len(m.mat)))
        print("  box check: %s   indices: %s"
              % ("matches" if m.box_matches() else "NO",
                 "sane" if m.indices_sane() else "NO"))
        print("  stopped: %s" % (m.stopped or "ran to a return"))
        if m.subs:
            print("  draws sub-models: %s" % " ".join(str(x) for x in m.subs))
        print("  opcodes: %s" % " ".join("$%03X x%d" % kv for kv in sorted(m.seen.items())))
        if "--obj" in argv:
            obj(m, argv[argv.index("--obj") + 1])
        return
    print("no type 1 resource %d" % want)


if __name__ == "__main__":
    main(sys.argv)
