"""The scheduler: picks the one scene on screen each frame.

Trains are the default and fill all unclaimed time. Everything else is a
`SceneSource` bound to a `Slot` (priority, cooldown, day parts, takeover). Each
frame the Director lets a running finite scene finish — unless a higher-priority
takeover is ready — then, when the screen is free, starts the highest-priority
source that wants it. See docs/scene-framework.md for the full design."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, Sequence

from PIL import Image

from ..profile import Profile
from .scenes.base import Scene


@dataclass
class Context:
    """A snapshot of the world handed to every source on each poll."""
    now: datetime
    mono_ms: int
    profile: Profile
    weather: Any = None
    sky: Any = None          # ISS pass + plane overhead snapshot
    space: Any = None        # humans-in-space + Earth-from-space
    local: Any = None        # farmers market + neighborhood events
    health: tuple = ()       # active warning strings; empty == all well


class SceneSource(Protocol):
    """Something that may want the screen. `poll` returns a fresh, finite Scene to
    play now, or None. Sources never decide timing relative to each other — the
    Director owns that via the slot."""
    name: str

    def poll(self, ctx: Context) -> Optional[Scene]: ...


@dataclass
class Slot:
    """A source plus its scheduling policy."""
    source: Any
    priority: int = 0
    cooldown_ms: int = 0
    profiles: frozenset = field(default_factory=lambda: frozenset(Profile))
    takeover: bool = False        # may cut into a lower-priority running scene
    interjection: bool = True     # subject to the global anti-back-to-back gap
    first_after_ms: int = 0       # earliest it may first play (lets trains show first)

    @property
    def name(self) -> str:
        return self.source.name


class Director:
    def __init__(self, default_scene: Scene, slots: Sequence[Slot] = (),
                 context_builder: Optional[Callable[[datetime, int], Context]] = None,
                 dimmer=None, min_interjection_gap_ms: int = 20_000):
        self._default = default_scene
        self._slots = sorted(slots, key=lambda s: s.priority, reverse=True)
        self._ctx_builder = context_builder
        self._dimmer = dimmer
        self._gap = min_interjection_gap_ms

        self._active: Scene = default_scene
        self._active_start = 0
        self._active_priority = -1
        # Init so a slot becomes eligible at mono_ms == first_after_ms.
        self._last_play = {s.name: s.first_after_ms - s.cooldown_ms for s in self._slots}
        self._interjection_free_at = 0

    # -- context -----------------------------------------------------------
    def _context(self, now: datetime, mono_ms: int) -> Context:
        if self._ctx_builder is not None:
            return self._ctx_builder(now, mono_ms)
        return Context(now=now, mono_ms=mono_ms, profile=Profile.DAY)

    # -- eligibility / start ----------------------------------------------
    def _eligible(self, slot: Slot, ctx: Context) -> bool:
        if ctx.profile not in slot.profiles:
            return False
        if ctx.mono_ms - self._last_play[slot.name] < slot.cooldown_ms:
            return False
        if slot.interjection and ctx.mono_ms < self._interjection_free_at:
            return False
        return True

    def _start(self, slot: Slot, scene: Scene, mono_ms: int) -> None:
        self._active = scene
        self._active_start = mono_ms
        self._active_priority = slot.priority
        self._last_play[slot.name] = mono_ms
        if slot.interjection:
            self._interjection_free_at = mono_ms + (scene.duration_ms or 0) + self._gap

    def _to_default(self) -> None:
        self._active = self._default
        self._active_start = 0          # trains run continuously since boot
        self._active_priority = -1

    # -- per-frame selection ----------------------------------------------
    def _select(self, ctx: Context) -> None:
        mono_ms = ctx.mono_ms
        running_finite = (self._active is not self._default
                          and self._active.duration_ms is not None)
        if running_finite:
            if mono_ms - self._active_start < self._active.duration_ms:
                # A finite scene is mid-play: only a higher-priority takeover cuts in.
                for slot in self._slots:
                    if (slot.takeover and slot.priority > self._active_priority
                            and self._eligible(slot, ctx)):
                        scene = slot.source.poll(ctx)
                        if scene is not None:
                            self._start(slot, scene, mono_ms)
                            return
                return
            self._to_default()

        # Screen is free: start the highest-priority source that wants it.
        for slot in self._slots:
            if not self._eligible(slot, ctx):
                continue
            scene = slot.source.poll(ctx)
            if scene is not None:
                self._start(slot, scene, mono_ms)
                return
        if self._active is not self._default:
            self._to_default()

    def render(self, now: datetime, mono_ms: int) -> Image.Image:
        ctx = self._context(now, mono_ms)
        self._select(ctx)
        img = self._active.render(mono_ms - self._active_start)
        if self._dimmer is not None:
            img = self._dimmer.apply(img, ctx)
        return img
