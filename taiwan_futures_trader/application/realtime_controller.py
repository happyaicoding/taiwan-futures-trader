"""RealtimeController: live Shioaji data feed → ChartDataset stream."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time as dtime, timedelta, timezone

# Taiwan Standard Time (UTC+8, no DST)
_TWN_TZ = timezone(timedelta(hours=8))

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from taiwan_futures_trader.application.chart_data_service import ChartDataService
from taiwan_futures_trader.domain.bar_builder import BarBuilder
from taiwan_futures_trader.domain.models import ChartDataset, OHLCVBar
from taiwan_futures_trader.infrastructure.bar_store import BarStore
from taiwan_futures_trader.infrastructure.shioaji_adapter import ShioajiAdapter
from taiwan_futures_trader.infrastructure.tick_store import TickStore

logger = logging.getLogger(__name__)

MAX_HISTORY_DAYS = 90
_SYMBOL = "TXFR1"


def _is_in_trading_session(dt: datetime) -> bool:
    """Return True if *dt* (Taiwan time, no tzinfo) falls within TAIFEX trading hours.

    Day session  : 08:45 – 13:45  (bar open times 08:45–13:44)
    Night session: 15:00 – 05:00  (bar open times 15:00–04:59, crosses midnight)
    """
    t = dt.time()
    # Day session
    if dtime(8, 45) <= t < dtime(13, 45):
        return True
    # Night session (straddles midnight)
    if t >= dtime(15, 0) or t < dtime(5, 0):
        return True
    return False


# ---------------------------------------------------------------------------
# Thread-safe bridge: Shioaji callback (non-Qt thread) → Qt main thread
# ---------------------------------------------------------------------------
class _TickBridge(QObject):
    tick_received = pyqtSignal(object)


# ---------------------------------------------------------------------------
# Background thread for connect + kbars download (keeps UI responsive)
# ---------------------------------------------------------------------------
class _ConnectThread(QThread):
    connect_done = pyqtSignal(list)   # list[OHLCVBar] — seeded bars
    connect_failed = pyqtSignal(str)

    def __init__(
        self,
        adapter: ShioajiAdapter,
        bar_store: BarStore,
        api_key: str,
        secret_key: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._bar_store = bar_store
        self._api_key = api_key
        self._secret_key = secret_key

    def run(self) -> None:
        try:
            self._adapter.login(self._api_key, self._secret_key)
            contract = self._adapter.get_txfr1_contract()
            logger.info("Contract: %s", getattr(contract, "code", contract))

            # Determine missing date range
            today = date.today()
            latest = self._bar_store.get_latest_date(_SYMBOL, "1min")
            logger.info("DB latest date: %s | today: %s", latest, today)
            if latest:
                fetch_start = latest + timedelta(days=1)
            else:
                fetch_start = today - timedelta(days=MAX_HISTORY_DAYS)

            # Fetch in 30-day batches (dynamic detection)
            now_twn = datetime.now(tz=_TWN_TZ).replace(tzinfo=None)
            cursor = today
            while cursor >= fetch_start:
                batch_start = max(fetch_start, cursor - timedelta(days=29))
                bars = self._adapter.fetch_kbars(contract, batch_start, cursor)
                if not bars:
                    break
                # Filter out future bars (simulation mode may return them)
                # and bars outside TAIFEX trading sessions
                bars = [b for b in bars if b.timestamp <= now_twn and _is_in_trading_session(b.timestamp)]
                if bars:
                    self._bar_store.upsert_bars(_SYMBOL, "1min", bars)
                cursor = batch_start - timedelta(days=1)

            # Load bars from DB to seed the chart (exclude future bars)
            seed_start = today - timedelta(days=MAX_HISTORY_DAYS)
            now_twn = datetime.now(tz=_TWN_TZ).replace(tzinfo=None)
            logger.info("Querying bars %s ~ %s (cutoff: %s)", seed_start, today, now_twn)
            all_bars = self._bar_store.query_bars(_SYMBOL, "1min", seed_start, today)
            seed_bars = [b for b in all_bars if b.timestamp <= now_twn and _is_in_trading_session(b.timestamp)]
            logger.info("Seed bars: %d (filtered from %d)", len(seed_bars), len(all_bars))

            # ── Rebuild today's bars from historical ticks ────────────────────
            # api.kbars() only returns *completed* bars up to the last finalized
            # minute.  api.ticks() fills every gap:
            #   • Day session bars already in DB (no-op — upsert is idempotent)
            #   • Night session completed bars NOT yet in DB → store + add to seed
            #   • Current in-progress bar → append to seed_bars only (not to DB)
            logger.info("Fetching today's ticks to rebuild all bars …")
            today_ticks = self._adapter.fetch_today_ticks(contract, today)

            # Night session (>=15:00) belongs to the NEXT trade date in Shioaji's
            # convention.  Fetch it separately and append.
            if now_twn.time() >= dtime(15, 0):
                next_trade = today + timedelta(days=1)
                night_ticks = self._adapter.fetch_today_ticks(contract, next_trade)
                logger.info("Night session: %d ticks for trade date %s", len(night_ticks), next_trade)
                today_ticks = today_ticks + night_ticks
            if today_ticks:
                intraday_builder = BarBuilder(1)
                tick_completed: list[OHLCVBar] = []
                for ts, price, vol in today_ticks:
                    if _is_in_trading_session(ts) and ts <= now_twn:
                        completed, _ = intraday_builder.push_tick(ts, price, vol)
                        if completed:
                            tick_completed.append(completed)

                # Persist all completed bars from today's ticks (idempotent upsert)
                if tick_completed:
                    self._bar_store.upsert_bars(_SYMBOL, "1min", tick_completed)
                    completed_ts = {b.timestamp for b in tick_completed}
                    seed_bars = [b for b in seed_bars if b.timestamp not in completed_ts]
                    seed_bars.extend(tick_completed)

                # Append current in-progress bar (not stored to DB until completed)
                current_bar = intraday_builder.current_bar
                if current_bar is not None:
                    seed_bars = [b for b in seed_bars if b.timestamp != current_bar.timestamp]
                    seed_bars.append(current_bar)

                seed_bars.sort(key=lambda b: b.timestamp)
                logger.info(
                    "Today ticks → %d completed bars + %s in-progress",
                    len(tick_completed),
                    current_bar.timestamp if current_bar else "none",
                )

            self.connect_done.emit(seed_bars)
        except Exception as exc:
            logger.exception("Connect failed")
            self.connect_failed.emit(str(exc))


# ---------------------------------------------------------------------------
# RealtimeController
# ---------------------------------------------------------------------------
class RealtimeController(QObject):
    dataset_ready  = pyqtSignal(object)   # ChartDataset
    status_changed = pyqtSignal(str)      # "connecting", "live", "error: ...", "disconnected"

    def __init__(
        self,
        adapter: ShioajiAdapter,
        tick_store: TickStore,
        bar_store: BarStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._tick_store = tick_store
        self._bar_store = bar_store
        self._service = ChartDataService()

        self._bars: list[OHLCVBar] = []
        self._timeframe: str = "1min"
        self._timeframe_minutes: int = 1
        self._session_filter: str = "all"  # "all" | "day" | "night"
        self._ma_periods: list[int] = [5, 10, 20, 60]
        self._include_macd: bool = True
        self._include_kd: bool = True
        self._ma_visibility: dict[int, bool] = {p: True for p in self._ma_periods}

        self._bar_builder = BarBuilder(1)
        self._bridge = _TickBridge(self)
        self._bridge.tick_received.connect(self._on_tick)

        self._connect_thread: _ConnectThread | None = None

    # ---------------------------------------------------------------- public API
    def load_from_db(self, timeframe: str = "1min") -> None:
        """Load historical bars from SQLite and emit dataset — no API login needed."""
        self._timeframe = timeframe
        self._timeframe_minutes = _parse_minutes(timeframe)
        start = date.today() - timedelta(days=90)
        end   = date.today()
        bars  = self._bar_store.query_bars(_SYMBOL, "1min", start, end)
        if bars:
            self._bars = bars
            self._emit_dataset()
            logger.info(
                "load_from_db: %d bars (%s ~ %s)",
                len(bars), bars[0].timestamp, bars[-1].timestamp,
            )

    def connect(self, api_key: str, secret_key: str, timeframe: str = "1min") -> None:
        self._timeframe = timeframe
        self._timeframe_minutes = _parse_minutes(timeframe)
        self._bar_builder.reset(1)  # always accumulate raw 1min from ticks
        self.status_changed.emit("connecting")

        self._connect_thread = _ConnectThread(
            self._adapter, self._bar_store, api_key, secret_key, self
        )
        self._connect_thread.connect_done.connect(self._on_connect_done)
        self._connect_thread.connect_failed.connect(self._on_connect_failed)
        self._connect_thread.start()

    def disconnect(self) -> None:
        contract = self._adapter._contract
        if contract is not None:
            self._adapter.unsubscribe_ticks(contract)
        self._adapter.logout()
        self.status_changed.emit("disconnected")
        logger.info("RealtimeController disconnected")

    def change_timeframe(self, timeframe: str) -> None:
        self._timeframe = timeframe
        self._timeframe_minutes = _parse_minutes(timeframe)
        self._bar_builder.reset(1)  # tick builder always stays at 1min
        if self._bars:
            self._emit_dataset()

    def change_session_filter(self, session: str) -> None:
        """session: 'all' | 'day' | 'night'"""
        self._session_filter = session
        if self._bars:
            self._emit_dataset()

    def toggle_ma(self, period: int, visible: bool) -> None:
        self._ma_visibility[period] = visible

    def toggle_macd(self, visible: bool) -> None:
        self._include_macd = visible

    def toggle_kd(self, visible: bool) -> None:
        self._include_kd = visible

    # -------------------------------------------------------- connect callbacks
    @pyqtSlot(list)
    def _on_connect_done(self, seed_bars: list[OHLCVBar]) -> None:
        logger.info("_on_connect_done: %d seed bars", len(seed_bars))
        self._bars = seed_bars

        # Warm up the bar builder with the last seed bar so the first live tick
        # continues from the correct in-progress state instead of starting fresh.
        if seed_bars:
            last = seed_bars[-1]
            self._bar_builder.seed(last)

        try:
            self._emit_dataset()
        except Exception as exc:
            logger.exception("_emit_dataset failed: %s", exc)
        self.status_changed.emit("live")

        # Start tick subscription
        contract = self._adapter._contract
        if contract is not None:
            try:
                self._adapter.subscribe_ticks(contract, self._bridge_callback)
            except Exception as exc:
                logger.exception("subscribe_ticks failed: %s", exc)
                self.status_changed.emit(f"error: subscribe failed — {exc}")
        else:
            logger.warning("No contract — skip tick subscription")

    @pyqtSlot(str)
    def _on_connect_failed(self, message: str) -> None:
        self.status_changed.emit(f"error: {message}")

    # -------------------------------------------------- tick ingestion (main thread)
    def _bridge_callback(self, exchange, tick) -> None:
        """Called on Shioaji background thread — forward to main thread via bridge."""
        self._bridge.tick_received.emit(tick)

    @pyqtSlot(object)
    def _on_tick(self, tick) -> None:
        """Runs on main thread. Update bars and emit new dataset."""
        try:
            ts = tick.datetime
            price = float(tick.close)
            volume = int(tick.volume)
        except Exception as exc:
            logger.warning("Bad tick: %s", exc)
            return

        # Ignore ticks outside TAIFEX trading sessions
        if not _is_in_trading_session(ts):
            return

        # Persist raw tick
        self._tick_store.insert(_SYMBOL, ts, price, volume)

        # Aggregate into 1min bar
        completed, current = self._bar_builder.push_tick(ts, price, volume)

        if completed:
            # Persist completed 1min bar
            self._bars.append(completed)
            self._bar_store.upsert_bars(_SYMBOL, "1min", [completed])

        # Replace or set the in-progress bar (last entry)
        if self._bars and self._bars[-1].timestamp == current.timestamp:
            self._bars[-1] = current
        else:
            self._bars.append(current)

        self._emit_dataset()

    # --------------------------------------------------------------- helpers
    def _emit_dataset(self) -> None:
        if not self._bars:
            return

        bars = self._get_resampled_bars()
        dataset = self._service.prepare_chart_dataset_from_bars(
            bars,
            symbol=_SYMBOL,
            timeframe=self._timeframe,
            ma_periods=self._ma_periods,
            include_macd=self._include_macd,
            include_kd=self._include_kd,
        )
        for ma in dataset.ma_results:
            ma.visible = self._ma_visibility.get(ma.period, True)
        self.dataset_ready.emit(dataset)

    def _filter_bars_by_session(self, bars: list[OHLCVBar]) -> list[OHLCVBar]:
        if self._session_filter == "all":
            return bars
        if self._session_filter == "day":
            return [b for b in bars if dtime(8, 45) <= b.timestamp.time() < dtime(13, 45)]
        # night
        return [b for b in bars if b.timestamp.time() >= dtime(15, 0) or b.timestamp.time() < dtime(5, 0)]

    def _get_resampled_bars(self) -> list[OHLCVBar]:
        """Return bars resampled to the current timeframe, filtered by session."""
        bars = self._filter_bars_by_session(self._bars)
        if self._timeframe_minutes <= 1:
            return bars

        df = self._service.bars_to_dataframe(bars)
        df_resampled = self._service.resample(df, self._timeframe)
        # Convert back to OHLCVBar list
        df_resampled = df_resampled.reset_index()
        return [
            OHLCVBar(
                timestamp=row.timestamp.to_pydatetime(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume),
                open_interest=int(row.open_interest),
            )
            for row in df_resampled.itertuples(index=False)
        ]


def _parse_minutes(timeframe: str) -> int:
    """Extract minute count from timeframe string. '5min'→5, '1h'→60, '日K'→1440."""
    if timeframe in ("日K", "1d"):
        return 1440
    if timeframe == "1h":
        return 60
    m = re.fullmatch(r"(\d+)min", timeframe)
    if m:
        return int(m.group(1))
    return 1
