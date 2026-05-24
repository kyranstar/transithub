from abc import ABC, abstractmethod
from typing import Optional

from PIL import Image


class Scene(ABC):
    duration_ms: Optional[int] = None   # None = runs until preempted

    @abstractmethod
    def render(self, elapsed_ms: int) -> Image.Image: ...
