from datetime import datetime

from transithub.config import Config, MatrixConfig
from transithub.models import Arrival
from transithub.store import ArrivalStore
from transithub.display.sign import SignRenderer
from transithub.display.scenes.trains import TrainScene


def test_train_scene_infinite_and_renders():
    cfg = Config(matrix=MatrixConfig(32, 64))
    store = ArrivalStore(1)
    store.set(0, [Arrival("L", "8 Av", datetime(2026, 5, 23, 12, 2))])
    scene = TrainScene(SignRenderer(cfg), store, now_fn=lambda: datetime(2026, 5, 23, 12, 0))
    assert scene.duration_ms is None
    img = scene.render(0)
    assert img.size == (64, 32)
