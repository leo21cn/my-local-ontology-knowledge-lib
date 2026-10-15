from PIL import Image, ImageDraw

BLUE = (37, 99, 235, 255)
WHITE = (255, 255, 255, 255)
GRAY = (209, 213, 219, 255)

# logo-1 geometry on a 512 canvas
BOOKS = [(118, 150, 182, 380, WHITE), (218, 110, 282, 380, GRAY), (318, 190, 382, 380, WHITE)]
BASE_BAR = (140, 400, 372, 424)
RADIUS = 12


def draw_logo_1(size: int) -> Image.Image:
    factor = size / 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=max(1, round(96 * factor)), fill=BLUE
    )
    for x0, y0, x1, y1, color in BOOKS:
        box = tuple(round(v * factor) for v in (x0, y0, x1, y1))
        draw.rounded_rectangle(box, radius=max(1, round(RADIUS * factor)), fill=color)
    base = tuple(round(v * factor) for v in BASE_BAR)
    draw.rounded_rectangle(base, radius=max(1, round(RADIUS * factor)), fill=WHITE)
    return img


if __name__ == "__main__":
    img16 = draw_logo_1(16)
    img32 = draw_logo_1(32)
    img48 = draw_logo_1(48)
    img16.save("web/public/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[img32, img48])
    draw_logo_1(180).save("web/public/apple-touch-icon.png")
    draw_logo_1(192).save("web/public/icon-192.png")
    draw_logo_1(512).save("web/public/icon-512.png")
    print("favicon set written to web/public/")
