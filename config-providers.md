# AI Trading Bot — Configurazione API

# Opzione 1: Groq (RAFFONDATA — più veloce, gratis, stabile)
# 1. Vai su https://console.groq.com/keys
# 2. Crea una nuova key (gratis, 30 req/min)
# 3. Modifica queste righe:
LLM_API_BASE=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_XXXXXXXXXXXXXXXXXXXXXXXX
ROLE_ANALYST=llama-3.3-70b-versatile
ROLE_RISK=llama-3.1-8b-instant
ROLE_EXECUTOR=llama-3.3-70b-versatile
ROLE_REVIEWER=llama-3.3-70b-versatile
ROLE_IMPROVEMENT=llama-3.3-70b-versatile

# Opzione 2: DeepSeek (molto economico, ~$0.001/1M tokens)
# 1. Vai su https://platform.deepseek.com/api_keys
# 2. Crea una key
# 3. Modifica queste righe:
# LLM_API_BASE=https://api.deepseek.com/v1
# LLM_API_KEY=sk-XXXXXXXXXXXXXXXXXXXXXXXX
# ROLE_ANALYST=deepseek-chat
# ROLE_RISK=deepseek-chat
# ROLE_EXECUTOR=deepseek-chat
# ROLE_REVIEWER=deepseek-chat
# ROLE_IMPROVEMENT=deepseek-reasoner

# Opzione 3: OpenRouter (conserva tutti i provider, tier gratis)
# 1. Vai su https://openrouter.ai/keys
# 2. Crea una key
# 3. Modifica queste righe:
# LLM_API_BASE=https://openrouter.ai/api/v1
# LLM_API_KEY=pk_or_xxxxxxxxxxxxxxxxx
# ROLE_ANALYST=google/gemini-2.0-flash-001
# ROLE_RISK=mistralai/mistral-small-3.1-24b-instruct
# ROLE_EXECUTOR=deepseek/deepseek-chat
# ROLE_REVIEWER=google/gemini-2.0-flash-001
# ROLE_IMPROVEMENT=deepseek/deepseek-chat

# Il bot userà QUALSIASI opzione tu scelga, basta commentare/decommentare le righe.
# La config attuale usa FreeLLMAPI con router auto (scelge il modello migliore disponibile).
LLM_API_BASE=http://127.0.0.1:3001/v1
LLM_API_KEY=freellmapi-f26f249af5e64368808e830b8b931aacf0ebd5217c4cf310
# Usa "auto" per routing automatico sul modello disponibile, oppure nomi specifici
# se sai quali sono attivi sul tuo proxy.
ROLE_ANALYST=auto
ROLE_RISK=auto
ROLE_EXECUTOR=auto
ROLE_REVIEWER=auto
ROLE_IMPROVEMENT=auto
