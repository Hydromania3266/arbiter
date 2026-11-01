"""Rich terminal output for the AI Trading Bot — Fidel Labs style transparency."""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

from .activity import AgentActivity, CycleSummary
from .roles import TradeResult

console = Console()

# ── Role colors ────────────────────────────────────────────────────────────────

_ROLE_COLORS: dict[str, str] = {
    "🔍 Analyst": "cyan",
    "🛡️ Risk": "yellow",
    "⚡ Executor": "green",
    "📋 Reviewer": "magenta",
    "🧠 Improver": "blue",
    "📰 Sentiment": "white",
    "🌐 News": "dim_white",
    "📡 Market": "dim_white",
}

_STATUS_COLORS: dict[str, str] = {
    "processing": "yellow",
    "done": "green",
    "skipped": "dim_white",
    "error": "red",
}


# ── Cycle framing ──────────────────────────────────────────────────────────────

def print_cycle_start(number: int) -> None:
    title = Text(f" 🤖 AI TRADING BOT — Cycle #{number} ", style="bold blue")
    console.rule(title)
    console.print()


def print_cycle_end() -> None:
    console.print()
    console.rule(style="dim")


# ── Activity display ───────────────────────────────────────────────────────────

def print_activity(activity: AgentActivity) -> None:
    """Print a single agent activity with role-specific formatting."""
    role_color = _ROLE_COLORS.get(activity.role, "white")
    action_icon = _action_icon(activity.action)

    lines: list[str] = []
    symbol_prefix = f" — {activity.symbol}" if activity.symbol else ""

    # Header line
    header = Text.assemble(
        ("  ", "dim"),
        (f"{activity.role}{symbol_prefix}", f"bold {role_color}"),
        ("  ", "dim"),
        (f"→ {action_icon}", role_color),
    )
    console.print(header)

    # Body lines based on role
    if activity.role == "📰 Sentiment" or activity.role == "🌐 News":
        _print_sentiment_body(activity, lines)
    elif activity.role == "🔍 Analyst":
        _print_analyst_body(activity, lines)
    elif activity.role == "🛡️ Risk":
        _print_risk_body(activity, lines)
    elif activity.role == "⚡ Executor":
        _print_executor_body(activity, lines)
    elif activity.role == "📋 Reviewer":
        _print_reviewer_body(activity, lines)
    elif activity.role == "🧠 Improver":
        _print_improver_body(activity, lines)
    else:
        _print_generic_body(activity, lines)

    for line in lines:
        console.print(f"   {line}")

    # Collapsible thinking block
    if activity.thinking:
        console.print(f"   [dim]💭 [italic]{activity.thinking[:200]}...[/italic][/dim]")

    # Status and timing
    status_style = _STATUS_COLORS.get(activity.status, "white")
    console.print(f"   ⏱️  {activity.duration_ms / 1000:.1f}s  [{status_style}]{activity.status}[/]")


def _print_sentiment_body(a: AgentActivity, lines: list[str]) -> None:
    sentiments = a.result.get("sentiments", {})
    events = a.result.get("events", [])
    for sym, score in sentiments.items():
        arrow = "🟢" if score > 0.3 else ("🔴" if score < -0.3 else "🟡")
        lines.append(f"{arrow} {sym}: {score:+.2f}")
    if events:
        lines.append(f"   Top event: {events[0][:100]}")


def _print_analyst_body(a: AgentActivity, lines: list[str]) -> None:
    signal = a.result.get("signal", "")
    confidence = a.result.get("confidence", 0)
    candles = a.meta.get("candles_count", 0)
    news = a.meta.get("news_count", 0)
    lines.append(f"Analyzing {candles} candles, {news} news items")
    if signal:
        color = "green" if signal in ("BUY", "LONG") else ("red" if signal == "SHORT" else "yellow")
        lines.append(f"→ DECISION: {signal} (confidence: {confidence:.2f})")


