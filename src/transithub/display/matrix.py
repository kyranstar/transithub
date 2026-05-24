from PIL import Image

from ..config import MatrixConfig
from .base import Display


def build_options_kwargs(cfg: MatrixConfig) -> dict:
    return {
        "rows": cfg.rows,
        "cols": cfg.cols,
        "chain_length": cfg.chain_length,
        "parallel": cfg.parallel,
        "hardware_mapping": cfg.hardware_mapping,
        "brightness": cfg.brightness,
        "gpio_slowdown": cfg.gpio_slowdown,
        "pwm_bits": cfg.pwm_bits,
        "limit_refresh_rate_hz": cfg.limit_refresh_rate_hz,
        "drop_privileges": cfg.drop_privileges,
    }


class RGBMatrixDisplay(Display):
    """Drives the physical panel via hzeller's rpi-rgb-led-matrix bindings."""

    def __init__(self, cfg: MatrixConfig):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions  # lazy: Pi-only
        options = RGBMatrixOptions()
        for key, value in build_options_kwargs(cfg).items():
            setattr(options, key, value)
        self._matrix = RGBMatrix(options=options)
        self._canvas = self._matrix.CreateFrameCanvas()

    def render(self, image: Image.Image) -> None:
        self._canvas.SetImage(image.convert("RGB"))
        self._canvas = self._matrix.SwapOnVSync(self._canvas)

    def close(self) -> None:
        self._matrix.Clear()
