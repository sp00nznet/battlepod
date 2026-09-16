#!/usr/bin/env python3
"""Draw a cockpit model the way the pod drew it.

Period footage settles what that means: flat-shaded solid polygons, no texture,
cast shadows on the ground, a vertical gradient sky and haze washing out the
horizon. Flat shading is the easy case - one colour per face, no interpolation
across it - so this is a z-buffered triangle filler and nothing more.

The geometry comes from model.py, which runs the model's own program to get it.
Nothing here is the pod's code; this is the "draw the display list with a
modern renderer" half of the plan in RENDERING.md, at the scale of one object.

usage:
  render.py <resource file> --id N [--out FILE] [--size 480x360] [--turn DEG]
  render.py <resource file> --mech N   a whole mech, parts hung on skeleton N
  render.py <resource file> --mechs    assemble every chassis, report what stood
  render.py --selftest
"""
import math
import struct
import sys
import zlib

import model as M

SCREEN = (480, 360)             # what the pod ran, from the display list
SKY_TOP = (0x2E, 0x5C, 0xA8)
SKY_LOW = (0xBF, 0xCF, 0xE2)
GROUND = (0xC9, 0xA9, 0x6E)
SHADOW = (0x6B, 0x55, 0x36)    # the footage draws a hard dark shadow, not a soft one
LIGHT = (-0.35, 0.80, -0.49)    # over the viewer's shoulder, roughly


