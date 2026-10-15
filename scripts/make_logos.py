from PIL import Image, ImageDraw

SIZE = 512
BLUE = (37, 99, 235, 255)       # #2563EB
BLUE_DARK = (29, 78, 216, 255)  # #1D4ED8
WHITE = (255, 255, 255, 255)
GRAY = (209, 213, 219, 255)     # #D1D5DB
GRAY_MID = (156, 163, 175, 255) # #9CA3AF


def new_base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, 511, 511), radius=96, fill=BLUE)
    return img, draw


def logo_1() -> Image.Image:
    # 并排书脊：三本高低不同的竖放书 + 白色底座
    img, draw = new_base()
    draw.rounded_rectangle((118, 150, 182, 380), radius=12, fill=WHITE)
    draw.rounded_rectangle((218, 110, 282, 380), radius=12, fill=GRAY)
    draw.rounded_rectangle((318, 190, 382, 380), radius=12, fill=WHITE)
    draw.rounded_rectangle((140, 400, 372, 424), radius=12, fill=WHITE)
    return img


def logo_2() -> Image.Image:
    # 叠放书本：三本横放堆叠 + 顶部小书签
    img, draw = new_base()
    draw.rounded_rectangle((96, 316, 416, 372), radius=16, fill=WHITE)
    draw.rounded_rectangle((112, 252, 400, 308), radius=16, fill=GRAY)
    draw.rounded_rectangle((128, 188, 384, 244), radius=16, fill=WHITE)
    draw.rounded_rectangle((300, 188, 320, 244), radius=6, fill=GRAY_MID)
    return img


def logo_3() -> Image.Image:
    # 打开的书：对称双页 + 中缝 + 底部强调条
    img, draw = new_base()
    draw.polygon([(132, 168), (256, 200), (256, 348), (132, 318)], fill=WHITE)
    draw.polygon([(256, 200), (380, 168), (380, 318), (256, 348)], fill=(229, 231, 235, 255))
    draw.line((256, 200, 256, 348), fill=GRAY_MID, width=8)
    draw.rounded_rectangle((176, 404, 336, 428), radius=12, fill=WHITE)
    return img


def logo_4() -> Image.Image:
    # 单本正面书 + 书签缎带
    img, draw = new_base()
    draw.rounded_rectangle((116, 128, 396, 384), radius=24, fill=WHITE)
    draw.rounded_rectangle((116, 128, 152, 384), radius=20, fill=GRAY)
    draw.polygon([(252, 128), (276, 128), (276, 236), (264, 252), (252, 236)], fill=GRAY_MID)
    draw.rounded_rectangle((196, 408, 332, 432), radius=12, fill=WHITE)
    return img


LOGO_FUNCS = {
    "1": logo_1,
    "2": logo_2,
    "3": logo_3,
    "4": logo_4,
}

for num, func in LOGO_FUNCS.items():
    img = func()
    img.save(f"docs/icons/logo-{num}.png")
    print(f"logo-{num}.png saved")
