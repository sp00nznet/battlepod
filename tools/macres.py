#!/usr/bin/env python3
"""List and extract Macintosh resources, for reading the operator console.

The operator console is a 68k Macintosh application and all of its code lives
in CODE resources in the resource fork. It is the authority on what the console
puts on the wire, so being able to get at those segments means the protocol can
be read from the sender as well as inferred from the pod.

Accepts either a raw resource fork or the AppleDouble sidecar that `unar
-k visible` writes alongside each file.

usage:
  macres.py <file>                       list every resource
  macres.py <file> CODE                  list one type
  macres.py <file> CODE 1 out.bin        extract one resource
"""
import struct
import sys

APPLEDOUBLE = b"\x00\x05\x16\x07"
RESOURCE_FORK_ENTRY = 2
FINDER_INFO_ENTRY = 9


def resource_fork(path):
    """Return the resource fork bytes, unwrapping AppleDouble if needed."""
    raw = open(path, "rb").read()
    if raw[:4] != APPLEDOUBLE:
        return raw
    count = struct.unpack(">H", raw[24:26])[0]
    for i in range(count):
        eid, off, length = struct.unpack(">III", raw[26 + i * 12:38 + i * 12])
        if eid == FINDER_INFO_ENTRY:
            print("type/creator: %s" % raw[off:off + 8].decode("mac-roman"),
                  file=sys.stderr)
        if eid == RESOURCE_FORK_ENTRY:
            return raw[off:off + length]
    sys.exit("no resource fork in %s" % path)


def resources(fork):
    """Yield (type, id, name, bytes) for every resource in the fork."""
    data_off, map_off = struct.unpack(">II", fork[:8])
    rmap = fork[map_off:]
    type_off, name_off = struct.unpack(">HH", rmap[24:28])
    ntypes = struct.unpack(">H", rmap[type_off:type_off + 2])[0] + 1

    for i in range(ntypes):
        at = type_off + 2 + i * 8
        rtype, count, ref_off = struct.unpack(">4sHH", rmap[at:at + 8])
        for j in range(count + 1):
            ref = type_off + ref_off + j * 12
            # id, name offset, then attributes packed into the top byte of the
            # data offset; the trailing handle is padding on disk.
            rid, noff, attr_off = struct.unpack(">hHI", rmap[ref:ref + 8])
            off = data_off + (attr_off & 0xFFFFFF)
            size = struct.unpack(">I", fork[off:off + 4])[0]
            name = ""
            if noff != 0xFFFF:
                p = name_off + noff
                name = rmap[p + 1:p + 1 + rmap[p]].decode("mac-roman", "replace")
            yield rtype.decode("mac-roman"), rid, name, fork[off + 4:off + 4 + size]


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    fork = resource_fork(argv[1])
    want_type = argv[2] if len(argv) > 2 else None
    want_id = int(argv[3]) if len(argv) > 3 else None

    total = 0
    for rtype, rid, name, body in resources(fork):
        if want_type and rtype != want_type:
            continue
        if want_id is not None and rid != want_id:
            continue
        if want_id is not None and len(argv) > 4:
            open(argv[4], "wb").write(body)
            print("wrote %s: %s %d, %d bytes" % (argv[4], rtype, rid, len(body)))
            return
        print("  %-4s %6d  %8d  %s" % (rtype, rid, len(body), name))
        total += len(body)
    print("  total %d bytes" % total)


if __name__ == "__main__":
    main(sys.argv)
