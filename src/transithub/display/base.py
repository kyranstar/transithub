from abc import ABC, abstractmethod

from PIL import Image


class Display(ABC):
    @abstractmethod
    def render(self, image: Image.Image) -> None: ...

    def close(self) -> None:
        pass
