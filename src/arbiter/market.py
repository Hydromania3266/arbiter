"""Market data — paper simulation + live feed via CCXT (Binance)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    symbol: str
    timestamp: datetime
    o: float = field(default=0, repr=False)
    h: float = field(default=0, repr=False)
    l: float = field(default=0, repr=False)
    c: float = field(default=0, repr=False)
    volume: float = field(default=0, repr=False)


@dataclass
class OrderResult:
    symbol: str
    side: str              # "buy" | "sell"
    quantity: float
    price: float
    status: str            # "filled" | "open" | "error"
    trade_id: str = ""
    error: str = ""


class MarketData(Protocol):
    async def get_price(self, symbol: str) -> float: ...
    async def get_candles(self, symbol: str, limit: int = 100, timeframe: str = "1h") -> list[Candle]: ...
    async def get_balance(self) -> float: ...
    async def place_order(self, symbol: str, side: str, quantity: float, stop_loss: float | None, take_profit: float | None) -> OrderResult: ...
    async def close_all_positions(self) -> list[OrderResult]: ...


# ────────────────────────────────────────────────────────────────────────────
# PAPER MARKET
# ────────────────────────────────────────────────────────────────────────────

class PaperMarket(MarketData):
    """Paper market that pulls real prices from Binance public API, simulates orders locally."""

    def __init__(self, seed_prices: dict[str, float] | None = None):
        import random
        self._prices: dict[str, float] = seed_prices or {
            "BTC/USDT": 67000.0,
            "ETH/USDT": 3500.0,
            "SOL/USDT": 178.0,
        }
        self._history: dict[str, list[Candle]] = {s: [] for s in self._prices}
        self._rng = random.Random(42)
        self._open_orders: list[dict] = []
        self._balance: float = 100_000.0
        self._positions: dict[str, dict] = {}

    async def get_price(self, symbol: str) -> float:
        # Use Binance public ticker (no API key needed)
        try:
            import httpx
            clean = symbol.replace("/", "")
            r = await httpx.AsyncClient(timeout=5).get(
                f"https://api.binance.com/api/v3/ticker/price?symbol={clean}"
            )
            r.raise_for_status()
            return float(r.json()["price"])
        except Exception:
            # Fallback: random walk
            change = self._rng.gauss(0, 0.001)
            self._prices[symbol] *= 1 + change
            return self._prices[symbol]

    async def get_candles(self, symbol: str, limit: int = 100, timeframe: str = "1h") -> list[Candle]:
        # Binance public klines
        try:
            import httpx
            clean = symbol.replace("/", "")
            r = await httpx.AsyncClient(timeout=10).get(
                f"https://api.binance.com/api/v3/klines?symbol={clean}&interval={timeframe}&limit={limit}"
            )
            r.raise_for_status()
            return [Candle(
                symbol=symbol,
                timestamp=datetime.fromtimestamp(row[0] / 1000),
                o=float(row[1]), h=float(row[2]), l=float(row[3]),
                c=float(row[4]), volume=float(row[5]),
            ) for row in r.json()]
        except Exception as e:
            logger.error(f"Public candles failed for {symbol}: {e}")
            return []

    async def get_balance(self) -> float:
        return self._balance

    async def place_order(self, symbol: str, side: str, quantity: float, stop_loss: float | None, take_profit: float | None) -> OrderResult:
        import uuid
        price = await self.get_price(symbol)
        trade_id = f"paper-{uuid.uuid4().hex[:8]}"
        if side == "buy":
            cost = price * quantity
            if cost > self._balance:
                return OrderResult(symbol, side, quantity, price, "error", trade_id, "Insufficient funds")
            self._balance -= cost
            pos = self._positions.get(symbol, {"qty": 0, "avg_price": 0, "cost": 0})
            pos["qty"] += quantity
            pos["cost"] = pos.get("cost", 0) + cost
            pos["avg_price"] = pos["cost"] / pos["qty"] if pos["qty"] else 0
            pos["stop_loss"] = stop_loss
            pos["take_profit"] = take_profit
            self._positions[symbol] = pos
        elif side == "sell":
            pos = self._positions.get(symbol)
            if not pos or pos["qty"] <= 0:
                return OrderResult(symbol, side, quantity, price, "error", trade_id, "No position to close")
            qty_to_sell = min(quantity, pos["qty"])
            revenue = price * qty_to_sell
            self._balance += revenue
            pos["qty"] -= qty_to_sell
            if pos["qty"] <= 0.00000001:
                del self._positions[symbol]
        return OrderResult(symbol, side, quantity, price, "filled", trade_id)

    async def close_all_positions(self) -> list[OrderResult]:
        results = []
        symbols = list(self._positions.keys())
        for sym in symbols:
            pos = self._positions.get(sym, {})
            qty = pos.get("qty", 0)
            if qty > 0:
                result = await self.place_order(sym, "sell", qty, None, None)
                results.append(result)
        return results


# ────────────────────────────────────────────────────────────────────────────
# LIVE MARKET (CCXT — Binance, Coinbase, OKX, Bybit, Kraken…)
# ────────────────────────────────────────────────────────────────────────────

class LiveMarket(MarketData):
    """Real exchange connection via CCXT."""

    def __init__(self, exchange_id: str = "binance", api_key: str = "", secret: str = ""):
        import ccxt
        ccxt_params: dict = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
        if api_key and secret:
            ccxt_params["apiKey"] = api_key
            ccxt_params["secret"] = secret
        self._exchange = getattr(ccxt, exchange_id)(ccxt_params)
        self._positions: dict[str, dict] = {}  # track local positions for stop/take-profit

    async def _check_open_positions(self) -> list[OrderResult]:
        """Check if any open position hit stop-loss or take-profit and auto-close."""
        results: list[OrderResult] = []
        for symbol, pos in list(self._positions.items()):
            price = await self.get_price(symbol)
            if pos.get("stop_loss") and price <= pos["stop_loss"]:
                logger.warning(f"⛔ STOP-LOSS triggered: {symbol} @ ${price:.2f}")
                r = await self.place_order(symbol, "sell", pos["qty"], None, None)
                results.append(r)
                del self._positions[symbol]
            elif pos.get("take_profit") and price >= pos["take_profit"]:
                logger.info(f"🎯 TAKE-PROFIT triggered: {symbol} @ ${price:.2f}")
                r = await self.place_order(symbol, "sell", pos["qty"], None, None)
                results.append(r)
                del self._positions[symbol]
        return results

    async def get_price(self, symbol: str) -> float:
        ticker = await self._exchange.fetch_ticker(symbol)
        await self._check_open_positions()
        return float(ticker["last"])

    async def get_candles(self, symbol: str, limit: int = 100, timeframe: str = "1h") -> list[Candle]:
        ohlcv = await self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [Candle(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(row[0] / 1000),
            o=float(row[1]), h=float(row[2]), l=float(row[3]),
            c=float(row[4]), volume=float(row[5]),
        ) for row in ohlcv]

    async def get_balance(self) -> float:
        balance = await self._exchange.fetch_balance()
        # Return USDT balance (most common)
        for coin in ("USDT", "USDC", "BUSD"):
            if coin in balance and balance[coin].get("total"):
                return float(balance[coin]["total"])
        return 0.0

    async def place_order(self, symbol: str, side: str, quantity: float, stop_loss: float | None, take_profit: float | None) -> OrderResult:
        # Round quantity to exchange precision
        market = self._exchange.markets.get(symbol)
        if market and market.get("precision", {}).get("amount"):
            quantity = round(quantity, market["precision"]["amount"])
        try:
            order = await self._exchange.create_market_order(symbol, side, quantity)
            filled_qty = float(order.get("filled", quantity))
            price = float(order.get("average", order.get("info", {}).get("fills", [{}])[0].get("price", 0)))
            if side == "buy":
                self._positions[symbol] = {
                    "qty": filled_qty,
                    "avg_price": price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                }
            elif side == "sell" and symbol in self._positions:
                del self._positions[symbol]
            return OrderResult(symbol, side, filled_qty, price, "filled", str(order.get("id", "")))
        except Exception as e:
            logger.error(f"Order failed: {e}")
            return OrderResult(symbol, side, quantity, 0, "error", "", str(e))

    async def close_all_positions(self) -> list[OrderResult]:
        results = []
        for sym, pos in list(self._positions.items()):
            r = await self.place_order(sym, "sell", pos["qty"], None, None)
            results.append(r)
        self._positions.clear()
        return results


def get_market(mode: str, exchange_id: str = "binance", api_key: str = "", secret: str = "") -> MarketData:
    if mode == "paper":
        return PaperMarket()
    return LiveMarket(exchange_id, api_key, secret)
