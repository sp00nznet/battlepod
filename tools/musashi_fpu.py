#!/usr/bin/env python3
"""Give Musashi's 68881 the transcendental opmodes it is missing.

Musashi implements a useful subset of the 68881's transcendental operations
and calls `fatalerror()` on the rest. The cockpit reaches **FTAN**, opmode
`0x0F`, the moment an entity is a Mech - the mech code needs a tangent - and
the run dies there.

Every missing opmode is a one-line libm call in exactly the shape the existing
`FSIN` and `FCOS` cases already use, so this adds all of them rather than only
the one that was in the way. The cycle counts copy `FSIN`'s 400, which is the
right order for a 68881 transcendental and which nothing here depends on.

This is a script rather than a patch file because `third_party/musashi` is
cloned by `make deps` and a context diff rots against upstream. It is
idempotent: it looks for its own marker and does nothing if the work is done.

usage: musashi_fpu.py [path/to/m68kfpu.c]
       musashi_fpu.py --selftest
"""
import sys

MARKER = "battlepod: transcendental opmodes"

ANCHOR = "\t\tdefault:\tfatalerror(\"fpgen_rm_reg: unimplemented opmode"

OPS = [
    (0x02, "FSINH", "sinh"),
    (0x06, "FLOGNP1", "log1p"),
    (0x08, "FETOXM1", "expm1"),
    (0x09, "FTANH", "tanh"),
    (0x0A, "FATAN", "atan"),
    (0x0C, "FASIN", "asin"),
    (0x0D, "FATANH", "atanh"),
    (0x0F, "FTAN", "tan"),
    (0x10, "FETOX", "exp"),
    (0x14, "FLOGN", "log"),
    (0x15, "FLOG10", "log10"),
    (0x16, "FLOG2", "log2"),
    (0x19, "FCOSH", "cosh"),
    (0x1C, "FACOS", "acos"),
]

POWS = [(0x11, "FTWOTOX", "2.0"), (0x12, "FTENTOX", "10.0")]


def block():
    out = ["\t\t/* %s */" % MARKER]
    for code, name, fn in OPS:
        out += ["\t\tcase 0x%02x:\t\t// %s" % (code, name),
                "\t\t\tREG_FP[dst] = double_to_fx80(%s(fx80_to_double(source)));" % fn,
                "\t\t\tSET_CONDITION_CODES(REG_FP[dst]);",
                "\t\t\tUSE_CYCLES(400);",
                "\t\t\tbreak;"]
    for code, name, base in POWS:
        out += ["\t\tcase 0x%02x:\t\t// %s" % (code, name),
                "\t\t\tREG_FP[dst] = double_to_fx80(pow(%s, fx80_to_double(source)));" % base,
                "\t\t\tSET_CONDITION_CODES(REG_FP[dst]);",
                "\t\t\tUSE_CYCLES(400);",
                "\t\t\tbreak;"]
    return "\n".join(out) + "\n\n"


def apply(text):
    """Returns (new text, what happened)."""
    if MARKER in text:
        return text, "already applied"
    at = text.find(ANCHOR)
    if at < 0:
        return text, "anchor not found - Musashi has moved; check by hand"
    return text[:at] + block() + text[at:], "applied"


def selftest():
    src = "x\n" + ANCHOR + " %02X\");\n"
    out, what = apply(src)
    assert what == "applied", what
    assert "case 0x0f:\t\t// FTAN" in out
    assert "tan(fx80_to_double(source))" in out
    assert out.index(MARKER) < out.index(ANCHOR)
    again, what = apply(out)
    assert what == "already applied" and again == out
    missing, what = apply("nothing like it here")
    assert what.startswith("anchor not found") and missing == "nothing like it here"
    print("musashi_fpu selftest ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    path = argv[1] if len(argv) > 1 else "third_party/musashi/m68kfpu.c"
    try:
        text = open(path, encoding="latin-1").read()
    except OSError as e:
        sys.exit("cannot read %s: %s" % (path, e))
    out, what = apply(text)
    if out != text:
        open(path, "w", encoding="latin-1").write(out)
    print("musashi fpu opmodes: %s (%s)" % (what, path))


if __name__ == "__main__":
    main(sys.argv)
