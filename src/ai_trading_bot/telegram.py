"""Telegram notification service — sends trade alerts, portfolio snapshots, and errors."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Simple Telegram bot notifier. No dependencies beyond httpx."""

    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        if self.enabled:
            logger.info("Telegram notifier configured")
        else:
            logger.info("Telegram notifier disabled — set TELEGRAM_TOKEN + TELEGRAM_CHAT_ID in .env")

    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return False
        import httpx
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, data={
                    "chat_id": self.chat_id,
                    "text": text[:4096],  # Telegram limit
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                })
                r.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def trade_opened(self, symbol: str, side: str, price: float, quantity: float, pnl: float | None = None) -> None:
        emoji = "🟢" if side == "buy" else "🔴"
        msg = (
            f"{emoji} <b>{side.upper()} {symbol}</b>\n"
            f"Price: ${price:,.2f}\n"
            f"Qty: {quantity:.4f}"
        )
        if pnl is not None:
            msg += f"\nPnL: ${pnl:+,.2f}"
        await self.send(msg)

    async def trade_closed(self, symbol: str, pnl: float, pnl_pct: float, reason: str) -> None:
        emoji = "💰" if pnl > 0 else "💸"
        msg = (
            f"{emoji} <b>{symbol} CLOSED</b>\n"
            f"PnL: <{'green' if pnl > 0 else 'red'}>${pnl:+,.2f} ({pnl_pct:+.2f}%)</{'green' if pnl > 0 else 'red'}>\n"
            f"Reason: {reason}"
        )
        await self.send(msg)

    async def portfolio_snapshot(self, cash: float, pnl: float, pnl_pct: float, win_rate: float, trade_count: int, can_live: bool) -> None:
        status = "🟢 LIVE READY" if can_live else "⚪ PAPER MODE"
        msg = (
            f"📊 <b>PORTFOLIO</b> {status}\n"
            f"💵 Balance: ${cash:,.2f}\n"
            f"📈 Total PnL: ${pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
            f"🎯 Win Rate: {win_rate:.0%}\n"
            f"🔄 Trades: {trade_count}"
        )
        await self.send(msg)

    async def stop_loss(self, symbol: str, price: float) -> None:
        await self.send(f"⛔ <b>STOP-LOSS</b> {symbol} @ ${price:,.2f}")

    async def take_profit(self, symbol: str, price: float) -> None:
        await self.send(f"🎯 <b>TAKE-PROFIT</b> {symbol} @ ${price:,.2f}")

    async def error(self, text: str) -> None:
        await self.send(f"❌ <b>ERROR</b>\n{text[:2000]}")

    async def improvement(self, rule: str, reason: str, expected_impact: str) -> None:
        msg = (
            f"🧠 <b>NEW STRATEGY</b>\n"
            f"Rule: {rule}\n"
            f"Why: {reason}\n"
            f"Expected: {expected_impact}"
        )
        await self.send(msg)
