"""FastAPI web dashboard — modern Fidel Labs style agent transparency."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)


class Dashboard:
    def __init__(self, bot: Any, port: int = 8090):
        self.bot = bot
        self.app = FastAPI(title="AI Trading Bot")
        self._running = True
        self._port = port
        self._news_cache: str = "(no news yet)"
        self._improvements: list[dict] = []
        self._errors: list[str] = []
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._log_buffer: list[str] = []

        # Load modern dashboard template from file
        templates_dir = Path(__file__).parent.parent / "templates"
        template_path = templates_dir / "dashboard.html"
        self._dashboard_html = template_path.read_text(encoding="utf-8") if template_path.exists() else ""

        @self.app.get("/", response_class=HTMLResponse)
        async def index():
            return self._dashboard_html

        @self.app.get("/api/status")
        async def api_status():
            port = self.bot.portfolio
            trades = port.trades
            avg_dur = sum(t.hold_duration_minutes for t in trades) / len(trades) if trades else 0
            best = max([t.pnl for t in trades]) if trades else 0
            worst = min([t.pnl for t in trades]) if trades else 0
            wins = [t for t in trades if t.pnl > 0]
            losses = [t for t in trades if t.pnl <= 0]
            avg_w = sum(t.pnl for t in wins) / len(wins) if wins else 0
            avg_l = sum(t.pnl for t in losses) / len(losses) if losses else 0
            pf = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else float('inf')
            return {
                "running": self._running,
                "mode": self.bot._cfg.trading.mode,
                "cash": round(port.cash, 2),
                "pnl": round(port.total_pnl, 2),
                "pnl_pct": round(port.total_pnl_pct, 4),
                "win_rate": round(port.win_rate, 4),
                "trade_count": len(port.trades),
                "can_live": len(port.trades) >= self.bot._cfg.learning.min_trades_before_live and port.win_rate >= self.bot._cfg.learning.target_win_rate,
                "avg_duration": round(avg_dur, 1),
                "best_trade": round(best, 2),
                "worst_trade": round(worst, 2),
                "avg_win": round(avg_w, 2),
                "avg_loss": round(avg_l, 2),
                "profit_factor": round(pf, 2) if pf != float('inf') else "∞",
                "win_trades": len(wins),
                "loss_trades": len(losses),
                "news": self._news_cache[:500] if self._news_cache else "",
            }

        @self.app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()
            async with self._lock:
                self._clients.append(ws)
            try:
                await self._send_snapshot(ws)
                while self._running:
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                    if msg == "ping":
                        await ws.send_text("pong")
                    elif msg == "snapshot":
                        await self._send_snapshot(ws)
            except (WebSocketDisconnect, asyncio.TimeoutError):
                pass
            finally:
                async with self._lock:
                    self._clients = [c for c in self._clients if c != ws]

        @self.app.post("/api/stop")
        async def api_stop():
            self._running = False
            self.bot._is_running = False
            return {"status": "stopped"}

        @self.app.post("/api/resume")
        async def api_resume():
            self._running = True
            self.bot._is_running = True
            return {"status": "resumed"}

        @self.app.post("/api/restart")
        async def api_restart(capital: float = 100000, mode: str = "paper"):
            import os
            os.environ["INITIAL_CAPITAL"] = str(capital)
            os.environ["PAPER_MODE"] = "true" if mode == "paper" else "false"
            self.bot.portfolio.cash = capital
            self.bot.portfolio.trades = []
            self.bot.portfolio.positions = {}
            self.bot._cfg.trading.mode = mode
            self.bot._cfg.trading.initial_capital = capital
            return {"status": "restarted", "capital": capital, "mode": mode}

    @property
    def is_running(self) -> bool:
        return self._running

    @is_running.setter
    def is_running(self, value: bool) -> None:
        self._running = value

    def add_log(self, msg: str):
        """Add a log line to the terminal buffer."""
        self._log_buffer.append(msg)
        if len(self._log_buffer) > 100:
            self._log_buffer.pop(0)

    def add_improvement(self, improvement: dict) -> None:
        """Called by bot.py when the Improver learns a new rule."""
        self._improvements.append(improvement)
        rule = improvement.get("rule", "")
        self.add_log(f"🧠 LEARNING: {rule}")

    def add_error(self, msg: str) -> None:
        """Called by bot.py on error."""
        self._errors.append(msg)
        self.add_log(f"❌ ERROR: {msg}")

    def update_news(self, news_brief: str) -> None:
        self._news_cache = news_brief

    async def _send_snapshot(self, ws: WebSocket) -> None:
        port = self.bot.portfolio
        can_live = (
            len(port.trades) >= self.bot._cfg.learning.min_trades_before_live
            and port.win_rate >= self.bot._cfg.learning.target_win_rate
        )
        activities = self.bot.log.get_recent(50)

        # Compute stats
        trades = port.trades
        avg_duration = sum(t.hold_duration_minutes for t in trades) / len(trades) if trades else 0
        best_trade = max([t.pnl for t in trades]) if trades else 0
        worst_trade = min([t.pnl for t in trades]) if trades else 0
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
        profit_factor = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else float('inf')

        await ws.send_json({
            "type": "snapshot",
            "status": {
                "running": self._running,
                "mode": self.bot._cfg.trading.mode,
                "cash": round(port.cash, 2),
                "pnl": round(port.total_pnl, 2),
                "pnl_pct": round(port.total_pnl_pct, 4),
                "win_rate": round(port.win_rate, 4),
                "trade_count": len(port.trades),
                "can_live": can_live,
                "news": self._news_cache[:500] if self._news_cache else "",
                "avg_duration": round(avg_duration, 1),
                "best_trade": round(best_trade, 2),
                "worst_trade": round(worst_trade, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
                "win_trades": len(wins),
                "loss_trades": len(losses),
                "logs": list(self._log_buffer[-30:]),
            },
            "activities": [
                {
                    "role": a.role, "action": a.action, "symbol": a.symbol,
                    "thinking": a.thinking[:500] if a.thinking else "",
                    "result": a.result,
                    "duration_ms": int(a.duration_ms),
                    "status": a.status,
                    "time": a.timestamp.isoformat(),
                }
                for a in activities
            ],
            "trades": [
                {
                    "symbol": t.symbol, "side": t.side,
                    "entry": t.entry_price, "exit": t.exit_price,
                    "pnl": round(t.pnl, 2), "pnl_pct": round(t.pnl_pct, 2),
                    "reason": t.reason[:80] if t.reason else "",
                    "time": t.timestamp.isoformat(),
                }
                for t in port.trades[-20:]
            ],
        })

    def start(self, port: int | None = None) -> None:
        from threading import Thread
        p = port or self._port
        thread = Thread(target=uvicorn.run, args=(self.app,), kwargs={
            "host": "0.0.0.0", "port": p, "log_level": "error",
        }, daemon=True)
        thread.start()

