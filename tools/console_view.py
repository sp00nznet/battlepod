"""The operator's view: the whole centre from above.

The real operator console showed the game on a map. This one draws what the
hub knows - the scenario's objects, and every Mech from the 0xEC broadcasts
going past - in a Tk window, and can write the same picture to a PNG with PIL
so a headless run can be looked at afterwards.

Keys in the window: Z switches between the whole map and a view that follows
the fighting; Esc closes the window (the game goes on).
"""
import math

COLOURS = ["#e8b33c", "#4fa3e0", "#e05a4f", "#6cc36c",
           "#c07ae0", "#e08a3c", "#3cc8c8", "#d0d0d0"]
BG, MAP, TEXT, DIM = "#16181c", "#555a60", "#e8e8e8", "#8a8f96"
SIZE, SIDE = 720, 250


def world_bounds(objects):
    xs = [o[0] for o in objects] or [0.0]
    ys = [o[1] for o in objects] or [0.0]
    return min(xs), min(ys), max(xs), max(ys)


def scene(hub, follow):
    """What to draw, as primitives in screen space: a list of
    ('dot', x, y, r, colour), ('line', x0, y0, x1, y1, colour, width),
    ('text', x, y, string, colour, anchor)."""
    out = []
    now = hub.clock()
    live = [(p, hub.mechs.get(p.node)) for p in hub.pods]
    live = [(p, m) for p, m in live if m]
    if follow and live:
        xs = [m.x for _, m in live]
        ys = [m.y for _, m in live]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        half = max(150.0, (max(xs) - min(xs)) * 0.7, (max(ys) - min(ys)) * 0.7)
        x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    else:
        x0, y0, x1, y1 = hub.bounds
        pad = max(x1 - x0, y1 - y0) * 0.03
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    span = max(x1 - x0, y1 - y0)
    scale = SIZE / span

    def sx(x):
        return (x - x0) * scale

    def sy(y):
        # Map +Y points down the screen: heading 0 walks toward -Y, which is
        # then up, the way a pilot would think of north.
        return (y - y0) * scale

    r_obj = max(1.0, min(4.0, 3.0 * scale))
    for x, y, cls in hub.map_objects:
        if x0 <= x <= x1 and y0 <= y <= y1:
            out.append(("dot", sx(x), sy(y), r_obj * (1.6 if cls == 2 else 1.0), MAP))

    for i, (pod, m) in enumerate(live):
        colour = COLOURS[(pod.node - 1) % len(COLOURS)]
        x, y = sx(m.x), sy(m.y)
        stale = now - m.seen > 3.0
        if pod.down or stale:
            d = 7
            out.append(("line", x - d, y - d, x + d, y + d, colour, 3))
            out.append(("line", x - d, y + d, x + d, y - d, colour, 3))
        else:
            h = math.radians(m.heading)
            out.append(("dot", x, y, 7, colour))
            out.append(("line", x, y, x + 18 * math.sin(h), y - 18 * math.cos(h), colour, 3))
        who = "YOU" if pod.human else "bot %d" % pod.node
        out.append(("text", x + 10, y - 14, who, colour, "w"))

    # The side panel.
    tx = SIZE + 14
    ty = 16
    out.append(("text", tx, ty, "BATTLEPOD CENTRE", TEXT, "w"))
    ty += 18
    out.append(("text", tx, ty, "%s   t %.0f s" % (hub.args.scenario, now - hub.t0), DIM, "w"))
    ty += 26
    for pod, m in live:
        colour = COLOURS[(pod.node - 1) % len(COLOURS)]
        state = "DOWN" if pod.down else ("---" if now - m.seen > 3.0 else "live")
        who = "you" if pod.human else "bot %d" % pod.node
        taken = hub.hits.get((pod.node, pod.node), 0)
        out.append(("text", tx, ty, "%-6s %-4s %5.0f kph" % (who, state, m.speed * 360.0),
                    colour, "w"))
        ty += 16
        out.append(("text", tx + 10, ty, "hits taken %d   heading %.0f" % (taken, m.heading),
                    DIM, "w"))
        ty += 22
    ty += 6
    out.append(("text", tx, ty, "packets relayed %d" % hub.relayed, DIM, "w"))
    ty += 16
    for t, node, _ in hub.kills[-6:]:
        out.append(("text", tx, ty, "%4.0f s  pod %d down" % (t, node), TEXT, "w"))
        ty += 16
    out.append(("text", tx, SIZE - 14, "Z: %s" % ("following" if follow else "whole map"),
                DIM, "w"))
    return out


class TkConsole:
    def __init__(self, hub):
        import tkinter
        self.hub = hub
        self.follow = False
        self.root = tkinter.Tk()
        self.root.title("battlepod - operator console")
        self.canvas = tkinter.Canvas(self.root, width=SIZE + SIDE, height=SIZE,
                                     bg=BG, highlightthickness=0)
        self.canvas.pack()
        self.root.bind("<KeyPress-z>", lambda e: self.toggle())
        self.root.bind("<Escape>", lambda e: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.open = True

    def toggle(self):
        self.follow = not self.follow

    def close(self):
        self.open = False
        try:
            self.root.destroy()
        except Exception:
            pass

    def draw(self):
        if not self.open:
            return
        c = self.canvas
        c.delete("all")
        for p in scene(self.hub, self.follow):
            if p[0] == "dot":
                _, x, y, r, col = p
                c.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="")
            elif p[0] == "line":
                _, a, b, x, y, col, w = p
                c.create_line(a, b, x, y, fill=col, width=w)
            else:
                _, x, y, s, col, anchor = p
                c.create_text(x, y, text=s, fill=col, anchor=anchor, font=("Consolas", 10))
        try:
            self.root.update()
        except Exception:
            self.open = False


def save_png(hub, path, follow):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (SIZE + SIDE, SIZE), BG)
    d = ImageDraw.Draw(img)
    for p in scene(hub, follow):
        if p[0] == "dot":
            _, x, y, r, col = p
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        elif p[0] == "line":
            _, a, b, x, y, col, w = p
            d.line([a, b, x, y], fill=col, width=w)
        else:
            _, x, y, s, col, anchor = p
            d.text((x, y - 6), s, fill=col)
    img.save(path)
