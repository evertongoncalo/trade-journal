import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, MARKET_LABEL, type Asset, type Draft, type Market, type Probability, type ProbLabel } from "../api";
import CorrelationPanel from "../components/CorrelationPanel";
import TradingViewChart from "../components/TradingViewChart";
import { Badge, Card, btnGhost, btnPrimary, inputCls, Field } from "../components/ui";
import { fmtDate, fmtNum, fmtPct, fmtPrice, roundPrice } from "../format";

const LABEL_TEXT: Record<ProbLabel, string> = {
  alta: "Inclinação para alta",
  baixa: "Inclinação para baixa",
  indistinta: "Sem inclinação distinguível",
  "sem dados": "Sem dados suficientes",
};
const LABEL_TONE = { alta: "emerald", baixa: "rose", indistinta: "zinc", "sem dados": "amber" } as const;
const PLACEHOLDER: Record<Market, string> = { acoes: "NVDA", cripto: "BTCUSDT", forex: "EURUSD ou XAUUSD" };

/** Pedido vindo do scanner para abrir um ativo já analisado. */
export interface AssetRequest {
  market: Market;
  symbol: string;
  setups: string[];
  nonce: number;
}

function draftFrom(a: Asset, setups: string[]): Draft {
  const long = a.snapshot.trend !== "baixa";
  const step = a.snapshot.atr14 ?? a.price * 0.02;
  return {
    market: a.market,
    symbol: a.symbol,
    direction: long ? "alta" : "baixa",
    entry_price: roundPrice(a.price),
    invalidation: roundPrice(long ? a.price - 1.5 * step : a.price + 1.5 * step),
    target: roundPrice(long ? a.price + 3 * step : a.price - 3 * step),
    setup: setups.join(" + ") || undefined,
    snapshot: {
      price: a.price,
      indicators: a.snapshot,
      probability: {
        horizon_days: a.probability.horizon_days,
        state: a.probability.state_label,
        n: a.probability.n,
        p_up: a.probability.p_up,
        ci: a.probability.ci,
        base: a.probability.base,
        label: a.probability.label,
      },
      health: a.health,
    },
  };
}

