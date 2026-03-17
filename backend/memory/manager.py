"""MemoryManager — Mémoire persistante des leçons apprises par les agents IA."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.storage.database import Database
from backend.utils.logger import logger

_MEMORY_MD_PATH = Path(__file__).resolve().parent / "memory.md"


class MemoryManager:
    """Lecture/écriture de la mémoire persistante (table memory_entries).

    La mémoire est injectée dans chaque prompt d'agent IA pour que
    le bot apprenne de ses erreurs et ne les répète pas.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_context(self, max_entries: int = 30) -> str:
        """Retourne les leçons actives formatées en markdown pour injection dans les prompts."""
        entries = await self.db.fetchall(
            """SELECT id, category, content, confidence, times_referenced
               FROM memory_entries
               WHERE active = TRUE
               ORDER BY confidence DESC, times_referenced DESC
               LIMIT ?""",
            (max_entries,),
        )
        if not entries:
            return "## Mémoire\nAucune leçon enregistrée pour le moment."

        lines = [f"## Leçons apprises ({len(entries)} plus pertinentes)"]
        for e in entries:
            lines.append(
                f"- [{e['category']}] {e['content']} (confiance: {e['confidence']:.1f}, ref: {e['times_referenced']})"
            )
        return "\n".join(lines)

    async def add_lesson(
        self,
        trade_id: int | None,
        category: str,
        content: str,
        confidence: float = 0.5,
    ) -> int:
        """Ajoute une leçon. Si une leçon similaire existe, renforce plutôt qu'ajouter.

        Retourne l'id de la leçon (nouvelle ou existante).
        """
        # Détection basique de doublon (même catégorie + mots en commun)
        existing = await self._find_similar(category, content)
        if existing:
            await self.reinforce(existing["id"])
            logger.info("Mémoire — leçon #{} renforcée (doublon détecté)", existing["id"])
            return existing["id"]

        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.db.execute(
            """INSERT INTO memory_entries (timestamp, source_trade_id, category, content, confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (now, trade_id, category, content, confidence),
        )
        entry_id = cursor.lastrowid
        logger.info("Mémoire — nouvelle leçon #{} [{}] : {}", entry_id, category, content[:80])
        await self._sync_markdown()
        return entry_id

    async def reinforce(self, entry_id: int) -> None:
        """Augmente la confidence d'une leçon (+0.1, max 1.0) et incrémente times_referenced."""
        await self.db.execute(
            """UPDATE memory_entries
               SET confidence = MIN(confidence + 0.1, 1.0),
                   times_referenced = times_referenced + 1
               WHERE id = ?""",
            (entry_id,),
        )
        await self._sync_markdown()

    async def weaken(self, entry_id: int) -> None:
        """Réduit la confidence (-0.15). Désactive si < 0.2."""
        await self.db.execute(
            """UPDATE memory_entries
               SET confidence = MAX(confidence - 0.15, 0.0)
               WHERE id = ?""",
            (entry_id,),
        )
        # Désactiver si trop faible
        await self.db.execute(
            """UPDATE memory_entries
               SET active = FALSE
               WHERE id = ? AND confidence < 0.2""",
            (entry_id,),
        )
        await self._sync_markdown()

    async def deactivate(self, entry_id: int) -> None:
        """Désactive une leçon manuellement."""
        await self.db.execute(
            "UPDATE memory_entries SET active = FALSE WHERE id = ?",
            (entry_id,),
        )
        await self._sync_markdown()

    async def _sync_markdown(self) -> None:
        """Synchronise memory.md avec la table memory_entries."""
        entries = await self.db.fetchall(
            """SELECT id, timestamp, category, content, confidence, times_referenced
               FROM memory_entries WHERE active = TRUE
               ORDER BY confidence DESC, times_referenced DESC"""
        )
        lines = [
            "# Mémoire persistante — CryptoBot",
            "",
            f"Dernière mise à jour : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Leçons actives : {len(entries)}",
            "",
            "## Leçons apprises",
            "",
        ]
        if not entries:
            lines.append("_Aucune leçon pour le moment._")
        else:
            for e in entries:
                lines.append(
                    f"- **[{e['category']}]** {e['content']} "
                    f"*(confiance: {e['confidence']:.1f}, ref: {e['times_referenced']}, "
                    f"#{e['id']})*"
                )
        lines.append("")
        try:
            _MEMORY_MD_PATH.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            logger.warning("Impossible de synchroniser memory.md : {}", exc)

    async def get_recent_trades_summary(self, n: int = 10) -> str:
        """Résumé des N derniers trades pour le contexte des agents."""
        trades = await self.db.fetchall(
            """SELECT pair, side, pnl, pnl_pct, status, entry_time, exit_time,
                      decision_reasoning, signal_score
               FROM trades
               WHERE status != 'open'
               ORDER BY id DESC
               LIMIT ?""",
            (n,),
        )
        if not trades:
            return "## Historique récent\nAucun trade clôturé pour le moment."

        wins = sum(1 for t in trades if (t["pnl"] or 0) > 0)
        losses = sum(1 for t in trades if (t["pnl"] or 0) <= 0)
        total_pnl = sum(t["pnl"] or 0 for t in trades)
        gross_profit = sum(t["pnl"] for t in trades if (t["pnl"] or 0) > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if (t["pnl"] or 0) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        win_rate = wins / len(trades) * 100 if trades else 0

        lines = [f"## {len(trades)} derniers trades"]
        for i, t in enumerate(trades, 1):
            pnl_pct = t["pnl_pct"] or 0
            sign = "+" if pnl_pct >= 0 else ""
            duration = _compute_duration(t.get("entry_time"), t.get("exit_time"))
            lines.append(
                f"{i}. {t['pair']} {t['side']} {sign}{pnl_pct:.1f}% "
                f"({t['status']}, {duration})"
            )
        lines.append(
            f"Bilan : {wins} wins, {losses} losses, "
            f"win rate {win_rate:.0f}%, profit factor {profit_factor:.1f}, "
            f"P&L total {total_pnl:+.2f} USDT"
        )
        return "\n".join(lines)

    async def get_all_active(self) -> list[dict[str, Any]]:
        """Retourne toutes les leçons actives (pour le Weekly Strategist)."""
        return await self.db.fetchall(
            """SELECT id, timestamp, source_trade_id, category, content,
                      confidence, times_referenced
               FROM memory_entries
               WHERE active = TRUE
               ORDER BY confidence DESC"""
        )

    async def _find_similar(self, category: str, content: str) -> dict[str, Any] | None:
        """Détection basique de doublon par mots-clés significatifs communs."""
        stopwords = {
            "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou",
            "en", "à", "au", "aux", "par", "pour", "avec", "sur", "dans",
            "qui", "que", "quand", "si", "ne", "pas", "plus", "mais", "est",
            "son", "sa", "ses", "ce", "cette", "ces", "se", "a", "the",
        }
        content_words = set(content.lower().split()) - stopwords
        if len(content_words) < 2:
            return None

        candidates = await self.db.fetchall(
            """SELECT id, content, confidence
               FROM memory_entries
               WHERE category = ? AND active = TRUE""",
            (category,),
        )
        for c in candidates:
            candidate_words = set(c["content"].lower().split()) - stopwords
            if not candidate_words:
                continue
            overlap = len(content_words & candidate_words) / min(
                len(content_words), len(candidate_words)
            )
            if overlap > 0.5:
                return c
        return None


def _compute_duration(entry_time: str | None, exit_time: str | None) -> str:
    """Calcule la durée d'un trade en format lisible."""
    if not entry_time or not exit_time:
        return "?"
    try:
        fmt = "%Y-%m-%dT%H:%M:%S" if "T" in entry_time else "%Y-%m-%d %H:%M:%S"
        entry = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        exit_ = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
        delta = exit_ - entry
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes}min"
        hours = minutes // 60
        remaining = minutes % 60
        return f"{hours}h{remaining:02d}min"
    except (ValueError, TypeError):
        return "?"
