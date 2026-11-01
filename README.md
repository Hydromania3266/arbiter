# Aegis Trader

An open-source, AI-powered autonomous trading bot with multi-role agents,
a web dashboard, a Tauri desktop app, and a one-command installer.

## Features

- **6 AI roles** working in a pipeline:
  - **News**: Scrapes CoinTelegraph, Decrypt, The Block, Reddit for market events
  - **Sentiment**: Analyzes news sentiment to bias direction
  - **Market**: Fetches real-time klines, order books, trades from Binance
  - **Analyst**: Combines all signals into a directional trade call
  - **Risk**: Computes position size, stop-loss, take-profit
  - **Executor**: Places the order (paper or live)
  - **Reviewer**: Reviews every closed trade
  - **Improver**: Learns from history, generates new strategy rules
- **Free LLM routing**: Uses FreeLLMAPI at `localhost:3001` with `auto` model routing
- **Paper trading first, live at 20 trades @ 55% win rate** — safety-gated
- **Web Dashboard** on port 8090:
  - Horizontal agent pipeline with clickable inspection
  - Live stats: avg duration, best/worst trade, avg win/loss, profit factor, W/L count
  - Terminal log, agent facecards, news feed
  - Settings panel with capital control, stop-loss, take-profit
  - WebSocket live feed for real-time updates
- **Tauri desktop app** (AppImage + deb) with embedded dashboard — offline-ready
- **One-command installer**: `./install.sh` runs a wizard, sets up venv, builds the desktop app
- **Telegram notifications** for open/close events
- **Configurable**: capital, stop-loss %, take-profit %, live thresholds via `.env`

## Quick Start

```bash
# Clone and install
git clone https://github.com/fidellabs/aegis-trader.git
cd aegis-trader
./install.sh

# Open the dashboard
http://localhost:8090

# Or launch the desktop app
~/.ai-trading-bot/Aegis_Trader.AppImage
```

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Description |
|----------|---------|-------------|
| `INITIAL_CAPITAL` | 100000 | Starting capital in quote currency |
| `PAPER_MODE` | true | `true` for paper, `false` for live |
| `STOP_LOSS_PCT` | 1.5 | Stop loss percentage |
| `TAKE_PROFIT_PCT` | 3.0 | Take profit percentage |
| `MIN_TRADES_BEFORE_LIVE` | 20 | Minimum trades before live mode |
| `TARGET_WIN_RATE` | 0.55 | Win rate threshold for live mode |
| `FREE_LLM_API_BASE` | http://localhost:3001 | FreeLLMAPI base URL |
| `FREE_LLM_API_KEY` | — | FreeLLMAPI API key |

## Architecture

```
frontend/index.html     → Tauri embedded dashboard (single-file HTML)
src-tauri/              → Tauri 2.x Rust wrapper (attach-or-spawn bot)
src/ai_trading_bot/     → Python bot (FastAPI dashboard + agent pipeline)
  - bot.py             → Main loop, wires loggers to dashboard
  - dashboard.py       → FastAPI app, /api/* endpoints, /ws
  - config.py          → Env-driven configuration
  - roles.py           → Agent role definitions
  - news.py            → News scraper + sentiment
  - market.py          → Binance market data
  - llm.py             → FreeLLMAPI client
  - activity.py        → Activity feed
  - terminal.py        → Terminal log handler
  - telegram.py        → Telegram notifications
install.sh              → One-command installer with setup wizard
```

## Dashboard Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Bot status, trades, PnL, running flag |
| GET | `/api/trades` | Recent trade history |
| GET | `/api/activities` | Agent activity feed |
| GET | `/api/news` | Latest news with sentiment |
| POST | `/api/restart` | Restart the bot |
| POST | `/api/stop` | Stop the bot |
| POST | `/api/resume` | Resume the bot |
| WS | `/ws` | WebSocket live feed |

## License

MIT