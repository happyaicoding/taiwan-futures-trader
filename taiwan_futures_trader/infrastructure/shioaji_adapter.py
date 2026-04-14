"""Shioaji API wrapper: login, contract lookup, kbars, tick subscription."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

# Taiwan Standard Time: UTC+8 (no DST)
_TWN_TZ = timezone(timedelta(hours=8))

from taiwan_futures_trader.domain.models import OHLCVBar

logger = logging.getLogger(__name__)


class ShioajiAdapter:
    def __init__(self, simulation: bool = True) -> None:
        self._simulation = simulation
        self._api = None
        self._contract = None
        self._tick_callback: Callable | None = None

    # ---------------------------------------------------------------- auth
    def login(self, api_key: str, secret_key: str) -> None:
        import shioaji as sj

        self._api = sj.Shioaji(simulation=self._simulation)
        self._api.login(api_key=api_key, secret_key=secret_key)
        logger.info("Shioaji login OK (simulation=%s)", self._simulation)

    def logout(self) -> None:
        if self._api is not None:
            try:
                self._api.logout()
            except Exception:
                pass
            self._api = None
            self._contract = None
        logger.info("Shioaji logout")

    @property
    def is_logged_in(self) -> bool:
        return self._api is not None

    # ---------------------------------------------------------- contract
    def get_txfr1_contract(self):
        """Return the near-month TXFR1 futures contract."""
        assert self._api is not None, "Not logged in"
        # TXFR1 is the near-month continuous contract
        contract = self._api.Contracts.Futures.TXF["TXFR1"]
        self._contract = contract
        return contract

    # -------------------------------------------------------- kbars
    def fetch_kbars(self, contract, start: date, end: date) -> list[OHLCVBar]:
        """
        Fetch 1-minute kbars from Shioaji.
        Shioaji returns bars with timestamp = bar close time (Taiwan convention).
        We subtract 1 minute to convert to international convention (bar open time).
        """
        assert self._api is not None, "Not logged in"
        try:
            kbars = self._api.kbars(
                contract=contract,
                start=str(start),
                end=str(end),
            )
        except Exception as exc:
            logger.warning("fetch_kbars %s~%s failed: %s", start, end, exc)
            return []

        if not kbars or not kbars.ts:
            return []

        bars: list[OHLCVBar] = []
        for i, ts in enumerate(kbars.ts):
            # Shioaji kbars ts is nanoseconds where the numeric value represents
            # Taiwan local time (CST, UTC+8) as if it were a UTC Unix epoch.
            # e.g. ts=1673859660_000000000 → "2023-01-16 09:01:00" Taiwan local
            # Correct conversion: treat the epoch value as UTC to recover local time.
            if isinstance(ts, int):
                dt = datetime.utcfromtimestamp(ts / 1e9)
            elif hasattr(ts, "to_pydatetime"):
                raw = ts.to_pydatetime()
                if raw.tzinfo is not None:
                    dt = raw.astimezone(_TWN_TZ).replace(tzinfo=None)
                else:
                    dt = raw  # naive → assume already Taiwan local time
            else:
                raw = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
                dt = raw.replace(tzinfo=None)
            # Subtract 1 min: Shioaji bar close time → international bar open time
            dt = dt - timedelta(minutes=1)
            bars.append(
                OHLCVBar(
                    timestamp=dt,
                    open=float(kbars.Open[i]),
                    high=float(kbars.High[i]),
                    low=float(kbars.Low[i]),
                    close=float(kbars.Close[i]),
                    volume=int(kbars.Volume[i]),
                    open_interest=int(getattr(kbars, "Amount", [0] * len(kbars.ts))[i] or 0),
                )
            )
        logger.info("fetch_kbars %s~%s → %d bars", start, end, len(bars))
        return bars

    # -------------------------------------------------------- historical ticks
    def fetch_today_ticks(self, contract, fetch_date: date) -> list[tuple[datetime, float, int]]:
        """
        Fetch all ticks for *fetch_date* via api.ticks() (AllDay mode).
        Returns list of (ts_taiwan_naive, price, volume) sorted by time.
        """
        assert self._api is not None, "Not logged in"
        from shioaji.constant import TicksQueryType

        try:
            ticks = self._api.ticks(
                contract=contract,
                date=str(fetch_date),
                query_type=TicksQueryType.AllDay,
            )
        except Exception as exc:
            logger.warning("fetch_today_ticks %s failed: %s", fetch_date, exc)
            return []

        if not ticks or not getattr(ticks, "ts", None):
            return []

        result: list[tuple[datetime, float, int]] = []
        for i, ts in enumerate(ticks.ts):
            if isinstance(ts, int):
                dt = datetime.utcfromtimestamp(ts / 1e9)
            elif hasattr(ts, "to_pydatetime"):
                raw = ts.to_pydatetime()
                dt = raw.astimezone(_TWN_TZ).replace(tzinfo=None) if raw.tzinfo else raw
            else:
                raw = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
                dt = raw.replace(tzinfo=None)

            result.append((dt, float(ticks.close[i]), int(ticks.volume[i])))

        logger.info("fetch_today_ticks %s → %d ticks", fetch_date, len(result))
        return result

    # ------------------------------------------------ tick subscription
    def subscribe_ticks(self, contract, callback: Callable) -> None:
        """
        Subscribe to real-time ticks. `callback(exchange, tick)` is called
        from a Shioaji background thread for every incoming tick.
        """
        assert self._api is not None, "Not logged in"
        self._tick_callback = callback

        from shioaji.constant import QuoteType, QuoteVersion

        # Register the FOP (Futures & Options) tick callback via decorator API
        self._api.on_tick_fop_v1()(callback)
        self._api.quote.subscribe(
            contract,
            quote_type=QuoteType.Tick,
            version=QuoteVersion.v1,
        )
        logger.info("Subscribed to ticks for %s", contract.code)

    def unsubscribe_ticks(self, contract) -> None:
        if self._api is None:
            return
        try:
            from shioaji.constant import QuoteType, QuoteVersion
            self._api.quote.unsubscribe(
                contract,
                quote_type=QuoteType.Tick,
                version=QuoteVersion.v1,
            )
        except Exception as exc:
            logger.warning("unsubscribe_ticks failed: %s", exc)
        logger.info("Unsubscribed ticks for %s", getattr(contract, "code", contract))
