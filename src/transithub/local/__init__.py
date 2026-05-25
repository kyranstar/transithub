"""Neighborhood content: the farmers market that's open near home today.

This is config-driven, not networked. NYC has no keyless, current,
coordinate-tagged market feed worth trusting, so the owner lists their market(s)
in YAML with an exact weekday and season window. ``markets.py`` parses those
entries into specs and answers a single question: which configured market is
open *today*?

The coordinator parses the config once (``parse_specs``), builds a
``MarketSource`` from the specs, and registers it with the Director — there's no
background poller for this feature, and scenes read ``ctx.now`` directly."""
from __future__ import annotations

from .markets import Market, MarketSpec, market_today, parse_specs, short_place

__all__ = ["Market", "MarketSpec", "market_today", "parse_specs", "short_place"]
