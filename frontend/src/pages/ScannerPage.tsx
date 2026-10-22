import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  MARKET_LABEL,
  type ConditionSpec,
  type Market,
  type ScanHit,
  type ScanRun,
  type ScanStatus,
  type Setup,
} from "../api";
import SetupsPanel from "../components/SetupsPanel";
import { Badge, Card, btnGhost, btnPrimary, inputSm, type Tone } from "../components/ui";
import { fmtDate, fmtDateTime, fmtNum, fmtPrice } from "../format";

const MARKETS = Object.keys(MARKET_LABEL) as Market[];
const PAGE = 60;

type SortKey = "conf" | "rsi_asc" | "rsi_desc" | "vol" | "symbol";
const SORT_LABEL: Record<SortKey, string> = {
  conf: "Mais confirmações",
  rsi_asc: "RSI crescente",
  rsi_desc: "RSI decrescente",
  vol: "Volume relativo",
  symbol: "Símbolo",
};
const TREND_TONE: Record<string, Tone> = { alta: "emerald", baixa: "rose", lateral: "zinc" };

interface Row {
  key: string;
  market: Market;
  symbol: string;
  name: string | null;
  details: ScanHit["details"];
  hits: ScanHit[];
  best: number;
  opened: boolean;
}

export default function ScannerPage({ onOpen }: { onOpen: (market: Market, symbol: string, setups: string[]) => void }) {
  const [latest, setLatest] = useState<{ run: ScanRun | null; hits: ScanHit[] } | null>(null);
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [catalog, setCatalog] = useState<ConditionSpec[]>([]);
  const [setups, setSetups] = useState<Setup[]>([]);
  const [markets, setMarkets] = useState<Market[]>([...MARKETS]);
  const [error, setError] = useState<string | null>(null);

  const [marketFilter, setMarketFilter] = useState<Market | "todos">("todos");
  const [setupFilter, setSetupFilter] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("conf");
  const [limit, setLimit] = useState(PAGE);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [showSetups, setShowSetups] = useState(false);

  const loadLatest = useCallback(async () => setLatest(await api.scannerLatest()), []);
  const loadSetups = useCallback(async () => setSetups(await api.scannerSetups()), []);

  useEffect(() => {
    Promise.all([loadLatest(), loadSetups(), api.scannerCatalog().then(setCatalog), api.scannerStatus().then(setStatus)]).catch(
      (err) => setError(err instanceof Error ? err.message : String(err)),
    );
  }, [loadLatest, loadSetups]);

  // enquanto roda, acompanha o andamento e recarrega o resultado ao terminar
  useEffect(() => {
    if (status?.state !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const s = await api.scannerStatus();
        setStatus(s);
        if (s.state !== "running") {
          window.clearInterval(timer);
          await loadLatest();
        }
      } catch {
        /* tenta de novo no próximo ciclo */
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [status?.state, loadLatest]);

  async function run() {
    setError(null);
    try {
      setStatus((await api.scannerRun(markets)).status);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const toggleMarket = (m: Market) =>
    setMarkets((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]));
  const toggleSetup = (name: string) => {
    setLimit(PAGE);
    setSetupFilter((cur) => (cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name]));
  };

  const hits = latest?.hits ?? [];
  const setupNames = useMemo(() => [...new Set(hits.map((h) => h.setup_name))], [hits]);
  const marketCounts = useMemo(() => {
    const seen: Record<string, Set<string>> = { acoes: new Set(), cripto: new Set(), forex: new Set() };
    for (const h of hits) seen[h.market].add(h.symbol);
    return seen;
  }, [hits]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const map = new Map<string, Row>();
    for (const h of hits) {
      if (marketFilter !== "todos" && h.market !== marketFilter) continue;
      if (setupFilter.length > 0 && !setupFilter.includes(h.setup_name)) continue;
      if (q && !h.symbol.toLowerCase().includes(q) && !(h.name ?? "").toLowerCase().includes(q)) continue;
      const key = `${h.market}:${h.symbol}`;
      let r = map.get(key);
      if (!r) {
        r = { key, market: h.market, symbol: h.symbol, name: h.name, details: h.details, hits: [], best: 0, opened: false };
        map.set(key, r);
      }
      r.hits.push(h);
      r.best = Math.max(r.best, h.details.confirmations.length);
      r.opened = r.opened || h.opened_at != null;
    }
    const list = [...map.values()];
    const bySymbol = (a: Row, b: Row) => a.symbol.localeCompare(b.symbol);
    const cmp: Record<SortKey, (a: Row, b: Row) => number> = {
      conf: (a, b) => b.best - a.best || b.hits.length - a.hits.length || bySymbol(a, b),
      rsi_asc: (a, b) => (a.details.rsi14 ?? 999) - (b.details.rsi14 ?? 999) || bySymbol(a, b),
      rsi_desc: (a, b) => (b.details.rsi14 ?? -1) - (a.details.rsi14 ?? -1) || bySymbol(a, b),
      vol: (a, b) => (b.details.volume_ratio ?? -1) - (a.details.volume_ratio ?? -1) || bySymbol(a, b),
      symbol: bySymbol,
    };
    return list.sort(cmp[sort]);
  }, [hits, marketFilter, setupFilter, query, sort]);

  function open(r: Row) {
    r.hits.forEach((h) => void api.hitOpened(h.id).catch(() => undefined));
    setLatest((cur) =>
      cur
        ? {
            ...cur,
            hits: cur.hits.map((h) =>
              h.market === r.market && h.symbol === r.symbol ? { ...h, opened_at: h.opened_at ?? new Date().toISOString() } : h,
            ),
          }
        : cur,
    );
    onOpen(r.market, r.symbol, r.hits.map((h) => h.setup_name));
  }

  const running = status?.state === "running";
  const pct = status && status.total > 0 ? Math.round((status.done / status.total) * 100) : 0;
  const run_ = latest?.run ?? null;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <h2 className="text-lg font-semibold">Scanner</h2>
            <p className="mt-1 text-xs text-zinc-500">
              Varre o universo inteiro atrás dos seus setups (timeframe diário, só barras já fechadas) e lista o que encontrou.
              Ações: S&P 500 + Nasdaq-100 · Cripto: as mais líquidas da Binance · Forex: majors, minors e ouro.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex gap-3 text-xs text-zinc-400">
              {MARKETS.map((m) => (
                <label key={m} className="flex items-center gap-1">
                  <input type="checkbox" checked={markets.includes(m)} onChange={() => toggleMarket(m)} disabled={running} />
                  {MARKET_LABEL[m]}
                </label>
              ))}
            </div>
            <button className={btnPrimary} onClick={() => void run()} disabled={running || markets.length === 0}>
              {running ? "Varrendo…" : "Rodar scanner"}
            </button>
          </div>
        </div>

        {running && status && (
          <div className="mt-4">
            <div className="mb-1 flex justify-between text-xs text-zinc-400">
              <span>{status.phase}</span>
              <span className="tabular-nums">
                {status.done}/{status.total} ({pct}%)
              </span>
            </div>
            <div className="h-2 rounded bg-zinc-800">
              <div className="h-2 rounded bg-emerald-600 transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
        {status?.state === "error" && (
          <p className="mt-3 rounded-md border border-rose-900 bg-rose-950/50 p-2 text-sm text-rose-300">
            A varredura falhou: {status.error}
          </p>
        )}
        {error && <p className="mt-3 rounded-md border border-rose-900 bg-rose-950/50 p-2 text-sm text-rose-300">{error}</p>}

        {run_ && (
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <Badge tone="sky">Varredura #{run_.id}</Badge>
            <Badge>concluída {fmtDateTime(run_.finished_at)}</Badge>
            <Badge>
              {run_.symbols_ok}/{run_.symbols_total} ativos avaliados
            </Badge>
            {Object.entries(run_.as_of).map(([m, d]) => (
              <Badge key={m}>
                {MARKET_LABEL[m as Market]}: barra de {fmtDate(d)}
              </Badge>
            ))}
            {run_.errors_count > 0 && (
              <button className="text-amber-300 hover:underline" onClick={() => setShowErrors((v) => !v)}>
                {run_.errors_count} {run_.errors_count === 1 ? "falha" : "falhas"} {showErrors ? "▲" : "▼"}
              </button>
            )}
          </div>
        )}
        {showErrors && run_?.errors && (
          <ul className="mt-2 space-y-0.5 text-xs text-zinc-500">
            {Object.entries(run_.errors).map(([k, v]) => (
              <li key={k}>
                <span className="text-zinc-400">{k.replace(":", " · ")}</span>: {v}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
          Encontrados {latest?.run ? `(${rows.length} ativos)` : ""}
        </h3>
        <button className="text-xs text-sky-400 hover:underline" onClick={() => setShowSetups((v) => !v)}>
          {showSetups ? "Ocultar setups" : `Setups (${setups.filter((s) => s.enabled).length} ativos)`}
        </button>
      </div>

      {showSetups && <SetupsPanel setups={setups} catalog={catalog} onChanged={() => void loadSetups()} />}

      {!latest && !error && <p className="text-sm text-zinc-500">Carregando…</p>}
      {latest && !latest.run && !running && (
        <p className="text-sm text-zinc-500">
          Nenhuma varredura concluída ainda. Clique em "Rodar scanner" (leva cerca de 1 a 2 minutos para o universo inteiro).
        </p>
      )}

      {latest?.run && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {(["todos", ...MARKETS] as const).map((m) => (
              <button
                key={m}
                onClick={() => {
                  setMarketFilter(m);
                  setLimit(PAGE);
                }}
                className={`rounded-full border px-3 py-1 text-xs ${
                  marketFilter === m ? "border-emerald-700 bg-emerald-950 text-emerald-300" : "border-zinc-700 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {m === "todos" ? "Todos" : MARKET_LABEL[m]}{" "}
                <span className="tabular-nums text-zinc-500">
                  {m === "todos" ? new Set(hits.map((h) => `${h.market}:${h.symbol}`)).size : marketCounts[m].size}
                </span>
              </button>
            ))}
            <span className="mx-1 h-4 w-px bg-zinc-700" />
            {setupNames.map((n) => (
              <button
                key={n}
                onClick={() => toggleSetup(n)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  setupFilter.includes(n) ? "border-sky-700 bg-sky-950 text-sky-300" : "border-zinc-700 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {n}
              </button>
            ))}
            <span className="ml-auto flex items-center gap-2">
              <input
                className={`${inputSm} w-36`}
                placeholder="Buscar ativo…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setLimit(PAGE);
                }}
              />
              <select className={inputSm} value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => (
                  <option key={k} value={k}>
                    {SORT_LABEL[k]}
                  </option>
                ))}
              </select>
            </span>
          </div>

          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-900 text-xs uppercase text-zinc-500">
                <tr>
                  <th className="px-3 py-2">Ativo</th>
                  <th className="px-3 py-2">Setups</th>
                  <th className="px-3 py-2 text-right">Preço</th>
                  <th className="px-3 py-2 text-right">RSI</th>
                  <th className="px-3 py-2">Tendência</th>
                  <th className="px-3 py-2 text-right">Vol. rel.</th>
                  <th className="px-3 py-2 text-right">Confirm.</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-6 text-center text-zinc-500">
                      Nenhum ativo com esses filtros.
                    </td>
                  </tr>
                )}
                {rows.slice(0, limit).map((r) => (
                  <Fragment key={r.key}>
                    <tr className="cursor-pointer align-top hover:bg-zinc-900/60" onClick={() => setExpanded(expanded === r.key ? null : r.key)}>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2 font-medium">
                          {r.symbol}
                          {r.opened && <span title="Já aberto" className="h-1.5 w-1.5 rounded-full bg-sky-400" />}
                        </div>
                        <div className="max-w-[16rem] truncate text-xs text-zinc-500">
                          {MARKET_LABEL[r.market]}
                          {r.name ? ` · ${r.name}` : ""}
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {r.hits.map((h) => (
                            <Badge key={h.id} tone={h.direction === "alta" ? "emerald" : "rose"}>
                              {h.setup_name}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtPrice(r.details.price)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtNum(r.details.rsi14, 1)}</td>
                      <td className="px-3 py-2">
                        <Badge tone={TREND_TONE[r.details.trend] ?? "zinc"}>{r.details.trend}</Badge>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {r.details.volume_ratio == null ? "—" : `${fmtNum(r.details.volume_ratio, 2)}×`}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {r.best}/{Math.max(...r.hits.map((h) => h.details.confirmations_applicable))}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          className={btnGhost}
                          onClick={(e) => {
                            e.stopPropagation();
                            open(r);
                          }}
                        >
                          Abrir
                        </button>
                      </td>
                    </tr>
                    {expanded === r.key && (
                      <tr className="bg-zinc-900/40">
                        <td colSpan={8} className="px-3 py-3">
                          <div className="grid gap-3 md:grid-cols-2">
                            {r.hits.map((h) => (
                              <div key={h.id} className="text-xs">
                                <div className="mb-1 font-medium text-zinc-300">{h.setup_name}</div>
                                <ul className="space-y-0.5 text-zinc-400">
                                  {h.details.required.map((c) => (
                                    <li key={c}>✓ {c}</li>
                                  ))}
                                  {h.details.confirmations.map((c) => (
                                    <li key={c} className="text-emerald-300">
                                      ✓ {c} <span className="text-zinc-500">(confirmação)</span>
                                    </li>
                                  ))}
                                  {h.details.not_applicable.map((c) => (
                                    <li key={c} className="text-zinc-600">
                                      – {c} (não se aplica a este mercado)
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ))}
                          </div>
                          <div className="mt-2 text-[11px] text-zinc-600">
                            Dados até {fmtDate(r.details.as_of)} · ATR {fmtNum(r.details.atr_pct, 2)}% · Bollinger %B {fmtNum(r.details.bb_pctb, 2)} ·
                            histograma do MACD {fmtNum(r.details.macd_hist, 4)}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > limit && (
            <button className={btnGhost} onClick={() => setLimit((l) => l + PAGE)}>
              Mostrar mais ({rows.length - limit} restantes)
            </button>
          )}
          <p className="text-[11px] text-zinc-600">
            A lista mostra o que bateu com as condições dos setups, sem nota nem ranking de qualidade. Setups largos listam muita
            coisa: aperte as condições em "Setups" ou use os filtros acima. Abrir um ativo leva à ficha completa.
          </p>
        </>
      )}
    </div>
  );
}
