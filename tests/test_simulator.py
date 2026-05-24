from PIL import Image

from transithub.display.simulator import SimulatorDisplay


def test_simulator_writes_scaled_png(tmp_path):
    out = tmp_path / "preview.png"
    disp = SimulatorDisplay(str(out), scale=8)
    disp.render(Image.new("RGB", (64, 32), (10, 20, 30)))
    disp.close()
    assert out.exists()
    saved = Image.open(out)
    assert saved.size == (64 * 8, 32 * 8)
