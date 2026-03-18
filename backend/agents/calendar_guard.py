"""CalendarGuard — Pause automatique avant/après les événements macro.

Lit economic_calendar.json et retourne un multiplicateur de position :
- 1.0 = trading normal
- 0.25 = réduire les positions (événement high)
- 0.0 = pause totale (événement critical, ex: FOMC)
- 0.5 = post-événement, reprise progressive

Les dates sont connues à l'avance. Aucun appel IA.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from backend.utils.logger import logger


class CalendarGuard:
    """Gère les pauses de trading autour des événements économiques."""

    def __init__(self, calendar_path: str | None = None) -> None:
        if calendar_path is None:
            # Chercher à côté du package backend/
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            calendar_path = os.path.join(base, "economic_calendar.json")

        self.calendar_path = calendar_path
        self.events: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Charge le calendrier depuis le fichier JSON."""
        try:
            with open(self.calendar_path, encoding="utf-8") as f:
                data = json.load(f)
            self.events = data.get("events", [])
            logger.info("CalendarGuard: {} événements chargés", len(self.events))
        except FileNotFoundError:
            logger.warning("CalendarGuard: fichier {} introuvable, aucun événement", self.calendar_path)
            self.events = []
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("CalendarGuard: erreur parsing {}: {}", self.calendar_path, e)
            self.events = []

    def get_current_multiplier(self) -> float:
        """Retourne le multiplicateur de position basé sur le calendrier.

        1.0 = normal, 0.0 = pause totale, 0.25/0.5 = réduit.
        """
        now = datetime.now(timezone.utc)
        min_multiplier = 1.0

        for event in self.events:
            try:
                event_time = datetime.fromisoformat(event["datetime"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue

            hours_until = (event_time - now).total_seconds() / 3600
            hours_since = -hours_until

            # Avant l'événement
            pause_before = event.get("pause_before_hours", 1)
            if 0 < hours_until <= pause_before:
                mult = event.get("reduce_multiplier", 0.0)
                logger.info(
                    "CalendarGuard: {} dans {:.1f}h → mult={:.2f}",
                    event["name"], hours_until, mult,
                )
                min_multiplier = min(min_multiplier, mult)

            # Après l'événement
            pause_after = event.get("pause_after_hours", 0.5)
            if 0 < hours_since <= pause_after:
                logger.info(
                    "CalendarGuard: {} terminé il y a {:.1f}h → mult=0.50",
                    event["name"], hours_since,
                )
                min_multiplier = min(min_multiplier, 0.5)

        return min_multiplier

    def get_next_event(self) -> dict[str, Any] | None:
        """Retourne le prochain événement à venir (pour le dashboard)."""
        now = datetime.now(timezone.utc)
        upcoming = []

        for event in self.events:
            try:
                event_time = datetime.fromisoformat(event["datetime"].replace("Z", "+00:00"))
                if event_time > now:
                    upcoming.append((event_time, event))
            except (KeyError, ValueError):
                continue

        if not upcoming:
            return None

        upcoming.sort(key=lambda x: x[0])
        next_time, next_event = upcoming[0]
        hours_until = (next_time - now).total_seconds() / 3600

        return {
            "name": next_event["name"],
            "datetime": next_event["datetime"],
            "importance": next_event.get("importance", "unknown"),
            "hours_until": round(hours_until, 1),
        }
