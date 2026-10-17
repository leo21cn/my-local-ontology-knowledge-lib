from PIL import Image

SRC = "docs/promotion/assets/logo-options/p4.png"
OUT = "docs/promotion/assets"

img = Image.open(SRC)

favicon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
img.resize((256, 256), Image.LANCZOS).save(f"{OUT}/favicon.ico",
                                          sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
img.resize((32, 32), Image.LANCZOS).save(f"{OUT}/favicon-32.png")
img.resize((180, 180), Image.LANCZOS).save(f"{OUT}/apple-touch-icon.png")
print("favicon.ico / favicon-32.png / apple-touch-icon.png saved")
