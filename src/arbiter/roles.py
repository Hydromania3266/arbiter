"""Trading roles — each LLM role has a specific job."""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Any

from .config import config

logger = logging.getLogger(__name__)


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SHORT = "SHORT"


@dataclass
class TradeDecision:
    symbol: str
    signal: Signal
    confidence: float  # 0–1
    reasoning: str
    position_size_pct: float = 0.0  # % of portfolio
    stop_loss: float | None = None
    take_profit: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeResult:
    symbol: str
    side: str  # "buy" or "sell"
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    hold_duration_minutes: float
    reason: str
    stop_loss: float | None = None
    take_profit: float | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, float] = field(default_factory=dict)  # symbol -> quantity
    trades: list[TradeResult] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        return self.cash

    def add_trade(self, result: TradeResult) -> None:
        self.trades.append(result)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades)

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def total_pnl_pct(self) -> float:
        if not self.trades:
            return 0.0
        return self.total_pnl / 100_000 * 100  # relative to initial capital


# ─── Role Implementations ───────────────────────────────────────────────────


class AnalystRole:
    """Analyzes market data and suggests signals."""

    SYSTEM_PROMPT = """You are a market analyst AI. Given candle data and market context,
output a trading signal with reasoning. Be precise, cite data points, and assign a
confidence score (0.0–1.0). Consider: trend, support/resistance, volume, RSI, MACD.
Do NOT be vague. Give a clear BUY/SELL/HOLD/SHORT signal."""

    async def __call__(self, symbol: str, candles: list[Any], llm: Any, news_context: str = "") -> TradeDecision:
        from arbiter.llm import get_llm as _get_llm
        client = llm or _get_llm()
        latest = candles[-5:] if len(candles) >= 5 else candles
        candle_text = "\n".join(
            f"  {c.timestamp} O={c.o} H={c.h} L={c.l} C={c.c} V={c.volume}"
            for c in latest
        )
        news_block = f"\n\nRecent market news/sentiment context:\n{news_context[:1500]}\n" if news_context else ""
        data = await client.structured_chat(
            model=config.roles.analyst,
            system=self.SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Analyze {symbol}:\n{candle_text}{news_block}\n\nOutput JSON: {{\"signal\":\"BUY|SELL|HOLD|SHORT\",\"confidence\":0.0-1.0,\"reasoning\":\"...\"}}",
            }],
        )
        return TradeDecision(
            symbol=symbol,
            signal=Signal(data["signal"]),
            confidence=float(data["confidence"]),
            reasoning=data["reasoning"],
        )


class RiskRole:
    """Validates decisions and sets stop-loss / take-profit."""

    SYSTEM_PROMPT = """You are a risk manager. For each trade proposal, determine:
position size (% of portfolio, max 5%), stop-loss distance, and take-profit target.
Be conservative. Never allow more than 3% risk per trade. Output JSON."""

    async def __call__(self, decision: TradeDecision, current_price: float, llm: Any) -> TradeDecision:
        from arbiter.llm import get_llm as _get_llm
        client = llm or _get_llm()
        data = await client.structured_chat(
            model=config.roles.risk,
            system=self.SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Trade proposal: {decision.signal.value} {decision.symbol}
Confidence: {decision.confidence:.2f}
Reasoning: {decision.reasoning}
Current price: ${current_price:.2f}
Max risk per trade: {config.trading.risk_percent_per_trade}%

Output JSON: {{\"position_size_pct\":0.0-5.0,\"stop_loss\":0.0,\"take_profit\":0.0}}""",
            }],
        )
        decision.position_size_pct = float(data["position_size_pct"])
        decision.stop_loss = float(data["stop_loss"])
        decision.take_profit = float(data["take_profit"])
        return decision


