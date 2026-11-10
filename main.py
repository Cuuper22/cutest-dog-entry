"""Cutest dog: a chibi puppy drawn with signed-distance shapes, written as a PNG.

Standard library only. Deterministic: no randomness, no timestamps.
Writes $MAKEFUN_OUTPUT_DIR/entry.png (default /output/entry.png).
"""
import math
import os
import struct
import zlib

SIZE = 768          # output pixels
DESIGN = 512.0      # design coordinate space
ZOOM = 1.06         # camera zoom on the design
CX, CY = 256.0, 266.0  # design point shown at the image centre
S = SIZE / DESIGN * ZOOM  # pixels per design unit


def to_px(x, y):
    return ((x - CX) * S + SIZE * 0.5, (y - CY) * S + SIZE * 0.5)


def to_design(i, j):
    return ((i + 0.5 - SIZE * 0.5) / S + CX, (j + 0.5 - SIZE * 0.5) / S + CY)


# ---------------------------------------------------------------- helpers
def clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def smoothstep(e0, e1, x):
    t = clamp01((x - e0) / (e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def hexc(h):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ---------------------------------------------------------------- shapes
# A shape is (sdf, bbox) with sdf(x, y) -> signed distance in design units
# (negative inside) and bbox = (x0, y0, x1, y1) in design units.

def ellipse(cx, cy, rx, ry, ang=0.0):
    ca, sa = math.cos(ang), math.sin(ang)
    irx, iry = 1.0 / rx, 1.0 / ry
    irx2, iry2 = irx * irx, iry * iry
    mn = min(rx, ry)

    def sdf(x, y):
        dx, dy = x - cx, y - cy
        u = dx * ca + dy * sa
        v = -dx * sa + dy * ca
        k0 = math.sqrt(u * u * irx2 + v * v * iry2)
        k1 = math.sqrt(u * u * irx2 * irx2 + v * v * iry2 * iry2)
        if k1 < 1e-9:
            return -mn
        return k0 * (k0 - 1.0) / k1
    r = max(rx, ry)
    return sdf, (cx - r, cy - r, cx + r, cy + r)


def stroke(points, r):
    segs = []
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        segs.append((ax, ay, dx, dy, 1.0 / max(dx * dx + dy * dy, 1e-9)))

    def sdf(x, y):
        best = 1e18
        for ax, ay, dx, dy, il in segs:
            px, py = x - ax, y - ay
            t = (px * dx + py * dy) * il
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            qx, qy = px - dx * t, py - dy * t
            d = qx * qx + qy * qy
            if d < best:
                best = d
        return math.sqrt(best) - r
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return sdf, (min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r)


def polygon(points):
    pts = list(points)
    edges = []
    for k in range(len(pts)):
        ax, ay = pts[k]
        bx, by = pts[(k + 1) % len(pts)]
        dx, dy = bx - ax, by - ay
        edges.append((ax, ay, bx, by, dx, dy, 1.0 / max(dx * dx + dy * dy, 1e-12)))

    def sdf(x, y):
        best = 1e18
        inside = False
        for ax, ay, bx, by, dx, dy, il in edges:
            px, py = x - ax, y - ay
            t = (px * dx + py * dy) * il
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            qx, qy = px - dx * t, py - dy * t
            d = qx * qx + qy * qy
            if d < best:
                best = d
            if (ay > y) != (by > y) and x < ax + (y - ay) * dx / dy:
                inside = not inside
        d = math.sqrt(best)
        return -d if inside else d
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return sdf, (min(xs), min(ys), max(xs), max(ys))


def heart(cx, cy, size, ang=0.0, n=48):
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        x, y = x * size / 32.0, (y + 2) * size / 32.0
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return polygon(pts)


def bezier(p0, p1, p2, n=16):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c = (1 - t) * (1 - t), 2 * (1 - t) * t, t * t
        pts.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return pts


def union(shapes, k=0.0):
    fns = [s[0] for s in shapes]

    def sdf(x, y):
        d = fns[0](x, y)
        for f in fns[1:]:
            e = f(x, y)
            if k > 0.0:
                h = k - abs(d - e)
                if h > 0.0:
                    d = min(d, e) - h * h * 0.25 / k
                    continue
            d = d if d < e else e
        return d
    bb = (min(s[1][0] for s in shapes) - k, min(s[1][1] for s in shapes) - k,
          max(s[1][2] for s in shapes) + k, max(s[1][3] for s in shapes) + k)
    return sdf, bb


def intersect(a, b):
    fa, fb = a[0], b[0]

    def sdf(x, y):
        return max(fa(x, y), fb(x, y))
    return sdf, (max(a[1][0], b[1][0]), max(a[1][1], b[1][1]),
                 min(a[1][2], b[1][2]), min(a[1][3], b[1][3]))


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, n):
        self.n = n
        self.r = [0.0] * (n * n)
        self.g = [0.0] * (n * n)
        self.b = [0.0] * (n * n)
        # Current group transform: rotate about a pivot (design units).
        self.rot = None

    def set_rotation(self, ang, px, py):
        self.rot = (math.cos(ang), math.sin(ang), px, py) if ang else None

    def background(self, fn):
        n = self.n
        for j in range(n):
            for i in range(n):
                c = fn(*to_design(i, j))
                k = j * n + i
                self.r[k], self.g[k], self.b[k] = c

    def paint(self, shape, color, alpha=1.0, outline=None, ow=0.0,
              shade=None, rim=0.0, light=None, soft=0.0):
        """Fill a shape.

        color   base RGB
        outline inner stroke colour of width ow (design units)
        shade   colour mixed in near the edge over `rim` design units
        light   (lx, ly, radius, rgb) radial highlight in local coords
        soft    extra edge feather in design units (for blush, shadows)
        """
        sdf, (x0, y0, x1, y1) = shape
        rot = self.rot
        if rot:
            c, s, px, py = rot
            corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
            xs, ys = [], []
            for (x, y) in corners:
                dx, dy = x - px, y - py
                xs.append(px + dx * c - dy * s)
                ys.append(py + dx * s + dy * c)
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = 2.0 + soft
        n = self.n
        px0, py0 = to_px(x0 - pad, y0 - pad)
        px1, py1 = to_px(x1 + pad, y1 + pad)
        i0, i1 = max(0, int(px0)), min(n, int(px1) + 1)
        j0, j1 = max(0, int(py0)), min(n, int(py1) + 1)
        R, G, B = self.r, self.g, self.b
        aa = 1.0 / S  # one pixel in design units
        feather = max(aa, soft)
        half = SIZE * 0.5
        for j in range(j0, j1):
            sy = (j + 0.5 - half) / S + CY
            row = j * n
            for i in range(i0, i1):
                sx = (i + 0.5 - half) / S + CX
                if rot:
                    dx, dy = sx - px, sy - py
                    x = px + dx * c + dy * s
                    y = py - dx * s + dy * c
                else:
                    x, y = sx, sy
                d = sdf(x, y)
                if d >= feather * 0.5 + soft * 0.5:
                    continue
                if soft > 0.0:
                    cov = smoothstep(soft, -soft, d)
                else:
                    cov = 0.5 - d / aa
                    cov = 0.0 if cov < 0.0 else (1.0 if cov > 1.0 else cov)
                if cov <= 0.0:
                    continue
                col = color
                if light is not None:
                    lx, ly, lr, lc = light
                    t = math.sqrt((x - lx) ** 2 + (y - ly) ** 2) / lr
                    col = mix(lc, col, smoothstep(0.0, 1.0, t))
                if shade is not None and rim > 0.0:
                    col = mix(col, shade, smoothstep(-rim, 0.0, d) * 0.85)
                if outline is not None:
                    t = 0.5 + (d + ow) / aa
                    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                    col = mix(col, outline, t)
                a = cov * alpha
                k = row + i
                R[k] += (col[0] - R[k]) * a
                G[k] += (col[1] - G[k]) * a
                B[k] += (col[2] - B[k]) * a

    def png(self):
        n = self.n
        raw = bytearray()
        R, G, B = self.r, self.g, self.b
        for j in range(n):
            raw.append(0)
            row = j * n
            for i in range(n):
                k = row + i
                raw.append(max(0, min(255, int(R[k] + 0.5))))
                raw.append(max(0, min(255, int(G[k] + 0.5))))
                raw.append(max(0, min(255, int(B[k] + 0.5))))

        def chunk(tag, data):
            body = tag + data
            return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF)
        ihdr = struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0)
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


