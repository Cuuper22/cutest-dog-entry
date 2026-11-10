"""Cutest dog: a fluffy puppy waving at a butterfly in a sunny meadow.

Drawn with signed-distance shapes and written as a PNG. Standard library only.
Deterministic: no randomness, no timestamps.
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


def fluffy(shape, cx, cy, n, amp, lo=-1.0, hi=1.0, phase=0.0):
    """Scallop a shape's edge into rounded fur bumps.

    Bumps follow the angle around (cx, cy); they are applied where the
    downward component sin(theta) lies between lo and hi (soft edges).
    """
    f = shape[0]

    def sdf(x, y):
        d = f(x, y)
        if d > amp + 2.0 or d < -amp - 2.0:
            return d
        dx, dy = x - cx, y - cy
        r = math.sqrt(dx * dx + dy * dy) or 1e-9
        s = dy / r
        w = smoothstep(lo - 0.15, lo + 0.15, s) * (1.0 - smoothstep(hi - 0.15, hi + 0.15, s))
        if w <= 0.0:
            return d
        th = math.atan2(dy, dx)
        return d - amp * w * abs(math.cos(n * th * 0.5 + phase))
    x0, y0, x1, y1 = shape[1]
    return sdf, (x0 - amp, y0 - amp, x1 + amp, y1 + amp)


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
INK = hexc('7a4a32')        # warm brown outline
FUR = hexc('f4b97c')
FUR_HI = hexc('fdd9ab')
FUR_SH = hexc('d99560')
EAR = hexc('c07a45')
EAR_SH = hexc('9a5d33')
CREAM = hexc('fff6e8')
CREAM_SH = hexc('f1dcc2')
EYE = hexc('2a1812')
IRIS = hexc('7e4a2f')
PUPIL = hexc('1a0d08')
NOSE = hexc('3a241b')
TONGUE = hexc('ff8a9a')
PAD = hexc('f7a3ad')
BLUSH = hexc('ff8fa0')
BROW = hexc('a3653d')
COLLAR = hexc('e8475a')
GOLD = hexc('ffc93c')
SKY_TOP = hexc('bfe2f6')
SKY_LOW = hexc('fff4df')
SUN = hexc('fffbea')
HILL_FAR = hexc('d3ebb4')
HILL_NEAR = hexc('b4dc93')
GRASS = hexc('8cc66e')
WING = hexc('ffb6d2')
WING_HI = hexc('fff0f6')
WING_SH = hexc('f08cb6')


def draw():
    cv = Canvas(SIZE)

    # ---- sunlit meadow background
    def bg(x, y):
        t = clamp01((y + 20) / 380.0)
        col = mix(SKY_TOP, SKY_LOW, t * t)
        g = math.sqrt((x - 70) ** 2 + (y - 40) ** 2) / 260.0
        col = mix(SUN, col, smoothstep(0.0, 1.0, g))
        far = 352 + 14 * math.sin(x / 70.0 + 1.0)
        if y > far - 2:
            col = mix(col, mix(HILL_FAR, HILL_NEAR, clamp01((y - far) / 120.0)),
                      smoothstep(far - 2, far + 2, y))
        near = 392 + 10 * math.sin(x / 55.0 + 3.0) + 0.0004 * (x - 256) ** 2
        if y > near - 2:
            col = mix(col, mix(HILL_NEAR, GRASS, clamp01((y - near) / 140.0)),
                      smoothstep(near - 2, near + 2, y))
        return col
    cv.background(bg)

    # bokeh dots in the sky (fixed positions)
    for bx, by, br, a in ((60, 120, 14, 0.35), (110, 60, 8, 0.45), (440, 70, 16, 0.3),
                          (470, 250, 9, 0.4), (40, 260, 10, 0.35), (380, 30, 6, 0.5),
                          (25, 190, 5, 0.5), (490, 140, 6, 0.45)):
        cv.paint(ellipse(bx, by, br, br), (255, 255, 255), alpha=a, soft=br * 0.35)

    # tiny meadow flowers, kept to the sides
    def daisy(fx, fy, r, petal=(255, 255, 255), centre=hexc('ffd34d')):
        for k in range(6):
            ang = k * math.pi / 3
            cv.paint(ellipse(fx + math.cos(ang) * r * 0.9, fy + math.sin(ang) * r * 0.9,
                             r * 0.62, r * 0.38, ang), petal)
        cv.paint(ellipse(fx, fy, r * 0.45, r * 0.45), centre)
    daisy(40, 428, 8)
    daisy(88, 446, 9, petal=hexc('ffd0de'))
    daisy(458, 418, 9)
    daisy(430, 470, 8, petal=hexc('ffd0de'))
    daisy(30, 470, 7)
    daisy(486, 372, 6)

    # soft ground shadow
    cv.paint(ellipse(256, 452, 165, 20), hexc('6fa45a'), alpha=0.35, soft=12)

    ow = 2.6
    # ---- tail (behind body), a happy upward curl with a cream tip
    # a tapered, wagging tail: circles shrinking along a curve
    path = bezier((196, 420), (118, 428), (96, 372), 14)
    tail = union([ellipse(x, y, 14 - 8 * k / 14, 14 - 8 * k / 14)
                  for k, (x, y) in enumerate(path)], k=6)
    cv.paint(tail, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=6,
             light=(120, 405, 30, FUR_HI))
    cv.paint(stroke(bezier((76, 384), (68, 372), (72, 358)), 1.6), INK, alpha=0.6)
    cv.paint(stroke(bezier((66, 396), (54, 380), (60, 362)), 1.6), INK, alpha=0.45)

    # ---- body with haunches
    body = union([ellipse(256, 372, 94, 82),
                  ellipse(186, 410, 50, 40), ellipse(326, 410, 50, 40)], k=22)
    cv.paint(body, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=14,
             light=(236, 350, 110, FUR_HI))
    # fluffy cream chest tuft
    chest = fluffy(ellipse(256, 356, 56, 62), 256, 356, 10, 6.0, lo=0.2, hi=1.0)
    cv.paint(intersect(chest, body), CREAM, shade=CREAM_SH, rim=7)
    # soft shadow under the chin
    cv.paint(ellipse(256, 312, 90, 22), FUR_SH, alpha=0.35, soft=12)

    # ---- back feet with cream toes
    for side in (-1, 1):
        fx = 256 + side * 100
        foot = ellipse(fx, 440, 34, 18, ang=side * math.radians(8))
        cv.paint(foot, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=7,
                 light=(fx - 6, 434, 26, FUR_HI))
        cv.paint(intersect(ellipse(fx + side * 14, 446, 24, 13), foot), CREAM, soft=1.0)
        for tx in (-7, 7):
            cv.paint(stroke([(fx + side * 16 + tx, 447), (fx + side * 16 + tx, 455)], 1.3), INK)
        # re-draw outline over the cream patch
        ring = intersect(foot, (lambda x, y, f=foot[0]: -f(x, y) - ow, foot[1]))
        cv.paint(ring, INK)

    # ---- red collar with a gold heart tag
    collar = intersect(stroke(bezier((180, 296), (256, 330), (332, 296)), 8), body)
    cv.paint(collar, COLLAR, outline=hexc('b02c40'), ow=1.4)
    cv.paint(ellipse(257, 323, 5.5, 5.5), GOLD, outline=hexc('b8862a'), ow=1.4)
    cv.paint(ellipse(257, 323, 2.4, 2.4), COLLAR)
    tag = heart(258, 336, 22, ang=math.radians(-6))
    cv.paint(tag, GOLD, outline=hexc('b8862a'), ow=1.6, light=(252, 331, 9, hexc('fff2b8')))

    # ---- planted front leg (viewer's left)
    lx = 228
    leg = union([stroke([(lx, 396), (lx, 426)], 25), ellipse(lx, 437, 32, 22)], k=14)
    cv.paint(leg, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=8,
             light=(lx - 8, 405, 45, FUR_HI))
    cv.paint(intersect(ellipse(lx, 448, 30, 14), leg), CREAM, soft=1.0)
    ring = intersect(leg, (lambda x, y, f=leg[0]: -f(x, y) - ow, leg[1]))
    cv.paint(ring, INK)
    for tx in (-9, 9):
        cv.paint(stroke([(lx + tx, 446), (lx + tx, 455)], 1.3), INK)

    # ---- head (tilted towards the butterfly)
    cv.set_rotation(math.radians(-11), 256, 300)
    for side in (-1, 1):
        ex = 256 + side * 128
        ear = ellipse(ex, 205, 42, 84, ang=side * math.radians(-16))
        ear = fluffy(ear, ex, 205, 9, 4.0, lo=0.55, hi=1.0)
        cv.paint(ear, EAR, outline=INK, ow=ow, shade=EAR_SH, rim=12,
                 light=(ex - side * 3, 185, 45, hexc('d48d56')))
    head = union([ellipse(256, 190, 134, 110),
                  ellipse(180, 236, 72, 56), ellipse(332, 236, 72, 56)], k=36)
    head = fluffy(head, 256, 210, 22, 5.5, lo=0.25, hi=1.0)
    tuft = union([ellipse(238, 86, 15, 14), ellipse(258, 78, 16, 15),
                  ellipse(278, 86, 14, 13)], k=4)
    head = union([head, tuft], k=6)
    cv.paint(head, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=15,
             light=(222, 140, 150, FUR_HI))
    muzzle = union([ellipse(256, 272, 50, 34), ellipse(256, 246, 26, 22)], k=14)
    cv.paint(muzzle, CREAM, shade=CREAM_SH, rim=6, soft=2.0)

    # small sweet eyebrows, inner ends raised
    cv.paint(stroke(bezier((190, 168), (198, 161), (208, 160), 8), 4.0), BROW)
    cv.paint(stroke(bezier((304, 160), (314, 161), (322, 168), 8), 4.0), BROW)

    # eyes: big, deep, layered highlights
    for ex in (198, 314):
        ey = 222
        eye = ellipse(ex, ey, 31, 35)
        cv.paint(eye, EYE)
        cv.paint(ellipse(ex, ey + 5, 25, 28), IRIS, light=(ex, ey + 28, 24, hexc('b9774a')), soft=1.5)
        cv.paint(ellipse(ex, ey + 1, 16, 18), PUPIL, soft=1.5)
        lid = intersect(stroke(bezier((ex - 14, ey + 25), (ex, ey + 35), (ex + 14, ey + 25)), 1.8), eye)
        cv.paint(lid, (255, 214, 170), alpha=0.65, soft=1.0)
        cv.paint(ellipse(ex - 11, ey - 14, 11.5, 12.5), (255, 255, 255))
        cv.paint(ellipse(ex + 12, ey + 12, 5.5, 5.5), (255, 255, 255))
        cv.paint(ellipse(ex + 4, ey - 24, 3, 3), (255, 255, 255), alpha=0.9)
        cv.paint(ellipse(ex - 4, ey + 22, 2.4, 2.4), (255, 255, 255), alpha=0.8)

    # cheeks
    for bx in (160, 352):
        cv.paint(ellipse(bx, 264, 24, 13), BLUSH, alpha=0.5, soft=6)

    # tongue, nose, mouth
    cv.paint(ellipse(256, 291, 11, 14), TONGUE, outline=INK, ow=2.0)
    cv.paint(stroke([(256, 285), (256, 295)], 0.9), hexc('d9607a'))
    cv.paint(ellipse(256, 257, 16, 11), NOSE, light=(256, 262, 14, hexc('5a3a2c')))
    cv.paint(ellipse(250, 252, 5, 3), (255, 255, 255), alpha=0.85)
    cv.paint(stroke([(256, 266), (256, 275)], 1.5), INK)
    cv.paint(stroke(bezier((236, 275), (246, 285), (256, 275)), 1.5), INK)
    cv.paint(stroke(bezier((256, 275), (266, 285), (276, 275)), 1.5), INK)
    cv.set_rotation(0, 0, 0)

    # ---- raised front paw, waving, toe beans showing
    px, py = 366, 314
    arm = union([stroke(bezier((316, 368), (346, 360), (px - 2, py + 16)), 22),
                 ellipse(px, py, 29, 27, ang=math.radians(-20))], k=12)
    arm = fluffy(arm, px, py, 8, 2.5, lo=-1.0, hi=-0.3)
    cv.paint(arm, FUR, outline=INK, ow=ow, shade=FUR_SH, rim=9,
             light=(px - 10, py + 10, 40, FUR_HI))
    cv.paint(ellipse(px + 1, py + 6, 12, 10, ang=math.radians(-20)), PAD)
    for bx, by in ((-14, -9), (0, -15), (14, -9)):
        cv.paint(ellipse(px + bx, py + by, 5.5, 6.5, ang=math.radians(bx * 1.5)), PAD)
    # little wave marks
    cv.paint(stroke(bezier((px + 36, py - 30), (px + 46, py - 16), (px + 40, py)), 1.8), INK, alpha=0.7)
    cv.paint(stroke(bezier((px + 46, py - 40), (px + 60, py - 18), (px + 52, py + 4)), 1.8), INK, alpha=0.5)

    # a little heart of delight between puppy and butterfly
    cv.paint(heart(450, 256, 22, ang=math.radians(12)), hexc('ff7f9c'),
             outline=hexc('d95c78'), ow=1.6, light=(445, 251, 8, hexc('ffd0dc')))

    # ---- butterfly visiting
    bx, by = 446, 196
    for side in (-1, 1):
        up = ellipse(bx + side * 13, by - 9, 14, 17, ang=side * math.radians(-35))
        lo = ellipse(bx + side * 10, by + 10, 9, 11, ang=side * math.radians(30))
        cv.paint(up, WING, outline=hexc('c45a8a'), ow=1.6, light=(bx + side * 10, by - 6, 14, WING_HI))
        cv.paint(lo, WING_SH, outline=hexc('c45a8a'), ow=1.6, light=(bx + side * 8, by + 8, 9, WING))
        cv.paint(ellipse(bx + side * 15, by - 12, 4, 4), hexc('fff6a8'))
        cv.paint(stroke(bezier((bx, by - 12), (bx + side * 4, by - 26), (bx + side * 12, by - 30)), 0.9),
                 hexc('6b3f2f'))
        cv.paint(ellipse(bx + side * 12, by - 30, 2.2, 2.2), hexc('6b3f2f'))
    cv.paint(ellipse(bx, by, 3.2, 13), hexc('6b3f2f'))

    return cv.png()


def main():
    out_dir = os.environ.get('MAKEFUN_OUTPUT_DIR', '/output')
    os.makedirs(out_dir, exist_ok=True)
    data = draw()
    with open(os.path.join(out_dir, 'entry.png'), 'wb') as f:
        f.write(data)


if __name__ == '__main__':
    main()
