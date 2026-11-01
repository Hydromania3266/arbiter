#!/usr/bin/env python3
"""Entry point for the Arbiter."""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from arbiter.bot import AITradingBot, print_status
from arbiter.config import config
from arbiter.llm import get_llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


async def setup_wizard() -> None:
    """Interactive one-time setup wizard for newcomers."""
    from rich.console import Console
    from rich.prompt import Prompt, Confirm

    console = Console()
    env_path = Path(__file__).parent.parent / ".env"

    console.print("[bold green]🚀 Arbiter Setup Wizard[/bold green]")
    console.print("Answer a few questions and we'll configure everything for you.\n")

    # Trading mode
    paper = Confirm.ask("[bold]Are you new?[/bold] Start in PAPER mode (no real money)?", default=True)
    mode = "paper" if paper else "live"
    if not paper:
        console.print("[bold red]⚠️  WARNING[/bold red]: You will trade with REAL MONEY.")
        console.print("Make sure your EXCHANGE_API_KEY and EXCHANGE_SECRET are set in .env")
        confirm_live = Confirm.ask("Continue to LIVE mode?", default=False)
        if not confirm_live:
            paper = True
            mode = "paper"
        console.print("")

    # Exchange
    exchange = Prompt.ask("Exchange", choices=["binance", "kraken", "okx", "bybit"], default="binance")
    api_key = Prompt.ask("Binance API Key", default="", hide_input=True)
    secret = Prompt.ask("Binance API Secret", default="", hide_input=True)

    # Telegram
    telegram = Confirm.ask("Setup Telegram notifications?", default=False)
    tg_token = ""
    tg_chat = ""
    if telegram:
        console.print("  1. Open Telegram, search @BotFather")
        console.print("  2. Send /newbot, follow instructions")
        console.print("  3. Copy the BOT TOKEN here")
        tg_token = Prompt.ask("Telegram Bot Token", default="", hide_input=True)
        if tg_token:
            console.print("  Now search @myidbot and copy your ID")
            tg_chat = Prompt.ask("Telegram Chat ID", default="")

    # Cap
    capital = Prompt.ask("Initial capital (USD)", default="100000")
    risk_pct = Prompt.ask("Risk per trade (%)", default="2.0")
    win_target = Prompt.ask("Target win rate (%)", default="55")
    min_trades = Prompt.ask("Trades before live", default="20")

    # Write .env
    content = f"""# Arbiter — AUTO-GENERATED CONFIGURATION
# Edit this file anytime to change settings.

PAPER_MODE={"true" if paper else "false"}
INITIAL_CAPITAL={capital}
RISK_PERCENT_PER_TRADE={risk_pct}
MAX_POSITIONS=5

ROLE_ANALYST=gemini-3.8-flash
ROLE_RISK=glm-5.3-flash
ROLE_EXECUTOR=qwen3.8-flash
ROLE_REVIEWER=agnes-2.5-flash
ROLE_IMPROVEMENT=deepseek-v4-flash

MIN_TRADES_BEFORE_LIVE={min_trades}
TARGET_WIN_RATE={float(win_target)/100}

EXCHANGE_ID={exchange}
EXCHANGE_API_KEY={api_key}
EXCHANGE_SECRET={secret}

TELEGRAM_TOKEN={tg_token}
TELEGRAM_CHAT_ID={tg_chat}

WEB_PORT=8080
"""
    env_path.write_text(content)
    console.print(f"\n[bold green]✅ Configuration saved to {env_path}[/bold green]\n")
    console.print("Next steps:")
    console.print("  1. pip install -e \".[dev]\"          (if not done yet)")
    console.print("  2. python -m src.main                 (start bot)")
    console.print("  3. Open http://localhost:8080         (dashboard)")
    console.print("  4. After 20 trades with >55% WR: set PAPER_MODE=false")
    console.print("\n💡 Pro tip: Leave PAPER_MODE=true for at least a week before going live.")
    console.print("\nGood luck! 🤖📈\n")


async def paper_test() -> None:
    """Run a quick paper trading test."""
    bot = AITradingBot()
    print(f"Paper trading test — {config.trading.mode.upper()} mode")
    print(f"Symbols: {', '.join(SYMBOLS)}\n")

    for i in range(5):
        print(f"--- Cycle {i+1} ---")
        trades = await bot.run_cycle(SYMBOLS)
        for t in trades:
            print(f"  {t.symbol}: {t.side} @ ${t.entry_price:.2f}")
        can_live = (
            len(bot.portfolio.trades) >= config.learning.min_trades_before_live
            and bot.portfolio.win_rate >= config.learning.target_win_rate
        )
        print_status(bot.portfolio, can_live, config)
        await asyncio.sleep(1)

    await bot.stop()


async def live_mode() -> None:
    """Switch to live trading (requires ccxt + exchange keys)."""
    config.trading.mode = "live"
    bot = AITradingBot()
    print("⚠️  LIVE TRADING MODE — REAL MONEY AT RISK")
    await bot.run_loop(SYMBOLS, interval=60)


def cli() -> None:
    """Command-line entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Arbiter")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "test", "live", "setup"],
                        help="run (default), test (5-paper cycles), live, setup (wizard)")
    args = parser.parse_args()
    commands = {"run": main, "test": paper_test, "live": live_mode, "setup": setup_wizard}
    asyncio.run(commands[args.command]())


async def main() -> None:
    bot = AITradingBot()
    try:
        await bot.run_loop(SYMBOLS, interval=30)  # 30s between cycles in paper mode
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
    finally:
        await bot.stop()


def run_web() -> None:
    """Launch just the web dashboard without running trades."""
    bot = AITradingBot()
    asyncio.run(bot.run_loop(SYMBOLS, interval=10))


if __name__ == "__main__":
    cli()