export default function AssetPage({
  onRegister,
  request,
}: {
  onRegister: (d: Draft) => void;
  request: AssetRequest | null;
}) {
  const [market, setMarket] = useState<Market>("acoes");
  const [symbol, setSymbol] = useState("NVDA");
  const [horizon, setHorizon] = useState(10);
  const [data, setData] = useState<Asset | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [setupNames, setSetupNames] = useState<string[]>([]);

  const analyze = useCallback(async (m: Market, s: string, h: number) => {
    if (!s.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setData(await api.asset(m, s.trim(), h));
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    setSetupNames([]); // busca manual: sem setup de origem
    void analyze(market, symbol, horizon);
  }

  // abre o ativo escolhido no scanner e já analisa
  useEffect(() => {
    if (!request) return;
    setMarket(request.market);
    setSymbol(request.symbol);
    setSetupNames(request.setups);
    void analyze(request.market, request.symbol, horizon);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request, analyze]);

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <Field label="Mercado" className="w-36">
          <select className={inputCls} value={market} onChange={(e) => setMarket(e.target.value as Market)}>
            {(Object.keys(MARKET_LABEL) as Market[]).map((m) => (
              <option key={m} value={m}>
                {MARKET_LABEL[m]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Símbolo" className="w-56">
          <input
            className={inputCls}
            value={symbol}
            placeholder={PLACEHOLDER[market]}
            onChange={(e) => setSymbol(e.target.value)}
          />
        </Field>
        <Field label="Horizonte" className="w-32">
          <select className={inputCls} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            {[5, 10, 20].map((h) => (
              <option key={h} value={h}>
                {h} dias
              </option>
            ))}
          </select>
        </Field>
        <button type="submit" className={btnPrimary} disabled={loading}>
          {loading ? "Analisando…" : "Analisar"}
        </button>
      </form>

      {error && (
        <p className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">{error}</p>
      )}
      {!data && !error && !loading && (
        <p className="text-sm text-zinc-500">
          O caminho principal é o Scanner: ele lista o que bate com os seus setups e abre a ficha daqui. Também dá para
          buscar um ativo à mão: escolha o mercado e o símbolo e clique em Analisar. Tudo aqui é calculado por código, sem IA.
        </p>
      )}
      {setupNames.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
          Veio do scanner:
          {setupNames.map((n) => (
            <Badge key={n} tone="emerald">
              {n}
            </Badge>
          ))}
        </div>
      )}
      {data && <AssetView data={data} onRegister={() => onRegister(draftFrom(data, setupNames))} />}
    </div>
  );
}

function AssetView({ data, onRegister }: { data: Asset; onRegister: () => void }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="text-2xl font-semibold">{data.symbol}</h2>
          <Badge tone="sky">{MARKET_LABEL[data.market]}</Badge>
          <span className="text-xl tabular-nums">{fmtPrice(data.price)}</span>
        </div>
        <button className={btnGhost} onClick={onRegister}>
          Registrar no diário
        </button>
      </div>
      <HealthBar health={data.health} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TradingViewChart symbol={data.tradingview_symbol} />
          <p className="mt-1 text-[11px] text-zinc-600">
            Gráfico do TradingView ({data.tradingview_symbol}); pode diferir um pouco da fonte dos cálculos.
          </p>
        </div>
        <div className="space-y-4">
          <IndicatorsCard data={data} />
          <ProbabilityCard p={data.probability} />
        </div>
      </div>

      <CorrelationPanel key={`${data.market}:${data.symbol}`} market={data.market} symbol={data.symbol} />
    </div>
  );
}

function HealthBar({ health }: { health: Asset["health"] }) {
  const d = health.daily;
  const i = health.intraday;
  const note = d.note || i?.note;
  return (
    <div className="flex flex-wrap gap-2">
      <Badge tone="sky">
        Fonte: {d.source} ({d.symbol_at_source})
      </Badge>
      <Badge>Diário até {fmtDate(d.last_bar_utc)}</Badge>
      {i ? (
        <Badge tone={(i.last_bar_age_minutes ?? 0) > 120 ? "amber" : "zinc"}>
          1h: barra aberta há {fmtNum(i.last_bar_age_minutes, 0)} min
          {(i.last_bar_age_minutes ?? 0) > 120 ? " (mercado pode estar fechado)" : ""}
        </Badge>
      ) : (
        <Badge tone="amber">Sem dado intradiário</Badge>
      )}
      {note && <Badge tone="amber">{note}</Badge>}
    </div>
  );
}

function IndicatorsCard({ data }: { data: Asset }) {
  const s = data.snapshot;
  const rows: [string, string, string?][] = [
    ["RSI (14, Wilder)", fmtNum(s.rsi14, 1), s.rsi14 == null ? undefined : s.rsi14 > 65 ? "alto" : s.rsi14 < 35 ? "baixo" : "neutro"],
    ["MACD − sinal", fmtNum(s.macd_hist, 4), s.macd_hist == null ? undefined : s.macd_hist > 0 ? "acima do sinal" : "abaixo do sinal"],
    ["MM20 / MM50", `${fmtPrice(s.sma20)} / ${fmtPrice(s.sma50)}`],
    ["MM200", fmtPrice(s.sma200)],
    ["ATR (14)", `${fmtPrice(s.atr14)} (${fmtNum(s.atr_pct, 2)}%)`],
    ["Bollinger %B", fmtNum(s.bb_pctb, 2)],
    ["Tendência", s.trend],
    ["Volume relativo (20)", s.volume_ratio == null ? "sem volume" : `${fmtNum(s.volume_ratio, 2)}×`],
  ];
  return (
    <Card title="Indicadores (diário)">
      <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-sm">
        {rows.map(([k, v, hint]) => (
          <div key={k} className="contents">
            <dt className="text-zinc-400">{k}</dt>
            <dd className="text-right tabular-nums">
              {v} {hint && <span className="text-xs text-zinc-500">· {hint}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function ProbabilityCard({ p }: { p: Probability }) {
  return (
    <Card title={`Inclinação provável em ${p.horizon_days} dias`}>
      <Badge tone={LABEL_TONE[p.label]}>{LABEL_TEXT[p.label]}</Badge>
      <p className="mt-2 text-xs text-zinc-400">{p.state_label ?? "—"}</p>
      <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-sm">
        <dt className="text-zinc-400">P(alta | estado)</dt>
        <dd className="text-right tabular-nums">
          {fmtPct(p.p_up)}{" "}
          {p.ci && (
            <span className="text-xs text-zinc-500">
              (IC95 {fmtPct(p.ci[0])}–{fmtPct(p.ci[1])})
            </span>
          )}
        </dd>
        <dt className="text-zinc-400">Base do ativo</dt>
        <dd className="text-right tabular-nums">{fmtPct(p.base)}</dd>
        <dt className="text-zinc-400">Diferença</dt>
        <dd className="text-right tabular-nums">
          {p.lift_pp == null ? "—" : `${p.lift_pp > 0 ? "+" : ""}${fmtNum(p.lift_pp, 1)} pp`}
        </dd>
        <dt className="text-zinc-400">Ocorrências (sem sobreposição)</dt>
        <dd className="text-right tabular-nums">{p.n}</dd>
      </dl>
      <p className="mt-3 text-xs text-zinc-500">{p.reason}</p>

      <details className="mt-3 text-xs">
        <summary className="cursor-pointer text-zinc-400">Todos os estados ({p.all_states.length})</summary>
        <table className="mt-2 w-full text-left">
          <thead className="text-zinc-500">
            <tr>
              <th className="pb-1 font-normal">Estado</th>
              <th className="pb-1 text-right font-normal">n</th>
              <th className="pb-1 text-right font-normal">P(alta)</th>
            </tr>
          </thead>
          <tbody>
            {p.all_states.map((r) => (
              <tr key={r.state_label} className={r.is_current ? "text-emerald-300" : "text-zinc-400"}>
                <td className="py-0.5 pr-2">{r.state_label}</td>
                <td className="py-0.5 text-right tabular-nums">{r.n}</td>
                <td className="py-0.5 text-right tabular-nums">{r.label === "sem dados" ? "—" : fmtPct(r.p_up)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      <p className="mt-2 text-[11px] text-zinc-600">
        Histórico desde {p.history_start ?? "—"} ({p.history_bars} barras diárias). Frequência histórica, não garantia; o
        intervalo assume amostras independentes.
      </p>
    </Card>
  );
}
