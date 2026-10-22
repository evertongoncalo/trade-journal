"""Configuração por variáveis de ambiente (com .env opcional na raiz do repositório)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _path(env: str, default: str) -> Path:
    p = Path(os.environ.get(env, default))
    return p if p.is_absolute() else ROOT / p


DB_PATH = _path("JOURNAL_DB_PATH", "data/journal.db")

# Análise com IA via OpenRouter (https://openrouter.ai). A chave fica só no .env, nunca no git.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_API_URL = os.environ.get("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions").strip()
AI_MODEL = os.environ.get("AI_MODEL", "anthropic/claude-sonnet-5.5").strip()
# O raciocínio do modelo é cobrado como saída: "low" mantém o custo baixo (vazio = padrão do modelo).
AI_REASONING_EFFORT = os.environ.get("AI_REASONING_EFFORT", "low").strip().lower()
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "6000"))
AI_TIMEOUT_SECONDS = float(os.environ.get("AI_TIMEOUT_SECONDS", "120"))

# Alertas de preço: a vigilância roda dentro do servidor (só vigia com o app ligado).
ALERTS_WATCHER = os.environ.get("ALERTS_WATCHER", "1") != "0"
ALERT_POLL_SECONDS = float(os.environ.get("ALERT_POLL_SECONDS", "60"))
APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8765/")  # aberto ao clicar na notificação
FRONTEND_DIST = _path("FRONTEND_DIST", "frontend/dist")
