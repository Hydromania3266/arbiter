# Arbiter

Autonomous AI-powered trading bot with multi-role agents, live dashboard, and self-updating desktop app.

## Features

- **8 AI agent roles** working in a pipeline: News → Sentiment → Market → Analyst → Risk → Executor → Reviewer → Improver
- **Free LLM routing** via FreeLLMAPI (localhost:3001) — no paid API keys required
- **Paper trading first**, live trading unlocked at 20 trades + 55% win rate
- **Live dashboard** on port 8090 with WebSocket real-time updates
- **Self-updating desktop app** (Tauri + GitHub Releases + signature verification)
- **One-command installer**: `./install.sh` → wizard → venv → build desktop app
- **Tauri desktop app** distributes as AppImage + deb, with auto-update checking on launch

## Architecture

```
frontend/index.html           → Dashboard UI (Tauri embedded)
src-tauri/                    → Tauri 2.x Rust wrapper
  - updater plugin            → Checks GitHub Releases for new versions
  - shell plugin              → Spawns bot subprocess, kills on close
src/arbiter/                  → Python bot engine
  - bot.py                   → Main loop, wires loggers to dashboard
  - dashboard.py             → FastAPI app, /api/* endpoints, /ws
  - config.py                → Env-driven configuration
  - roles.py                 → Agent role definitions
  - news.py / market.py / llm.py / activity.py / terminal.py / telegram.py
install.sh                    → One-command installer with setup wizard
.github/workflows/            → CI/CD (tests + signed releases)
```

## Quick Start

```bash
# Clone and install
git clone https://github.com/fidellabs/arbiter.git
cd arbiter
./install.sh

# Open the dashboard in browser
http://localhost:8090

# Or launch the desktop app (auto-checks for updates on startup)
~/.arbiter/Arbiter.AppImage
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

## Auto-Update System

Arbiter checks for updates on startup and shows a badge when a new version is available:

1. **On launch**: Tauri queries the latest GitHub Release
2. **Badge shown**: "🔄 Update" button appears in the header
3. **Click to view**: Shows changelog and version notes
4. **Install**: Downloads and verifies signature, then restarts the app

### CI/CD Release Process

Push a git tag to trigger a release:

```bash
git tag v0.2.0
git push origin v0.2.0
```

GitHub Actions will:
1. Run tests
2. Build the Tauri app (AppImage + deb)
3. Sign artifacts with the Tauri signing key
4. Generate `latest.json` for the updater
5. Publish a GitHub Release with all artifacts

### Adding a New Release

The release workflow expects these secrets:
- `TAURI_SIGNING_PRIVATE_KEY`: Your Minisign private key
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`: Key password

Get your signing key (first-time setup):
```bash
cd src-tauri && cargo tauri signer generate --password "your-password"
```

Save the private key to GitHub Secrets. The public key is embedded in `tauri.conf.json`.

## Local Development

```bash
# Start bot + dashboard (port 8090)
python -m src.main run

# Or with the installer
cd ~/.arbiter
source .venv/bin/activate
python -m src.main run
```

## License

MIT