def png(path, w, h, rgb):
    """A PNG, with zlib doing the only hard part."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)                       # filter: none
        raw += rgb[y * w * 3:(y + 1) * w * 3]

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        fh.write(chunk(b"IEND", b""))


class Frame:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)
        self.z = [1e30] * (w * h)

    def background(self, horizon):
        """Sky above, ground below, both graded the way the footage looks."""
        for y in range(self.h):
            if y < horizon:
                t = y / max(1, horizon)
                c = tuple(int(SKY_TOP[i] + (SKY_LOW[i] - SKY_TOP[i]) * t)
                          for i in range(3))
            else:
                # the ground fades toward the horizon - distance haze
                t = (y - horizon) / max(1, self.h - horizon)
                c = tuple(int(SKY_LOW[i] + (GROUND[i] - SKY_LOW[i]) * min(1.0, t * 3))
                          for i in range(3))
            row = bytes(c) * self.w
            self.px[y * self.w * 3:(y + 1) * self.w * 3] = row

    def triangle(self, p0, p1, p2, colour):
        """One flat-shaded triangle, z-buffered. Screen space, z for depth."""
        xs = [p0[0], p1[0], p2[0]]
        ys = [p0[1], p1[1], p2[1]]
        lo_x, hi_x = max(0, int(min(xs))), min(self.w - 1, int(max(xs)) + 1)
        lo_y, hi_y = max(0, int(min(ys))), min(self.h - 1, int(max(ys)) + 1)
        if lo_x > hi_x or lo_y > hi_y:
            return
        area = ((p1[0] - p0[0]) * (p2[1] - p0[1]) -
                (p2[0] - p0[0]) * (p1[1] - p0[1]))
        if abs(area) < 1e-9:
            return
        c = bytes(colour)
        for y in range(lo_y, hi_y + 1):
            for x in range(lo_x, hi_x + 1):
                px, py = x + 0.5, y + 0.5
                w0 = ((p1[0] - p0[0]) * (py - p0[1]) -
                      (px - p0[0]) * (p1[1] - p0[1])) / area
                w1 = ((px - p0[0]) * (p2[1] - p0[1]) -
                      (p2[0] - p0[0]) * (py - p0[1])) / area
                if w0 < 0 or w1 < 0 or w0 + w1 > 1:
                    continue
                z = p0[2] + w1 * (p1[2] - p0[2]) + w0 * (p2[2] - p0[2])
                i = y * self.w + x
                if z < self.z[i]:
                    self.z[i] = z
                    self.px[i * 3:i * 3 + 3] = c


def normalise(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def shade(rgb, normal, kind=1):
    """One flat colour per face - lit, unless the material says otherwise.

    A model declares each material as kind 0 or kind 1, and the archive settles
    what that means: every one of the 212 lights and markers in it points at a
    kind 0 material and not one points at a kind 1, and kind 0 materials average
    twice the luminance of kind 1. Kind 0 is emissive, so it takes no lighting
    term - which is how a cockpit lamp stays lit on the side facing away from
    the sun.
    """
    if kind == 0:
        return tuple(min(255, max(0, int(255 * c))) for c in rgb)
    d = max(0.0, sum(normal[i] * LIGHT[i] for i in range(3)))
    k = 0.35 + 0.65 * d
    return tuple(min(255, max(0, int(255 * c * k))) for c in rgb)


def view(verts, turn, pitch, dist, centre):
    """Orbit the model: spin about Y, tilt, then push away from the camera."""
    ct, st = math.cos(turn), math.sin(turn)
    cp, sp = math.cos(pitch), math.sin(pitch)
    out = {}
    for i, (x, y, z) in verts.items():
        x, y, z = x - centre[0], y - centre[1], z - centre[2]
        x, z = x * ct + z * st, -x * st + z * ct
        y, z = y * cp - z * sp, y * sp + z * cp
        out[i] = (x, y, z + dist)
    return out


def project(p, w, h, fov=0.95):
    """Perspective. Y is up in the model and down on the screen."""
    if p[2] <= 0.01:
        return None
    f = (w / 2) / math.tan(fov / 2)
    return (w / 2 + p[0] * f / p[2], h / 2 - p[1] * f / p[2], p[2])


def extent(m):
    """Frame on the vertices actually decoded, not the stated bounding sphere.

    The sphere is padded - it has to contain the origin as well - so framing on
    it leaves the model small in the middle of the picture.
    """
    vs = list(m.vert.values())
    if not vs:
        bb = m.box
        return ((bb[0] + bb[1]) / 2, (bb[2] + bb[3]) / 2, (bb[4] + bb[5]) / 2), max(bb[6], 1e-3)
    lo = [min(v[a] for v in vs) for a in range(3)]
    hi = [max(v[a] for v in vs) for a in range(3)]
    centre = tuple((lo[a] + hi[a]) / 2 for a in range(3))
    radius = max(max(hi[a] - lo[a] for a in range(3)) / 2, 1e-3)
    return centre, radius, lo[1]


def draw(m, size=SCREEN, turn=0.6, pitch=0.18, out="out/model.png", shadow=True,
         zoom=2.4):
    w, h = size
    centre, radius, floor = extent(m)
    frame = Frame(w, h)
    frame.background(int(h * 0.52))

    dist = radius * zoom
    cam = view(m.vert, turn, pitch, dist, centre)

    # The footage puts a hard dark shadow under every mech: flatten the model
    # onto the ground plane and draw that first, so the model paints over it.
    if shadow:
        floored = {i: (v[0], floor, v[2]) for i, v in m.vert.items()}
        sm = view(floored, turn, pitch, dist, centre)
        for face, verts, mat in m.poly:
            pts = [sm[v] for v in verts if v in sm]
            if len(pts) < 3:
                continue
            pr = [project(p, w, h) for p in pts]
            if any(p is None for p in pr):
                continue
            for k in range(1, len(pr) - 1):
                frame.triangle(pr[0], pr[k], pr[k + 1], SHADOW)

    drawn = culled = 0
    for face, verts, mat in m.poly:
        pts = [cam[v] for v in verts if v in cam]
        if len(pts) < 3:
            continue
        a, b, c = pts[0], pts[1], pts[2]
        u = tuple(b[i] - a[i] for i in range(3))
        v = tuple(c[i] - a[i] for i in range(3))
        n = normalise((u[1] * v[2] - u[2] * v[1],
                       u[2] * v[0] - u[0] * v[2],
                       u[0] * v[1] - u[1] * v[0]))
        # Backface cull, the way the renderer does it: the sign of a dot
        # product, here between the face normal and the direction we look.
        if sum(n[i] * a[i] for i in range(3)) > 0:
            n = tuple(-c for c in n)
            culled += 1
        entry = m.mat.get(mat, (1, 0.7, 0.7, 0.7, 0.5))
        colour = shade(entry[1:4], n, entry[0])
        flat = [project(p, w, h) for p in pts]
        if any(p is None for p in flat):
            continue
        for k in range(1, len(flat) - 1):       # fan, so quads work too
            frame.triangle(flat[0], flat[k], flat[k + 1], colour)
        drawn += 1
    # A model's lights and markers: $200 puts one pixel at a vertex, $280 and
    # $2A0 a marker whose size is a world measurement the renderer scales by
    # distance. Drawn after the polygons and unlit, because they are emissive.
    lit = 0
    for vi, size, mat in m.points:
        if vi not in cam:
            continue
        p = project(cam[vi], w, h)
        if p is None:
            continue
        rgb = m.mat.get(mat, (0, 1.0, 1.0, 0.8, 0.5))[1:4]
        colour = tuple(min(255, int(255 * c)) for c in rgb)
        r = max(0, int(size * (w / 2) / math.tan(0.95 / 2) / max(p[2], 1e-3) / 2))
        r = min(r, 24)
        # A light sits on the surface it belongs to, so it is coplanar with the
        # polygon underneath and loses a straight depth test. Pull it a hair
        # toward the camera rather than widen the test.
        z = p[2] * 0.998
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = int(p[0]) + dx, int(p[1]) + dy
                if 0 <= x < w and 0 <= y < h:
                    i = y * w + x
                    if z <= frame.z[i]:
                        frame.z[i] = z
                        frame.px[i*3:i*3+3] = bytes(colour)
        lit += 1

    png(out, w, h, frame.px)
    print("%s: %dx%d, %d polygons and %d lights drawn"
          % (out, w, h, drawn, lit))


def selftest():
    f = Frame(8, 8)
    f.background(4)
    assert f.px[0:3] != f.px[7 * 8 * 3:7 * 8 * 3 + 3], "sky and ground must differ"
    f.triangle((1.0, 1.0, 5.0), (7.0, 1.0, 5.0), (1.0, 7.0, 5.0), (255, 0, 0))
    i = (2 * 8 + 2) * 3
    assert bytes(f.px[i:i + 3]) == b"\xff\x00\x00", "the triangle must cover (2,2)"
    j = (6 * 8 + 6) * 3
    assert bytes(f.px[j:j + 3]) != b"\xff\x00\x00", "and not the far corner"
    # nearer z must win
    f.triangle((1.0, 1.0, 9.0), (7.0, 1.0, 9.0), (1.0, 7.0, 9.0), (0, 255, 0))
    assert bytes(f.px[i:i + 3]) == b"\xff\x00\x00", "the z-buffer must reject the far one"
    f.triangle((1.0, 1.0, 1.0), (7.0, 1.0, 1.0), (1.0, 7.0, 1.0), (0, 0, 255))
    assert bytes(f.px[i:i + 3]) == b"\x00\x00\xff", "and accept the near one"
    assert shade((1.0, 1.0, 1.0), (0, 0, 0)) == (89, 89, 89), shade((1.,1.,1.), (0,0,0))
    assert shade((1.0, 1.0, 1.0), (0, 0, 0), 0) == (255, 255, 255), "kind 0 takes no light"

    # The rules that hang parts on a skeleton, on parts built here. A limb
    # reaches from its node to the next one down, so its box has to contain
    # that offset; the twin is the same part reflected in x.
    assert inside((-1.0, 1.0, -2.75, 0.24, -0.5, 1.6), (0.08, -2.75, 0.26))
    assert not inside((-1.0, 1.0, -2.00, 0.00, -0.5, 1.6), (0.08, -2.75, 0.26))
    assert volume((0.0, 2.0, 0.0, 3.0, 0.0, 4.0)) == 24.0

    class P(object):
        def __init__(self, vs):
            self.vert = vs
    right = P({0: (0.5, 0.0, 0.0), 1: (1.5, -2.0, 0.3)})
    left = P({0: (-0.5, 0.0, 0.0), 1: (-1.5, -2.0, 0.3)})
    other = P({0: (0.5, 0.0, 0.0), 1: (1.5, -2.0, 9.9)})
    pool = {1: right, 2: left, 3: other}
    assert mirror_of(1, pool) == 2 and mirror_of(2, pool) == 1
    assert mirror_of(3, pool) is None, "not a reflection of anything"
    assert side(right) > 0 > side(left)
    print("selftest: ok")


def best_model(data, lib):
    """Walk a model the way that draws the most of it without drawing it twice.

    Walking every branch is right for some models and wrong for others, and
    the data says which. A model that keeps levels of detail behind its
    branches writes the *same* vertex slots again on each arm, so a full walk
    ends up with several versions stacked in one frame. A model that uses its
    branches as a sequence - one $460 sub-model per arm, which is how the
    assembled ones are built - writes each slot once. So: take the full walk
    when it did not rewrite anything, and otherwise whichever single path drew
    more.
    """
    full = M.Model(data, paths="all", archive=lib)
    full.run()
    if len(full.written) <= max(1, full.nvert) * 1.2:
        return full
    best = None
    for how in ("fall", "take"):
        cand = M.Model(data, paths=how, archive=lib)
        cand.run()
        if best is None or len(cand.poly) > len(best.poly):
            best = cand
    return best


def volume(b):
    return max(b[1] - b[0], 1e-6) * max(b[3] - b[2], 1e-6) * max(b[5] - b[4], 1e-6)


def inside(b, d):
    """Does a part's own bounding box reach the point d."""
    return all(b[2 * a] - 1e-3 <= d[a] <= b[2 * a + 1] + 1e-3 for a in range(3))


