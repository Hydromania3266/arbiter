#!/usr/bin/env bash
set -euo pipefail

# ════════════════════════════════════════════════════════════════════════════════
#  Aegis Trader — Installer & Setup Wizard
#  One-command install for Linux, macOS, Windows (WSL)
# ════════════════════════════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

BOLD='\033[1m'
DIM='\033[2m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.ai-trading-bot}"
VENV_DIR="$INSTALL_DIR/.venv"
DESKTOP_FILE="$HOME/.local/share/applications/ai-trading-bot.desktop"

echo -e "${CYAN}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║         🤖  Aegis Trader — Installer                    ║
║     Autonomous Multi-Agent Trading System                 ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check Python
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VER=$(python3 --version 2>&1 | awk '{print $2}')
        echo -e "${GREEN}✓${NC} Python 3 found: ${PYTHON_VER}"
        return 0
    elif command -v python &> /dev/null; then
        PYTHON_VER=$(python --version 2>&1 | awk '{print $2}')
        echo -e "${GREEN}✓${NC} Python found: ${PYTHON_VER}"
        return 0
    else
        echo -e "${RED}✗${NC} Python 3.11+ required"
        echo "   Install: https://www.python.org/downloads/"
        exit 1
    fi
}

# Check pip/uv
check_pip() {
    if command -v uv &> /dev/null; then
        echo -e "${GREEN}✓${NC} uv found (fast installer)"
        PIP_CMD="uv pip"
        return 0
    elif command -v pip3 &> /dev/null; then
        echo -e "${GREEN}✓${NC} pip3 found"
        PIP_CMD="pip3"
        return 0
    elif command -v pip &> /dev/null; then
        echo -e "${GREEN}✓${NC} pip found"
        PIP_CMD="pip"
        return 0
    else
        echo -e "${YELLOW}!${NC} pip not found, will use python -m pip"
        PIP_CMD="python3 -m pip"
        return 0
    fi
}

# Create virtual environment
create_venv() {
    echo -e "\n${BLUE}→${NC} Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    echo -e "${GREEN}✓${NC} Virtual environment created at ${VENV_DIR}"
}

# Install dependencies
install_deps() {
    echo -e "\n${BLUE}→${NC} Installing dependencies..."
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip first
    python -m pip install --upgrade pip wheel setuptools -q
    
    # Install from pyproject.toml
    $PIP_CMD install -e "$SCRIPT_DIR" -q
    
    echo -e "${GREEN}✓${NC} Dependencies installed"
}