# ---------------------------------------------------------------- palette
INK = hexc('4a2e22')
FUR = hexc('f2b67a')
FUR_HI = hexc('fcd3a1')
FUR_SH = hexc('d8935a')
EAR = hexc('b9733f')
EAR_SH = hexc('94592d')
CREAM = hexc('fff4e4')
CREAM_SH = hexc('f0d9bf')
EYE = hexc('2b1a14')
NOSE = hexc('2f1d17')
TONGUE = hexc('ff8a9a')
BLUSH = hexc('ff8fa0')
BG_IN = hexc('eef8fd')
BG_OUT = hexc('b9def2')
COLLAR = hexc('e8475a')
GOLD = hexc('ffc93c')
HEART = hexc('ff8fa8')


def draw():
    cv = Canvas(SIZE)

    def bg(x, y):
        t = math.sqrt((x - 256) ** 2 + (y - 220) ** 2) / 380.0
        return mix(BG_IN, BG_OUT, smoothstep(0.05, 1.0, t))
    cv.background(bg)

    # ground shadow
    cv.paint(ellipse(256, 452, 185, 20), hexc('8fb9d3'), alpha=0.45, soft=10)

    # two little floating hearts
    cv.paint(heart(420, 118, 34, ang=math.radians(14)), HEART, outline=hexc('d95c78'), ow=2.2,
             light=(414, 112, 14, hexc('ffc4d2')))
    cv.paint(heart(452, 172, 20, ang=math.radians(-10)), HEART, alpha=0.75)

    ow = 3.0
    # tail (behind body), a happy upward curl
    tail = union([stroke(bezier((320, 415), (392, 410), (382, 345), 20), 15),
                  ellipse(380, 342, 17, 19)], k=10)
    cv.paint(tail, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=8,
             light=(372, 360, 30, FUR_HI))

    # body with haunches
    body = union([ellipse(256, 372, 94, 82),
                  ellipse(186, 410, 50, 40), ellipse(326, 410, 50, 40)], k=22)
    cv.paint(body, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=14,
             light=(236, 350, 110, FUR_HI))
    chest = intersect(ellipse(256, 360, 58, 64), body)
    cv.paint(chest, CREAM, shade=CREAM_SH, rim=8)

    # back feet: separate outlined paws turned outwards
    for side in (-1, 1):
        fx = 256 + side * 100
        foot = ellipse(fx, 440, 34, 18, ang=side * math.radians(8))
        cv.paint(foot, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=7,
                 light=(fx - 6, 434, 26, FUR_HI))
        for tx in (-8, 8):
            cv.paint(stroke([(fx + side * 14 + tx, 446), (fx + side * 14 + tx, 455)], 1.5), INK)

    # red collar with a gold heart tag
    collar = intersect(stroke(bezier((180, 296), (256, 330), (332, 296)), 8), body)
    cv.paint(collar, COLLAR, outline=hexc('a8283a'), ow=1.6)
    ring = ellipse(257, 323, 5.5, 5.5)
    cv.paint(ring, GOLD, outline=hexc('b8862a'), ow=1.6)
    cv.paint(ellipse(257, 323, 2.4, 2.4), COLLAR)
    tag = heart(258, 336, 24, ang=math.radians(-6))
    cv.paint(tag, GOLD, outline=hexc('b8862a'), ow=1.8, light=(252, 331, 9, hexc('fff2b8')))

    # stubby front legs + round paws
    for lx in (227, 285):
        leg = union([stroke([(lx, 396), (lx, 426)], 25),
                     ellipse(lx, 437, 32, 22)], k=14)
        cv.paint(leg, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=8,
                 light=(lx - 8, 405, 45, FUR_HI))
        for tx in (-9, 9):
            cv.paint(stroke([(lx + tx, 446), (lx + tx, 455)], 1.5), INK)

    # tennis-ball toy
    ball = ellipse(94, 436, 26, 26)
    cv.paint(ball, hexc('d6ea6a'), outline=INK, ow=ow, shade=hexc('a9c446'), rim=9,
             light=(85, 425, 23, hexc('f3fbb8')))
    for seam in (bezier((70, 420), (92, 436), (76, 458)), bezier((118, 414), (96, 436), (112, 458))):
        cv.paint(intersect(stroke(seam, 2.2), ball), (255, 255, 250))

    # ---- head (tilted)
    cv.set_rotation(math.radians(-11), 256, 300)
    for side in (-1, 1):
        ear = ellipse(256 + side * 128, 205, 42, 84, ang=side * math.radians(-16))
        cv.paint(ear, EAR, outline=INK, ow=ow, shade=EAR_SH, rim=12,
                 light=(256 + side * 125, 190, 40, hexc('c98450')))
    head = union([ellipse(256, 190, 134, 110),
                  ellipse(180, 236, 72, 56), ellipse(332, 236, 72, 56)], k=36)
    tuft = union([ellipse(238, 86, 15, 14), ellipse(258, 78, 16, 15),
                  ellipse(278, 86, 14, 13)], k=4)
    head = union([head, tuft], k=6)
    cv.paint(head, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=15,
             light=(222, 140, 150, FUR_HI))
    muzzle = ellipse(256, 270, 46, 32)
    cv.paint(muzzle, CREAM, shade=CREAM_SH, rim=6, soft=1.5)

    # soft "puppy-dog" brow spots, raised towards the middle
    for side in (-1, 1):
        cv.paint(ellipse(256 + side * 50, 175, 10.5, 6.5, ang=side * math.radians(-18)),
                 FUR_SH, alpha=0.8, soft=2.0)

    # eyes: big, low, glossy
    for ex in (200, 312):
        ey = 222
        cv.paint(ellipse(ex, ey, 29, 33), EYE, light=(ex, ey + 24, 32, hexc('7d4a32')))
        cv.paint(ellipse(ex - 10, ey - 13, 10.5, 11.5), (255, 255, 255))
        cv.paint(ellipse(ex + 11, ey + 13, 5, 5), (255, 255, 255))
        cv.paint(ellipse(ex + 3, ey - 21, 2.8, 2.8), (255, 255, 255), alpha=0.9)

    # cheeks
    for bx in (162, 350):
        cv.paint(ellipse(bx, 262, 24, 13), BLUSH, alpha=0.55, soft=5)

    # tongue, nose, mouth
    cv.paint(ellipse(256, 290, 11, 14), TONGUE, outline=INK, ow=2.2)
    cv.paint(stroke([(256, 284), (256, 294)], 0.9), hexc('d9607a'))
    cv.paint(ellipse(256, 257, 16, 11), NOSE)
    cv.paint(ellipse(250, 252, 5, 3), (255, 255, 255), alpha=0.85)
    cv.paint(stroke([(256, 266), (256, 275)], 1.6), INK)
    cv.paint(stroke(bezier((236, 275), (246, 285), (256, 275)), 1.6), INK)
    cv.paint(stroke(bezier((256, 275), (266, 285), (276, 275)), 1.6), INK)
    cv.set_rotation(0, 0, 0)

    return cv.png()


def main():
    out_dir = os.environ.get('MAKEFUN_OUTPUT_DIR', '/output')
    os.makedirs(out_dir, exist_ok=True)
    data = draw()
    with open(os.path.join(out_dir, 'entry.png'), 'wb') as f:
        f.write(data)


if __name__ == '__main__':
    main()
