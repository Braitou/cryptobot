# CryptoBot v2 — Plan de refonte complet

## Objectif

Transformer le bot d'un analyste paralysé (0 trades en 10h) en un scalper agressif qui vise 10-20 trades/jour, apprend par l'action, et génère du cashflow par accumulation de petits gains.

**Philosophie** : le Risk Guard Python est le vrai filet de sécurité. Il est codé en dur, inviolable. Cela nous permet de rendre les agents IA agressifs — si l'IA fait une erreur, le Python la rattrape. Le pire scénario est un stop-loss à -1.5% sur 10% du capital = -0.15% du portfolio. C'est acceptable.

---

## CHANGEMENT 1 — Mémoire persistante (memory.md)

**Action** : SUPPRIMER les 3 leçons actuelles et les remplacer par ceci.

Les anciennes leçons disent toutes "ne pas entrer sans confirmation dynamique" = un verrou circulaire qui bloque tout.

### Nouveau contenu de memory.md

```markdown
# Mémoire persistante — CryptoBot v2
Dernière mise à jour : {date}
Leçons actives : 2

- **[principle]** Un bon scalp est un trade rapide avec un edge statistique clair : RSI extrême (<30 ou >70) + prix hors Bollinger = haute probabilité de mean reversion dans les 5-15 prochaines minutes. Entrer vite, sortir vite, ne pas attendre la perfection. *(confiance: 0.9, ref: 0, #1)*
- **[principle]** Le volume confirme la conviction : un signal avec volume_ratio > 1.5× est plus fiable qu'un signal en volume faible. En cas de doute, réduire la taille de position plutôt que de ne pas entrer. *(confiance: 0.8, ref: 0, #2)*
```

---

## CHANGEMENT 2 — Signal Analyzer (deux modes de trading)

### 2a. Modifier le seuil de déclenchement

**Avant** : seuil unique à |score| >= 0.20 (trop bas, génère 107 signaux/10h dont 90% de bruit)

**Après** : deux seuils

```python
# Mode SCALP (mean reversion) — déclenché par conditions RSI/BB extrêmes
# Pas besoin du score composite, conditions directes :
SCALP_CONDITIONS = {
    "rsi_oversold": 30,      # RSI <= 30 → potentiel achat scalp
    "rsi_overbought": 70,    # RSI >= 70 → potentiel vente scalp (si on a une position)
    "bb_lower_threshold": 0.10,  # %B <= 0.10 → prix sous bande basse
    "bb_upper_threshold": 0.90,  # %B >= 0.90 → prix au-dessus bande haute
    "min_volume_ratio": 0.8,     # volume minimum pour valider
}
# Déclencheur scalp : (RSI <= 30 OU %B <= 0.10) ET volume_ratio >= 0.8

# Mode MOMENTUM (trend following) — utilise le score composite
MOMENTUM_THRESHOLD = 0.45  # au lieu de 0.20 — ne passe aux agents IA que les vrais signaux
```

### 2b. Modifier les pondérations du score composite

**Avant** : order book à 15% (bruit sur altcoins)

**Après** :
```python
WEIGHTS = {
    "trend": 0.30,      # était 0.25 — EMA + VWAP plus importants
    "rsi": 0.25,        # était 0.20 — RSI est le meilleur indicateur scalping
    "macd": 0.20,       # était 0.25 — légèrement réduit
    "bollinger": 0.15,  # inchangé
    "orderbook": 0.10,  # était 0.15 — réduit car trop bruité sur altcoins
}
```

### 2c. Ajouter la classification du signal

Le Signal Analyzer doit classifier chaque signal avant de l'envoyer aux agents :

```python
def classify_signal(self, indicators: dict) -> dict:
    rsi = indicators["rsi_14"]
    bb_pct = indicators["bb_percent"]
    score = indicators["composite_score"]
    volume_ratio = indicators["volume_ratio"]
    
    # Mode SCALP : conditions directes, pas besoin du score composite
    if (rsi <= 30 or bb_pct <= 0.10) and volume_ratio >= 0.8:
        return {
            "mode": "SCALP_LONG",
            "urgency": "HIGH",
            "target_profit_pct": 0.5,   # TP à 0.5%
            "stop_loss_pct": 0.3,       # SL à 0.3%
            "max_hold_minutes": 30,
            "position_size_pct": 5.0,   # petite position
        }
    
    if (rsi >= 70 or bb_pct >= 0.90) and volume_ratio >= 0.8:
        return {
            "mode": "SCALP_SHORT_EXIT",  # En spot, on ne short pas — on vend si on a une position
            "urgency": "HIGH",
            "target_action": "SELL_IF_HOLDING",
        }
    
    # Mode MOMENTUM : score composite fort
    if abs(score) >= 0.45:
        direction = "LONG" if score > 0 else "EXIT"
        return {
            "mode": f"MOMENTUM_{direction}",
            "urgency": "MEDIUM",
            "target_profit_pct": 1.5,   # TP plus large
            "stop_loss_pct": 1.0,       # SL plus large
            "max_hold_minutes": 240,
            "position_size_pct": 8.0,   # position plus grosse
        }
    
    # Pas de signal actionnable
    return {"mode": "NO_SIGNAL"}
```