def _print_risk_body(a: AgentActivity, lines: list[str]) -> None:
    ps = a.result.get("position_size_pct", 0)
    sl = a.result.get("stop_loss", 0)
    tp = a.result.get("take_profit", 0)
    entry = a.meta.get("entry_price", 0)
    lines.append(f"Position size: {ps:.1f}%  Stop-loss: ${sl:.2f}  Take-profit: ${tp:.2f}")
    if entry > 0:
        sl_pct = (sl - entry) / entry * 100
        tp_pct = (tp - entry) / entry * 100
        lines.append(f"Risk: {sl_pct:+.1f}%  Reward: {tp_pct:+.1f}%  R:R = {abs(tp_pct/sl_pct):.2f}:1")


def _print_executor_body(a: AgentActivity, lines: list[str]) -> None:
    if a.result.get("filled"):
        lines.append(f"Order filled ✅  qty={a.result.get('qty', '?')} @ ${a.result.get('price', '?'):.2f}")
    elif a.result.get("failed"):
        lines.append(f"Order failed: {a.error}")
    else:
        lines.append(f"Status: {a.status}")


def _print_reviewer_body(a: AgentActivity, lines: list[str]) -> None:
    mistake = a.result.get("mistake", "")
    improvement = a.result.get("improvement", "")
    well = a.result.get("what_went_well", "")
    if well:
        lines.append(f"✓ {well}")
    if mistake:
        lines.append(f"✗ {mistake}")
    if improvement:
        lines.append(f"→ Improve: {improvement}")


def _print_improver_body(a: AgentActivity, lines: list[str]) -> None:
    rule = a.result.get("rule", "")
    reason = a.result.get("reason", "")
    impact = a.result.get("expected_impact", "")
    if rule:
        lines.append(f"NEW RULE: {rule}")
    if reason:
        lines.append(f"WHY: {reason}")
    if impact:
        lines.append(f"EFFECT: {impact}")


def _print_generic_body(a: AgentActivity, lines: list[str]) -> None:
    for k, v in a.result.items():
        lines.append(f"  {k}: {v}")


def _action_icon(action: str) -> str:
    icons = {
        "analyzing": "🔎",
        "deciding": "🎯",
        "executing": "⚡",
        "reviewing": "📋",
        "learning": "🧠",
        "scoring": "📊",
        "fetching": "📡",
    }
    return icons.get(action, "•")


# ── Cycle summary ─────────────────────────────────────────────────────────────

def print_cycle_summary(summary: CycleSummary) -> None:
    trades = summary.trades_executed
    pnl = summary.portfolio_state.get("total_pnl", 0)
    win_rate = summary.portfolio_state.get("win_rate", 0)
    balance = summary.portfolio_state.get("balance", 0)

    pnl_color = "green" if pnl >= 0 else "red"
    pnl_icon = "✅" if pnl >= 0 else "❌"
    wr_color = "green" if win_rate >= 0.55 else "red"

    console.print(f"  {pnl_icon} Trades: {trades}  Balance: ${balance:,.2f}  PnL: ${pnl:+,.2f} ({win_rate:.0%} WR)")


# ── Trade result ──────────────────────────────────────────────────────────────

def print_trade_result(trade: TradeResult) -> None:
    color = "green" if trade.pnl >= 0 else "red"
    icon = "✅" if trade.pnl >= 0 else "❌"
    console.print(
        f"  {icon} [bold {color}]{trade.symbol} {trade.side.upper()}[/bold {color}] "
        f"@ ${trade.entry_price:.2f} → ${trade.exit_price:.2f} "
        f"PnL: ${trade.pnl:+.2f} ({trade.pnl_pct:+.2f}%)"
    )


# ── Learning ──────────────────────────────────────────────────────────────────

def print_learning(learning: dict) -> None:
    rule = learning.get("rule", "")
    if rule:
        console.print(f"  🧠 [bold cyan]NEW STRATEGY RULE[/bold cyan]: {rule}")
        reason = learning.get("reason", "")
        if reason:
            console.print(f"     [dim]Reason: {reason}[/dim]")
