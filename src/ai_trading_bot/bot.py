"""Main bot loop — orchestrates roles, market data, news, notifications, and learning."""

from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .activity import ActivityLog, AgentActivity, CycleSummary
from .config import config
from .llm import get_llm
from .market import PaperMarket, LiveMarket, get_market, Candle
from .roles import (
    Portfolio, TradeDecision, TradeResult, Signal,
    AnalystRole, RiskRole, ExecutorRole, ReviewerRole, ImprovementRole, SentimentRole,
)
from .news import NewsService
from .telegram import TelegramNotifier
from .dashboard import Dashboard
from .terminal import (
    print_cycle_start, print_cycle_end, print_activity,
    print_cycle_summary, print_trade_result, print_learning,
)

logger = logging.getLogger(__name__)

# ─── Dashboard terminal logger (pushes to dashboard._log_buffer) ────────────

class _DashboardHandler(logging.Handler):
    """Forwards all ai_trading_bot log records to the active dashboard instance."""

    def __init__(self, dashboard_ref):
        super().__init__()
        self._ref = dashboard_ref

    def emit(self, record):
        try:
            msg = self.format(record)
            self._ref(msg)
        except Exception:
            pass


# Hook all bot sub-module loggers into the dashboard once Dashboard is available
_dh = None  # set during bot init, updated per-dashboard


def wire_dashboard_loggers(dashboard):
    global _dh
    if _dh:
        for _name in list(logging.root.manager.loggerDict.keys()):
            if _name.startswith("ai_trading_bot"):
                logging.getLogger(_name).removeHandler(_dh)
    _dh = _DashboardHandler(dashboard.add_log)
    _dh.setLevel(logging.INFO)
    for _name in list(logging.root.manager.loggerDict.keys()):
        if _name.startswith("ai_trading_bot"):
            logging.getLogger(_name).addHandler(_dh)

# ─── Activity helper ──────────────────────────────────────────────────────────


def _track(
    log: ActivityLog,
    role: str,
    action: str,
    symbol: str = "",
    thinking: str = "",
    result: dict | None = None,
    raw: str = "",
    duration_ms: float = 0,
    status: str = "done",
    error: str = "",
    **meta,
) -> AgentActivity:
    activity = AgentActivity(
        timestamp=datetime.now(),
        role=role,
        action=action,
        symbol=symbol,
        thinking=thinking,
        result=result or {},
        raw_llm_output=raw,
        duration_ms=duration_ms,
        status=status,
        error=error,
        meta=meta,
    )
    log.add_activity(activity)
    return activity


# ─── Main Bot ─────────────────────────────────────────────────────────────────

