"""
One-shot script: clear DB and fetch TXFR1 1min kbars for a fixed date range.

Usage:
    python scripts/fetch_history.py

Fetches: 2026-01-05 ~ 2026-04-13  (both day and night sessions)
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

# ── project root on sys.path ─────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── credentials ──────────────────────────────────────────────────────────────
for _env in [
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent.parent / "claude_demo" / ".env",
]:
    if _env.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_env)
        except ImportError:
            pass
        break

from taiwan_futures_trader.infrastructure.bar_store import BarStore
from taiwan_futures_trader.infrastructure.database import Database
from taiwan_futures_trader.infrastructure.shioaji_adapter import ShioajiAdapter

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── config ────────────────────────────────────────────────────────────────────
SYMBOL      = "TXFR1"
FETCH_START = date(2026, 4, 7)
FETCH_END   = date(2026, 4, 13)
BATCH_DAYS  = 7            # small batch to stay well under API bar-count limit

# Exact datetime boundaries (bar open times).
#   First bar : 2026-04-07 08:45  (day-session open)
#   Last  bar : 2026-04-13 13:44  (bar that closes at 13:45)
DT_START = datetime(2026, 4,  7,  8, 45)
DT_END   = datetime(2026, 4, 13, 13, 44)

_TWN_TZ = timezone(timedelta(hours=8))


def _in_session(dt: datetime) -> bool:
    """True if *dt* (Taiwan naive) falls within a TAIFEX trading session.

    Day session  : 08:45 – 13:44  (bar open times)
    Night session: 15:00 – 04:59  (bar open times, straddles midnight)
    """
    t = dt.time()
    if dtime(8, 45) <= t < dtime(13, 45):   # day
        return True
    if t >= dtime(15, 0) or t < dtime(5, 0): # night
        return True
    return False


def main() -> None:
    api_key    = os.environ.get("SINOPAC_API_KEY", "")
    secret_key = os.environ.get("SINOPAC_SECRET_KEY", "")
    if not api_key or not secret_key:
        logger.error("SINOPAC_API_KEY / SINOPAC_SECRET_KEY not found in environment")
        sys.exit(1)

    db_path = Path(__file__).parent.parent / "data" / "futures.db"
    db = Database(db_path)
    db.initialize()

    # ── 1. Clear all existing data ────────────────────────────────────────────
    conn = db.get_connection()
    conn.execute("DELETE FROM bars")
    conn.execute("DELETE FROM ticks")
    conn.commit()
    logger.info("DB cleared (bars + ticks tables)")

    bar_store = BarStore(db)
    adapter   = ShioajiAdapter(simulation=True)

    try:
        # ── 2. Login ──────────────────────────────────────────────────────────
        adapter.login(api_key, secret_key)
        contract = adapter.get_txfr1_contract()
        logger.info("Contract : %s", getattr(contract, "code", contract))
        logger.info("Range    : %s ~ %s", FETCH_START, FETCH_END)
        logger.info("─" * 60)

        # ── 3. Fetch in 30-day batches (newest → oldest) ──────────────────────
        total_raw      = 0
        total_filtered = 0
        cursor = FETCH_END

        while cursor >= FETCH_START:
            batch_start = max(FETCH_START, cursor - timedelta(days=BATCH_DAYS))
            bars = adapter.fetch_kbars(contract, batch_start, cursor)

            raw_count = len(bars)
            total_raw += raw_count

            if bars:
                session_bars = [
                    b for b in bars
                    if _in_session(b.timestamp)
                    and DT_START <= b.timestamp <= DT_END
                ]
                filtered_count = len(session_bars)
                total_filtered += filtered_count

                if session_bars:
                    bar_store.upsert_bars(SYMBOL, "1min", session_bars)

                logger.info(
                    "  %s ~ %s  raw=%5d  session=%5d  cumulative=%d",
                    batch_start, cursor, raw_count, filtered_count, total_filtered,
                )
            else:
                logger.info("  %s ~ %s  (no data returned)", batch_start, cursor)

            cursor = batch_start - timedelta(days=1)

        # ── 4. Verification summary ───────────────────────────────────────────
        logger.info("─" * 60)
        logger.info("Raw bars received  : %d", total_raw)
        logger.info("Session bars stored: %d", total_filtered)
        logger.info("Discarded (non-session): %d", total_raw - total_filtered)

        all_bars = bar_store.query_bars(SYMBOL, "1min", FETCH_START, FETCH_END)
        logger.info("Bars verified in DB: %d", len(all_bars))

        if all_bars:
            first, last = all_bars[0], all_bars[-1]
            logger.info(
                "First bar : %s  O=%.0f H=%.0f L=%.0f C=%.0f V=%d",
                first.timestamp, first.open, first.high,
                first.low, first.close, first.volume,
            )
            logger.info(
                "Last bar  : %s  O=%.0f H=%.0f L=%.0f C=%.0f V=%d",
                last.timestamp, last.open, last.high,
                last.low, last.close, last.volume,
            )

            # Count bars per session type
            day_bars   = [b for b in all_bars if dtime(8,45) <= b.timestamp.time() < dtime(13,45)]
            night_bars = [b for b in all_bars if b.timestamp.time() >= dtime(15,0) or b.timestamp.time() < dtime(5,0)]
            logger.info("Day session bars  : %d", len(day_bars))
            logger.info("Night session bars: %d", len(night_bars))

    finally:
        adapter.logout()
        db.close_all()
        logger.info("Done.")


if __name__ == "__main__":
    main()