def side(m):
    """Which side of the origin a part's geometry sits on."""
    vs = list(m.vert.values())
    return sum(v[0] for v in vs) / max(len(vs), 1)


def mirror_of(rid, pool):
    """The same part for the other side: the same vertices reflected in x."""
    a = pool[rid].vert
    for other, p in pool.items():
        if other == rid or len(p.vert) != len(a):
            continue
        if all(k in p.vert and abs(p.vert[k][0] + v[0]) < 1e-4
               and abs(p.vert[k][1] - v[1]) < 1e-4 and abs(p.vert[k][2] - v[2]) < 1e-4
               for k, v in a.items()):
            return other
    return None


class Assembly(object):
    """A whole mech: parts hung on a skeleton's nodes at their rest pose.

    Nothing here is placed by hand. `$040` gives every node a constant offset
    from its parent, so running the chain gives the pose. A part is authored in
    the space of the node it hangs on and reaches from that node down to the
    next one, so the part that belongs on a node is **the one whose own
    bounding box contains the offset of that node's child** - the upper leg
    reaches exactly from hip to knee - and where several do, the smallest.
    Left and right are separate resources holding mirrored geometry, told apart
    by which side of the origin their own vertices sit on.

    Two kinds of node are placed differently and say so. The torso hangs on
    node 2 and is taken from the part block ten ids above the skeleton, the
    alignment RENDERING.md argues for, because several parts contain node 2's
    child offset and the smallest is not the torso. A foot hangs on a node with
    no child at all, so there is no offset to match: it is whatever is left
    unused in the seven-id block the rest of the leg came from.
    """

    def __init__(self, blob, lib, skel):
        self.parts = []                 # (node, resource id, where it went)
        self.vert, self.poly, self.mat, self.points = {}, [], {}, []
        pool, rig = {}, None
        for rid, rtype, data in M.walk(blob):
            if rtype != 1:
                continue
            if rid == skel:
                rig = M.Model(data)
                rig.run()
            elif 460 <= rid <= 520:
                p = best_model(data, lib)
                if p.poly:
                    pool[rid] = p
        if rig is None or not rig.arm:
            raise SystemExit("resource %d is not a skeleton" % skel)
        self.rig = rig

        kid = {}
        for node, (parent, _slot, d) in rig.arm.items():
            kid.setdefault(parent, d)

        used = set()
        # The torso always hangs on node 2. It is not matched by reach: on a
        # chassis with no shoulder nodes at all node 2 has no child to match
        # against, and where it does, several parts contain that offset and
        # the smallest of them is not the torso.
        if skel + 10 in pool:
            self.place(pool, rig, 2, skel + 10, used)

        for node in sorted(rig.arm):
            want = kid.get(node)
            if node == 2 or want is None:
                continue
            fit = [(volume(pool[r].box), r) for r in pool
                   if r not in used and inside(pool[r].box, want)]
            if not fit:
                continue
            self.place(pool, rig, node, min(fit)[1], used)

        # Feet. The leg parts all came out of one contiguous block of seven
        # ids; whatever of that block is still unused is the pair of feet. A
        # foot node has nothing below it, so there is no offset to match and
        # this is the only rule left that is not a guess.
        legs = [rid for node, rid, _at in self.parts if node != 2]
        if legs:
            block = [r for r in range(min(legs), min(legs) + 7) if r in pool]
            for node in sorted(rig.arm):
                if node in kid or node == 2:
                    continue
                spare = [r for r in block if r not in used]
                if not spare:
                    break
                self.place(pool, rig, node,
                           min(spare, key=lambda r: volume(pool[r].box)), used)

        vs = list(self.vert.values()) or [(0.0, 0.0, 0.0)]
        self.box = [min(v[0] for v in vs), max(v[0] for v in vs),
                    min(v[1] for v in vs), max(v[1] for v in vs),
                    min(v[2] for v in vs), max(v[2] for v in vs), 1.0]

    def place(self, pool, rig, node, pick, used):
        twin = mirror_of(pick, pool)
        if twin is not None and side(pool[pick]) * rig.node[node][0] < 0:
            pick, twin = twin, pick
        used.add(pick)
        self.add(pool[pick], rig.node[node], node, pick)

    def add(self, part, at, node, rid):
        vbase = (max(self.vert) + 1) if self.vert else 0
        mbase = (max(self.mat) + 1) if self.mat else 0
        remap = {}
        for k, v in part.vert.items():
            remap[k] = vbase + k
            self.vert[vbase + k] = (v[0] + at[0], v[1] + at[1], v[2] + at[2])
        for k, v in part.mat.items():
            self.mat[mbase + k] = v
        for face, verts, mat in part.poly:
            if all(v in remap for v in verts):
                self.poly.append((face, [remap[v] for v in verts], mbase + mat))
        self.parts.append((node, rid, at))


