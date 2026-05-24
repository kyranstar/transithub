from PIL import Image

from .base import Display


class SimulatorDisplay(Display):
    """Writes each frame to a PNG, upscaled with an LED-dot look, for off-Pi preview."""

    def __init__(self, path: str = "preview.png", scale: int = 10):
        self.path = path
        self.scale = scale

    def render(self, image: Image.Image) -> None:
        s = self.scale
        w, h = image.size
        out = Image.new("RGB", (w * s, h * s), (0, 0, 0))
        px = image.load()
        op = out.load()
        r = max(1, int(s * 0.42))
        for y in range(h):
            for x in range(w):
                color = px[x, y]
                if color == (0, 0, 0):
                    continue
                cx, cy = x * s + s // 2, y * s + s // 2
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        if dx * dx + dy * dy <= r * r:
                            op[cx + dx, cy + dy] = color
        out.save(self.path)
