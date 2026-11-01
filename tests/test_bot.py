"""Tests for the trading bot."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value='{"signal":"BUY","confidence":0.85,"reasoning":"Trending up"}')
    llm.close = AsyncMock()
    return llm


@pytest.fixture
def mock_market():
    market = AsyncMock()
    market.get_price = AsyncMock(return_value=67000.0)
    market.get_candles = AsyncMock(return_value=[])
    return market


@pytest.mark.asyncio
async def test_analyze(mocker, mock_llm, mock_market):
    from ai_trading_bot.roles import AnalystRole
    role = AnalystRole()
    decision = await role("BTC/USD", [], mock_llm)
    assert decision.signal.value == "BUY"
    assert decision.confidence == 0.85


@pytest.mark.asyncio
async def test_risk_assessment(mocker, mock_llm):
    from ai_trading_bot.roles import RiskRole, TradeDecision, Signal
    role = RiskRole()
    decision = TradeDecision(symbol="BTC/USD", signal=Signal.BUY, confidence=0.85, reasoning="test")
    result = await role(decision, 67000.0, mock_llm)
    assert result.position_size_pct > 0


@pytest.mark.asyncio
async def test_bot_paper_cycle(mocker, mock_llm, mock_market):
    from ai_trading_bot.bot import AITradingBot
    from ai_trading_bot.config import Config
    with patch("ai_trading_bot.bot.config", Config.from_env()):
        with patch("ai_trading_bot.bot.get_market", return_value=mock_market):
            with patch("ai_trading_bot.bot.get_llm", return_value=mock_llm):
                bot = AITradingBot()
                bot.llm = mock_llm
                trades = await bot.run_once(["BTC/USD"])
                # Should not crash; may or may not produce trades depending on confidence
                assert isinstance(trades, list)
