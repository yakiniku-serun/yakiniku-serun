"""
セルン 店休日お知らせ動画ジェネレーター（v2: 期間指定・BGM内蔵）
使い方: python3 gen.py config.json out.mp4
config.json 例:
{
  "year": 2026, "month": 12, "mode": "announce",        # announce=前月25日 / reminder=当月1日
  "closed": [7, 8, 14, 21, 31],                          # その月の休み
  "open_notes": [{"day": 28, "text": "28日(月)は\\n年末営業します！"}],
  "extra": "年始：1/1(金)・1/2(土)はお休み／1/3(日)から営業"   # 任意
}
"""
import calendar as cal_mod, datetime as dt, json, math, os, random, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, 'assets')
W, H, FPS, SEC = 1080, 1920, 30, 15
FB = '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'
FR = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
_fc = {}
def font(sz, black=True):
    k = (sz, black)
    if k not in _fc: _fc[k] = ImageFont.truetype(FB if black else FR, sz, index=0)
    return _fc[k]
INK, RED, BLUE, BG = (34, 34, 34), (214, 51, 51), (42, 111, 209), (255, 255, 255)
WK = ['月', '火', '水', '木', '金', '土', '日']   # date.weekday() 順
WK_SUN = ['日', '月', '火', '水', '木', '金', '土']

# ---------- 季節テーマ（月×モードで24種類） ----------
# accent: タイトル下の線や飾りの色 / fx: 背景の動き
THEMES = {
    (1, 'announce'): dict(accent=(200, 40, 40), fx='confetti', cols=[(212, 175, 55), (200, 40, 40)], tag='迎春'),
    (1, 'reminder'): dict(accent=(212, 160, 40), fx='plum', cols=[(225, 90, 120)], tag='新春'),
    (2, 'announce'): dict(accent=(90, 140, 200), fx='snow', cols=[(170, 200, 230)], tag='冬'),
    (2, 'reminder'): dict(accent=(220, 90, 130), fx='heart', cols=[(235, 120, 150)], tag='バレンタイン'),
    (3, 'announce'): dict(accent=(220, 110, 150), fx='plum', cols=[(235, 140, 170)], tag='春'),
    (3, 'reminder'): dict(accent=(150, 190, 90), fx='petal', cols=[(250, 190, 205)], tag='春'),
    (4, 'announce'): dict(accent=(230, 130, 160), fx='petal', cols=[(250, 185, 200)], tag='桜'),
    (4, 'reminder'): dict(accent=(230, 130, 160), fx='petal', cols=[(255, 205, 215), (250, 170, 190)], tag='桜'),
    (5, 'announce'): dict(accent=(70, 160, 90), fx='leaf', cols=[(110, 185, 110)], tag='新緑'),
    (5, 'reminder'): dict(accent=(60, 120, 200), fx='leaf', cols=[(150, 205, 120)], tag='新緑'),
    (6, 'announce'): dict(accent=(80, 120, 200), fx='rain', cols=[(150, 180, 225)], tag='梅雨'),
    (6, 'reminder'): dict(accent=(140, 100, 190), fx='rain', cols=[(175, 150, 220)], tag='あじさい'),
    (7, 'announce'): dict(accent=(40, 90, 180), fx='star', cols=[(240, 200, 60)], tag='七夕'),
    (7, 'reminder'): dict(accent=(30, 150, 200), fx='sparkle', cols=[(80, 180, 230)], tag='夏'),
    (8, 'announce'): dict(accent=(220, 70, 60), fx='firework', cols=[(235, 90, 70), (240, 190, 50), (70, 140, 230)], tag='夏祭り'),
    (8, 'reminder'): dict(accent=(30, 150, 200), fx='sparkle', cols=[(90, 190, 235)], tag='真夏'),
    (9, 'announce'): dict(accent=(200, 160, 40), fx='moon', cols=[(240, 210, 90)], tag='お月見'),
    (9, 'reminder'): dict(accent=(200, 120, 50), fx='leaf', cols=[(225, 165, 70)], tag='初秋'),
    (10, 'announce'): dict(accent=(220, 110, 40), fx='leaf', cols=[(230, 130, 50), (210, 90, 40)], tag='秋'),
    (10, 'reminder'): dict(accent=(150, 90, 50), fx='leaf', cols=[(200, 140, 60)], tag='秋'),
    (11, 'announce'): dict(accent=(200, 60, 40), fx='maple', cols=[(215, 70, 45), (235, 150, 40)], tag='紅葉'),
    (11, 'reminder'): dict(accent=(185, 95, 40), fx='maple', cols=[(205, 70, 45), (230, 175, 40), (220, 120, 40)], tag='晩秋',
                           bg=((250, 236, 214), (255, 251, 244)), deco=['leafgarland', 'imo'], greet='〜 秋の夜長は焼肉で 〜', costume='kuri', bgm='autumn'),
    (12, 'announce'): dict(accent=(40, 130, 80), fx='snow', cols=[(150, 185, 220)], tag='冬', bg=((222, 236, 248), (250, 252, 255)),
                           deco=['holly', 'tree', 'snowground'], greet='〜 Merry Christmas 〜', costume='santa'),
    (12, 'reminder'): dict(accent=(200, 50, 50), fx='star', cols=[(225, 180, 50)], tag='年の瀬', bg=((252, 238, 228), (255, 252, 248)),
                           deco=['mizuhiki', 'kadomatsu', 'kagami'], greet='〜 よいお年を ・ 謹賀新年 〜', costume='mochi'),
}

