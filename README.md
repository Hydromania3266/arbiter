# AI Trading Bot 🤖📈

多角色 AI 交易机器人，具备自我学习能力。从模拟盘训练到实盘交易，循序渐进。

## 功能特性

- **5 个 AI 角色协作**
  - 分析师 (Analyst): 分析行情，生成交易信号
  - 风控官 (Risk): 计算仓位、止损止盈
  - 执行员 (Executor): 下单交易
  - 复盘员 (Reviewer): 分析每笔交易得失
  - 改进者 (Improver): 从历史中学习，生成新策略

- **自动新闻采集**
  - CoinTelegraph、Decrypt、The Block 等权威加密货币媒体
  - Reddit 社区热点（如可用）
  - 情感分析辅助决策

- **多交易所支持**
  - 通过 CCXT 支持 Binance、OKX、Bybit 等
  - Paper 模式无需 API Key，Live 模式配置交易所密钥

- **Web Dashboard**
  - 实时查看余额、PnL、胜率
  - 查看近期交易记录
  - 查看学到的策略规则
  - 远程控制启停

- **Telegram 通知**
  - 开仓/平仓通知
  - 止损/止盈触发
  - 新策略学习提醒
  - 错误报警

- **自我进化**
  - 每 N 笔交易后自动复盘
  - 识别重复错误模式
  - 生成改进策略并保存
  - 下次交易自动应用新规则

## 快速开始

### 1. 安装依赖
```bash
cd ai-trading-bot
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
```

### 2. 配置 API Key

编辑 `.env` 文件：
```bash
cp .env.example .env
nano .env
```

需要填写的变量：
| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_API_KEY` | LLM API 密钥 | `freellmapi-xxx` |
| `EXCHANGE_API_KEY` | 交易所 API Key | (实盘需要) |
| `EXCHANGE_SECRET` | 交易所 Secret | (实盘需要) |
| `TELEGRAM_TOKEN` | Telegram Bot Token | (可选) |
| `TELEGRAM_CHAT_ID` | 你的 Chat ID | (可选) |

### 3. 运行

```bash
# 首次运行 - 启动设置向导
python -m src.main setup

# 测试模式 (5个周期，验证功能)
python -m src.main test

# 正式运行 (Paper 模式)
python -m src.main run

# 实盘模式 (需要配置交易所 API)
python -m src.main live
```

### 4. 访问 Dashboard

浏览器打开: `http://localhost:8082`

## 使用 FreeLLMAPI

从你的截图可以看到，FreeLLMAPI 已配置多个免费模型通道：
- Google AI Studio (Gemini)
- Groq (Llama, Mixtral)
- OpenRouter (多模型路由)
- Cloudflare Workers AI
- Agnes AI
- BazaarLink
- 等等

在 `.env` 中设置：
```
LLM_API_BASE=http://127.0.0.1:3001/v1
LLM_API_KEY=你的Unified API Key
ROLE_ANALYST=auto
ROLE_RISK=auto
ROLE_EXECUTOR=auto
ROLE_REVIEWER=auto
ROLE_IMPROVEMENT=auto
```

使用 `auto` 让系统自动选择最优可用的模型。

## 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                     交易循环 (每30秒)                         │
├─────────────────────────────────────────────────────────────┤
│  1. 获取市场数据 ──▶ 获取新闻 ──▶ 情感分析                    │
│         │                                                    │
│         ▼                                                    │
│  2. 分析师决策 ──▶ 风控评估 ──▶ 决定是否执行                  │
│         │                                                    │
│         ▼                                                    │
│  3. 执行员下单 ──▶ 记录交易 ──▶ 监控持仓                      │
│         │                                                    │
│         ▼                                                    │
│  4. 平仓结算 ──▶ 复盘分析 ──▶ 学习改进                        │
└─────────────────────────────────────────────────────────────┘
```

## 纸盘 → 实盘过渡

系统设置了两道安全门槛：
1. **最小交易数**: 至少完成 20 笔纸盘交易
2. **最低胜率**: 胜率需达到 55% 以上

达到条件后 Dashboard 会显示 "LIVE READY"，此时可切换实盘。

## 文件结构

```
ai-trading-bot/
├── pyproject.toml          # 项目配置
├── .env.example            # 环境变量模板
├── README.md
├── config-providers.md     # 各LLM提供商配置指南
├── src/
│   ├── main.py             # 入口
│   └── ai_trading_bot/
│       ├── __init__.py
│       ├── config.py       # 配置管理
│       ├── llm.py          # LLM 客户端
│       ├── news.py         # 新闻采集
│       ├── market.py       # 市场行情 (Paper/Live)
│       ├── roles.py        # 5个AI角色
│       ├── bot.py          # 主循环
│       ├── dashboard.py    # Web UI
│       └── telegram.py     # Telegram 通知
└── tests/
    └── test_bot.py
```

## 安全提示

⚠️ **重要安全建议**:
1. 交易所 API Key 只开启 **交易权限**，**不要开启提现权限**
2. 使用 IP 白名单限制 API 访问
3. 实盘前务必充分测试纸盘模式
4. 设置合理的风险控制参数
5. 本工具仅供学习研究，交易有风险，投资需谨慎

## 许可证

MIT License
