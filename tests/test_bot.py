"""Tests for the Arbiter trading bot."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_roles_import():
    """Smoke test: roles can be imported."""
    from arbiter.roles import AnalystRole, RiskRole, Signal, TradeDecision
    assert Signal.BUY.value == "BUY"
    assert AnalystRole is not None
    assert RiskRole is not None


@pytest.mark.asyncio
async def test_trade_decision():
    """Smoke test: TradeDecision works."""
    from arbiter.roles import TradeDecision, Signal
    decision = TradeDecision(symbol="BTC/USD", signal=Signal.BUY, confidence=0.85, reasoning="test")
    assert decision.symbol == "BTC/USD"
    assert decision.confidence == 0.85


@pytest.mark.asyncio
async def test_bot_import():
    """Smoke test: bot can be imported."""
    from arbiter.bot import AITradingBot
    assert AITradingBot is not None


@pytest.mark.asyncio
async def test_config():
    """Smoke test: config can be created."""
    from arbiter.config import Config
    cfg = Config()
    assert cfg is not None