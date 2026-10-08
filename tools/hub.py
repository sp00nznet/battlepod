#!/usr/bin/env python3
"""The centre: a network of emulated pods, CPU pilots, and the operator's view.

Every pod is a whole emulated cockpit - `battlepod.exe` with no window for a
bot, `cockpit.exe --live-pod` for a person - joined to this hub by `--net`.
The hub is what the ARCNET segment and the operator console were:

  * it starts the game on each pod the way the console's own log does it -
    a welcome with the visibility range, a MECH_CLASS for every pod's
    vehicle, the scenario's map as 0xE4s, then PLAYER_LINK to the pod's own;
  * it relays every packet a pod transmits to all the others, which is the
    whole of multiplayer (DEVICES.md, *Two pods*);
  * it reads the 0xEC position broadcasts going past and so knows where every
    Mech is, which is what the operator's view and the CPU pilots are made of.

A CPU pilot drives its pod through the panel's own input reports - analog C0
for throttle and stick, B1/B0 for buttons - exactly as a person would. It
steers toward the nearest other Mech, closes at full throttle, and fires when
it is pointing at it. What happens then - hits, damage, death - is the pod's
firmware, not the hub.

usage:
  hub.py [--scenario NAME] [--bots N] [--human] [--vehicles 0,8,12,...]
         [--port P] [--seconds S]

Needs VWE_GAME_FILES, `make` (and `make cockpit` for --human). Pod output
goes to build/pod<N>.log.
The wire between the hub and its pods is docs/api.md.
"""
import math
import os
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mapsend  # noqa: E402
import console_view  # noqa: E402

# Opcodes only the console and the router send. The console's own packets
# come back from pods only as forwards, which the origin check drops; a pod
# does send 0xE4 and 0xED of its own - a thing it made, the escape pod it
# climbs into when its Mech dies - and those are relayed.
CONSOLE_OPS = {0xE5, 0xEE, 0xC4, 0xC6} | set(range(0xF6, 0x100))

POD_ARGS = ["--duart", "11000", "--rstub", "3FF00000", "--rirq", "--astub",
            "--monitor", "--clock", "2000808", "--set", "40000100=1234567",
            "--steps", "1000000000000", "--top", "0"]


def pkt(op, n, fields):
    b = bytearray(n)
    b[0] = op
    for off, fmt, v in fields:
        struct.pack_into(fmt, b, off, v)
    return bytes(b)


def addressed(p, node):
    """Set a console packet's +0x08/+0x09: net 1 and a node - the pod the
    message is for, or the pod a thing belongs to (0 for the game's)."""
    b = bytearray(p)
    b[8], b[9] = 1, node
    return bytes(b)


def rio(data):
    """One Remote I/O report, framed as the panel board frames it."""
    d = bytes(data)
    return bytes([1, 0, len(d), len(d)]) + d + bytes([sum(d) & 0xFF])


class Mech:
    def __init__(self, thing):
        self.thing = thing
        self.x = self.y = self.z = 0.0
        self.heading = 0.0
        self.speed = 0.0
        self.seen = 0.0


class Pod:
    def __init__(self, node, vehicle, human):
        self.node = node
        self.vehicle = vehicle
        self.human = human
        self.addr = None
        self.outbox = []
        self.started = 0.0
        self.proc = None
        self.log = None
        self.firing = False
        self.fire_at = 0.0
        self.down = False
        self.moded = 0
        self.ops = {}
        self.pool = []