class ExecutorRole:
    """Executes the trade (paper or live)."""

    async def execute(self, decision: TradeDecision, portfolio: Any, market: Any, llm: Any) -> TradeResult | None:
        from arbiter.llm import get_llm as _get_llm
        client = llm or _get_llm()
        current_price = await market.get_price(decision.symbol)
        qty = (portfolio.total_value * decision.position_size_pct / 100) / current_price
        entry = current_price

        if decision.signal == Signal.BUY:
            if portfolio.cash >= entry * qty:
                portfolio.cash -= entry * qty
                portfolio.positions[decision.symbol] = portfolio.positions.get(decision.symbol, 0) + qty
                return TradeResult(
                    symbol=decision.symbol,
                    side="buy", entry_price=entry, exit_price=0, quantity=qty,
                    pnl=0, pnl_pct=0, hold_duration_minutes=0, reason="opened",
                )
        elif decision.signal == Signal.SELL:
            if decision.symbol in portfolio.positions:
                qty_to_sell = portfolio.positions[decision.symbol]
                portfolio.cash += entry * qty_to_sell
                pnl = (entry - entry) * qty_to_sell  # simplified
                del portfolio.positions[decision.symbol]
                return TradeResult(
                    symbol=decision.symbol, side="sell", entry_price=entry, exit_price=entry,
                    quantity=qty_to_sell, pnl=pnl, pnl_pct=0, hold_duration_minutes=0,
                    reason="closed",
                )
        return None


class SentimentRole:
    """Reads market news and outputs a sentiment score per symbol."""

    SYSTEM_PROMPT = """You are a market sentiment analyst. Given a digest of recent
news and social posts, score the market sentiment for each symbol.

Score: -1.0 (very bearish) to +1.0 (very bullish). 0.0 = neutral/mixed.
Be strict: only score strongly when multiple items agree. Isolated headlines
score ±0.2 at most. Consider: regulatory news, hacks, ETF flows, macro events,
hype vs. fear ratio.

Output JSON: {"symbol": score, ...} for each symbol mentioned, plus
"events": ["top 3 market-moving headlines"].

Symbol normalization: Use canonical symbol names like "BTC/USDT", "ETH/USDT",
"SOL/USDT" as keys, even if the news uses "Bitcoin", "BTC", "ethereum", etc.
Always include scores for ALL requested symbols, even if no news mentions them
(scoré as 0.0 if truly no signal)."""

    # Maps common aliases to canonical symbol keys
    _SYMBOL_ALIASES: dict[str, str] = {
        # BTC variants
        "btc/usdt": "BTC/USDT", "btc/USD": "BTC/USD", "btc": "BTC/USDT",
        "bitcoin": "BTC/USDT", "bitcion": "BTC/USDT", "xbt": "BTC/USDT",
        # ETH variants
        "eth/usdt": "ETH/USDT", "eth/USD": "ETH/USD", "eth": "ETH/USDT",
        "ethereum": "ETH/USDT", "ether": "ETH/USDT",
        # SOL variants
        "sol/usdt": "SOL/USDT", "sol/USD": "SOL/USD", "sol": "SOL/USDT",
        "solana": "SOL/USDT",
        # General
        "usdt": "USDT", "usdc": "USDC",
    }

    async def __call__(
        self, news_brief: str, symbols: list[str], llm: Any, retries: int = 3
    ) -> dict:
        from arbiter.llm import get_llm as _get_llm
        client = llm or _get_llm()

        # Normalize requested symbols to canonical forms for matching
        canonical_symbols = self._normalize_symbols(symbols)

        for attempt in range(retries):
            try:
                data = await client.structured_chat(
                    model=config.roles.analyst,
                    system=self.SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Symbols to score: {', '.join(symbols)}\n\n"
                            f"News digest:\n{news_brief}\n\n"
                            "Output JSON with sentiment score per symbol and top 3 events."
                        ),
                    }],
                )

                # If we got events, include them
                events = data.pop("events", [])

                # Ensure all requested symbols are present
                sentiments = self._ensure_all_symbols(data, canonical_symbols)

                return {"sentiments": sentiments, "events": events}

            except Exception as e:
                logger.warning(f"Sentiment parsing attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    continue
                logger.warning("Sentiment all retries exhausted, using neutral")
                return {"sentiments": {s: 0.0 for s in symbols}, "events": []}

        return {"sentiments": {s: 0.0 for s in symbols}, "events": []}

    def _normalize_symbols(self, symbols: list[str]) -> dict[str, str]:
        """Map requested symbols to their canonical forms."""
        normalized: dict[str, str] = {}
        for sym in symbols:
            lower = sym.lower().strip()
            canonical = self._SYMBOL_ALIASES.get(lower, sym)
            normalized[canonical] = sym
        return normalized

    def _parse_sentiment_response(self, raw: str, canonical_map: dict[str, str]) -> dict[str, float]:
        """Parse JSON response and normalize symbol keys."""
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(cleaned)

        # Normalize keys
        sentiments: dict[str, float] = {}
        for key, value in data.items():
            if key == "events":
                continue
            lower_key = key.lower().strip()
            # Try exact match first, then alias match
            if lower_key in canonical_map:
                sentiments[canonical_map[lower_key]] = self._clamp_score(value)
            elif lower_key in self._SYMBOL_ALIASES:
                canon = self._SYMBOL_ALIASES[lower_key]
                sentiments[canon] = self._clamp_score(value)
            else:
                # Try partial match
                for canon_sym, original in canonical_map.items():
                    if key.lower() in canon_sym.lower() or canon_sym.lower() in key.lower():
                        sentiments[original] = self._clamp_score(value)
                        break
                else:
                    # Keep unknown symbols as-is (might be a new symbol)
                    sentiments[key] = self._clamp_score(value)

        return sentiments

    @staticmethod
    def _clamp_score(value: Any) -> float:
        """Ensure score is between -1.0 and 1.0."""
        try:
            score = float(value)
            return max(-1.0, min(1.0, score))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _ensure_all_symbols(
        sentiments: dict[str, float], canonical_map: dict[str, str]
    ) -> dict[str, float]:
        """Ensure all requested symbols have a score."""
        for canon, original in canonical_map.items():
            if original not in sentiments and canon not in sentiments:
                sentiments[original] = 0.0
        return sentiments


class ReviewerRole:
    """Reviews completed trades and extracts lessons."""

    SYSTEM_PROMPT = """You are a trade review analyst. Given a completed trade with entry,
exit, P&L, and reasoning, identify: what was done well, what was wrong, and one
actionable improvement. Output JSON."""

    async def __call__(self, trade: TradeResult, llm: Any) -> dict:
        from arbiter.llm import get_llm as _get_llm
        client = llm or _get_llm()
        try:
            data = await client.structured_chat(
                model=config.roles.reviewer,
                system=self.SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"""Trade: {trade.symbol} {trade.side.upper()}
Entry: ${trade.entry_price:.2f} | Exit: ${trade.exit_price:.2f}
PnL: ${trade.pnl:.2f} ({trade.pnl_pct:+.2f}%)
Duration: {trade.hold_duration_minutes:.0f} min
Reason: {trade.reason}

Output JSON: {{\"what_went_well\":\"...\",\"mistake\":\"...\",\"improvement\":\"...\"}}""",
                }],
            )
            return data
        except Exception as e:
            logger.warning(f"Reviewer failed: {e}")
            return {"what_went_well": "", "mistake": "", "improvement": ""}