# Interactive setup wizard
setup_wizard() {
    echo -e "\n${CYAN}╔════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     🧙  Setup Wizard — Quick Config    ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════╝${NC}\n"
    
    source "$VENV_DIR/bin/activate"
    
    # Run Python wizard
    python3 << 'PYTHON_WIZARD'
import os
import sys
from pathlib import Path
from getpass import getpass

def ask(prompt, default=None, choices=None, hide=False):
    if choices:
        opts = '/'.join(choices)
        full_prompt = f"{prompt} [{opts}]"
    else:
        full_prompt = prompt
    
    if default:
        full_prompt += f" (default: {default})"
    
    while True:
        try:
            if hide:
                val = getpass(full_prompt + ": ")
            else:
                val = input(full_prompt + ": ")
        except (EOFError, KeyboardInterrupt):
            print("\n")
            sys.exit(0)
        
        if not val and default:
            return default
        if choices and val not in choices:
            print(f"  Choose from: {', '.join(choices)}")
            continue
        return val

def main():
    env_path = Path(".env")
    
    print("Answer a few questions to configure your bot.\n")
    
    # Trading mode
    paper_input = ask("Start in PAPER mode? (y/n)", default="y", choices=["y", "n", "Y", "N"])
    paper = paper_input.lower() == "y"
    
    if not paper:
        print("\n⚠️  WARNING: LIVE MODE = REAL MONEY AT RISK")
        confirm = ask("Are you sure? Type 'yes'", default="no")
        if confirm.lower() != "yes":
            paper = True
            print("Switched to PAPER mode for safety.\n")
        else:
            print("LIVE MODE ENABLED — configure API keys below.\n")
    
    # Exchange
    exchange = ask("Exchange", default="binance", choices=["binance", "kraken", "okx", "bybit", "coinbase"])
    
    # API Keys
    print(f"\n📡 {exchange.upper()} API Configuration")
    print("   Get keys at: https://www.binance.com/en/my/settings/api-management")
    api_key = ask("API Key", hide=True)
    api_secret = ask("API Secret", hide=True)
    
    # Capital & Risk
    print("\n💰 Trading Configuration")
    capital = ask("Initial Capital (USD)", default="10000")
    risk_pct = ask("Risk per Trade (%)", default="1.0")
    
    # Learning targets
    print("\n🎯 Learning Targets (before going live)")
    min_trades = ask("Minimum trades before live", default="20")
    target_wr = ask("Target Win Rate (%)", default="55")
    
    # LLM Provider
    print("\n🧠 LLM Provider")
    print("   Options: openai, groq, deepseek, freellmapi, ollama")
    provider = ask("LLM Provider", default="freellmapi")
    
    if provider == "openai":
        api_base = "https://api.openai.com/v1"
        model = ask("Model", default="gpt-4o-mini")
        llm_key = ask("OpenAI API Key", hide=True)
    elif provider == "groq":
        api_base = "https://api.groq.com/openai/v1"
        model = ask("Model", default="llama-3.3-70b-versatile")
        llm_key = ask("Groq API Key", hide=True)
    elif provider == "deepseek":
        api_base = "https://api.deepseek.com/v1"
        model = ask("Model", default="deepseek-chat")
        llm_key = ask("DeepSeek API Key", hide=True)
    elif provider == "freellmapi":
        api_base = ask("FreeLLMAPI URL", default="http://127.0.0.1:3001/v1")
        model = ask("Model", default="auto")
        llm_key = ask("API Key (if required)", default="", hide=True)
    elif provider == "ollama":
        api_base = ask("Ollama URL", default="http://localhost:11434/v1")
        model = ask("Model", default="llama3.2")
        llm_key = ""
    else:
        api_base = ""
        model = ""
        llm_key = ""
    
    # Telegram (optional)
    print("\n📬 Telegram Notifications (optional)")
    tg_setup = ask("Setup Telegram? (y/n)", default="n", choices=["y", "n", "Y", "N"])
    
    tg_token = ""
    tg_chat = ""
    if tg_setup.lower() == "y":
        print("   1. Open Telegram, search @BotFather")
        print("   2. Send /newbot, follow instructions")
        print("   3. Copy the BOT TOKEN")
        tg_token = ask("Telegram Bot Token", hide=True)
        if tg_token:
            print("   Search @myidbot to get your Chat ID")
            tg_chat = ask("Telegram Chat ID")
    
    # Write .env
    content = f"""# Aegis Trader — Configuration
# Generated by install.sh

# Trading Mode
PAPER_MODE={"true" if paper else "false"}
INITIAL_CAPITAL={capital}
RISK_PERCENT_PER_TRADE={risk_pct}

# Exchange
EXCHANGE_ID={exchange}
EXCHANGE_API_KEY={api_key}
EXCHANGE_SECRET={api_secret}

# Learning
MIN_TRADES_BEFORE_LIVE={min_trades}
TARGET_WIN_RATE={int(target_wr) / 100}

# LLM Provider
LLM_PROVIDER={provider}
LLM_API_BASE={api_base}
LLM_MODEL={model}
LLM_API_KEY={llm_key}

# Telegram (optional)
TELEGRAM_TOKEN={tg_token}
TELEGRAM_CHAT_ID={tg_chat}

# Dashboard
WEB_PORT=8090
"""
    
    env_path.write_text(content)
    print(f"\n{GREEN}✓{NC} Configuration saved to .env")
    
    # Create systemd service (Linux)
    if sys.platform.startswith("linux"):
        setup_systemd(paper)

def setup_systemd(paper):
    """Create systemd user service for auto-start"""
    import subprocess
    from pathlib import Path
    
    service_name = "ai-trading-bot"
    service_file = Path.home() / f".config/systemd/user/{service_name}.service"
    service_file.parent.mkdir(parents=True, exist_ok=True)
    
    script_path = Path(__file__).parent / "src" / "main.py"
    
    content = f"""[Unit]
Description=Aegis Trader
After=network.target

[Service]
Type=simple
WorkingDirectory={Path.cwd()}
Environment="PATH={Path.cwd()}/.venv/bin"
ExecStart={Path.cwd()}/.venv/bin/python -m src.main run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
    
    service_file.write_text(content)
    
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", service_name], check=True, capture_output=True)
        print(f"{GREEN}✓{NC} Systemd service created: {service_name}")
        print(f"   Start: systemctl --user start {service_name}")
        print(f"   Stop:  systemctl --user stop {service_name}")
        print(f"   Logs:  journalctl --user -u {service_name} -f")
    except Exception as e:
        print(f"{YELLOW}!{NC} Systemd setup skipped: {e}")

if __name__ == "__main__":
    main()
PYTHON_WIZARD
}

# Create desktop launcher
create_launcher() {
    echo -e "\n${BLUE}→${NC} Creating desktop launcher..."

    cat > "$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Name=Aegis Trader
Comment=Autonomous Multi-Agent Trading System
Exec=$INSTALL_DIR/.venv/bin/python -m src.main run
Icon=utilities-terminal
Terminal=true
Type=Application
Categories=Finance;Utility;
Keywords=trading;crypto;bot;ai;
DESKTOP

    chmod +x "$DESKTOP_FILE"
    echo -e "${GREEN}✓${NC} Desktop launcher created"
}

# Build Tauri desktop app
build_desktop() {
    echo -e "\n${BLUE}→${NC} Building Tauri desktop app..."

    if ! command -v cargo &> /dev/null; then
        echo -e "${YELLOW}!${NC} Rust/Cargo not found, skipping desktop build"
        echo "   Install Rust: https://rustup.rs/"
        return
    fi

    # Install tauri-cli if needed
    if ! command -v cargo-tauri &> /dev/null; then
        echo -e "${BLUE}→${NC} Installing tauri-cli..."
        cargo install tauri-cli -q
    fi

    cd "$SCRIPT_DIR/src-tauri"
    cargo tauri build 2>&1 || {
        echo -e "${YELLOW}!${NC} Desktop build failed, but web dashboard still works"
        echo "   Install dependencies: sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev"
        cd "$SCRIPT_DIR"
        return
    }
    cd "$SCRIPT_DIR"

    echo -e "${GREEN}✓${NC} Desktop app built"
    echo "   Deb: $SCRIPT_DIR/src-tauri/target/release/bundle/deb/"
    echo "   AppImage: $SCRIPT_DIR/src-tauri/target/release/bundle/appimage/"
}

# Create start script
create_start_script() {
    cat > "$INSTALL_DIR/start.sh" << 'START'
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python -m src.main run
START
    chmod +x "$INSTALL_DIR/start.sh"
}

# Main
main() {
    check_python
    check_pip
    
    echo -e "\n${BLUE}→${NC} Installing to ${INSTALL_DIR}"
    mkdir -p "$INSTALL_DIR"
    
    # Copy files
    echo -e "${BLUE}→${NC} Copying project files..."
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
    
    cd "$INSTALL_DIR"
    
    create_venv
    install_deps
    setup_wizard
    create_start_script
    create_launcher
    build_desktop

    # Add Tauri desktop launcher if app was built
    APPIMAGE_PATH=$(ls "$SCRIPT_DIR/src-tauri/target/release/bundle/appimage/"*_amd64.AppImage 2>/dev/null | head -1)
    if [ -n "$APPIMAGE_PATH" ]; then
        cp "$APPIMAGE_PATH" "$INSTALL_DIR/Aegis_Trader.AppImage"
        chmod +x "$INSTALL_DIR/Aegis_Trader.AppImage"
        
        # Update desktop launcher to use Tauri app
        cat > "$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Name=Aegis Trader
Comment=Autonomous Multi-Agent Trading System
Exec="$INSTALL_DIR/Aegis_Trader.AppImage"
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Finance;Utility;
Keywords=trading;crypto;bot;ai;
DESKTOP
        chmod +x "$DESKTOP_FILE"
        echo -e "${GREEN}✓${NC} Desktop launcher created (Tauri app)"
    fi
    
    echo -e "\n${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        ✅  Installation Complete!        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}\n"
    
    echo -e "${CYAN}Quick Start:${NC}"
    echo "  cd $INSTALL_DIR"
    echo "  source .venv/bin/activate"
    echo "  python -m src.main run"
    echo ""
    echo -e "${CYAN}Or use the launcher:${NC}"
    echo "  $INSTALL_DIR/start.sh"
    echo ""
    echo -e "${CYAN}Or launch the desktop app:${NC}"
    echo "  $INSTALL_DIR/Aegis_Trader.AppImage"
    echo ""
    echo -e "${CYAN}Dashboard:${NC} http://localhost:8090"
    echo ""
    echo -e "${DIM}Uninstall: rm -rf $INSTALL_DIR${NC}"
}

main "$@"
