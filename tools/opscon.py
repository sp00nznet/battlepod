#!/usr/bin/env python3
"""Read the operator console's protocol out of the console itself.

Starting a game is the oldest blocker in this project: the pod consumes packets
and the opcode dispatch is mapped, but the sender is a 68k Macintosh
application and nothing said what its messages contain.

It turns out the console says. It logs every message it sends, by name and with
its fields, through `printf`-style format strings that sit in its `DATA`
resource - so the format strings *are* the field list, written by the program
that sends them. The same region carries the `scanf` formats it reads the
release's own data files with, which is the map and setup file grammar for
free.

This reads them out. It is the "lift it to read it" half of the plan in
ARCHITECTURE.md, and it needed no lifting at all in the end: the strings were
enough. What is still missing after this is the byte *layout* on the wire -
these give the fields and their C types, not their order and width - and that
does need the code.

Cross-checks against `tools/logproto.py`, which recovers the same vocabulary
from the other end: a `Console Log` a real centre kept for eight months of
1995. Two independent sources, one the sender and one its diary.

usage:
  opscon.py <Console .rsrc>              every message, with its fields
  opscon.py <Console .rsrc> --formats    the scanf grammars for the data files
  opscon.py <Console .rsrc> --check      counts, for the harness
  opscon.py --selftest
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macres

# A message line names itself first, in the shouting case the console uses for
# anything that goes on the wire, and then lists its fields.
MESSAGE = re.compile(r"^([A-Z][A-Z0-9_]{3,})\s+(.*)$")
FIELD = re.compile(r"([A-Za-z_][A-Za-z_ ]*?)\s*(%[-0-9.]*(?:ld|lx|[dfsxc]))")
SPEC = re.compile(r"%[-0-9.]*(?:\[\^?[^\]]*\]|ld|lx|[dfsxc])")

# What the C conversion means for something that has to go on a wire.
CTYPE = {"d": "int", "ld": "long", "lx": "long, printed as hex",
         "f": "float", "s": "string", "x": "hex", "c": "char"}


def data(path):
    fork = macres.resource_fork(path)
    for kind, rid, _name, blob in macres.resources(fork):
        if kind == "DATA":
            return blob
    sys.exit("no DATA resource in %s" % path)


def strings(blob, least=5):
    for m in re.finditer(rb"[ -~]{%d,}" % least, blob):
        yield m.start(), m.group().decode("latin1")


def messages(blob):
    """Every logged message, as a name and the fields it carries."""
    out = {}
    for off, s in strings(blob):
        m = MESSAGE.match(s)
        if not m or "%" not in s:
            continue
        name, rest = m.group(1), m.group(2)
        if name.endswith(".C") or "ERROR" == name:
            continue
        fields = [(a.strip(), CTYPE.get(b.lstrip("%-0123456789."), b))
                  for a, b in FIELD.findall(rest)]
        if not fields:
            continue
        # Several strings report the same message - the send, the timeout,
        # the mismatch. The send is the one that names the fields as they go
        # out, and it is the one without an error marker on it.
        rank = (("*" in s or "(" in s), -len(fields))
        if name not in out or rank < out[name][0]:
            out[name] = (rank, off, fields, s)
    return dict((n, v[1:]) for n, v in out.items())


def formats(blob):
    """The scanf grammars, each tagged with the line that introduces it.

    A pure conversion string - nothing but specifiers and spaces - is a file
    grammar rather than a log line, and the readable string nearest above it
    says which file it parses.
    """
    seen = list(strings(blob, 4))
    out = []
    for i, (off, s) in enumerate(seen):
        body = s.strip()
        if not body.startswith("%") or not SPEC.match(body):
            continue
        # Quotes are part of a grammar - `"%[^"]"` is how the console reads a
        # quoted name - so they do not count as prose.
        if SPEC.sub("", body).strip(' \t"'):     # anything but specifiers left
            continue
        # A grammar is introduced by the line above it ("Reading
        # Net_Configuration") or explained by the line below it, which for the
        # map file is the class the parsed line becomes. Prefer the class.
        near = ""
        for j in range(i + 1, min(i + 4, len(seen))):        # what it becomes
            m2 = MESSAGE.match(seen[j][1].strip())
            if m2 and ("_CLASS" in m2.group(1) or "_POSITION" in m2.group(1)):
                near = m2.group(1)
                break
        for j in range(i - 1, max(i - 6, -1), -1):           # or what introduced it
            if near:
                break
            cand = seen[j][1].strip()
            if "%" not in cand and len(cand) > 6:
                near = cand
        out.append((off, body, near))
    return out


def show(blob):
    msgs = messages(blob)
    print("%d messages the console logs by name\n" % len(msgs))
    for name in sorted(msgs):
        off, fields, _raw = msgs[name]
        print("  %-26s 0x%04x" % (name, off))
        for label, ctype in fields:
            print("        %-16s %s" % (label, ctype))


def show_formats(blob):
    fs = formats(blob)
    print("%d file grammars\n" % len(fs))
    for off, body, near in fs:
        print("  0x%04x  %-42s %s" % (off, body, near))


def check(blob):
    msgs, fs = messages(blob), formats(blob)
    named = sum(1 for n in msgs if n.endswith("_CLASS") or n.endswith("_MSG"))
    print("")
    print("messages recovered from the console: %d" % len(msgs))
    print("entity classes and wire messages   : %d" % named)
    print("file grammars recovered            : %d" % len(fs))
    return msgs, fs


def selftest():
    """Built here, so the parser is not only ever tried on strings we are
    still learning to read."""
    made = (b"\0MECH_CLASS class %ld, thing_number %ld, type %ld, name %s\0"
            b"Drop Location (%.2f, %.2f, %.2f)\0"
            b"Reading Net_Configuration\0"
            b"%d %d %d %d %d %d %d %s %s \"%[^\"]\"\0"
            b"gDocument != NULL\0Functions.c\0")
    msgs = messages(made)
    assert "MECH_CLASS" in msgs, sorted(msgs)
    fields = msgs["MECH_CLASS"][1]
    assert [f[0] for f in fields] == ["class", "thing_number", "type", "name"], fields
    assert [f[1] for f in fields] == ["long", "long", "long", "string"], fields
    # A line with no conversions is not a message, however shouty.
    assert "NULL" not in msgs and "Functions" not in msgs

    fs = formats(made)
    assert len(fs) == 1, fs
    assert fs[0][2] == "Reading Net_Configuration", fs[0]
    assert fs[0][1].startswith("%d %d"), fs[0]

    # A format string with prose in it is a log line, not a file grammar.
    assert formats(b"\0Loaded %d of %d\0") == []
    print("selftest: ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) < 2:
        sys.exit(__doc__)
    blob = data(argv[1])
    if "--formats" in argv:
        return show_formats(blob)
    if "--check" in argv:
        return check(blob)
    show(blob)


if __name__ == "__main__":
    main(sys.argv)
