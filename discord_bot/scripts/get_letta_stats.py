#!/usr/bin/env python3
"""
Get Letta stats from database
Used by lettaStatsMonitor.ts
"""

import sqlite3
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# Get arguments
if len(sys.argv) < 2:
    print(json.dumps({"error": "Missing timeframe argument"}))
    sys.exit(1)

timeframe = sys.argv[1]
db_path = Path(__file__).parent.parent.parent / 'letta_usage.db'

# Support custom date range
custom_start = None
custom_end = None
if timeframe == "custom" and len(sys.argv) >= 4:
    custom_start = sys.argv[2]
    custom_end = sys.argv[3]

if not db_path.exists():
    print(json.dumps({"error": f"Database not found at {db_path}"}))
    sys.exit(1)

try:
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    
    now = datetime.now()
    where_clause = ""
    params = []
    
    if custom_start and custom_end:
        # Custom date range
        where_clause = "WHERE timestamp >= ? AND timestamp < ?"
        params = [custom_start, custom_end]
    elif timeframe == "today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        where_clause = "WHERE timestamp >= ?"
        params = [today_start]
    elif timeframe == "week":
        week_ago = (now - timedelta(days=7)).isoformat()
        where_clause = "WHERE timestamp >= ?"
        params = [week_ago]
    elif timeframe == "month":
        month_ago = (now - timedelta(days=30)).isoformat()
        where_clause = "WHERE timestamp >= ?"
        params = [month_ago]
    # 'all' = no filter
    
    # Use total_credits (includes tool calls) instead of just credits
    c.execute(f'''
        SELECT 
          COALESCE(SUM(total_credits), 0) as credits,
          COUNT(*) as runs,
          COALESCE(SUM(api_calls), 0) as api_calls,
          COALESCE(SUM(tool_calls), 0) as tool_calls,
          COALESCE(SUM(credits), 0) as base_credits,
          COALESCE(SUM(tool_call_credits), 0) as tool_call_credits
        FROM runs {where_clause}
    ''', params)
    
    row = c.fetchone()
    conn.close()
    
    result = {
        "credits": float(row[0]) if row[0] else 0,  # Total credits (includes tool calls)
        "runs": int(row[1]) if row[1] else 0,
        "api_calls": float(row[2]) if row[2] else 0,
        "tool_calls": int(row[3]) if row[3] else 0,
        "base_credits": float(row[4]) if row[4] else 0,  # Base run credits
        "tool_call_credits": float(row[5]) if row[5] else 0  # Tool call credits
    }
    
    print(json.dumps(result))
    
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)

