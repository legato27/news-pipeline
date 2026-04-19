"""OSINT indices — rolling risk signals derived from osint_events.

Computed signals:
  geopolitical_risk_index  — per-region weighted sum of conflict-adjacent events
  sanctions_pressure_index — per-country delta of sanctions_change events
  cyber_threat_level       — count-weighted cyber_advisory + cyber_incident

These are the same formulas exposed by /api/osint/indices, extracted here so
Phase 8 forecast features can join them at ticker+timestamp via
`osint_indices_timeseries` (migration 011).

Pure functions over an event iterable — DB integration lives in
`app.tasks.osint_tasks.compute_indices_snapshot`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable


URGENCY_WEIGHT = {"low": 1, "medium": 2, "high": 4, "critical": 8}

CONFLICT_TYPES = ("armed_conflict", "protest", "diplomatic")
CYBER_TYPES = ("cyber_advisory", "cyber_incident")


def geopolitical_risk(events: Iterable[dict]) -> float:
    score = 0.0
    for e in events:
        if e.get("event_type") in CONFLICT_TYPES:
            score += URGENCY_WEIGHT.get(e.get("urgency", "low"), 1)
    return round(score, 2)


def sanctions_pressure(events: Iterable[dict]) -> float:
    return float(sum(1 for e in events if e.get("event_type") == "sanctions_change"))


def cyber_threat(events: Iterable[dict]) -> float:
    score = 0.0
    for e in events:
        if e.get("event_type") in CYBER_TYPES:
            score += URGENCY_WEIGHT.get(e.get("urgency", "low"), 1)
    return round(score, 2)


def compute_all(events: Iterable[dict]) -> dict[str, float]:
    evs = list(events)
    return {
        "geopolitical_risk": geopolitical_risk(evs),
        "sanctions_pressure": sanctions_pressure(evs),
        "cyber_threat": cyber_threat(evs),
    }
