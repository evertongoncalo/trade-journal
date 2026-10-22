"""Atualiza as listas de ações: S&P 500 (Wikipedia) e Nasdaq-100 (API pública da Nasdaq).

Uso (na pasta backend):  .venv\\Scripts\\python scripts\\update_universes.py
Requer lxml (requirements-dev.txt). As listas ficam em app/scanner/data/ e são versionadas no git.
"""
from __future__ import annotations

import io
import json
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "app" / "scanner" / "data"
UA = {"User-Agent": "Mozilla/5.0 (trade-journal universe updater)"}


def tables(url: str) -> list[pd.DataFrame]:
    html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8")
    return pd.read_html(io.StringIO(html))


def nasdaq100_rows() -> list[dict]:
    """Componentes do Nasdaq-100 pela API pública da própria Nasdaq (a Wikipedia mudou o formato da página)."""
    req = urllib.request.Request(
        "https://api.nasdaq.com/api/quote/list-type/nasdaq100", headers={**UA, "Accept": "application/json"}
    )
    rows = json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]["data"]["rows"]
    if len(rows) < 90:
        raise SystemExit(f"Nasdaq-100 veio com só {len(rows)} linhas")
    return rows


def pick(tbls: list[pd.DataFrame], column: str, min_rows: int) -> pd.DataFrame:
    for t in tbls:
        if column in t.columns and len(t) >= min_rows:
            return t
    raise SystemExit(f"Tabela com a coluna {column!r} e >= {min_rows} linhas não encontrada")


def yahoo(sym: str) -> str:
    return str(sym).strip().replace(".", "-")  # BRK.B -> BRK-B


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    sp = pick(tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"), "Symbol", 400)
    sp_out = pd.DataFrame({"symbol": sp["Symbol"].map(yahoo), "name": sp["Security"], "sector": sp["GICS Sector"]})
    sp_out.to_csv(OUT / "sp500.csv", index=False)

    nd_rows = nasdaq100_rows()
    nd_out = pd.DataFrame(
        {"symbol": [yahoo(r["symbol"]) for r in nd_rows], "name": [r["companyName"] for r in nd_rows]}
    )
    nd_out.to_csv(OUT / "nasdaq100.csv", index=False)

    (OUT / "README.txt").write_text(
        f"Listas geradas em {date.today().isoformat()} por scripts/update_universes.py "
        "(S&P 500: Wikipedia; Nasdaq-100: API pública da Nasdaq).\n"
        "Atualize de tempos em tempos: a composição dos índices muda.\n",
        encoding="utf-8",
    )
    both = set(sp_out["symbol"]) | set(nd_out["symbol"])
    print(f"S&P 500: {len(sp_out)} | Nasdaq-100: {len(nd_out)} | união: {len(both)}")


if __name__ == "__main__":
    main()
