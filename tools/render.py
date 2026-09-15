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


def shade(rgb, normal):
    """Flat shading: the material's colour, lit by one directional source.

    The material kinds the model declares are "flat" and "lit"; both end up as
    one colour per face, which is what the footage shows.
    """
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


def draw(m, size=SCREEN, turn=0.6, pitch=0.18, out="out/model.png", shadow=True):
    w, h = size
    centre, radius, floor = extent(m)
    frame = Frame(w, h)
    frame.background(int(h * 0.52))

    dist = radius * 2.4
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
        rgb = m.mat.get(mat, (0, 0.7, 0.7, 0.7, 0.5))[1:4]
        colour = shade(rgb, n)
        flat = [project(p, w, h) for p in pts]
        if any(p is None for p in flat):
            continue
        for k in range(1, len(flat) - 1):       # fan, so quads work too
            frame.triangle(flat[0], flat[k], flat[k + 1], colour)
        drawn += 1
    png(out, w, h, frame.px)
    print("%s: %dx%d, %d polygons drawn of %d" % (out, w, h, drawn, len(m.poly)))


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
    print("selftest: ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2 or "--id" not in argv:
        sys.exit(__doc__)
    blob = open(argv[1], "rb").read()
    want = int(argv[argv.index("--id") + 1])
    size = SCREEN
    if "--size" in argv:
        size = tuple(int(v) for v in argv[argv.index("--size") + 1].split("x"))
    turn = math.radians(float(argv[argv.index("--turn") + 1])) if "--turn" in argv else 0.6
    out = argv[argv.index("--out") + 1] if "--out" in argv else "out/model.png"
    for rid, rtype, data in M.walk(blob):
        if rid != want or rtype != 1:
            continue
        # One level of detail, not the union of them - stacking every branch
        # puts the near and far versions of the model in the same frame. Which
        # side of a branch holds the detailed geometry differs per model, so
        # walk it both ways and keep whichever drew more.
        best = None
        for how in ("fall", "take"):
            cand = M.Model(data, paths=how)
            cand.run()
            if best is None or len(cand.poly) > len(best.poly):
                best = cand
        m = best
        print("model %d: %d vertices, %d polygons, %d materials%s"
              % (rid, len(m.vert), len(m.poly), len(m.mat),
                 "" if m.box_matches() else "  (box check does NOT pass)"))
        if not m.poly:
            print("nothing to draw - the walk stopped at %s" % m.stopped)
            return
        return draw(m, size, turn, 0.18, out)
    print("no type 1 resource %d" % want)


if __name__ == "__main__":
    main(sys.argv)