def mechs(blob, lib):
    """Assemble every skeleton in the archive and say how much of each stood up."""
    total = 0
    whole = 0
    for rid, rtype, data in M.walk(blob):
        if rtype != 1:
            continue
        m = M.Model(data)
        m.run()
        if not m.arm or m.poly:
            continue
        a = Assembly(blob, lib, rid)
        total += len(a.parts)
        whole += len(a.parts) >= 8
        print("%4d  %-8s %d parts, %4d polygons: %s"
              % (rid, M.named(rid), len(a.parts), len(a.poly),
                 " ".join(str(r) for _n, r, _at in a.parts)))
    print("")
    print("chassis that assemble whole: %d" % whole)
    print("parts placed on skeletons  : %d" % total)


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2 or not any(f in argv for f in ("--id", "--mech", "--mechs")):
        sys.exit(__doc__)
    blob = open(argv[1], "rb").read()
    lib = M.archive(blob)
    want = int(argv[argv.index("--id") + 1]) if "--id" in argv else None
    size = SCREEN
    if "--size" in argv:
        size = tuple(int(v) for v in argv[argv.index("--size") + 1].split("x"))
    turn = math.radians(float(argv[argv.index("--turn") + 1])) if "--turn" in argv else 0.6
    out = argv[argv.index("--out") + 1] if "--out" in argv else "out/model.png"
    if "--mechs" in argv:
        return mechs(blob, lib)
    if "--mech" in argv:
        skel = int(argv[argv.index("--mech") + 1])
        a = Assembly(blob, lib, skel)
        print("skeleton %d: %d parts, %d vertices, %d polygons"
              % (skel, len(a.parts), len(a.vert), len(a.poly)))
        for node, rid, at in a.parts:
            print("   node %2d  model %3d  at %6.2f %6.2f %6.2f" % (node, rid, at[0], at[1], at[2]))
        # a mech is far taller than it is wide, so it needs the camera
        # further back than a building does to keep its feet in frame
        return draw(a, size, turn, 0.10, out, zoom=3.4)
    for rid, rtype, data in M.walk(blob):
        if rid != want or rtype != 1:
            continue
        m = best_model(data, lib)
        print("model %d: %d vertices, %d polygons, %d materials, %d points%s"
              % (rid, len(m.vert), len(m.poly), len(m.mat), len(m.points),
                 "" if m.box_matches() else "  (box check does NOT pass)"))
        if not m.poly:
            print("nothing to draw - the walk stopped at %s" % m.stopped)
            return
        return draw(m, size, turn, 0.18, out)
    print("no type 1 resource %d" % want)


if __name__ == "__main__":
    main(sys.argv)
