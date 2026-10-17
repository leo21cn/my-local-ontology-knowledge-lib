from PIL import Image

BASE = "docs/promotion/assets/"
lobby = Image.open(BASE + "sparkwave-lobby.png")
room = Image.open(BASE + "sparkwave-room.png")

w, h = 720, 450
lobby = lobby.resize((w, h), Image.LANCZOS)
room = room.resize((w, h), Image.LANCZOS)

combined = Image.new("RGB", (w * 2, h), "white")
combined.paste(lobby, (0, 0))
combined.paste(room, (w, 0))
combined.save(BASE + "sparkwave-combined.png")
print("sparkwave-combined.png saved", combined.size)