class ImprovementRole:
    """Learns from accumulated trade history and suggests strategy changes."""

    SYSTEM_PROMPT = """You are a trading strategy improvement engine. Given a history of
past trades with outcomes, identify patterns in mistakes and suggest ONE concrete
rule change that would improve future performance. Focus on repeatable errors."""

    async def __call__(self, trades: list[TradeResult], llm: Any) -> dict | None:
        from arbiter.llm import get_llm as _get_llm
        client = llm or _get_llm()
        if len(trades) < config.learning.feedback_window:
            return None

        recent = trades[-config.learning.feedback_window:]
        trade_summary = "\n".join(
            f"{t.symbol} {t.side} entry=${t.entry_price:.2f} exit=${t.exit_price:.2f} pnl=${t.pnl:.2f} ({t.pnl_pct:+.1f}%) — {t.reason}"
            for t in recent
        )
        try:
            data = await client.structured_chat(
                model=config.roles.improvement,
                system=self.SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Last {len(recent)} trades:\n{trade_summary}\n\nSuggest ONE rule change. Output JSON: {{\"rule\":\"...\",\"reason\":\"...\",\"expected_impact\":\"...\"}}",
                }],
            )
            return data
        except Exception as e:
            logger.warning(f"Improver failed: {e}")
            return None