---

## CHANGEMENT 3 — Supprimer le Risk Evaluator Agent

**Pourquoi** : 
- Le Risk Guard Python fait déjà tout le travail (limites dures inviolables)
- Le Risk Evaluator IA ajoute un 2ème frein conservateur qui bloque les trades
- Ça économise 1 appel API par signal (~33% de tokens en moins)
- Ça réduit la latence de ~5 secondes par décision

**Avant** : Signal → MarketAnalyst → DecisionAgent → RiskEvaluator → RiskGuard → Executor

**Après** : Signal → DecisionAgent (qui intègre l'analyse marché dans son prompt) → RiskGuard → Executor

On fusionne le MarketAnalyst et le DecisionAgent en un seul appel. Le MarketAnalyst actuel ne fait que reformuler les indicateurs en mots — autant les donner directement au DecisionAgent.

---

## CHANGEMENT 4 — Nouveau prompt du Decision Agent (CŒUR de la refonte)

### System prompt

```
Tu es un scalper crypto agressif qui gère un portefeuille spot de 500 USDT sur Binance.
Tu trades 5 paires : BTC, ETH, SOL, LINK, AVAX.

TON OBJECTIF : faire 10-20 trades par jour. Chaque trade vise un gain de 0.3% à 1.5%.
Tu apprends en tradant — un WAIT ne t'apprend rien.

RÈGLES DE DÉCISION :

1. MODE SCALP (signal "SCALP_LONG" ou "SCALP_SHORT_EXIT") :
   - RSI < 30 ou %B < 0.10 → tu ACHÈTES. C'est un mean reversion, pas besoin de "confirmation".
   - RSI > 70 ou %B > 0.90 + position ouverte → tu VENDS.
   - Position size : 5% du capital. TP : +0.5%. SL : -0.3%. Durée max : 30 min.
   - Tu n'as PAS besoin que tous les indicateurs soient alignés. Un RSI < 28 suffit.

2. MODE MOMENTUM (signal "MOMENTUM_LONG" ou "MOMENTUM_EXIT") :
   - Score composite > 0.45 avec EMA9 > EMA21 et MACD positif → tu ACHÈTES.
   - Position size : 8% du capital. TP : +1.5%. SL : -1.0%. Durée max : 4h.
   - Ici tu veux plus de confluence.

3. WAIT est l'exception, pas la règle. Tu ne dis WAIT que si :
   - Aucun signal SCALP ni MOMENTUM n'est actif (le système ne t'aurait pas appelé)
   - Le drawdown du jour approche 2.5% (prudence avant le kill switch à 3%)
   - Tu as déjà 3 positions ouvertes (max du Risk Guard)

MÉMOIRE : la mémoire contient des leçons de tes trades passés. Utilise-les comme des BIAIS
probabilistes, pas comme des interdictions. Une leçon qui dit "attention au RSI statique"
signifie "réduis la taille de position" — PAS "ne trade pas".

Tu es en phase d'apprentissage. Les erreurs sont ton carburant. Un trade perdant avec un 
stop-loss à -0.3% te coûte 0.075 USDT sur une position de 25 USDT. C'est le prix d'une leçon.
Un WAIT ne te coûte rien mais ne t'apprend rien non plus.

Réponds UNIQUEMENT en JSON.
```

### User prompt (template)

```
## Trade — {pair} — Mode: {signal_mode}

### Signal
{signal_classification en JSON — mode, urgency, target_profit, stop_loss, etc.}

### Indicateurs
RSI: {rsi_14} | MACD hist: {macd_histogram} | BB%: {bb_pct}
EMA9 vs EMA21: {ema_direction} | Volume: {volume_ratio}x
ATR: {atr_14} | Prix: {current_price}
Variation: 5m={change_5m}% | 15m={change_15m}% | 1h={change_1h}%

### Portefeuille
Capital: {capital} USDT | Positions ouvertes: {open_positions}/{max_positions}
P&L jour: {daily_pnl} USDT ({daily_pnl_pct}%)

{mémoire persistante — max 5 leçons les plus pertinentes}

Décide. JSON :
{
  "action": "BUY|SELL|WAIT",
  "confidence": 0-100,
  "position_size_pct": 5.0,
  "stop_loss_pct": 0.3,
  "take_profit_pct": 0.5,
  "max_hold_minutes": 30,
  "reasoning": "2-3 phrases max"
}
```

---

## CHANGEMENT 5 — Nouveau prompt du Post-Trade Learner

Le learner actuel génère des leçons trop vagues et trop restrictives ("ne jamais entrer sans confirmation dynamique"). On le recadre.

### System prompt

```
Tu es un analyste post-trade. Tu examines un trade terminé et tu cherches 
des PATTERNS ACTIONNABLES.

RÈGLES CRITIQUES :
1. Tu ne génères JAMAIS de leçon qui dit "ne pas trader" ou "attendre plus de confirmation".
   Le bot DOIT trader pour apprendre. Les leçons doivent améliorer le COMMENT, pas empêcher le QUAND.

2. Bonnes leçons (améliorer l'exécution) :
   - "Sur LINK, le RSI rebondit plus vite quand le volume est > 2× → augmenter la taille"
   - "Les scalps après 2h du matin UTC ont un win rate plus bas → réduire la taille de 50%"
   - "Le TP de 0.5% est atteint dans 70% des cas en < 10min → garder ce target"
   
3. Mauvaises leçons (empêchent de trader) :
   - "Ne pas entrer sans confirmation dynamique" ← INTERDIT
   - "Attendre que tous les indicateurs soient alignés" ← INTERDIT
   - "Éviter les marchés en range" ← INTERDIT (le range EST notre setup de scalp)

4. Tu ne génères une leçon que si tu vois un pattern sur AU MOINS 2 trades similaires.
   Un seul trade perdant n'est pas un pattern, c'est de la variance.

5. Max 10 leçons actives. Si tu en ajoutes une 11ème, tu dois en désactiver une ancienne.

Réponds UNIQUEMENT en JSON.
```

---

## CHANGEMENT 6 — Paramètres Risk Guard ajustés

Le Risk Guard actuel est correct dans l'esprit mais ses paramètres sont calibrés pour du swing trading, pas du scalping.

### Changements de paramètres

```python
# AVANT → APRÈS

# Position sizing
max_position_pct = 10       # → 10 (inchangé — c'est le max, les modes utilisent 5-8%)
max_open_positions = 3      # → 5 (pour supporter 10-20 trades/jour sur 5 paires)
max_positions_per_pair = 2  # → 1 (une seule position par paire — simplifie la gestion)

# Stop-loss / Take-profit — DEUX PROFILS
# Le Decision Agent envoie le SL/TP avec chaque trade, le Risk Guard vérifie les caps

# Caps pour le mode SCALP
scalp_max_sl_pct = 0.5      # SL max 0.5% (typiquement 0.3%)
scalp_max_tp_pct = 1.0      # TP max 1.0% (typiquement 0.5%)

# Caps pour le mode MOMENTUM  
momentum_max_sl_pct = 2.0   # SL max 2.0% (typiquement 1.0%)
momentum_max_tp_pct = 3.0   # TP max 3.0% (typiquement 1.5%) — inchangé

# Trailing stop
trailing_stop_activation = 0.3  # S'active à +0.3% de profit (était 1×ATR, trop loin pour scalp)
trailing_stop_distance = 0.15   # Suit à 0.15% du high (serré pour lock les gains scalp)

# Kill switches — inchangés (bien calibrés)
max_daily_loss_pct = 3      # 3% jour = stop
max_total_drawdown_pct = 15 # 15% total = stop complet
min_order_size = 5          # 5 USDT minimum Binance
```

### Ajout : cooldown après stop-loss

```python
# Après un stop-loss touché, attendre N minutes avant de re-trader la même paire
# Évite les entrées en cascade dans un mouvement directionnel fort
pair_cooldown_after_sl_minutes = 15
```

---

## CHANGEMENT 7 — Simplifier le flux d'exécution

### Nouveau flux

```
Toutes les 5 minutes (ou sur candle 5m fermée) :
  Pour chaque paire (BTC, ETH, SOL, LINK, AVAX) :
    
    1. Signal Analyzer calcule les indicateurs
    2. Signal Analyzer classifie : SCALP_LONG / SCALP_SHORT_EXIT / MOMENTUM_LONG / MOMENTUM_EXIT / NO_SIGNAL
    
    3. Si NO_SIGNAL → skip, pas d'appel IA, pas de log verbeux
    
    4. Si SCALP ou MOMENTUM :
       a. Appel au Decision Agent (Haiku 4.5) — 1 seul appel, pas 3
       b. Decision Agent retourne BUY/SELL/WAIT + paramètres
       c. Risk Guard Python vérifie les limites dures
       d. Si OK → Executor passe l'ordre avec SL/TP/trailing
       e. Si REJECTED → log la raison, on passe à la paire suivante
    
    5. Post-Trade Learner appelé uniquement à la CLÔTURE d'un trade (pas à l'ouverture)

Monitoring continu :
  - Vérifier les SL/TP/trailing de toutes les positions ouvertes (chaque minute)
  - Vérifier le max_hold_time et forcer la clôture si dépassé
```

---

## CHANGEMENT 8 — Améliorations optionnelles (phase 2)

Ces changements ne sont pas urgents mais amélioreront les performances :

### 8a. Filtre horaire
```python
# Heures de trading optimales (UTC) — volume et volatilité plus élevés
OPTIMAL_HOURS = {
    "high_activity": [(8, 11), (13, 17), (20, 23)],  # EU open, US open, Asia open
    "low_activity": [(2, 7)],  # nuit EU/US
}
# En heures de faible activité, réduire la taille de position de 50%
# NE PAS arrêter de trader — juste être plus petit
```

### 8b. Conscience événementielle
```python
# Avant un événement majeur (FOMC, CPI, etc.) :
# - 2h avant : réduire les tailles de position de 50%
# - Pendant : ne pas ouvrir de nouvelles positions
# - 1h après : reprendre normalement
# Implémentation : fichier JSON avec les dates d'événements, vérifié au démarrage
```

### 8c. Decay temporel des leçons
```python
# Chaque leçon a un compteur "trades_since_creation"
# Après 50 trades sans que la leçon soit référencée → confiance divisée par 2
# Après 100 trades → leçon désactivée automatiquement
```

### 8d. Métriques de performance par paire
```python
# Tracker le win rate par paire pour allouer plus de capital aux paires rentables
# Après 20 trades sur une paire :
#   - Win rate > 60% → augmenter la taille de 25%
#   - Win rate < 40% → réduire la taille de 50%
#   - Win rate < 30% après 30 trades → exclure temporairement la paire
```

---

## RÉSUMÉ DES FICHIERS À MODIFIER

| Fichier | Action | Priorité |
|---------|--------|----------|
| memory.md | Remplacer le contenu entier | CRITIQUE |
| Signal Analyzer (signal_analyzer.py) | Ajouter classify_signal(), nouveaux seuils, nouvelles pondérations | CRITIQUE |
| Decision Agent prompt | Remplacer system + user prompt | CRITIQUE |
| Risk Evaluator | SUPPRIMER de la chaîne d'exécution dans main.py | CRITIQUE |
| Market Analyst | SUPPRIMER de la chaîne (fusionné dans Decision Agent) | CRITIQUE |
| main.py / orchestrateur | Nouveau flux simplifié (Signal → Decision → RiskGuard → Executor) | CRITIQUE |
| Post-Trade Learner prompt | Remplacer system prompt | IMPORTANT |
| Risk Guard (risk_guard.py) | Nouveaux paramètres, deux profils SL/TP, cooldown | IMPORTANT |
| Weekly Strategist | Implémenter dans main.py (pas urgent, phase 2) | OPTIONNEL |

---

## ORDRE D'IMPLÉMENTATION RECOMMANDÉ

1. **memory.md** — 30 secondes, impact immédiat
2. **Prompt Decision Agent** — remplacer le system prompt et le user template
3. **Supprimer Risk Evaluator et Market Analyst** du flux dans main.py
4. **Signal Analyzer** — ajouter classify_signal() et nouveaux seuils
5. **Risk Guard** — nouveaux paramètres, cooldown
6. **Post-Trade Learner** — nouveau prompt
7. **Tester** — laisser tourner 4-6h et analyser les premiers trades
8. **Itérer** — ajuster les seuils en fonction des résultats

---

## CE QU'ON NE CHANGE PAS

- Le Data Collector WebSocket — il fonctionne parfaitement
- L'Executor — il fait son job
- La base SQLite — bonne pour le logging
- Le dashboard React — utile pour le monitoring
- Le principe Risk Guard en Python codé en dur — c'est la meilleure décision architecturale du projet
- Haiku 4.5 pour tous les agents quotidiens — bon rapport qualité/prix pour du scalping
- Les 5 paires surveillées — bonne diversification

---

## MÉTRIQUES DE SUCCÈS (après 48h de fonctionnement)

- [ ] Le bot fait au moins 5 trades par jour (vs 0 actuellement)
- [ ] Le ratio API calls / trades est < 5:1 (vs infini actuellement)
- [ ] Le win rate est > 45% (seuil minimum viable pour un scalper)
- [ ] Le drawdown journalier reste < 2% (bien en dessous du kill switch)
- [ ] Le Post-Trade Learner génère des leçons actionnables (pas des interdictions)
- [ ] Coût API < 1$/jour pour les agents Haiku