class Hub:
    def __init__(self, args):
        self.args = args
        self.gf = os.environ.get("VWE_GAME_FILES")
        if not self.gf:
            sys.exit("hub: set VWE_GAME_FILES")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 22)
        self.sock.bind(("127.0.0.1", args.port))
        self.sock.setblocking(False)
        self.mechs = {}
        self.pods = []
        self.relayed = 0
        self.forwards = 0
        self.unicast = 0
        self.kills = []
        self.hits = {}
        n = 0
        if args.human:
            n += 1
            self.pods.append(Pod(n, args.vehicles[0], True))
        for i in range(args.bots):
            n += 1
            self.pods.append(Pod(n, args.vehicles[n - 1], False))
        self.world = self.build_world()
        scen = os.path.join(self.gf, "Scenarios", self.args.scenario)
        self.map_objects = [(o[2], o[3], o[0]) for o in mapsend.objects(scen)]
        self.bounds = console_view.world_bounds(self.map_objects)
        self.console = None
        self.t0 = time.time()

    def clock(self):
        return time.time()

    # -- the game the console would start --------------------------------

    def build_world(self):
        scen = os.path.join(self.gf, "Scenarios", self.args.scenario)
        text = open(scen, "rb").read().decode("mac-roman", "replace").replace("\r", "\n")
        drops = []
        for line in text.split("\n"):
            f = line.split()
            if len(f) == 5 and f[4] == "-1":
                drops.append([float(v) for v in f[:4]])
        world = [pkt(0xE5, 0x60, [(0x3C, ">l", 600000),
                                  (0x44, ">l", self.args.range),
                                  (0x48, ">l", self.args.range)]),
                 addressed(bytes.fromhex(mapsend.reset_world()), 0)]
        spots = self.arena(scen) if self.args.arena else None
        for pod in self.pods:
            if spots:
                facing, x, y = spots[pod.node - 1]
            else:
                facing, x, y, _ = drops[(pod.node - 1) % len(drops)]
            # The Mech belongs to its pod: +0x08 is the owner word, and a hit
            # on a Mech another pod owns is sent to that pod as 0xBA.
            world.append(addressed(pkt(0xE4, 0x60, [
                (0x0E, ">l", 1), (0x12, ">l", pod.node),
                (0x16, ">f", x), (0x1A, ">f", y), (0x1E, ">f", 5.4),
                (0x22, "8s", ("Pod %d" % pod.node).encode()),
                (0x4A, ">h", pod.vehicle), (0x50, ">f", facing)]), pod.node))
            m = self.mechs[pod.node] = Mech(pod.node)
            m.x, m.y, m.heading = x, y, facing
        nmap = 0
        for o in mapsend.objects(scen):
            world.append(addressed(bytes.fromhex(mapsend.create(11 + nmap, *o)), 0))
            nmap += 1
        # A pod allocates a thing - a shot, an effect - only from a free slot
        # whose owner word is its own address (0x0214C57E), and a fresh arena
        # owns nothing. The console hands each pod a pool with class 0 0xE4s
        # (the arm at 0x0213CFB2). Each pod's range is reserved in its own
        # arena only, so no two pods number their shots alike. Slots from
        # 944 up are treated specially by that arm, so the pools stay below.
        first = 11 + nmap
        per = max(4, min(40, (944 - first) // max(1, len(self.pods))))
        for pod in self.pods:
            lo = first + per * (pod.node - 1)
            pod.pool = [addressed(pkt(0xE4, 0x40, [(0x0E, ">l", 0), (0x12, ">l", n)]),
                                  pod.node)
                        for n in range(lo, min(lo + per, 944))]
        return world

    def arena(self, scen):
        """Open ground: the point on a coarse grid farthest from any map
        object, and the pods on a ring round it facing in. Drop points are in
        bases, and a base's walls stop shots."""
        objs = [(o[2], o[3]) for o in mapsend.objects(scen)]
        xs = [x for x, _ in objs]
        ys = [y for _, y in objs]
        best, at = -1.0, (0.0, 0.0)
        # Only the middle of the map: the edges are open because nothing is
        # there at all, and the game may not be played there.
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        mx, my = (x1 - x0) * 0.2, (y1 - y0) * 0.2
        for gx in range(int(x0 + mx), int(x1 - mx), 25):
            for gy in range(int(y0 + my), int(y1 - my), 25):
                d = min((gx - x) ** 2 + (gy - y) ** 2 for x, y in objs)
                if d > best:
                    best, at = d, (gx, gy)
        cx, cy = at
        r = min(self.args.ring, math.sqrt(best) * 0.7)
        print("hub: open ground at (%.0f, %.0f), nothing within %.0f; ring %.0f"
              % (cx, cy, math.sqrt(best), r))
        spots = []
        n = len(self.pods)
        for i in range(n):
            a = 2 * math.pi * i / n
            x, y = cx + r * math.sin(a), cy - r * math.cos(a)
            # Heading h walks along (sin h, -cos h): face the centre.
            face = math.degrees(math.atan2(cx - x, -(cy - y))) % 360.0
            spots.append((face, x, y))
        return spots

    def start(self, pod):
        pod.outbox = ([addressed(self.world[0], pod.node)] + self.world[1:] +
                      pod.pool)
        pod.outbox.append(addressed(pkt(0xED, 0x40, [
            (0x0A, "16s", b"B1_BattleTech_1"), (0x32, ">l", pod.node)]), pod.node))
        pod.started = time.time()
        print("hub: pod %d said hello; sending %d packets" % (pod.node, len(pod.outbox)))

    # -- processes -------------------------------------------------------

    def launch(self):
        for pod in self.pods:
            exe = "cockpit.exe" if pod.human else "battlepod.exe"
            cmd = [os.path.join(ROOT, "build", exe),
                   os.path.join(self.gf, "Full_Load_3_0")] + POD_ARGS + [
                   "--net", "127.0.0.1:%d" % self.args.port,
                   "--net-node", str(pod.node)]
            cmd += ["--live-pod"] if pod.human else ["--realtime"]
            cmd += self.args.pod_args.split()
            pod.log = open(os.path.join(ROOT, "build", "pod%d.log" % pod.node), "w")
            pod.proc = subprocess.Popen(cmd, stdout=pod.log, stderr=subprocess.STDOUT,
                                        cwd=ROOT)

    def stop(self):
        # Ask first: a pod told to quit ends its run and prints its report.
        for pod in self.pods:
            self.send(pod, b"Q", b"")
        for pod in self.pods:
            if pod.proc:
                try:
                    pod.proc.wait(10)
                except subprocess.TimeoutExpired:
                    pod.proc.kill()

    # -- the wire --------------------------------------------------------

    def send(self, pod, kind, data):
        if pod.addr:
            self.sock.sendto(kind + data, pod.addr)

    def receive(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(4096)
            except (BlockingIOError, ConnectionResetError):
                return
            if not data:
                continue
            kind = data[:1]
            if kind == b"H" and len(data) >= 2:
                pod = self.pod(data[1])
                if pod and not pod.addr:
                    pod.addr = addr
                    self.start(pod)
                if pod:
                    self.send(pod, b"A", b"")         # heard you
            elif kind == b"P" and len(data) > 2:
                self.from_pod(self.pod_at(addr), data[1], data[2:])

    def pod(self, node):
        return next((p for p in self.pods if p.node == node), None)

    def pod_at(self, addr):
        return next((p for p in self.pods if p.addr == addr), None)

    def from_pod(self, src, node, packet):
        """Route what a pod sent. Node 0xFE is the hub: a broadcast, for
        every other pod. Any other node is one pod - a hit on its Mech, say.
        A pod also forwards broadcasts it received, as a router would; those
        carry someone else's address as their origin at [4..5], and are
        dropped, or the pods would pass them round for ever."""
        op = packet[0]
        if src and len(packet) > 5 and (packet[4], packet[5]) != (1, src.node):
            self.forwards += 1
            return
        if src:
            src.ops[op] = src.ops.get(op, 0) + 1
        if op == 0xEA and len(packet) >= 0x18:
            thing, shooter, loc = struct.unpack_from(">lll", packet, 0x08)
            key = (src.node if src else 0, thing)
            self.hits[key] = self.hits.get(key, 0) + 1
            if loc == -1:
                print("hub: thing %d destroyed, credited to %d" % (thing, shooter), flush=True)
                self.kills.append((time.time() - self.t0, thing, shooter))
        if op == 0xED and src and time.time() - src.started > self.args.settle:
            # A pod relinks its pilot when its Mech is destroyed.
            print("hub: pod %d's Mech is down at %.0f s" % (src.node, time.time() - self.t0),
                  flush=True)
            self.kills.append((time.time() - self.t0, src.node, 0))
            src.down = True
        if op in (0xE2, 0xED) and self.args.debug:
            print("hub: pod %s sent %s" % (src.node if src else "?",
                  " ".join("%02X" % b for b in packet[:0x40])), flush=True)
        if op == 0xEC and len(packet) >= 0x24:
            thing, = struct.unpack_from(">l", packet, 0x08)
            x, y, z, h, _fc, sp = struct.unpack_from(">ffffff", packet, 0x0C)
            m = self.mechs.setdefault(thing, Mech(thing))
            m.x, m.y, m.z, m.heading, m.speed, m.seen = x, y, z, h, sp, time.time()
        if op in CONSOLE_OPS:
            return
        if node == 0xFE:
            for pod in self.pods:
                if pod is not src and pod.addr:
                    self.send(pod, b"P", packet)
        else:
            dest = self.pod(node)
            if dest and dest is not src:
                self.send(dest, b"P", packet)
                self.unicast += 1
        self.relayed += 1

    def flush(self):
        """Console packets go out a few at a time; a burst of nine hundred
        datagrams would overrun the pod's socket buffer."""
        for pod in self.pods:
            for p in pod.outbox[:40]:
                self.send(pod, b"P", p)
            del pod.outbox[:40]

    # -- CPU pilots ------------------------------------------------------

    def pilot(self, pod, now):
        me = self.mechs.get(pod.node)
        if not me or pod.down or now - pod.started < self.args.settle:
            return
        # Advanced mode and "stick turns", so the stick steers (buttons 33,
        # 31). Pressed a couple of times in case the first went in while the
        # Mech was still dropping and ignoring its controls.
        if pod.moded < 3 and now - pod.started > self.args.settle + 4 * pod.moded:
            for b in (0x33, 0x31):
                self.send(pod, b"R", rio([0xB1, b]) + rio([0xB0, b]))
            pod.moded += 1
        down = {p.node for p in self.pods if p.down}
        foes = [m for t, m in self.mechs.items()
                if t != pod.node and t not in down and now - m.seen < 3.0]
        if not foes:
            self.send(pod, b"R", rio([0xC0, 0xA0, 0, 0]))
            return
        foe = min(foes, key=lambda m: (m.x - me.x) ** 2 + (m.y - me.y) ** 2)
        dx, dy = foe.x - me.x, foe.y - me.y
        dist = math.hypot(dx, dy)
        # Heading h walks along (sin h, -cos h): 0 is -Y, 90 is +X.
        want = math.degrees(math.atan2(dx, -dy)) % 360.0
        err = (want - me.heading + 540.0) % 360.0 - 180.0
        turn = min(0x80, int(abs(err) * 6))
        a1, a2 = (0, turn) if err > 0 else (turn, 0)     # A2 turns up, A1 down
        throttle = 0x340 if dist > 200 else (0x1A0 if dist > 90 else 0)
        if abs(err) > 60:
            throttle = min(throttle, 0x100)
        out = (rio([0xC0, 0xA0, throttle >> 8, throttle & 0xFF]) +
               rio([0xC0, 0xA1, 0, a1]) + rio([0xC0, 0xA2, 0, a2]))
        # The trigger is held while the target is in front, as a pilot would
        # hold it; the weapons recycle at their own rate.
        aimed = abs(err) < 6 and dist < self.args.fire_range
        if self.args.debug and int(now * 10) % 20 == 0:
            print("  pilot %d: me %.0f,%.0f h %.0f  foe %.0f,%.0f  want %.0f err %.0f dist %.0f%s"
                  % (pod.node, me.x, me.y, me.heading, foe.x, foe.y, want, err, dist,
                     "  FIRE" if aimed else ""), flush=True)
        # All three trigger groups (buttons A5, A6, A7).
        # Pressed again every so often: a press that lands while the Mech is
        # still dropping in is ignored, and a pilot who thinks he is holding
        # the trigger would never press it again.
        if aimed and (not pod.firing or now >= pod.fire_at):
            if pod.firing:
                out += rio([0xB0, 0xA5]) + rio([0xB0, 0xA6]) + rio([0xB0, 0xA7])
            out += rio([0xB1, 0xA5]) + rio([0xB1, 0xA6]) + rio([0xB1, 0xA7])
            pod.firing, pod.fire_at = True, now + 1.5
        elif not aimed and pod.firing:
            out += rio([0xB0, 0xA5]) + rio([0xB0, 0xA6]) + rio([0xB0, 0xA7])
            pod.firing = False
        self.send(pod, b"R", out)

    # -- the operator's view, as text for now ------------------------------

    def status(self, now):
        rows = []
        for pod in self.pods:
            m = self.mechs.get(pod.node)
            live = m and now - m.seen < 3.0
            rows.append("%s%d %s %7.0f %7.0f %5.0f %5.1f" % (
                "you" if pod.human else "bot", pod.node,
                "live" if live else ("wait" if not pod.addr else "----"),
                m.x if m else 0, m.y if m else 0, m.heading if m else 0,
                (m.speed * 360.0) if m else 0))
        print("t %5.0f  relayed %6d | %s" % (now - self.t0, self.relayed, " | ".join(rows)),
              flush=True)

    def run(self):
        self.t0 = time.time()
        if self.args.console:
            self.console = console_view.TkConsole(self)
        self.launch()
        last_view = 0.0
        last_pilot = last_status = 0.0
        try:
            while self.args.seconds <= 0 or time.time() - self.t0 < self.args.seconds:
                self.receive()
                self.flush()
                now = time.time()
                if now - last_pilot >= 0.1:
                    for pod in self.pods:
                        if not pod.human and pod.addr:
                            self.pilot(pod, now)
                    last_pilot = now
                if self.console and now - last_view >= 0.1:
                    self.console.draw()
                    last_view = now
                if now - last_status >= 2.0:
                    self.status(now)
                    last_status = now
                if all(p.proc.poll() is not None for p in self.pods):
                    print("hub: every pod has exited")
                    break
                time.sleep(0.005)
        except KeyboardInterrupt:
            pass
        finally:
            if self.args.console_png:
                console_view.save_png(self, self.args.console_png, self.args.follow)
                print("hub: operator's view written to %s" % self.args.console_png)
            self.stop()
            ms = [self.mechs[p.node] for p in self.pods if p.node in self.mechs]
            if len(ms) > 1:
                d = min(math.hypot(a.x - b.x, a.y - b.y)
                        for i, a in enumerate(ms) for b in ms[i + 1:])
                print("hub: closest two Mechs ended %.0f apart" % d)
            print("hub: relayed %d packets, %d of them to one pod; dropped %d forwarded"
                  % (self.relayed, self.unicast, self.forwards))
            for (sender, thing), n in sorted(self.hits.items()):
                print("hub: pod %d reported %d damage to thing %d" % (sender, n, thing))
            for t, thing, shooter in self.kills:
                print("hub: at %.0f s pod %d's Mech was destroyed" % (t, thing))
            for pod in self.pods:
                print("hub: pod %d sent %s" % (pod.node, " ".join(
                    "%02X:%d" % (op, n) for op, n in sorted(pod.ops.items()))))


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scenario", default="BadLands-16")
    ap.add_argument("--bots", type=int, default=1)
    ap.add_argument("--human", action="store_true")
    ap.add_argument("--vehicles", default="0,8,12,30,34,4,26,13")
    ap.add_argument("--port", type=int, default=5170)
    ap.add_argument("--seconds", type=float, default=0)
    ap.add_argument("--range", type=int, default=500,
                    help="visibility range sent in 0xE5, each half")
    ap.add_argument("--settle", type=float, default=12.0,
                    help="seconds before a CPU pilot touches the controls")
    ap.add_argument("--fire-range", type=float, default=800.0)
    ap.add_argument("--arena", action="store_true",
                    help="start on open ground, on a ring, instead of drop points")
    ap.add_argument("--ring", type=float, default=150.0)
    ap.add_argument("--debug", action="store_true", help="print what each pilot sees")
    ap.add_argument("--console", action="store_true",
                    help="open the operator's view: the centre from above")
    ap.add_argument("--console-png", default="",
                    help="write the operator's view to a PNG when the run ends")
    ap.add_argument("--follow", action="store_true",
                    help="with --console-png, follow the fighting instead of the whole map")
    ap.add_argument("--pod-args", default="",
                    help="more options for every pod, e.g. peeks for a report")
    args = ap.parse_args(argv[1:])
    args.vehicles = [int(v) for v in args.vehicles.split(",")]
    while len(args.vehicles) < args.bots + 1:
        args.vehicles.append(0)
    Hub(args).run()


if __name__ == "__main__":
    main(sys.argv)
