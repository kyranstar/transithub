from PIL import Image

from ...clock import now as now_eastern
from ..sign import SignRenderer
from .base import Scene


class TrainScene(Scene):
    """The default, infinite scene: the live train sign."""
    duration_ms = None

    def __init__(self, renderer: SignRenderer, store, now_fn=now_eastern):
        self._renderer = renderer
        self._store = store
        self._now = now_fn

    def render(self, elapsed_ms: int) -> Image.Image:
        return self._renderer.render(
            self._store.snapshot(), elapsed_ms, self._now(), self._store.alerts())
