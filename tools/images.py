#!/usr/bin/env python3
"""Decode the renderer's images: the type 7 payloads and the type 4 sprites.

Type 7 is 607 KB of the archive and every byte of it is an image. Each
payload is a longword of unpacked size and then the stream the renderer's
own decompressor at 0xFE0090F0 reads: blocks, each opened by a 16-bit word
(0 ends the payload), holding commands -

    n >= 0          copy n literal bytes
    0x80 - 0xFE     copy n & 0x7F bytes from block start + a 16-bit offset
    0xFF            a 16-bit count: 0 ends the block, else a long copy, whose
                    16-bit offset follows

The renderer is little-endian and every longword was reversed on its way
up, so the byte stream is each longword back to front. Unpacked, an image is
four 16-bit little-endian words - width, height, 0, a reference row (the
horizon of a sky) - then 15-bit RGB pixels. All 131 unpack to exactly their
declared size, which is the check that the reading is right.

A type 4 resource that carries data (most are aliases, with none) is a
sprite: width, height and a hotspot, big-endian, then the same pixels, 0
transparent. 72-79 are the reticle, 82 a planet, 83 a moon.

The C in src/battlepod.c (t7_unpack, image_get) draws them; this is the
reference and the way to look at them. RENDERING.md, *Images*.

usage:
  images.py <battletech_ti_res>                 list every image
  images.py <battletech_ti_res> --png ID OUT    one image (an alias is followed)
  images.py <battletech_ti_res> --sheet OUT     every image, small, on one sheet
  images.py --selftest
"""
import struct
import sys
import zlib

import resmap


def stream(data):
    """The bytes the renderer reads: each longword reversed."""
    return bytes(b for i in range(0, len(data) // 4 * 4, 4) for b in data[i:i + 4][::-1])


def unpack(data):
    """A type 7 payload -> (declared size, unpacked bytes)."""
    size = struct.unpack(">I", data[:4])[0]
    b, at, out = stream(data), 4, bytearray()

    def u16():
        nonlocal at
        v = b[at] | b[at + 1] << 8
        at += 2
        return v

    while at + 2 <= len(b) and len(out) < size:
        start = len(out)
        if not b[at] and not b[at + 1]:
            break
        at += 2
        while True:
            n = b[at]
            at += 1
            if n < 0x80:
                if n == 0:
                    raise ValueError("an empty literal run at %d" % at)
                out += b[at:at + n]
                at += n
                continue
            if n == 0xFF:
                n = u16()
                if n == 0:
                    break
            else:
                n &= 0x7F
            src = start + u16()
            for k in range(n):
                out.append(out[src + k])
    return size, bytes(out)


def image(items, rid):
    """(w, h, hx, hy, pixels) for an image or sprite id, following aliases."""
    by_id = {it[1]: it for it in items}
    for _ in range(4):
        _, _, rtype, flags, count, data = by_id[rid]
        if (flags & 0xFF) & resmap.ALIAS:
            rid = count
            continue
        if rtype == 7:
            _, raw = unpack(data)
            w, h, _, ref = struct.unpack("<4H", raw[:8])
            return w, h, 0, ref, struct.unpack("<%dH" % (w * h), raw[8:8 + w * h * 2])
        if rtype == 4 and len(data) >= 8:
            w, h, hx, hy = struct.unpack(">4H", data[:8])
            if 8 + w * h * 2 > len(data):
                return None             # 126-130 carry data that is not a sprite
            return w, h, hx, hy, struct.unpack(">%dH" % (w * h), data[8:8 + w * h * 2])
        return None
    return None


def png(path, w, h, pixels):
    """15-bit RGB to an RGB PNG, with nothing but the standard library."""
    rows = b"".join(b"\0" + bytes(c for v in pixels[y * w:(y + 1) * w]
                                  for c in (((v >> 10) & 31) * 255 // 31,
                                            ((v >> 5) & 31) * 255 // 31,
                                            (v & 31) * 255 // 31))
                    for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def check(items):
    """How many type 7 payloads unpack to exactly their declared size, and are
    an image of that size: the harness's checkpoint."""
    exact = images = 0
    for _, rid, rtype, flags, count, data in items:
        if rtype != 7:
            continue
        try:
            size, raw = unpack(data)
        except (ValueError, IndexError):
            continue
        if len(raw) == size:
            exact += 1
            w, h = struct.unpack("<2H", raw[:4])
            images += 8 + w * h * 2 == size
    return exact, images


def selftest():
    # Two literal bytes, then a 2-byte copy from the block's start, then the
    # end of the block and of the payload - written as the renderer sees it,
    # then reversed per longword the way the archive stores it.
    body = bytes([1, 0, 2, 0xAA, 0xBB, 0x82, 0, 0, 0xFF, 0, 0, 0, 0, 0, 0, 0])
    stored = struct.pack(">I", 4) + bytes(b for i in range(0, len(body), 4)
                                          for b in body[i:i + 4][::-1])
    size, out = unpack(stored)
    assert size == 4 and out == bytes([0xAA, 0xBB, 0xAA, 0xBB]), out
    print("images selftest OK")


def main(argv):
    if len(argv) > 1 and argv[1] == "--selftest":
        selftest()
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 1
    items = list(resmap.walk(open(argv[1], "rb").read()))
    if "--png" in argv:
        i = argv.index("--png")
        im = image(items, int(argv[i + 1]))
        if not im:
            print("no image %s" % argv[i + 1])
            return 1
        png(argv[i + 2], im[0], im[1], im[4])
        print("%s: %dx%d" % (argv[i + 2], im[0], im[1]))
        return 0
    if "--sheet" in argv:
        out = argv[argv.index("--sheet") + 1]
        tiles = [(it[1], image(items, it[1])) for it in items
                 if it[2] == 7 or (it[2] == 4 and it[5])]
        tiles = [(rid, im) for rid, im in tiles if im]
        cell, cols = 96, 12
        rows = (len(tiles) + cols - 1) // cols
        W, H = cell * cols, cell * rows
        sheet = [0] * (W * H)
        for n, (rid, (w, h, _, _, px)) in enumerate(tiles):
            ox, oy, step = (n % cols) * cell, (n // cols) * cell, max(w, h) / (cell - 2)
            for y in range(cell - 2):
                for x in range(cell - 2):
                    sx, sy = int(x * max(step, 1)), int(y * max(step, 1))
                    if sx < w and sy < h:
                        sheet[(oy + y) * W + ox + x] = px[sy * w + sx]
        png(out, W, H, sheet)
        print("%s: %d images, in archive order: %s" % (out, len(tiles), " ".join(str(r) for r, _ in tiles)))
        return 0
    exact, imgs = check(items)
    for it in items:
        if it[2] == 7 or (it[2] == 4 and it[5]):
            im = image(items, it[1])
            if im:
                print("  %4d  type %d  %4dx%-4d  ref %d,%d" % (it[1], it[2], im[0], im[1], im[2], im[3]))
    print("type 7 payloads unpacked exactly: %d" % exact)
    print("type 7 payloads that are images : %d" % imgs)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
