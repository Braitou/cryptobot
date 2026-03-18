"""ConfigManager — Lecture/écriture atomique de config.json avec fallback.

Le Python (RegimeDetector) écrit active_regime.
L'IA (Regime Advisor) écrit regime_override + expiration.
Le bot lit : si override non expiré → override, sinon → active_regime.

Écriture atomique : tmp + os.replace (safe sur Linux).
Fallback : si config.json invalide → charge config.json.last_valid.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any

from backend.presets import REGIME_PRESETS, get_preset
from backend.utils.logger import logger

# Champs obligatoires dans config.json
REQUIRED_FIELDS = ["_meta", "active_regime", "global", "pair_status"]
VALID_REGIMES = set(REGIME_PRESETS.keys())


class ConfigManager:
    """Gère config.json avec écriture atomique et fallback."""

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            base = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base, "config.json")

        self.path = path
        self.fallback_path = path + ".last_valid"
        self.config: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Charge config.json avec fallback sur .last_valid si invalide."""
        try:
            with open(self.path, encoding="utf-8") as f:
                config = json.load(f)
            self._validate(config)
            # Sauvegarder comme dernière config valide
            shutil.copy2(self.path, self.fallback_path)
            logger.info("ConfigManager: config.json chargé (régime={})", config.get("active_regime"))
            return config
        except FileNotFoundError:
            logger.warning("ConfigManager: {} introuvable, création config par défaut", self.path)
            config = self._default_config()
            self.atomic_write(self.path, config)
            return config
        except Exception as e:
            logger.warning("ConfigManager: config invalide ({}), fallback", e)
            try:
                with open(self.fallback_path, encoding="utf-8") as f:
                    config = json.load(f)
                self._validate(config)
                logger.info("ConfigManager: fallback chargé OK")
                return config
            except Exception:
                logger.error("ConfigManager: fallback aussi invalide, config par défaut")
                return self._default_config()

    def reload(self) -> None:
        """Recharge config.json depuis le disque."""
        self.config = self._load()

    @staticmethod
    def _validate(config: dict[str, Any]) -> None:
        """Valide le schéma minimal de config.json."""
        for field in REQUIRED_FIELDS:
            if field not in config:
                raise ValueError(f"Champ obligatoire manquant: {field}")

        regime = config.get("active_regime", "")
        if regime not in VALID_REGIMES:
            raise ValueError(f"Régime invalide: {regime} (valides: {VALID_REGIMES})")

        override = config.get("regime_override")
        if override is not None and override not in VALID_REGIMES:
            raise ValueError(f"Override invalide: {override}")

        # Vérifier que le multiplier IA ne dépasse pas 1.5x
        mult = config.get("global", {}).get("position_size_multiplier", 1.0)
        if mult > 1.5:
            raise ValueError(f"position_size_multiplier {mult} > 1.5 (cap IA)")

    @staticmethod
    def _default_config() -> dict[str, Any]:
        """Retourne une config par défaut (RANGING, tout actif)."""
        return {
            "_meta": {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": "config_manager_default",
                "update_reason": "Config par defaut (fallback)",
            },
            "active_regime": "RANGING",
            "regime_source": "default",
            "regime_override": None,
            "regime_override_expires": None,
            "global": {
                "trading_enabled": True,
                "position_size_multiplier": 1.0,
                "calendar_multiplier": 1.0,
                "pause_until": None,
            },
            "pair_status": {
                "BTCUSDT": "active",
                "ETHUSDT": "active",
                "SOLUSDT": "active",
                "LINKUSDT": "momentum_only",
                "AVAXUSDT": "momentum_only",
            },
        }

    @staticmethod
    def atomic_write(path: str, config: dict[str, Any]) -> None:
        """Écriture atomique : tmp + rename. Utilisé par Python ET par l'IA."""
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)  # Atomique sur Linux

    # ─── Lecture du preset actif ──────────────────────────────────────

    def get_active_preset(self) -> dict:
        """Retourne le preset actif en tenant compte des overrides IA.

        Priorité : regime_override (si non expiré) > active_regime.
        """
        override = self.config.get("regime_override")
        override_expires = self.config.get("regime_override_expires")

        if override and override_expires:
            try:
                expires = datetime.fromisoformat(override_expires.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < expires:
                    logger.debug("ConfigManager: override actif → {}", override)
                    return get_preset(override)
                else:
                    logger.info("ConfigManager: override {} expiré, retour au régime Python", override)
            except (ValueError, TypeError):
                pass

        return get_preset(self.config.get("active_regime", "RANGING"))

    def get_active_regime(self) -> str:
        """Retourne le nom du régime actif (avec override si applicable)."""
        override = self.config.get("regime_override")
        override_expires = self.config.get("regime_override_expires")

        if override and override_expires:
            try:
                expires = datetime.fromisoformat(override_expires.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < expires:
                    return override
            except (ValueError, TypeError):
                pass

        return self.config.get("active_regime", "RANGING")

    def get_position_multiplier(self) -> float:
        """Retourne le multiplicateur de position global (cap à 1.5x)."""
        mult = self.config.get("global", {}).get("position_size_multiplier", 1.0)
        return min(mult, 1.5)

    def is_trading_enabled(self) -> bool:
        """Vérifie si le trading est activé globalement."""
        if not self.config.get("global", {}).get("trading_enabled", True):
            return False

        # Vérifier pause_until
        pause_until = self.config.get("global", {}).get("pause_until")
        if pause_until:
            try:
                pause_dt = datetime.fromisoformat(pause_until.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < pause_dt:
                    return False
            except (ValueError, TypeError):
                pass

        return True

    def get_pair_status(self, pair: str) -> str:
        """Retourne le statut d'une paire : 'active', 'momentum_only', 'disabled'."""
        return self.config.get("pair_status", {}).get(pair, "active")

    # ─── Écriture (pour le RegimeDetector et l'IA) ────────────────────

    def update_regime(self, regime: str, source: str, reason: str) -> None:
        """Met à jour le régime actif (appelé par le RegimeDetector Python)."""
        if regime not in VALID_REGIMES:
            logger.error("ConfigManager: régime invalide refusé: {}", regime)
            return

        self.config["active_regime"] = regime
        self.config["regime_source"] = source
        self.config["_meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.config["_meta"]["updated_by"] = source
        self.config["_meta"]["update_reason"] = reason

        self.atomic_write(self.path, self.config)
        logger.info("ConfigManager: régime mis à jour → {} ({})", regime, reason)

    def set_override(self, regime: str, expires: str, reason: str) -> None:
        """Définit un override de régime (appelé par l'IA Regime Advisor)."""
        if regime not in VALID_REGIMES:
            logger.error("ConfigManager: override invalide refusé: {}", regime)
            return

        self.config["regime_override"] = regime
        self.config["regime_override_expires"] = expires
        self.config["_meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.config["_meta"]["updated_by"] = "ia_regime_advisor"
        self.config["_meta"]["update_reason"] = reason

        self.atomic_write(self.path, self.config)
        logger.info("ConfigManager: override IA → {} (expire: {}, raison: {})", regime, expires, reason)

    def update_calendar_multiplier(self, multiplier: float) -> None:
        """Met à jour le multiplicateur calendrier."""
        self.config["global"]["calendar_multiplier"] = multiplier
        self.atomic_write(self.path, self.config)
