"""Schémas SQL pour la base SQLite."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL,
    quote_volume REAL NOT NULL,
    trades_count INTEGER NOT NULL,
    UNIQUE(pair, interval, open_time)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    pnl REAL,
    pnl_pct REAL,
    fees_paid REAL DEFAULT 0,
    signal_score REAL,
    market_analysis TEXT,
    decision_reasoning TEXT,
    risk_evaluation TEXT,
    indicators_snapshot TEXT,
    post_trade_analysis TEXT,
    lesson_learned TEXT,
    binance_order_id TEXT
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    agent TEXT NOT NULL,
    action TEXT NOT NULL,
    prompt_sent TEXT,
    response_received TEXT,
    tokens_used INTEGER,
    cost_usd REAL,
    duration_ms INTEGER,
    data TEXT
);

CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    total_capital REAL NOT NULL,
    available_cash REAL NOT NULL,
    open_positions INTEGER NOT NULL,
    daily_pnl REAL NOT NULL,
    daily_pnl_pct REAL NOT NULL,
    total_pnl REAL NOT NULL,
    total_pnl_pct REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    total_api_cost REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source_trade_id INTEGER,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    times_referenced INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE
);
"""
