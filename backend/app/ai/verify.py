"""Confere as citações da IA contra o pacote que ela recebeu.

Cada evidência cita um `campo` (caminho com pontos) e um `valor`. Aqui o código resolve o caminho no pacote e compara.
Resultado por evidência: verificada True (confere), False (o campo não existe ou o valor não bate) ou None (não dá
para comparar). É a defesa contra citação inventada: a tela marca as que não conferem.
"""
from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
_NUMBER = re.compile(r"[-+]?\d[\d.,]*")


def resolve(package: dict, path: str) -> tuple[bool, object]:
    """(existe, valor) para um caminho como `dados.indicadores.valores.rsi14` ou `a.b[2][0]`."""
    if not isinstance(path, str) or not path.strip():
        return False, None
    cur: object = package
    for name, idx in _TOKEN.findall(path.strip()):
        if name:
            if not isinstance(cur, dict) or name not in cur:
                return False, None
            cur = cur[name]
        else:
            i = int(idx)
            if not isinstance(cur, list) or i >= len(cur):
                return False, None
            cur = cur[i]
    return True, cur


def parse_number(text: str) -> float | None:
    """Primeiro número de um texto como '62%', '1,23×' ou '1.234,5' (vírgula ou ponto decimal)."""
    m = _NUMBER.search(str(text).replace(" ", ""))
    if not m:
        return None
    t = m.group(0).rstrip(".,")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0.02, abs_tol=0.05)


def check(package: dict, campo: str, valor: str) -> tuple[bool | None, str]:
    found, resolved = resolve(package, campo)
    if not found:
        return False, "o campo citado não existe no pacote"
    if isinstance(resolved, (dict, list)):
        return None, "o campo citado é um grupo de dados, não um valor"
    if resolved is None:
        return False, "o campo existe, mas está vazio (null) no pacote"
    if isinstance(resolved, bool):
        ok = str(resolved).lower() in str(valor).lower()
        return ok, "" if ok else "o valor citado não bate com o do pacote"
    if isinstance(resolved, (int, float)):
        cited = parse_number(valor)
        if cited is None:
            return False, "o valor citado não é um número"
        ok = _close(cited, float(resolved)) or _close(cited / 100, float(resolved)) or _close(cited, float(resolved) * 100)
        return ok, "" if ok else f"o pacote tem {resolved}, a citação diz {valor}"
    ok = str(resolved).strip().lower() in str(valor).strip().lower() or str(valor).strip().lower() in str(resolved).lower()
    return ok, "" if ok else f"o pacote tem '{resolved}', a citação diz '{valor}'"


def verify_evidences(package: dict, evidences: list[dict]) -> list[dict]:
    out = []
    for ev in evidences:
        ok, why = check(package, ev.get("campo", ""), ev.get("valor", ""))
        out.append({**ev, "verificada": ok, "motivo_da_verificacao": why})
    return out
