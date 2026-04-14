# CLAUDE.md - Taiwan Futures Trader 開發指南

## 專案概述

**目標**：用 PyQt6 打造台灣期貨交易軟體（類 MultiCharts），支援看盤、下單、回測、策略執行。  
**技術棧**：PyQt6 + Qt Charts、Pandas/NumPy、Shioaji（永豐）、SQLite/PostgreSQL、Parquet

---

## 架構分層（嚴格遵守）

```
Presentation (PyQt6)  →  Application (Services)  →  Domain (Core)  →  Infrastructure (API/DB)
```

- **Presentation**：只顯示 UI，透過 Controller → Service 溝通，**不直接呼叫券商 API 或 DB**
- **Application**：協調 use case，不含業務規則
- **Domain**：核心邏輯，不依賴 PyQt / 券商 API 等外部框架
- **Infrastructure**：券商 Adapter、資料源、DB、指標實作

---

## ⚠️ 欄位標準化（最常見的 bug 來源）

所有資料進入 Application 層前，必須在 `infrastructure/market_data/column_mapper.py` 標準化：

```python
STANDARD_COLUMNS = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'open_interest']

COLUMN_ALIASES = {
    'volume':    ['Volume', '總Volume', '成交量', 'vol', 'v'],
    'open':      ['Open', '開盤價', 'o'],
    'high':      ['High', '最高價', 'h'],
    'low':       ['Low', '最低價', 'l'],
    'close':     ['Close', '收盤價', 'c'],
    'timestamp': ['Timestamp', 'Time', 'Date', '時間', '日期'],
}
```

遇到 `KeyError: 'Volume'` 之類的錯誤，**一律在 `column_mapper.py` 修**，不要在其他地方做欄位判斷。

---

## PyQt6 開發規則

1. **Signal/Slot 溝通**：跨元件用 `pyqtSignal`，不要直接 call method
2. **耗時操作用 QThread**：網路請求、大量計算不得在主執行緒執行
3. **表格元件用 QAbstractTableModel**（報價表、成交表等）
4. Widget 不持有 Service 或 Adapter 的直接引用，一律透過 Controller

```python
# ✅ 正確
class OrderController(QObject):
    order_placed = pyqtSignal(str)
    def place_order(self, dto: OrderDTO):
        order_id = self._order_service.submit(dto)
        self.order_placed.emit(order_id)

# ❌ 錯誤：Widget 直接呼叫券商 API
class OrderWidget(QWidget):
    def on_submit_clicked(self):
        shioaji.place_order(...)
```

---

## 多券商支援：Adapter 模式

新增券商繼承 `infrastructure/brokers/base.py` 的 `BrokerPort` ABC，實作 `connect / place_order / cancel_order / get_positions`，不修改 Application 層。

---

## 命名規則

| 類型 | 規則 |
|------|------|
| 檔案 | `snake_case.py` |
| 類別 | `PascalCase` |
| 函數 | `snake_case()` |
| 常數 | `UPPER_SNAKE` |
| 私有 | `_前綴底線` |

---

## 開發優先順序

**Phase 1（看盤 MVP）**
- `column_mapper.py` → `chart_data_service.py` → `candlestick_widget.py` → `volume_widget.py` → `crosshair.py` → MA / MACD / KD 指標

**Phase 2（交易核心）**
- `brokers/base.py` → `brokers/paper/adapter.py` → `order_service.py` → `position_service.py` → order_entry widget

**Phase 3（回測引擎）**
- `backtest/engine.py` → `broker_simulator.py` → `fill_model.py` → `performance.py`

**Phase 4（券商串接）**
- Shioaji adapter

---

## 常用指令

```bash
python main.py                                                        # 啟動
python -m cli.run_backtest --strategy ma_cross --symbol TXFR1 --start 2024-01-01
python -m cli.import_data --source csv --file data/txf_2024.csv
python -m cli.doctor                                                  # 環境檢查
pytest tests/                                                         # 全部測試
pytest --cov=taiwan_futures_trader --cov-report=html                  # 覆蓋率
```

---

## 參考資料

永豐API https://sinotrade.github.io/llms-full.txt
即時行情獲取 https://sinotrade.github.io/zh/tutor/market_data/streaming/futures/
歷史行情獲取 https://sinotrade.github.io/zh/tutor/market_data/historical/


## 禁止事項

- ❌ Widget 直接處理欄位或呼叫券商 API
- ❌ API Key 寫在程式碼裡（用環境變數或 `.env`）
- ❌ commit 前未執行測試
