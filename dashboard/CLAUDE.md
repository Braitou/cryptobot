# Dashboard CryptoBot — Guidelines

Ce dashboard est l'interface de monitoring d'un bot de trading IA.
Son rôle principal : montrer comment l'IA raisonne et apprend, pas juste les chiffres de trading.

## Stack

- React 19 + Vite
- Tailwind CSS (dark mode supporté)
- lightweight-charts (graphiques prix/chandeliers TradingView)
- recharts (graphiques statistiques : courbe d'apprentissage, coûts)
- WebSocket natif pour les données temps réel

## Direction de design

Style : terminal de trading professionnel, épuré, dense en information.
Inspiration : TradingView, Bloomberg Terminal (version simplifiée).
Palette : fond sombre (slate-900/950), texte clair, vert pour profits, rouge pour pertes.
Typographie : font mono pour les chiffres et prix, sans-serif pour le texte.
Pas de décorations inutiles — chaque pixel doit informer.

## Layout — 4 sections verticales

### 1. Header + Métriques globales (toujours visible en haut)

Barre supérieure :
- Nom "CryptoBot" à gauche
- Statut : pastille verte "Paper trading" ou orange "Live trading"
- Bouton Kill Switch (rouge, toujours accessible)

Grille de 4 metric cards :
- Capital total (USDT) + variation %
- P&L aujourd'hui (USDT) + nb trades + nb wins
- Drawdown actuel % + max historique
- Positions ouvertes (N / max)

### 2. KPIs Intelligence IA (ce qui distingue ce dashboard)

Grille de 4 metric cards avec bordure bleue (visuellement distinctes des métriques trading) :

**Courbe d'apprentissage** : win rate calculé par tranche de 20 trades.
Afficher le chiffre actuel (ex: "58%") + tendance (flèche haut/bas).
En dessous : graphique recharts en ligne montrant l'évolution du win rate par tranche.
C'est le KPI le plus important — il répond à "le bot s'améliore-t-il ?"

**Coût API** : dépensé aujourd'hui ($) + dépensé ce mois + budget max.
Format : "$0.04 — Mois: $0.62 / $60"

**Accord inter-agents** : pourcentage de fois où Market Analyst et Decision Agent
sont d'accord sur la direction. Un taux bas = les agents se contredisent souvent.
Calculé sur les 50 dernières décisions.

**Qualité mémoire** : nombre de leçons actives + confiance moyenne.
Format : "23 leçons, conf. moy: 0.68"

### 3. Zone principale — 2 colonnes

**Colonne gauche (60%)** :
- Graphique chandeliers temps réel (lightweight-charts, bougies 5m)
- Marqueurs sur le graphique pour chaque trade (triangle vert = buy, rouge = sell)
- Sous le graphique : tableau des derniers trades avec colonnes :
  Paire | Side | Entrée | Sortie | P&L % | Durée | Sortie par | Décision IA (résumé 1 ligne)

**Colonne droite (40%)** :
- "Raisonnement en cours" : affiche le dernier raisonnement de chaque agent dans l'ordre
  Market Analyst → Decision Agent → Risk Evaluator
  Chaque bloc a : nom de l'agent, badge verdict (BUY/SELL/WAIT/REDUCE/REJECT), texte du raisonnement
  Quand un agent est en train de réfléchir : afficher "Raisonne..." avec un indicateur de chargement

- "Mémoire (top leçons)" : liste des 10 leçons avec la plus haute confiance
  Chaque ligne : [catégorie] texte de la leçon + barre de confiance visuelle (0-1)
  Catégories avec couleurs : pattern=bleu, mistake=rouge, insight=violet, rule=vert

### 4. Footer léger

Statut de chaque agent (running/stopped/error) + dernière activité
Lien vers la config (lecture seule)

## WebSocket

Se connecter à ws://localhost:8000/ws/live
Messages entrants :
- type "price" → mettre à jour le graphique chandeliers
- type "signal" → flash temporaire sur le prix (signal détecté)
- type "thinking" → afficher "Raisonne..." dans le panneau raisonnement
- type "decision" → afficher la décision complète avec raisonnement
- type "trade" → ajouter au tableau des trades + marqueur sur le graphique
- type "lesson" → ajouter à la liste mémoire avec animation d'apparition
- type "portfolio" → mettre à jour les métriques globales

## Endpoints REST (chargement initial)

```
GET /api/portfolio      → métriques globales
GET /api/trades         → historique trades (pagination)
GET /api/trades/{id}    → détail avec raisonnement complet
GET /api/signals        → derniers signaux
GET /api/memory         → toutes les leçons actives
GET /api/agents/status  → statut de chaque agent
GET /api/agents/costs   → consommation API par agent
```

## Composants React

```
src/
├── App.jsx                 # Layout principal, WebSocket provider
├── components/
│   ├── Header.jsx          # Nom + statut + kill switch
│   ├── MetricCards.jsx     # Grille de 4 métriques trading
│   ├── AIMetricCards.jsx   # Grille de 4 KPIs IA (bordure bleue)
│   ├── LearningCurve.jsx  # Graphique recharts du win rate par tranche
│   ├── PriceChart.jsx      # Chandeliers lightweight-charts + marqueurs trades
│   ├── TradeHistory.jsx    # Tableau des trades avec résumé décision IA
│   ├── AgentReasoning.jsx  # Panneau raisonnement live (3 agents)
│   ├── MemoryView.jsx      # Liste des leçons avec barres de confiance
│   ├── AgentStatus.jsx     # Footer avec statut des agents
│   └── KillSwitch.jsx      # Bouton d'arrêt d'urgence (POST /api/kill-switch)
└── hooks/
    ├── useWebSocket.js     # Connexion + reconnexion auto
    └── usePortfolio.js     # État global du portefeuille
```

## Règles

- Dark mode par défaut (le fond sombre repose les yeux pour du monitoring continu)
- Les chiffres d'argent en font mono, toujours avec 2 décimales
- Vert = profit/positif, Rouge = perte/négatif, partout sans exception
- Les pourcentages toujours avec signe (+2.3% ou -1.5%, jamais juste 2.3%)
- Le panneau raisonnement est le coeur du dashboard — il doit être visible sans scroller
- Responsive : sur mobile, empiler les colonnes verticalement
- Pas d'animations décoratives — uniquement fonctionnelles (flash signal, apparition leçon)
