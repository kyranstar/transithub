from datetime import datetime

from PIL import Image

from transithub.display.director import Context, Director, Slot
from transithub.profile import Profile

NOW = datetime(2026, 5, 25, 12, 0)


class FakeScene:
    def __init__(self, name, duration_ms=5000):
        self.name = name
        self.duration_ms = duration_ms

    def render(self, elapsed_ms):
        return self.name


class FakeSource:
    def __init__(self, name, factory):
        self.name = name
        self._f = factory

    def poll(self, ctx):
        return self._f(ctx)


DEFAULT = FakeScene("trains", duration_ms=None)


def _builder(profile=Profile.DAY, health=()):
    def build(now, mono):
        return Context(now=now, mono_ms=mono, profile=profile, health=health)
    return build


def test_default_when_no_sources():
    d = Director(DEFAULT, [], context_builder=_builder())
    assert d.render(NOW, 1000) == "trains"


def test_source_fires_when_eligible():
    src = FakeSource("wx", lambda c: FakeScene("wx", 5000))
    d = Director(DEFAULT, [Slot(src, priority=50)], context_builder=_builder())
    assert d.render(NOW, 0) == "wx"


def test_cooldown_blocks_refire_until_elapsed():
    src = FakeSource("wx", lambda c: FakeScene("wx", 5000))
    d = Director(DEFAULT, [Slot(src, priority=50, cooldown_ms=60_000)],
                 context_builder=_builder())
    assert d.render(NOW, 0) == "wx"          # fires (lasts 5s)
    assert d.render(NOW, 6000) == "trains"   # ended; cooldown not elapsed
    assert d.render(NOW, 61_000) == "wx"     # cooldown elapsed -> fires again


def test_finite_scene_runs_then_returns_to_default():
    src = FakeSource("wx", lambda c: FakeScene("wx", 5000))
    d = Director(DEFAULT, [Slot(src, priority=50, cooldown_ms=600_000)],
                 context_builder=_builder())
    assert d.render(NOW, 0) == "wx"
    assert d.render(NOW, 3000) == "wx"
    assert d.render(NOW, 5000) == "trains"   # exactly at duration -> ended


def test_priority_orders_idle_selection():
    lo = FakeSource("lo", lambda c: FakeScene("lo", 5000))
    hi = FakeSource("hi", lambda c: FakeScene("hi", 5000))
    d = Director(DEFAULT, [Slot(lo, priority=10), Slot(hi, priority=90)],
                 context_builder=_builder())
    assert d.render(NOW, 0) == "hi"


def test_takeover_preempts_running_lower_priority():
    wx = FakeSource("wx", lambda c: FakeScene("wx", 60_000))
    ev = FakeSource("ev", lambda c: FakeScene("ev", 5000) if c.mono_ms >= 1000 else None)
    d = Director(DEFAULT, [
        Slot(wx, priority=50, cooldown_ms=600_000),
        Slot(ev, priority=90, takeover=True, interjection=False, cooldown_ms=600_000),
    ], context_builder=_builder())
    assert d.render(NOW, 0) == "wx"       # ev not ready -> weather starts (60s)
    assert d.render(NOW, 2000) == "ev"    # ev now ready and higher priority -> takes over


def test_non_takeover_waits_for_running_scene():
    wx = FakeSource("wx", lambda c: FakeScene("wx", 60_000))
    ev = FakeSource("ev", lambda c: FakeScene("ev", 5000) if c.mono_ms >= 1000 else None)
    d = Director(DEFAULT, [
        Slot(wx, priority=50, cooldown_ms=600_000, interjection=False),
        Slot(ev, priority=90, takeover=False, cooldown_ms=600_000, interjection=False),
    ], context_builder=_builder())
    assert d.render(NOW, 0) == "wx"        # weather starts
    assert d.render(NOW, 2000) == "wx"     # ev ready & higher prio but no takeover -> waits
    assert d.render(NOW, 61_000) == "ev"   # weather ended -> ev fires


def test_profile_gates_source():
    src = FakeSource("mk", lambda c: FakeScene("mk", 5000))
    slot = Slot(src, priority=40, profiles=frozenset({Profile.DAY}))
    night = Director(DEFAULT, [slot], context_builder=_builder(profile=Profile.NIGHT))
    assert night.render(NOW, 0) == "trains"
    day = Director(DEFAULT, [slot], context_builder=_builder(profile=Profile.DAY))
    assert day.render(NOW, 0) == "mk"


def test_interjection_gap_blocks_back_to_back():
    a = FakeSource("a", lambda c: FakeScene("a", 4000))
    b = FakeSource("b", lambda c: FakeScene("b", 4000))
    d = Director(DEFAULT, [
        Slot(a, priority=30, cooldown_ms=600_000, interjection=True),
        Slot(b, priority=20, cooldown_ms=0, interjection=True),
    ], context_builder=_builder(), min_interjection_gap_ms=20_000)
    assert d.render(NOW, 0) == "a"          # a fires; free_at = 0+4000+20000 = 24000
    assert d.render(NOW, 4000) == "trains"  # a ended; b blocked by interjection gap
    assert d.render(NOW, 24_000) == "b"     # gap elapsed -> b fires (a now on cooldown)


def test_dimmer_applied_to_output():
    from transithub.display.dimmer import Dimmer

    class ImgScene:
        duration_ms = None

        def render(self, e):
            return Image.new("RGB", (2, 2), (200, 200, 200))

    night = datetime(2026, 5, 25, 23, 0)   # no weather -> fallback NIGHT
    d = Director(ImgScene(), [], context_builder=_builder(profile=Profile.NIGHT),
                 dimmer=Dimmer(night_floor=0.5))
    assert d.render(night, 0).getpixel((0, 0)) == (100, 100, 100)
