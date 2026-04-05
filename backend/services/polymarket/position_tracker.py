"""
Position Tracker — Dedicated SQLite DB for Polymarket Trades

Stores all trading data in polymarket_positions.db, completely isolated
from the agent's archival memory and conversation state.

Tables:
  - positions: Open and closed positions with P&L
  - trade_log: Full history of all trade events
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


DB_PATH = os.environ.get("POLYMARKET_DB_PATH", "./backend/data/db/polymarket_positions.db")


def _get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode for concurrent access."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables():
    """Create tables if they don't exist."""
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                contract_name TEXT,
                question TEXT,
                side TEXT NOT NULL CHECK(side IN ('YES', 'NO')),
                size_usdc REAL NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL,
                stop_loss_price REAL,
                city TEXT,
                metro_area TEXT,
                metric TEXT,
                threshold REAL,
                comparison TEXT,
                station_id TEXT,
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed', 'settled', 'stopped_out')),
                paper_trade INTEGER NOT NULL DEFAULT 1,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                close_price REAL,
                pnl_usdc REAL,
                close_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER,
                event_type TEXT NOT NULL,
                market_id TEXT NOT NULL,
                side TEXT,
                size_usdc REAL,
                price REAL,
                model_p REAL,
                market_p REAL,
                edge REAL,
                ev_per_dollar REAL,
                kelly_fraction REAL,
                consensus_score REAL,
                source_count INTEGER,
                paper_trade INTEGER NOT NULL DEFAULT 1,
                reason TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (position_id) REFERENCES positions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
            CREATE INDEX IF NOT EXISTS idx_positions_metro ON positions(metro_area, status);
            CREATE INDEX IF NOT EXISTS idx_positions_market ON positions(market_id);
            CREATE INDEX IF NOT EXISTS idx_trade_log_market ON trade_log(market_id);
            CREATE INDEX IF NOT EXISTS idx_trade_log_time ON trade_log(timestamp);
        """)
        conn.commit()
    finally:
        conn.close()


# Initialize tables on import
_ensure_tables()


def record_trade(
    market_id: str,
    question: str,
    side: str,
    size_usdc: float,
    entry_price: float,
    model_p: float,
    market_p: float,
    edge: float,
    ev_per_dollar: float,
    kelly_fraction: float,
    consensus_score: float,
    source_count: int,
    city: str = None,
    metro_area: str = None,
    metric: str = None,
    threshold: float = None,
    comparison: str = None,
    station_id: str = None,
    stop_loss_price: float = None,
    paper_trade: bool = True,
) -> Dict[str, Any]:
    """Record a new trade (open a position)."""
    conn = _get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cursor = conn.execute(
            """INSERT INTO positions
               (market_id, contract_name, question, side, size_usdc, entry_price,
                stop_loss_price, city, metro_area, metric, threshold, comparison,
                station_id, status, paper_trade, opened_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
            (market_id, question, question, side, size_usdc, entry_price,
             stop_loss_price, city, metro_area, metric, threshold, comparison,
             station_id, 1 if paper_trade else 0, now),
        )
        position_id = cursor.lastrowid

        conn.execute(
            """INSERT INTO trade_log
               (position_id, event_type, market_id, side, size_usdc, price,
                model_p, market_p, edge, ev_per_dollar, kelly_fraction,
                consensus_score, source_count, paper_trade, reason, timestamp)
               VALUES (?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New position opened', ?)""",
            (position_id, market_id, side, size_usdc, entry_price,
             model_p, market_p, edge, ev_per_dollar, kelly_fraction,
             consensus_score, source_count, 1 if paper_trade else 0, now),
        )
        conn.commit()

        return {
            "status": "OK",
            "position_id": position_id,
            "message": f"{'[PAPER] ' if paper_trade else ''}Position opened: {side} ${size_usdc:.2f} @ {entry_price:.4f}",
        }
    finally:
        conn.close()