class AITradingBot:
    def __init__(self, cfg: Any = None):
        self._cfg = cfg or config
        self.market = get_market(
            self._cfg.trading.mode,
            exchange_id=os.getenv("EXCHANGE_ID", "binance"),
            api_key=os.getenv("EXCHANGE_API_KEY", ""),
            secret=os.getenv("EXCHANGE_SECRET", ""),
        )
        self.portfolio = Portfolio(cash=self._cfg.trading.initial_capital)
        self.llm = get_llm()
        self.news = NewsService(x_bearer=os.getenv("X_BEARER_TOKEN", ""))
        self.notifier = TelegramNotifier(
            token=os.getenv("TELEGRAM_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        )
        self.log = ActivityLog(max_activities=500)

        # Roles
        self.analyst = AnalystRole()
        self.risk = RiskRole()
        self.executor = ExecutorRole()
        self.reviewer = ReviewerRole()
        self.improver = ImprovementRole()
        self.sentiment = SentimentRole()

        # State
        self._strategies: list[dict] = []
        self._strategy_file = Path.home() / ".ai_trading_bot" / "strategies.json"
        self._load_strategies()

        # Dashboard (starts in background thread)
        self.dashboard = Dashboard(self, port=int(os.getenv("WEB_PORT", "8081")))
        self.dashboard.start()
        wire_dashboard_loggers(self.dashboard)

        logger.info(f"Bot initialized in {self._cfg.trading.mode.upper()} mode")

    # ─── persistence ────────────────────────────────────────────────────────────────

    def _load_strategies(self) -> None:
        if self._strategy_file.exists():
            try:
                self._strategies = json.loads(self._strategy_file.read_text())
                logger.info(f"Loaded {len(self._strategies)} learned strategies")
            except Exception:
                pass

    def _save_strategies(self) -> None:
        self._strategy_file.parent.mkdir(parents=True, exist_ok=True)
        self._strategy_file.write_text(json.dumps(self._strategies, indent=2))

    # ─── roles ──────────────────────────────────────────────────────────────

    async def get_sentiment(self, symbols: list[str]) -> dict:
        start = time.monotonic()
        # Fetch news
        _track(self.log, "🌐 News", "fetching", result={"fetching_sources": True})
        news = await self.news.get_news()
        fetched_ms = (time.monotonic() - start) * 1000
        _track(self.log, "🌐 News", "analyzing", result={"collected": len(news)},
               duration_ms=fetched_ms, meta={"sources_count": len(news)})
        news_brief = self.news.brief(news, max_items=30)
        self.dashboard.update_news(news_brief)

        # Sentiment scoring
        sent_start = time.monotonic()
        sentiment = await self.sentiment(news_brief, symbols, self.llm)
        dur = (time.monotonic() - sent_start) * 1000
        _track(self.log, "📰 Sentiment", "scoring", result=sentiment,
               duration_ms=dur, meta={"symbols_scored": len(sentiment.get("sentiments", {}))})
        return sentiment

    async def analyze(self, symbol: str, news_context: str = "") -> TradeDecision:
        start = time.monotonic()
        candles = await self.market.get_candles(symbol, limit=50)
        candles_ms = (time.monotonic() - start) * 1000
        _track(self.log, "📡 Market", "fetching", symbol=symbol,
               result={"candles": len(candles)}, duration_ms=candles_ms)

        # Analyst
        a_start = time.monotonic()
        decision = await self.analyst(symbol, candles, self.llm, news_context)
        dur = (time.monotonic() - a_start) * 1000

        activity = _track(self.log, "🔍 Analyst", "deciding", symbol=symbol,
                          result={
                              "signal": decision.signal.value,
                              "confidence": round(decision.confidence, 2),
                              "reasoning": decision.reasoning[:300],
                          },
                          thinking=decision.reasoning,
                          duration_ms=dur,
                          meta={"candles_count": len(candles), "news_count": len(news_context)})
        logger.info(f"[ANALYST] {decision.symbol} → {decision.signal.value} (conf={decision.confidence:.2f})")
        return decision

    async def assess_risk(self, decision: TradeDecision) -> TradeDecision:
        start = time.monotonic()
        price = await self.market.get_price(decision.symbol)
        risk_start = time.monotonic()
        decision = await self.risk(decision, price, self.llm)
        dur = (time.monotonic() - risk_start) * 1000

        _track(self.log, "🛡️ Risk", "deciding", symbol=decision.symbol,
               result={
                   "position_size_pct": round(decision.position_size_pct, 1),
                   "stop_loss": round(decision.stop_loss, 2) if decision.stop_loss else None,
                   "take_profit": round(decision.take_profit, 2) if decision.take_profit else None,
               },
               thinking=decision.reasoning,
               duration_ms=dur,
               meta={"entry_price": round(price, 2), "confidence": round(decision.confidence, 2)})
        return decision

    async def execute_trade(self, decision: TradeDecision) -> TradeResult | None:
        price = await self.market.get_price(decision.symbol)
        qty = (self.portfolio.cash * decision.position_size_pct / 100) / price

        act_start = time.monotonic()
        order = await self.market.place_order(
            symbol=decision.symbol,
            side="buy" if decision.signal in (Signal.BUY, Signal.SHORT) else "sell",
            quantity=qty,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
        )
        dur = (time.monotonic() - act_start) * 1000

        if order.status != "filled":
            _track(self.log, "⚡ Executor", "executing", symbol=decision.symbol,
                   status="error", error=order.error, duration_ms=dur)
            logger.error(f"[EXECUTOR] Order failed: {order.error}")
            return None

        _track(self.log, "⚡ Executor", "executing", symbol=decision.symbol,
               result={"filled": True, "price": round(order.price, 2), "qty": round(order.quantity, 6)},
               duration_ms=dur,
               meta={"symbol": decision.symbol, "side": "buy" if decision.signal in (Signal.BUY, Signal.SHORT) else "sell"})

        result = TradeResult(
            symbol=decision.symbol,
            side="buy",
            entry_price=order.price,
            exit_price=0,
            quantity=order.quantity,
            pnl=0,
            pnl_pct=0,
            hold_duration_minutes=0,
            reason=decision.reasoning[:200],
        )

        # Notify
        if self.notifier.enabled:
            await self.notifier.trade_opened(
                decision.symbol, "buy", order.price, order.quantity
            )
        return result

    async def simulate_exit(self, trade: TradeResult) -> TradeResult:
        """Paper mode: simulate price movement and close."""
        import random
        await asyncio.sleep(0.5)
        change = random.gauss(0, 0.015)  # 1.5% vol per cycle
        exit_price = trade.entry_price * (1 + change)
        pnl = (exit_price - trade.entry_price) * trade.quantity
        trade.exit_price = exit_price
        trade.pnl = pnl
        trade.pnl_pct = (pnl / (trade.entry_price * trade.quantity)) * 100
        trade.hold_duration_minutes = random.uniform(10, 240)
        trade.reason = f"simulated exit (vol={change:+.2%})"

        self.portfolio.cash += pnl
        self.portfolio.add_trade(trade)

        _track(self.log, "📋 Reviewer", "reviewing", symbol=trade.symbol,
               result={"pnl": round(trade.pnl, 2), "pnl_pct": round(trade.pnl_pct, 2),
                       "hold_minutes": round(trade.hold_duration_minutes, 0)},
               thinking=trade.reason,
               meta={"entry": round(trade.entry_price, 2), "exit": round(trade.exit_price, 2)})

        if pnl > 0:
            logger.info(f"✅ {trade.symbol} +${pnl:.2f} ({trade.pnl_pct:+.2f}%)")
        else:
            logger.warning(f"❌ {trade.symbol} ${pnl:.2f} ({trade.pnl_pct:+.2f}%)")

        if self.notifier.enabled:
            await self.notifier.trade_closed(trade.symbol, pnl, trade.pnl_pct, trade.reason)
        return trade

    async def review_and_learn(self) -> None:
        for trade in self.portfolio.trades[-5:]:
            start = time.monotonic()
            review = await self.reviewer(trade, self.llm)
            dur = (time.monotonic() - start) * 1000
            _track(self.log, "📋 Reviewer", "reviewing", symbol=trade.symbol,
                   result=review, duration_ms=dur)
            if review.get("mistake"):
                logger.info(f"[REVIEW] {trade.symbol}: {review['mistake']}")

        if self._cfg.learning.enabled and len(self.portfolio.trades) >= self._cfg.learning.feedback_window:
            start = time.monotonic()
            improvement = await self.improver(self.portfolio.trades[-self._cfg.learning.feedback_window:], self.llm)
            dur = (time.monotonic() - start) * 1000
            if improvement:
                _track(self.log, "🧠 Improver", "learning", result=improvement, duration_ms=dur,
                       thinking=improvement.get("reason", ""))
                logger.info(f"[LEARNING] New rule: {improvement['rule']}")
                self._strategies.append({
                    **improvement,
                    "at_trades": len(self.portfolio.trades),
                    "time": datetime.now().isoformat(),
                })
                self._save_strategies()
                self.dashboard.add_improvement(improvement)
                if self.notifier.enabled:
                    await self.notifier.improvement(
                        improvement.get("rule", ""),
                        improvement.get("reason", ""),
                        improvement.get("expected_impact", ""),
                    )

    def _should_skip(self, decision: TradeDecision, sentiment: dict) -> tuple[bool, str]:
        """Check sentiment and learned strategies."""
        sentiments = sentiment.get("sentiments", {})
        sym_sent = sentiments.get(decision.symbol, 0)
        if decision.signal == Signal.BUY and sym_sent < -0.5:
            return True, f"sentiment too bearish ({sym_sent:+.2f})"
        if decision.signal == Signal.SHORT and sym_sent > 0.5:
            return True, f"sentiment too bullish ({sym_sent:+.2f})"
        for rule in self._strategies[-5:]:
            rule_text = rule.get("rule", "").lower()
            if "avoid" in rule_text and decision.symbol.lower().split("/")[0] in rule_text:
                return True, f"learned rule: {rule['rule'][:80]}"
        return False, ""

    # ─── main loop ──────────────────────────────────────────────────────────

    async def run_cycle(self, symbols: list[str]) -> list[TradeResult]:
        """One full analysis + execution cycle."""
        results: list[TradeResult] = []
        cycle_num = self.log.next_cycle_number()

        print_cycle_start(cycle_num)

        # Get sentiment across all symbols (non-fatal: fall back to neutral)
        try:
            sentiment = await self.get_sentiment(symbols)
        except Exception as e:
            logger.warning(f"News/sentiment unavailable, continuing neutral: {e}")
            self.dashboard.add_error(f"News unavailable: {e}")
            sentiment = {"sentiments": {}, "events": []}
        events = sentiment.get("events", [])
        if events:
            logger.info(f"[NEWS] {len(events)} market events: {events[0][:100] if events else ''}")
            _track(self.log, "📰 Sentiment", "scoring", result={"events": [events[0][:100]]},
                   status="done", meta={"events_count": len(events)})

        # Execute trades
        for symbol in symbols:
            if len(self.portfolio.positions) >= self._cfg.trading.max_positions:
                break
            try:
                decision = await self.analyze(symbol)
                if decision.signal == Signal.HOLD:
                    _track(self.log, "🔍 Analyst", "deciding", symbol=symbol,
                           result={"signal": "HOLD"}, status="skipped")
                    continue

                skip, reason = self._should_skip(decision, sentiment)
                if skip:
                    logger.info(f"[GATE] Skipping {decision.symbol}: {reason}")
                    _track(self.log, "🔍 Analyst", "deciding", symbol=symbol,
                           result={"signal": "HOLD (skipped)"}, status="skipped",
                           error=reason)
                    continue

                if decision.confidence < 0.55:
                    _track(self.log, "🔍 Analyst", "deciding", symbol=symbol,
                           result={"signal": "HOLD (low confidence)"}, status="skipped")
                    continue

                decision = await self.assess_risk(decision)
                trade = await self.execute_trade(decision)

                if trade:
                    # Paper mode: auto-exit after short delay
                    if self._cfg.is_paper:
                        trade = await self.simulate_exit(trade)
                    results.append(trade)
                    print_trade_result(trade)
            except Exception as e:
                logger.error(f"Cycle error for {symbol}: {e}")
                self.dashboard.add_error(str(e))
                if self.notifier.enabled:
                    await self.notifier.error(str(e))

        # Learn
        if results:
            await self.review_and_learn()

        print_cycle_end()

        # Build cycle summary
        port_state = {
            "balance": self.portfolio.cash,
            "total_pnl": self.portfolio.total_pnl,
            "win_rate": self.portfolio.win_rate,
            "trades": len(self.portfolio.trades),
        }
        activities = self.log.get_recent(50)
        self.log.add_cycle(CycleSummary(
            cycle_number=cycle_num,
            start_time=datetime.now(),
            symbols_analyzed=symbols,
            trades_executed=len(results),
            activities=activities,
            portfolio_state=port_state,
        ))

        can_live = (
            len(self.portfolio.trades) >= self._cfg.learning.min_trades_before_live
            and self.portfolio.win_rate >= self._cfg.learning.target_win_rate
        )
        print_cycle_summary(CycleSummary(
            cycle_number=cycle_num, start_time=datetime.now(),
            symbols_analyzed=symbols, trades_executed=len(results),
            activities=[], portfolio_state=port_state,
        ))

        return results

    async def run_loop(self, symbols: list[str], interval: int = 60) -> None:
        mode = self._cfg.trading.mode.upper()
        logger.info(f"🚀 AI Trading Bot started ({mode} mode)")
        logger.info(f"💰 Capital: ${self._cfg.trading.initial_capital:,.2f}")
        logger.info(f"📊 Symbols: {', '.join(symbols)}")
        logger.info(f"📡 Dashboard: http://localhost:{os.getenv('WEB_PORT', '8081')}")

        if not self._cfg.is_paper:
            logger.warning("⚠️  LIVE MODE — REAL MONEY AT RISK")
            if self.notifier.enabled:
                await self.notifier.send("⚠️ <b>LIVE MODE</b> — real money at risk!")

        # Send start notification
        if self.notifier.enabled:
            await self.notifier.send(
                f"🤖 <b>AI Trading Bot started</b>\n"
                f"Mode: {mode}\n"
                f"Symbols: {', '.join(symbols)}\n"
                f"Dashboard: http://localhost:{os.getenv('WEB_PORT', '8081')}"
            )

        while self.dashboard.is_running:
            try:
                trades = await self.run_cycle(symbols)

                # Portfolio snapshot
                port = self.portfolio
                can_live = (
                    len(port.trades) >= self._cfg.learning.min_trades_before_live
                    and port.win_rate >= self._cfg.learning.target_win_rate
                )

                # Telegram periodic update every 5 cycles
                if self.notifier.enabled and len(port.trades) % 5 == 0 and port.trades:
                    await self.notifier.portfolio_snapshot(
                        port.cash, port.total_pnl, port.total_pnl_pct,
                        port.win_rate, len(port.trades), can_live,
                    )

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                self.dashboard.add_error(str(e))
                if self.notifier.enabled:
                    await self.notifier.error(f"Loop crash: {e}")

            await asyncio.sleep(interval)

        await self.stop()

    async def stop(self) -> None:
        self.dashboard.is_running = False
        # Close all positions
        results = await self.market.close_all_positions()
        logger.info(f"Bot stopped. Closed {len(results)} positions.")
        await self.llm.close()
        if self.notifier.enabled:
            await self.notifier.send("🛑 <b>Bot stopped</b>")

    @property
    def _llm(self):
        return self.llm


def print_status(port: Portfolio, can_live: bool, cfg: Any) -> None:
    mode = "PAPER" if cfg.is_paper else "LIVE"
    print(f"\n{'='*60}")
    print(f"  [{mode}] Balance: ${port.cash:,.2f} | Trades: {len(port.trades)}")
    if port.trades:
        print(f"  📈 PnL: ${port.total_pnl:+,.2f} ({port.total_pnl_pct:+.2f}%) | WR: {port.win_rate:.0%}")
    print(f"  Live ready: {'✅ YES' if can_live else f'⏳ {len(port.trades)}/{cfg.learning.min_trades_before_live} trades, {port.win_rate:.0%}/{cfg.learning.target_win_rate:.0%} WR'}")
    if port.positions:
        print(f"  Open positions: {', '.join(port.positions.keys())}")
    print(f"{'='*60}")


import os  # noqa: E402