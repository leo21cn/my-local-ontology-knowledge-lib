from PIL import Image, ImageDraw

SIZE = 512
BLUE = (37, 99, 235, 255)
BLUE_SOFT = (147, 197, 253, 255)
WHITE = (255, 255, 255, 255)
WHITE_T = (255, 255, 255, 210)
GRAY = (209, 213, 219, 255)


def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, 511, 511), radius=96, fill=BLUE)
    return img, draw


def p1() -> Image.Image:
    # 节点网络：中心大节点 + 卫星节点
    img, d = base()
    nodes = [(256, 256, 46), (144, 150, 26), (368, 140, 26), (140, 370, 26),
             (372, 372, 26), (256, 88, 20)]
    for x, y, r in nodes[1:]:
        d.line((256, 256, x, y), fill=WHITE, width=8)
    for x, y, r in nodes:
        d.ellipse((x - r, y - r, x + r, y + r), fill=WHITE)
    d.ellipse((256 - 46 + 12, 256 - 46 + 12, 256 + 46 - 12, 256 + 46 - 12), fill=BLUE)
    return img


def p2() -> Image.Image:
    # 书本 + 网络：上方节点网络，下方打开的书
    img, d = base()
    for (x, y), r in [((190, 150), 24), ((322, 150), 24), ((256, 90), 22)]:
        d.ellipse((x - r, y - r, x + r, y + r), fill=WHITE)
    d.line((190, 150, 322, 150), fill=WHITE, width=6)
    d.line((256, 90, 190, 150), fill=WHITE, width=6)
    d.line((256, 90, 322, 150), fill=WHITE, width=6)
    d.polygon([(128, 240), (256, 272), (256, 392), (128, 360)], fill=WHITE)
    d.polygon([(256, 272), (384, 240), (384, 360), (256, 392)], fill=GRAY)
    d.line((256, 272, 256, 392), fill=BLUE_SOFT, width=8)
    return img


def p3() -> Image.Image:
    # 三环交叠（本体/实体/关系）
    img, d = base()
    for cx, cy in ((206, 238), (306, 238), (256, 342)):
        d.ellipse((cx - 98, cy - 98, cx + 98, cy + 98), fill=WHITE_T)
    return img


def p4() -> Image.Image:
    # 节点 + AI 火花
    img, d = base()
    cx, cy, r = 224, 290, 60
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE)
    # spark at upper right
    sx, sy = 330, 200
    spark = [(sx, sy - 52), (sx + 14, sy - 14), (sx + 52, sy), (sx + 14, sy + 14),
             (sx, sy + 52), (sx - 14, sy + 14), (sx - 52, sy), (sx - 14, sy - 14)]
    d.polygon(spark, fill=WHITE)
    d.line((224, 290, 330, 200), fill=WHITE, width=8)
    for x, y, r in ((170, 150, 22), (150, 380, 26)):
        d.ellipse((x - r, y - r, x + r, y + r), fill=GRAY)
        d.line((224, 290, x, y), fill=WHITE, width=6)
    return img


def p5() -> Image.Image:
    # 三层堆叠（文档→本体→智能体）+ 上行箭头
    img, d = base()
    for y, color in ((120, WHITE), (212, GRAY), (304, WHITE)):
        d.rounded_rectangle((120, y, 392, y + 56), radius=16, fill=color)
    arrow = [(196, 390), (256, 320), (316, 390), (288, 390), (288, 440), (224, 440), (224, 390)]
    d.polygon(arrow, fill=WHITE)
    return img


FUNCS = {"p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5}
for name, func in FUNCS.items():
    img = func()
    img.save(f"docs/promotion/assets/logo-options/{name}.png")
    print(f"{name}.png saved")
