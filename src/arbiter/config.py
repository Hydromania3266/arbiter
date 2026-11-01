"""Configuration — all settings loaded from .env + defaults."""

from __future__ import annotations
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class LLMConfig(BaseModel):
    # Works with ANY OpenAI-compatible endpoint (freellmapi, Groq, DeepSeek, OpenRouter…)
    api_base: str = "http://127.0.0.1:3001/v1"
    api_key: str = ""
    default_model: str = "gemini-3.8-flash"
    temperature: float = 0.3
    max_tokens: int = 2048


class RoleConfigs(BaseModel):
    analyst: str = "gemini-3.8-flash"
    risk: str = "glm-5.3-flash"
    executor: str = "qwen3.8-flash"
    reviewer: str = "agnes-2.5-flash"
    improvement: str = "deepseek-v4-flash"  # learns from mistakes


class TradingConfig(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    initial_capital: float = 100_000.0
    risk_percent_per_trade: float = 2.0  # % of capital at risk per trade
    max_positions: int = 5
    min_trades_before_live: int = 20
    target_win_rate: float = 0.55
    stop_loss_pct: float = 5.0
    take_profit_pct: float = 10.0


class LearningConfig(BaseModel):
    enabled: bool = True
    min_trades_before_live: int = 20
    target_win_rate: float = 0.55
    feedback_window: int = 10  # use last N trades for improvement
    improvement_prompt_template: str = (
        "You are a trading strategy improvement engine. "
        "Here are my last {n} trades with outcomes. "
        "Analyze the pattern of mistakes and suggest ONE concrete rule change. "
        "Output JSON: {{\"rule\": \"...\", \"reason\": \"...\", \"expected_impact\": \"...\"}}"
    )


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    roles: RoleConfigs = Field(default_factory=RoleConfigs)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            llm=LLMConfig(
                api_base=os.getenv("LLM_API_BASE", "http://127.0.0.1:3001/v1"),
                api_key=os.getenv("LLM_API_KEY") or os.getenv("FREELLMAPI_KEY", ""),
                default_model=os.getenv("ROLE_ANALYST", "gemini-3.8-flash"),
            ),
            roles=RoleConfigs(
                analyst=os.getenv("ROLE_ANALYST", "gemini-3.8-flash"),
                risk=os.getenv("ROLE_RISK", "glm-5.3-flash"),
                executor=os.getenv("ROLE_EXECUTOR", "qwen3.8-flash"),
                reviewer=os.getenv("ROLE_REVIEWER", "agnes-2.5-flash"),
                improvement=os.getenv("ROLE_IMPROVEMENT", "deepseek-v4-flash"),
            ),
            trading=TradingConfig(
                mode="paper" if os.getenv("PAPER_MODE", "true").lower() in ("true", "1", "paper") else "live",
                initial_capital=float(os.getenv("INITIAL_CAPITAL", "100000")),
                risk_percent_per_trade=float(os.getenv("RISK_PERCENT_PER_TRADE", "2.0")),
                max_positions=int(os.getenv("MAX_POSITIONS", "5")),
                min_trades_before_live=int(os.getenv("MIN_TRADES_BEFORE_LIVE", "20")),
                target_win_rate=float(os.getenv("TARGET_WIN_RATE", "0.55")),
                stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "5.0")),
                take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "10.0")),
            ),
            learning=LearningConfig(
                min_trades_before_live=int(os.getenv("MIN_TRADES_BEFORE_LIVE", "20")),
                target_win_rate=float(os.getenv("TARGET_WIN_RATE", "0.55")),
            ),
        )

    @property
    def is_paper(self) -> bool:
        return self.trading.mode == "paper"


import os  # noqa: E402 — need after Config class
config = Config.from_env()
