#!/usr/bin/env python3
"""Recover the cockpit network protocol from an operator console log.

The operator console logged every message it exchanged with the pods, by name,
with its source file and line. A surviving log is therefore a protocol
specification written by the software itself - far better evidence than reading
the firmware's dispatch table and guessing.

This reads a log you supply and prints the message vocabulary and, with
--sequence, one complete game start in order. It ships no log of its own.

usage: logproto.py <Console Log> [--sequence] [--limit N]
"""
import collections
import re
import sys

LINE = re.compile(
    r"^\w{3} \w{3} +\d+ ([\d:]+) \d{4} - (.*?) - File: (\S+) Line: (\d+)\s*$")

# Message names the console logs verbatim; everything else is free text.
KNOWN = ("IDENTIFY_YOURSELF", "SHADOW_ROM", "GO ", "COCKPIT_CONFIG_MSG",
         "PLAYER_CONFIG", "MECH_CLASS", "GAME_OVER", "NET_CONFIG_SEND_MSG",
         "GAME_SETUP_SEND_MSG", "Drop Location", "Acknowledged")


def parse(path):
    raw = open(path, "rb").read().decode("mac-roman", "replace")
    for line in raw.replace("\r", "\n").split("\n"):
        m = LINE.match(line)
        if m:
            yield m.group(1), m.group(2), m.group(3)


def shape(msg):
    """Collapse the varying parts so identical messages group together.

    Cockpit and pilot names are logged bare, not quoted, so mask them by
    keyword - otherwise every node looks like a different message, and the
    names are the site's own data rather than anything about the protocol.
    """
    s = re.sub(r"-?\d+(\.\d+)?", "N", msg)
    s = re.sub(r'"[^"]*"', '"S"', s)
    s = re.sub(r"\b(name|cockpit)\s+\S.*?(?=,|$)", r"\1 S", s)
    return s


def vocabulary(msgs, limit):
    forms = collections.Counter()
    files = collections.Counter()
    for _, msg, src in msgs:
        forms[shape(msg)[:76]] += 1
        files[src] += 1
    print("console source files seen: %s\n" %
          ", ".join("%s (%d)" % (f, n) for f, n in files.most_common()))
    print("%7s  %s" % ("count", "message"))
    for form, n in forms.most_common(limit):
        print("%7d  %s" % (n, form))


def sequence(msgs, limit):
    """Print one game start, from the last cockpit configuration in the log."""
    starts = [i for i, (_, m, _) in enumerate(msgs)
              if m.startswith("Configuring Cockpits")]
    if not starts:
        print("no 'Configuring Cockpits' in this log", file=sys.stderr)
        return
    prev, shown = None, 0
    for when, msg, _ in msgs[starts[-1]:]:
        key = shape(msg)[:60]
        if key == prev:
            continue            # collapse the per-node repeats
        prev = key
        print("%s  %s" % (when, shape(msg)[:88]))
        shown += 1
        if shown >= limit:
            break


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    limit = 40
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    msgs = list(parse(argv[1]))
    print("parsed %d logged messages\n" % len(msgs))
    if "--sequence" in argv:
        sequence(msgs, limit)
    else:
        vocabulary(msgs, limit)


if __name__ == "__main__":
    main(sys.argv)