def ease(x): x = max(0, min(1, x)); return 1 - (1 - x) ** 3
def pop(x):
    x = max(0, min(1, x)); return 1 + 2.2 * (x - 1) ** 3 + 1.2 * (x - 1) ** 2

def ctext(d, y, s, f, fill=INK, cx=W / 2):
    w = d.textlength(s, font=f); d.text((cx - w / 2, y), s, font=f, fill=fill)

# ---------- 背景の動き ----------
class FX:
    def __init__(self, kind, cols, seed=7):
        self.kind, self.cols = kind, cols
        r = random.Random(seed)
        n = {'snow': 34, 'petal': 26, 'plum': 22, 'leaf': 20, 'maple': 20, 'rain': 40, 'heart': 16,
             'confetti': 40, 'star': 18, 'sparkle': 22, 'firework': 4, 'moon': 18}.get(kind, 20)
        self.p = [dict(x=r.uniform(0, W), y=r.uniform(0, H), s=r.uniform(0.6, 1.3), sp=r.uniform(0.6, 1.4),
                       ph=r.uniform(0, 6.28), c=r.choice(cols)) for _ in range(n)]

    def draw(self, im, t):
        d = ImageDraw.Draw(im)
        k = self.kind
        if k == 'moon':
            cx, cy = W - 170, 240
            d.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=(250, 232, 150))
        for q in self.p:
            fall = {'rain': 900, 'snow': 90, 'petal': 120, 'plum': 110, 'leaf': 130, 'maple': 130, 'heart': 80,
                    'confetti': 150, 'star': 0, 'sparkle': 0, 'firework': 0, 'moon': 40}[k]
            y = (q['y'] + t * fall * q['sp']) % (H + 100) - 50
            x = q['x'] + math.sin(t * 1.2 + q['ph']) * 30 * (0 if k == 'rain' else 1)
            s, c = q['s'], q['c']
            a = t * 2 + q['ph']
            if k == 'snow':
                r = 12 * s
                for i in range(3):
                    ang = a * 0.4 + i * math.pi / 3
                    d.line([x - r * math.cos(ang), y - r * math.sin(ang), x + r * math.cos(ang), y + r * math.sin(ang)], fill=c, width=3)
            elif k in ('petal', 'plum'):
                r = 13 * s
                if k == 'plum':
                    for i in range(5):
                        ang = a * 0.3 + i * 2 * math.pi / 5
                        px, py = x + r * 0.8 * math.cos(ang), y + r * 0.8 * math.sin(ang)
                        d.ellipse([px - r * 0.55, py - r * 0.55, px + r * 0.55, py + r * 0.55], fill=c)
                    d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(240, 200, 80))
                else:
                    sq = abs(math.cos(a * 0.7))
                    d.ellipse([x - r, y - r * 0.55 * (0.3 + sq), x + r, y + r * 0.55 * (0.3 + sq)], fill=c)
            elif k in ('leaf', 'maple'):
                r = 18 * s
                pts = []
                npt = 10 if k == 'maple' else 2
                if k == 'maple':
                    for i in range(npt):
                        ang = a * 0.3 + i * 2 * math.pi / npt
                        rr = r if i % 2 == 0 else r * 0.45
                        pts.append((x + rr * math.cos(ang), y + rr * math.sin(ang)))
                    d.polygon(pts, fill=c)
                else:
                    ang = a * 0.3
                    ux, uy = math.cos(ang), math.sin(ang)
                    vx, vy = -uy, ux
                    d.polygon([(x - ux * r, y - uy * r), (x + vx * r * 0.45, y + vy * r * 0.45),
                               (x + ux * r, y + uy * r), (x - vx * r * 0.45, y - vy * r * 0.45)], fill=c)
            elif k == 'rain':
                d.line([x, y, x - 6, y + 34 * s], fill=c, width=3)
            elif k == 'heart':
                r = 11 * s * (1 + 0.1 * math.sin(a * 2))
                d.ellipse([x - r * 2, y - r, x, y + r], fill=c); d.ellipse([x, y - r, x + r * 2, y + r], fill=c)
                d.polygon([(x - r * 2 + 1, y + 2), (x + r * 2 - 1, y + 2), (x, y + r * 2.4)], fill=c)
            elif k == 'confetti':
                r = 9 * s; sq = abs(math.cos(a))
                d.rectangle([x - r, y - r * sq * 0.5, x + r, y + r * sq * 0.5], fill=c)
            elif k in ('star', 'sparkle'):
                tw = (math.sin(a * 1.5) + 1) / 2
                r = (14 if k == 'star' else 10) * s * (0.4 + 0.6 * tw)
                if k == 'star':
                    pts = [(x + (r if i % 2 == 0 else r * 0.42) * math.cos(-math.pi / 2 + i * math.pi / 5),
                            y + (r if i % 2 == 0 else r * 0.42) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
                    d.polygon(pts, fill=c)
                else:
                    d.line([x - r, y, x + r, y], fill=c, width=4); d.line([x, y - r, x, y + r], fill=c, width=4)
            elif k == 'firework':
                per = 2.4
                lt = ((t + q['ph']) % per) / per
                rr = 140 * s * ease(lt / 0.6)
                if lt < 0.85:
                    for i in range(14):
                        ang = i * 2 * math.pi / 14
                        x1, y1 = q['x'] + rr * 0.7 * math.cos(ang), (q['y'] % 900) + 150 + rr * 0.7 * math.sin(ang)
                        x2, y2 = q['x'] + rr * math.cos(ang), (q['y'] % 900) + 150 + rr * math.sin(ang)
                        d.line([x1, y1, x2, y2], fill=c, width=5)
            elif k == 'moon':  # すすき代わりの光の粒
                r = 4 * s
                d.ellipse([x - r, y - r, x + r, y + r], fill=c)


# ---------- 季節の飾り ----------
def bg_grad(im, top, bot):
    d = ImageDraw.Draw(im)
    for y in range(0, H, 8):
        k = y / H
        c = tuple(int(top[i] * (1 - k) + bot[i] * k) for i in range(3))
        d.rectangle([0, y, W, y + 8], fill=c)

def deco_holly(d, t):
    # 上のガーランド（ヒイラギ）
    for i in range(-1, 13):
        x = i * 92 + 20; y = 70 + 22 * math.sin(i * 0.9)
        d.line([x - 46, 70 + 22 * math.sin((i - 0.5) * 0.9), x, y], fill=(60, 120, 70), width=6)
        for sgn in (-1, 1):
            pts = [(x, y), (x + sgn * 34, y - 18), (x + sgn * 52, y - 4), (x + sgn * 30, y + 10)]
            d.polygon(pts, fill=(50, 140, 80))
        for dx, dy in ((-7, 6), (6, 8), (0, -2)):
            d.ellipse([x + dx - 8, y + dy - 8, x + dx + 8, y + dy + 8], fill=(210, 40, 40))

def deco_tree(d, t):
    cx, by = 970, 470
    sw = math.sin(t * 1.5) * 3
    for i, (w, h) in enumerate(((170, 120), (135, 110), (95, 95))):
        y0 = by - 60 - i * 85
        d.polygon([(cx - w / 2 + sw * i, y0), (cx + w / 2 + sw * i, y0), (cx + sw * (i + 1), y0 - h)], fill=(45, 130, 75), outline=(30, 90, 50))
    d.rectangle([cx - 16, by - 60, cx + 16, by - 20], fill=(130, 85, 50))
    sx, sy = cx + sw * 3, by - 60 - 2 * 85 - 95
    r = 22 + 3 * math.sin(t * 4)
    pts = [(sx + (r if j % 2 == 0 else r * 0.42) * math.cos(-math.pi / 2 + j * math.pi / 5),
            sy + (r if j % 2 == 0 else r * 0.42) * math.sin(-math.pi / 2 + j * math.pi / 5)) for j in range(10)]
    d.polygon(pts, fill=(240, 200, 50))
    for j, (ox, oy, c) in enumerate(((-45, -80, (210, 40, 40)), (30, -95, (240, 200, 50)), (-20, -160, (60, 110, 210)),
                                     (25, -185, (210, 40, 40)), (-5, -245, (240, 200, 50)), (55, -40, (60, 110, 210)), (-60, -30, (240, 200, 50)))):
        on = (math.sin(t * 3 + j) + 1) / 2 > 0.3
        rr = 9
        d.ellipse([cx + ox - rr, by + oy - rr, cx + ox + rr, by + oy + rr], fill=c if on else (250, 250, 250))

def deco_snowground(d, t):
    for i in range(-1, 9):
        x = i * 150
        d.ellipse([x - 40, H - 120 + (i % 2) * 20, x + 200, H + 80], fill=(255, 255, 255), outline=(200, 220, 240), width=4)

def deco_mizuhiki(d, t):
    # 上の紅白の帯と水引
    d.rectangle([0, 0, W, 34], fill=(200, 40, 40)); d.rectangle([0, 34, W, 52], fill=(255, 255, 255))
    d.rectangle([0, 52, W, 60], fill=(210, 170, 60))
    for i in range(6):
        x = 90 + i * 180
        d.arc([x - 40, 40, x + 40, 110], 0, 180, fill=(200, 40, 40), width=6)
        d.arc([x - 28, 46, x + 28, 100], 0, 180, fill=(210, 170, 60), width=5)

def deco_kadomatsu(d, t):
    cx, by = 1000, 470
    for dx, h in ((-38, 230), (0, 290), (38, 200)):
        x = cx + dx
        top = by - h
        d.polygon([(x - 18, by), (x + 18, by), (x + 18, top + 18), (x - 18, top)], fill=(90, 160, 80), outline=(50, 110, 50))
        d.line([x - 18, top + h * 0.45, x + 18, top + h * 0.45], fill=(50, 110, 50), width=4)
    for j in range(7):   # 松
        ang = -math.pi / 2 + (j - 3) * 0.45
        x2, y2 = cx + 95 * math.cos(ang), by - 120 + 70 * math.sin(ang)
        d.line([cx, by - 110, x2, y2], fill=(40, 100, 50), width=8)
        d.ellipse([x2 - 16, y2 - 10, x2 + 16, y2 + 10], fill=(40, 120, 60))
    d.rounded_rectangle([cx - 80, by - 70, cx + 80, by + 10], radius=14, fill=(215, 185, 120), outline=(160, 120, 60), width=4)
    for k in range(5):
        d.line([cx - 80, by - 60 + k * 16, cx + 80, by - 60 + k * 16], fill=(170, 135, 70), width=2)

def deco_kagami(d, t):
    cx, by, k = 918, 482, 0.62
    P = lambda x, y: (cx + x * k, by + y * k)
    E = lambda x0, y0, x1, y1: [cx + x0 * k, by + y0 * k, cx + x1 * k, by + y1 * k]
    d.polygon([P(-80, 0), P(80, 0), P(66, -40), P(-66, -40)], fill=(240, 240, 240), outline=(180, 180, 180))
    d.rectangle(E(-60, -44, 60, -36), fill=(200, 40, 40))
    d.ellipse(E(-75, -110, 75, -40), fill=(255, 255, 255), outline=(200, 200, 200), width=3)
    d.ellipse(E(-55, -160, 55, -95), fill=(255, 255, 255), outline=(200, 200, 200), width=3)
    d.ellipse(E(-26, -196, 26, -146), fill=(245, 150, 40))
    d.polygon([P(-4, -196), P(20, -214), P(10, -190)], fill=(60, 140, 60))

def _leaf(d, x, y, r, ang, kind):
    if kind == 'ginkgo':   # イチョウ（扇形）
        a0 = ang - 0.75; a1 = ang + 0.75
        pts = [(x, y)] + [(x + r * math.cos(a0 + (a1 - a0) * j / 10), y + r * math.sin(a0 + (a1 - a0) * j / 10)) for j in range(11)]
        d.polygon(pts, fill=(235, 185, 40), outline=(190, 140, 20))
        d.line([x, y, x - 0.5 * r * math.cos(ang), y - 0.5 * r * math.sin(ang)], fill=(150, 110, 30), width=4)
    else:                  # もみじ（5枚の先）
        pts = []
        for j in range(10):
            rr = r if j % 2 == 0 else r * 0.45
            a = ang + j * math.pi / 5
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        d.polygon(pts, fill=(210, 65, 45), outline=(160, 40, 30))

def deco_leafgarland(d, t):
    # 上のひもにイチョウともみじが揺れる
    pts = [(x, 60 + 26 * math.sin(x / 160 + 0.6)) for x in range(-20, W + 40, 20)]
    d.line(pts, fill=(140, 95, 55), width=5)
    for i in range(12):
        x = 40 + i * 92; y = 60 + 26 * math.sin(x / 160 + 0.6)
        sw = math.sin(t * 2.0 + i) * 0.25
        _leaf(d, x, y + 22, 30, math.pi / 2 + sw, 'ginkgo' if i % 2 == 0 else 'maple')

def deco_imo(d, t):
    # 右上：ふたつに割った焼き芋から湯気
    cy = 410
    for sgn, cx in ((-1, 930), (1, 1000)):
        tip = (cx + sgn * 62, cy + sgn * 8)
        cut = cx - sgn * 18
        pts = [(cut, cy - 38), (cx + sgn * 22, cy - 36), tip, (cx + sgn * 22, cy + 34), (cut, cy + 36)]
        d.polygon(pts, fill=(150, 55, 95), outline=INK, width=6)
        d.ellipse([cut - 17, cy - 38, cut + 17, cy + 36], fill=(250, 205, 70), outline=INK, width=5)
    for j, ox in enumerate((945, 985)):
        k = (t * 0.7 + j * 0.5) % 1.0
        g = int(150 + 100 * k)
        pts = [(ox + math.sin(n * 0.6 + t * 3 + j) * (5 + n), cy - 50 - n * 10 - k * 50) for n in range(8)]
        d.line(pts, fill=(g, g, g), width=5, joint='curve')

DECO = dict(leafgarland=deco_leafgarland, imo=deco_imo, holly=deco_holly, tree=deco_tree, snowground=deco_snowground,
            mizuhiki=deco_mizuhiki, kadomatsu=deco_kadomatsu, kagami=deco_kagami)

# ---------- セルン君 ----------
KUN = Image.open(os.path.join(A, 'kun2.png')).convert('RGBA')
EYES = [(332, 392, 398, 442), (482, 392, 538, 440)]
MOUTH = (340, 498, 562, 628)
KCX, KCY = 420, 500

def kun(im, cx, cy, s, mo, blink, t, costume=None):
    spr = KUN.copy(); dd = ImageDraw.Draw(spr)
    if blink:
        for (x0, y0, x1, y1) in EYES:
            spr.paste((0, 0, 0, 0), (x0, y0, x1, y1))
            ym = (y0 + y1) // 2
            dd.line([x0 + 6, ym, x1 - 6, ym], fill=INK + (255,), width=12)
    if mo > 0:
        m = spr.crop(MOUTH); spr.paste((0, 0, 0, 0), MOUTH)
        mw, mh = m.size
        m2 = m.resize((mw, max(1, int(mh * (1.0 - 0.42 * mo)))), Image.LANCZOS)
        spr.alpha_composite(m2, (MOUTH[0], MOUTH[1] + (mh - m2.height) // 2))
    # 体の中を白く塗って背景の飾りが透けないようにする
    body = Image.new('RGBA', spr.size, (0, 0, 0, 0)); bd = ImageDraw.Draw(body)
    bd.rounded_rectangle([238, 290, 600, 690], radius=80, fill=(255, 255, 255, 255))
    bd.polygon([(20, 60), (760, 20), (760, 240), (40, 290)], fill=(255, 255, 255, 255))
    body.alpha_composite(spr); spr = body
    PAD = 240
    if costume:
        big = Image.new('RGBA', (spr.width + 220, spr.height + PAD), (0, 0, 0, 0))
        big.alpha_composite(spr, (0, PAD)); spr = big
        costume_draw(ImageDraw.Draw(spr), costume, t, PAD)
    else:
        PAD = 0
    spr = spr.resize((int(spr.width * s), int(spr.height * s)), Image.LANCZOS)
    ox, oy = int(cx - KCX * s), int(cy - (KCY + PAD) * s)
    oy_body = oy + int(PAD * s)
    im.paste(spr, (ox, oy), spr)
    d = ImageDraw.Draw(im)
    for mx, ph in (() if costume in ('mochi', 'kuri') else ((300, 0.0),) if costume == 'santa' else ((300, 0.0), (510, 1.7))):
        for j in range(2):
            k = ((t * 0.9 + ph * 0.3 + j * 0.5) % 1.0)
            pts = [(ox + mx * s + math.sin(n * 0.55 + t * 3 + ph) * (6 + n * 1.3), oy_body + 40 * s - n * 9 - k * 60) for n in range(8)]
            g = int(150 + 100 * k)
            d.line(pts, fill=(g, g, g), width=6, joint='curve')


def costume_draw(d, kind, t, P):
    RED_, WHITE_, LW = (210, 40, 45), (255, 255, 255), 10
    if kind == 'santa':
        sw = math.sin(t * 2.2) * 14
        base = [(360, P + 42), (660, P + 20)]               # 網の右上にななめにのせる
        apex = (580 + sw, P - 190)
        tip = (720 + sw * 1.4, P - 130)
        d.polygon([base[0], base[1], tip, apex], fill=RED_, outline=INK, width=LW)
        d.rounded_rectangle([335, P - 2, 685, P + 64], radius=30, fill=WHITE_, outline=INK, width=LW)
        r = 36
        d.ellipse([tip[0] - r, tip[1] - r, tip[0] + r, tip[1] + r], fill=WHITE_, outline=INK, width=LW)
    elif kind == 'kuri':
        # 網の上で栗が焼けて、順番にぴょんと跳ねる
        for i, (mx, ph) in enumerate(((170, 0.0), (360, 0.9), (550, 1.8))):
            base_y = P + 78 - (mx - 40) * 0.05
            cyc = ((t + ph) % 2.7) / 2.7
            jump = math.sin(cyc / 0.25 * math.pi) * 60 if cyc < 0.25 else 0
            y = base_y - jump
            body = [(mx - 70, y), (mx + 70, y), (mx + 60, y - 58), (mx, y - 104), (mx - 60, y - 58)]
            d.polygon(body, fill=(130, 75, 40), outline=INK, width=8)
            d.chord([mx - 72, y - 40, mx + 72, y + 30], 0, 180, fill=(225, 195, 140), outline=INK, width=8)
            d.line([mx - 20, y - 70, mx - 6, y - 82], fill=(185, 130, 85), width=6)   # つや
    elif kind == 'mochi':
        # 網の上でお餅が焼けてぷくーっとふくらむ
        for i, (mx, ph) in enumerate(((190, 0.0), (520, 1.3))):
            base_y = P + 30 - (mx - 40) * 0.03
            d.rounded_rectangle([mx - 70, base_y - 64, mx + 70, base_y + 6], radius=16, fill=WHITE_, outline=INK, width=9)
            d.line([mx - 50, base_y - 10, mx + 50, base_y - 10], fill=(225, 190, 120), width=6)   # 焼き目
            cyc = ((t + ph) % 2.6) / 2.6
            r = 6 + 44 * ease(cyc / 0.75) if cyc < 0.85 else 0
            if r > 0:
                bx, by = mx + 14, base_y - 64 - r * 0.7
                d.ellipse([bx - r, by - r * 0.9, bx + r, by + r * 0.9], fill=WHITE_, outline=INK, width=8)
                d.rectangle([bx - r * 0.6, base_y - 70, bx + r * 0.6, base_y - 58], fill=WHITE_)

def bubble(d, cx, cy, w, h, tail_x, tail_y, sc):
    if sc <= 0.01: return
    w, h = w * sc, h * sc
    rx = cx + w / 2
    d.polygon([(rx - 20, cy - 28 * sc), (rx - 20, cy + 28 * sc), (tail_x, tail_y)], fill=INK)
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=int(50 * sc), fill=BG, outline=INK, width=8)
    d.polygon([(rx - 12, cy - 18 * sc), (rx - 12, cy + 18 * sc), (tail_x - 14, tail_y - 2)], fill=BG)


D = dt.date
def iso(x): return D.fromisoformat(x)

def calendar(d, top, start, end, shown, opens, final, accent, compact, holis):
    cw = 132
    g0 = start - dt.timedelta(days=(start.weekday() + 1) % 7)          # 直前の日曜
    g1 = end + dt.timedelta(days=(5 - end.weekday()) % 7)              # 直後の土曜
    rows = ((g1 - g0).days + 1) // 7
    ch = (92 if rows <= 5 else 80) if not compact else (80 if rows <= 5 else 70)
    x0 = (W - cw * 7) / 2
    d.rounded_rectangle([x0 - 16, top - 16, x0 + cw * 7 + 16, top + 90 + (rows - 1) * ch + 60], radius=28, fill=BG)
    for i, w in enumerate(WK_SUN):
        ctext(d, top, w, font(38), RED if i == 0 else BLUE if i == 6 else INK, x0 + cw * i + cw / 2)
    cross = start.month != end.month
    cur = g0
    while cur <= g1:
        idx = (cur - g0).days
        col, row = idx % 7, idx // 7
        cx, cy = x0 + cw * col + cw / 2, top + 90 + row * ch
        if start <= cur <= end:
            col_ = RED if col == 0 or cur in holis else BLUE if col == 6 else INK
            if cur in shown:
                r = 46 * pop(shown[cur])
                d.ellipse([cx - r, cy - r + 4, cx + r, cy + r + 4], fill=RED); col_ = BG
            if cross and (cur.day == 1 or cur == start):
                ctext(d, cy - 24, f'{cur.month}/{cur.day}', font(36), col_, cx)
            else:
                ctext(d, cy - 30, str(cur.day), font(46), col_, cx)
            if cur in opens and final > 0:
                d.ellipse([cx - 42, cy - 38, cx + 42, cy + 46], outline=accent, width=5)
        cur += dt.timedelta(days=1)
    return top + 90 + (rows - 1) * ch + 60

# ---------- BGM（自作・著作権フリー） ----------
def make_bgm(path, sec=SEC, seed=0, style=None):
    import numpy as np, wave
    sr = 44100
    n = int(sr * sec)
    out = np.zeros(n)
    bpm = 112; beat = 60 / bpm
    prog = [[60, 64, 67], [57, 60, 64], [65, 69, 72], [67, 71, 74]]   # C Am F G
    mel_pat = [[0, 2, 1, 2], [2, 1, 0, 1], [0, 1, 2, 3], [2, 1, 2, 0]]
    if style == 'autumn':
        return _bgm_autumn(path, sec, seed)
    rng = np.random.default_rng(seed)
    def tone(f, dur, amp, kind='bell'):
        t = np.arange(int(sr * dur)) / sr
        if kind == 'bell':
            w = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2 * t) + 0.12 * np.sin(2 * np.pi * f * 3.01 * t)
            env = np.exp(-t * 4.5)
        else:
            w = np.sin(2 * np.pi * f * t); env = np.exp(-t * 2.0)
        att = np.minimum(1, t / 0.008)
        return amp * w * env * att
    def add(sig, at):
        i = int(at * sr); j = min(n, i + len(sig))
        if i < n: out[i:j] += sig[:j - i]
    mf = lambda m: 440 * 2 ** ((m - 69) / 12)
    bar = beat * 4; t = 0.0; b = 0
    while t < sec:
        ch = prog[b % 4]
        add(tone(mf(ch[0] - 24), bar, 0.30, 'pad'), t)                    # ベース
        for k in range(4):                                               # 和音の刻み
            for m in ch: add(tone(mf(m - 12), beat * 0.9, 0.07, 'pad'), t + k * beat + beat / 2)
        pat = mel_pat[b % 4]
        for k in range(8):                                               # メロディ（8分）
            if rng.random() < 0.82:
                m = ch[pat[k % 4] % 3] + (12 if pat[k % 4] == 3 else 0) + 12
                add(tone(mf(m), beat * 0.7, 0.16), t + k * beat / 2)
        t += bar; b += 1
    fade = np.minimum(1, np.minimum(np.arange(n) / (sr * 0.5), (n - np.arange(n)) / (sr * 1.2)))
    out = out * fade
    out = out / max(1e-9, np.abs(out).max()) * 0.5
    pcm = (out * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

def _bgm_autumn(path, sec, seed):
    # 晩秋：ゆったりしたマリンバ＋ウッドベース＋シェイカー（F→Dm→B♭→C）
    import numpy as np, wave
    sr = 44100; n = int(sr * sec); out = np.zeros(n)
    beat = 60 / 92
    prog = [[65, 69, 72], [62, 65, 69], [58, 62, 65], [60, 64, 67]]
    mel = [[2, 1, 0, None, 1, 2, 3, None], [2, None, 1, 0, 1, None, 0, None],
           [1, 2, 3, None, 2, 1, None, 0], [0, 1, 2, None, 3, None, 2, None]]
    mf = lambda m: 440 * 2 ** ((m - 69) / 12)
    def add(sig, at):
        i = int(at * sr); j = min(n, i + len(sig))
        if i < n: out[i:j] += sig[:j - i]
    def marimba(f, dur, amp):
        t = np.arange(int(sr * dur)) / sr
        w = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 30)
        return amp * w * np.exp(-t * 6) * np.minimum(1, t / 0.004)
    def bass(f, dur, amp):
        t = np.arange(int(sr * dur)) / sr
        w = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t)
        return amp * w * np.exp(-t * 3.5) * np.minimum(1, t / 0.01)
    rng = np.random.default_rng(seed)
    def shaker(amp):
        t = np.arange(int(sr * 0.06)) / sr
        return amp * rng.standard_normal(len(t)) * np.exp(-t * 70)
    bar = beat * 4; t = 0.0; b = 0
    while t < sec:
        ch = prog[b % 4]
        add(bass(mf(ch[0] - 24), beat * 1.8, 0.35), t)
        add(bass(mf(ch[2] - 24), beat * 1.8, 0.28), t + beat * 2)
        for k in (1, 3):
            for m in ch: add(marimba(mf(m - 12), beat, 0.05), t + k * beat)
        for k in range(8):
            sw = 0.06 if k % 2 else 0.0                                       # 少しはねる
            add(shaker(0.025 if k % 2 else 0.04), t + k * beat / 2 + sw * beat)
            idx = mel[b % 4][k]
            if idx is not None:
                m = ch[idx % 3] + (12 if idx == 3 else 0) + 12
                add(marimba(mf(m), beat * 0.9, 0.17), t + k * beat / 2 + sw * beat)
        t += bar; b += 1
    fade = np.minimum(1, np.minimum(np.arange(n) / (sr * 0.5), (n - np.arange(n)) / (sr * 1.2)))
    out = out * fade
    out = out / max(1e-9, np.abs(out).max()) * 0.5
    pcm = (out * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

def render(cfg, out):
    start, end = iso(cfg['start']), iso(cfg['end'])
    mode = cfg.get('mode', 'month')                      # month=1日〜末 / week=第3週〜翌月第2週
    th = THEMES[(start.month if mode == 'month' else start.month, 'announce' if mode == 'month' else 'reminder')]
    closed = sorted(iso(x) for x in cfg['closed'] if start <= iso(x) <= end)
    opens = {iso(o['date']): o['text'] for o in cfg.get('open_notes', [])}
    holis = set(iso(x) for x in cfg.get('holidays', []))
    finals = list(opens.values()) + cfg.get('finals', [])
    banner = cfg.get('banner', [])
    compact = bool(banner)
    fx = FX(th['fx'], th['cols'], seed=start.toordinal())
    logo = Image.open(os.path.join(A, 'logo_line.png')).convert('RGBA')
    logo = logo.resize((int(logo.width * 290 / logo.height), 290), Image.LANCZOS)
    cross = start.month != end.month
    def lab(x):
        w = WK[x.weekday()]
        return f'{x.month}/{x.day}({w})' if cross else f'{x.day}日({w})'
    if mode == 'month':
        title, sub = f'{start.month}月の店休日', 'のお知らせ'
    else:
        title, sub = f'{start.month}/{start.day}〜{end.month}/{end.day}', 'のお休み'
    intro = cfg.get('intro', 'お休みはこの日！')

    n = len(closed)
    T_DATES = 2.6
    STEP = min(1.25, 7.2 / max(n, 1))
    T_END = T_DATES + STEP * n
    BGIMG = None
    if th.get('bg'):
        BGIMG = Image.new('RGB', (W, H), BG); bg_grad(BGIMG, *th['bg'])
    tmp = tempfile.mkdtemp()
    for fi in range(FPS * SEC):
        t = fi / FPS
        im = BGIMG.copy() if BGIMG else Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(im)
        for dk in th.get('deco', []):
            if dk != 'snowground': DECO[dk](d, t)
        fx.draw(im, t)
        d = ImageDraw.Draw(im)
        if 'snowground' in th.get('deco', []): deco_snowground(d, t)
        a = ease(t / 0.5)
        im.paste(logo, (70, int(200 - 40 * (1 - a))), logo)
        ctext(d, 300, 'ヤキニク セルン', font(64), INK, W / 2 + 70)
        k = pop((t - 0.3) / 0.6)
        if k > 0:
            ctext(d, 470, title, font(int((96 if mode == 'month' else 84) * min(k, 1.2))))
            ctext(d, 600, sub, font(int(54 * min(k, 1.2)), False))
            lw = int(260 * ease((t - 0.6) / 0.5))
            d.line([W / 2 - lw, 680, W / 2 + lw, 680], fill=th['accent'], width=6)
            if th.get('greet') and t > 0.9:
                ctext(d, 418, th['greet'], font(34), th['accent'])
        shown = {}
        for i, x in enumerate(closed):
            st = T_DATES + STEP * i + 0.4
            if t >= st: shown[x] = min(1, (t - st) / 0.35)
        ca = ease((t - 1.2) / 0.6)
        bottom = 1240
        if ca > 0:
            final = ease((t - T_END - 0.3) / 0.5)
            bottom = calendar(d, 710 + int(60 * (1 - ca)), start, end, shown, opens, final, th['accent'], compact, holis)
        ky = (1700 if th.get('costume') == 'santa' else 1650) if compact else 1620
        enter = ease((t - 0.8) / 0.7)
        kx = W - 200 + int(500 * (1 - enter))
        talking = T_DATES <= t < T_END or (T_END + 0.6 <= t < T_END + 2.4)
        mo = (math.sin(t * 2 * math.pi * 5) + 1) / 2 if talking else 0
        hop = abs(math.sin(t * math.pi * 2.4)) * 18 if talking else math.sin(t * 2) * 6
        kun(im, kx, ky - hop, 0.5, mo, (t % 3.1) < 0.12, t, th.get('costume'))
        d = ImageDraw.Draw(im)
        bx, by = 335, 1560
        tail = (kx - 140, ky + 10 - hop)
        if 1.4 < t < T_DATES:
            sc = pop((t - 1.4) / 0.3)
            bubble(d, bx, by, 560, 170, *tail, sc)
            if sc > 0.6: ctext(d, by - 42, intro, font(52 if len(intro) > 8 else 56), INK, bx)
        elif T_DATES <= t < T_END and n:
            i = int((t - T_DATES) // STEP)
            sc = pop(((t - T_DATES) - STEP * i) / 0.3)
            bubble(d, bx, by, 560, 190, *tail, sc)
            if sc > 0.6: ctext(d, by - 62, lab(closed[i]), font(92 if not cross else 84), RED, bx)
        elif t >= T_END + 0.4:
            lt = t - T_END - 0.4
            fl = finals or ['ご来店\nお待ちしてます！']
            seg = (SEC - T_END - 0.6) / len(fl)
            j = min(int(lt // seg), len(fl) - 1)
            sc = pop((lt - seg * j) / 0.3)
            bubble(d, bx, by, 600, 230, *tail, sc)
            if sc > 0.6:
                l1, _, l2 = fl[j].partition('\n')
                ctext(d, by - 82, l1, font(50), INK, bx); ctext(d, by - 12, l2, font(50), th['accent'], bx)
        fa = ease((t - T_END - 0.6) / 0.5)
        if fa > 0:
            yy = bottom + 6 + int(30 * (1 - fa))
            if banner:
                bh = 132 + 48 * (len(banner) - 2)
                d.rounded_rectangle([90, yy, W - 90, yy + bh], radius=24, fill=BG, outline=th['accent'], width=5)
                ctext(d, yy + 10, banner[0], font(36), th['accent'])
                ctext(d, yy + 56, banner[1], font(50), RED)
                for i, ln in enumerate(banner[2:]):
                    ctext(d, yy + 122 + i * 46, ln, font(34, False), INK)
            else:
                ctext(d, yy, 'ご予約はLINEから ／ TEL 078-927-0021', font(34, False), INK)
        im.save(os.path.join(tmp, f'{fi:04d}.png'))
        if fi in (60, 200, 330, 420): im.save(out.replace('.mp4', f'_check{fi}.png'))
    bgm = os.path.join(tmp, 'bgm.wav'); make_bgm(bgm, seed=start.toordinal(), style=th.get('bgm'))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(tmp, '%04d.png'),
                    '-i', bgm, '-shortest',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-crf', '20', '-movflags', '+faststart',
                    '-c:a', 'aac', '-b:a', '128k', '-ac', '2', out], check=True)
    shutil.rmtree(tmp)

if __name__ == '__main__':
    render(json.load(open(sys.argv[1], encoding='utf-8')), sys.argv[2])
    print(sys.argv[2])
