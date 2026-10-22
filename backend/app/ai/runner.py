"""Orquestra a análise: monta o pacote, chama uma lente por vez (em paralelo), valida e confere as citações.

Sem veredito global: o resultado é a lista das lentes, cada uma com sua inclinação. Se uma lente falha, as outras
seguem; só quando todas falham a análise inteira vira erro.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from .. import config
from . import client, package as package_mod, prompts, store, verify
from .client import AIError, ChatResult

Chat = Callable[[str, str, dict], ChatResult]


class OutputError(ValueError):
    """A resposta do modelo veio em JSON, mas fora do formato esperado."""


def _strings(value, cap: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:300] for v in value if str(v).strip()][:cap]


def validate_output(obj: dict) -> dict:
    """Valida e normaliza a saída de uma lente. Rígido em inclinação e confiança; tolerante no resto."""
    if obj.get("inclinacao") not in prompts.INCLINACOES:
        raise OutputError(f"inclinacao inválida: {obj.get('inclinacao')!r}")
    if obj.get("confianca") not in prompts.CONFIANCAS:
        raise OutputError(f"confianca inválida: {obj.get('confianca')!r}")
    resumo = str(obj.get("resumo") or "").strip()
    if not resumo:
        raise OutputError("resumo vazio")
    evidences = []
    for ev in obj.get("evidencias") or []:
        if not isinstance(ev, dict) or not str(ev.get("campo", "")).strip():
            continue
        aponta = ev.get("aponta_para")
        evidences.append(
            {
                "campo": str(ev["campo"]).strip(),
                "valor": str(ev.get("valor", "")).strip()[:120],
                "leitura": str(ev.get("leitura", "")).strip()[:300],
                "aponta_para": aponta if aponta in prompts.APONTA else "neutro",
            }
        )
    return {
        "inclinacao": obj["inclinacao"],
        "confianca": obj["confianca"],
        "resumo": resumo[:600],
        "evidencias": evidences[:12],
        "lacunas": _strings(obj.get("lacunas")),
        "mudaria_a_conclusao": _strings(obj.get("mudaria_a_conclusao")),
    }


def run_lens(market: str, lens: prompts.Lens, lens_package: dict, chat: Chat) -> dict:
    started = time.monotonic()
    base = {"lente": lens.id, "titulo": lens.title}
    try:
        res = chat(prompts.system_prompt(market, lens.id), prompts.user_message(lens_package), prompts.LENS_SCHEMA)
        out = validate_output(res.data)
        out["evidencias"] = verify.verify_evidences(lens_package, out["evidencias"])
        checked = [e["verificada"] for e in out["evidencias"]]
        return {
            **base,
            "status": "ok",
            "resultado": out,
            "citacoes": {
                "total": len(checked),
                "conferem": sum(1 for c in checked if c is True),
                "nao_conferem": sum(1 for c in checked if c is False),
            },
            "uso": res.usage,
            "modelo_respondeu": res.model,
            "duracao_ms": int((time.monotonic() - started) * 1000),
        }
    except AIError as exc:
        err = {"tipo": exc.kind, "mensagem": exc.message}
    except OutputError as exc:
        err = {"tipo": "resposta_invalida", "mensagem": f"A resposta do modelo não segue o formato: {exc}."}
    return {**base, "status": "erro", "erro": err, "uso": None, "duracao_ms": int((time.monotonic() - started) * 1000)}


def lens_packages(pkg: dict, lens_ids: list[str]) -> dict[str, dict]:
    """Cada lente recebe só a parte comum e as suas fatias (isolamento: uma não influencia a outra)."""
    common = {k: pkg[k] for k in ("ativo", "saude_dados", "avisos")}
    return {
        lid: {**common, "dados": {s: pkg["fatias"][s] for s in prompts.LENSES[lid].slices if s in pkg["fatias"]}}
        for lid in lens_ids
    }


def analyze(
    market: str,
    symbol: str,
    horizon: int = 10,
    *,
    chat: Chat | None = None,
    build: Callable[..., dict] | None = None,
) -> dict:
    """Roda todas as lentes do mercado. Levanta AIError (sem chave, ou todas as lentes falharam)."""
    if chat is None:
        if not client.configured():
            raise AIError("sem_chave", "Defina OPENROUTER_API_KEY no arquivo .env e reinicie o app.")
        chat = client.chat_json
    started = time.monotonic()

    lens_ids = prompts.MARKET_LENSES[market]
    slices = {s for lid in lens_ids for s in prompts.LENSES[lid].slices}
    pkg = (build or package_mod.build)(market, symbol, horizon, slices)
    per_lens = lens_packages(pkg, lens_ids)

    with ThreadPoolExecutor(max_workers=len(lens_ids)) as pool:
        results = list(pool.map(lambda lid: run_lens(market, prompts.LENSES[lid], per_lens[lid], chat), lens_ids))

    ok = [r for r in results if r["status"] == "ok"]
    if not ok:
        first = results[0]["erro"]
        raise AIError(first["tipo"], first["mensagem"])

    costs = [r["uso"]["cost"] for r in ok if r["uso"] and r["uso"].get("cost") is not None]
    analysis = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": market,
        "symbol": pkg["ativo"]["simbolo"],
        "horizon_days": horizon,
        "prompt_version": prompts.PROMPT_VERSION,
        "prompt_fingerprint": prompts.fingerprint(),
        "model": config.AI_MODEL,
        "effort": config.AI_REASONING_EFFORT or None,
        "lenses": results,
        "cost_usd": round(sum(costs), 6) if costs else None,
        "prompt_tokens": sum((r["uso"] or {}).get("prompt_tokens") or 0 for r in ok),
        "completion_tokens": sum((r["uso"] or {}).get("completion_tokens") or 0 for r in ok),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    analysis["id"] = store.save(analysis, pkg)
    return analysis
