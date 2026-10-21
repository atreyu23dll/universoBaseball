"""Reloj del universo: tiempo del mundo, no tiempo real."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class WorldClock:
    """Fecha del mundo. Inmutable: avanzar devuelve un reloj nuevo."""

    world_date: date

    def plus_days(self, days: int) -> WorldClock:
        if days < 0:
            raise ValueError("el reloj del universo no retrocede")
        return WorldClock(self.world_date + timedelta(days=days))

    def days_until(self, other: date) -> int:
        return (other - self.world_date).days