def close_position(
    position_id: int,
    close_price: float,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Close an open position and calculate P&L."""
    conn = _get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
        if not row:
            return {"status": "error", "message": f"Position {position_id} not found"}
        if row["status"] != "open":
            return {"status": "error", "message": f"Position {position_id} is already {row['status']}"}

        # Calculate P&L
        side = row["side"]
        entry = row["entry_price"]
        size = row["size_usdc"]
        shares = size / entry if entry > 0 else 0

        if side == "YES":
            pnl = shares * (close_price - entry)
        else:
            pnl = shares * (entry - close_price)

        status = "stopped_out" if reason == "stop_loss" else "closed"

        conn.execute(
            """UPDATE positions SET status = ?, closed_at = ?, close_price = ?,
               pnl_usdc = ?, close_reason = ? WHERE id = ?""",
            (status, now, close_price, round(pnl, 4), reason, position_id),
        )

        conn.execute(
            """INSERT INTO trade_log
               (position_id, event_type, market_id, side, size_usdc, price,
                paper_trade, reason, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (position_id, "close", row["market_id"], side, size, close_price,
             row["paper_trade"], reason, now),
        )
        conn.commit()

        return {
            "status": "OK",
            "position_id": position_id,
            "pnl_usdc": round(pnl, 4),
            "message": f"Position closed: P&L ${pnl:+.2f} ({reason})",
        }
    finally:
        conn.close()


def mark_settled(
    market_id: str,
    settlement_price: float,
) -> Dict[str, Any]:
    """Mark all open positions for a market as settled."""
    conn = _get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = conn.execute(
            "SELECT * FROM positions WHERE market_id = ? AND status = 'open'",
            (market_id,),
        ).fetchall()

        if not rows:
            return {"status": "OK", "message": f"No open positions for market {market_id}"}

        results = []
        for row in rows:
            entry = row["entry_price"]
            size = row["size_usdc"]
            shares = size / entry if entry > 0 else 0
            side = row["side"]

            if side == "YES":
                pnl = shares * (settlement_price - entry)
            else:
                pnl = shares * (entry - settlement_price)

            conn.execute(
                """UPDATE positions SET status = 'settled', closed_at = ?,
                   close_price = ?, pnl_usdc = ?, close_reason = 'settlement'
                   WHERE id = ?""",
                (now, settlement_price, round(pnl, 4), row["id"]),
            )

            conn.execute(
                """INSERT INTO trade_log
                   (position_id, event_type, market_id, side, size_usdc, price,
                    paper_trade, reason, timestamp)
                   VALUES (?, 'settlement', ?, ?, ?, ?, ?, 'Market settled', ?)""",
                (row["id"], market_id, side, size, settlement_price,
                 row["paper_trade"], now),
            )

            results.append({"position_id": row["id"], "pnl_usdc": round(pnl, 4)})

        conn.commit()
        total_pnl = sum(r["pnl_usdc"] for r in results)
        return {
            "status": "OK",
            "settled_count": len(results),
            "total_pnl": round(total_pnl, 4),
            "positions": results,
        }
    finally:
        conn.close()


def get_open_positions() -> List[Dict[str, Any]]:
    """Get all open positions."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY opened_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_open_by_metro(metro_area: str) -> List[Dict[str, Any]]:
    """Get open positions in a specific metro area (for correlation guard)."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM positions WHERE metro_area = ? AND status = 'open'",
            (metro_area,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_performance_summary() -> Dict[str, Any]:
    """Get overall trading performance statistics."""
    conn = _get_connection()
    try:
        # All closed/settled positions
        closed = conn.execute(
            "SELECT * FROM positions WHERE status IN ('closed', 'settled', 'stopped_out')"
        ).fetchall()

        open_positions = conn.execute(
            "SELECT * FROM positions WHERE status = 'open'"
        ).fetchall()

        if not closed and not open_positions:
            return {
                "total_trades": 0,
                "open_positions": 0,
                "message": "No trades recorded yet",
            }

        wins = [r for r in closed if (r["pnl_usdc"] or 0) > 0]
        losses = [r for r in closed if (r["pnl_usdc"] or 0) <= 0]
        total_pnl = sum(r["pnl_usdc"] or 0 for r in closed)
        total_wagered = sum(r["size_usdc"] or 0 for r in closed)
        roi = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0

        return {
            "total_trades": len(closed) + len(open_positions),
            "closed_trades": len(closed),
            "open_positions": len(open_positions),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "total_pnl_usdc": round(total_pnl, 2),
            "total_wagered_usdc": round(total_wagered, 2),
            "roi_pct": round(roi, 2),
            "avg_pnl_per_trade": round(total_pnl / len(closed), 2) if closed else 0,
            "paper_trades": sum(1 for r in closed if r["paper_trade"]),
            "live_trades": sum(1 for r in closed if not r["paper_trade"]),
        }
    finally:
        conn.close()


def get_dashboard_data() -> Dict[str, Any]:
    """Get full dashboard data: open positions, recent trades, performance."""
    conn = _get_connection()
    try:
        open_pos = conn.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY opened_at DESC"
        ).fetchall()

        recent_trades = conn.execute(
            """SELECT * FROM trade_log
               ORDER BY timestamp DESC LIMIT 20"""
        ).fetchall()

        perf = get_performance_summary()

        return {
            "status": "OK",
            "open_positions": [dict(r) for r in open_pos],
            "recent_trades": [dict(r) for r in recent_trades],
            "performance": perf,
        }
    finally:
        conn.close()


def check_stop_losses(current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Check if any open positions should be stopped out.

    Args:
        current_prices: Dict of market_id -> current YES price
    """
    conn = _get_connection()
    try:
        open_pos = conn.execute(
            "SELECT * FROM positions WHERE status = 'open' AND stop_loss_price IS NOT NULL"
        ).fetchall()

        stopped = []
        for pos in open_pos:
            current = current_prices.get(pos["market_id"])
            if current is None:
                continue

            stop = pos["stop_loss_price"]
            side = pos["side"]

            # For YES positions: stop out if price drops below stop
            # For NO positions: stop out if price rises above (1 - stop)
            should_stop = False
            if side == "YES" and current <= stop:
                should_stop = True
            elif side == "NO" and current >= (1.0 - stop):
                should_stop = True

            if should_stop:
                result = close_position(pos["id"], current, reason="stop_loss")
                stopped.append(result)

        return stopped
    finally:
        conn.close()


def get_daily_pnl() -> float:
    """Get today's realized P&L for circuit breaker checks."""
    conn = _get_connection()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT COALESCE(SUM(pnl_usdc), 0) as daily_pnl
               FROM positions
               WHERE closed_at LIKE ? AND status IN ('closed', 'settled', 'stopped_out')""",
            (f"{today}%",),
        ).fetchone()
        return rows["daily_pnl"] if rows else 0.0
    finally:
        conn.close()
