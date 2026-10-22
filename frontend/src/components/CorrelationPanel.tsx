import { useCallback, useEffect, useMemo, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { api, type CorrCharts, type CorrelationData, type Market, type PairRow, type PairStatus, type RefreshStatus } from "../api";
import { fmtDate, fmtDateTime, fmtNum, fmtPct } from "../format";
import EChart, { CHART } from "./EChart";
import { Badge, Card, btnGhost, type Tone } from "./ui";

const STATUS_TONE: Record<PairStatus, Tone> = {
  estável: "emerald",
  "sem relação estável": "zinc",
  mecânica: "amber",
  "sem dados": "zinc",
};

const corrCls = (v?: number | null) =>
  v == null ? "text-zinc-500" : v >= 0.3 ? "text-emerald-300" : v <= -0.3 ? "text-rose-300" : "text-zinc-300";
const fmtCorr = (v?: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fmtNum(v, 2)}`);

/** Descolamento de 20 dias contra o que a referência explica. Só faz sentido para relações estáveis. */
function nowText(r: PairRow): string {
  if (r.mechanical) return "mecânica";
  if (r.status !== "estável" || r.z20 == null) return "—";
  const a = Math.abs(r.z20);
  const cls = a < 1 ? "normal" : a < 2 ? "divergência relevante" : "divergência forte";
  return `${cls} (z ${fmtNum(r.z20, 1)})`;
}

function moveText(r: PairRow): string {
  if (r.move20_target == null || r.move20_other == null) return "—";
  return `${fmtNum(r.move20_target, 1)}% × ${fmtNum(r.move20_other, 1)}${r.other_unit === "pts" ? " pts" : "%"}`;
}

export default function CorrelationPanel({ market, symbol }: { market: Market; symbol: string }) {
  const [data, setData] = useState<CorrelationData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [refresh, setRefresh] = useState<RefreshStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await api.correlation(market, symbol);
      setData(d);
      setRefresh(d.refresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [market, symbol]);

  useEffect(() => {
    void load();
  }, [load]);

  // enquanto o universo é baixado, acompanha o andamento e recarrega o painel ao terminar
  useEffect(() => {
    if (refresh?.state !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const s = await api.correlationStatus();
        setRefresh(s.refresh);
        if (s.refresh.state !== "running") {
          window.clearInterval(timer);
          void load();
        }
      } catch {
        /* tenta de novo no próximo ciclo */
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [refresh?.state, load]);

  async function startRefresh() {
    try {
      const r = await api.correlationRefresh();
      setRefresh(r.refresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (loading && !data) return <Card title="Correlações (só código)"><p className="text-sm text-zinc-500">Calculando…</p></Card>;
  if (error && !data) {
    return (
      <Card title="Correlações (só código)">
        <p className="text-sm text-rose-300">{error}</p>
      </Card>
    );
  }
  if (!data) return null;

  const running = refresh?.state === "running";
  const uni = data.universe;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">Correlações e mercado de referência</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge tone="sky">Só código, sem IA</Badge>
            <Badge>Alinhado às 16h de Nova York</Badge>
            <Badge>
              {data.target.observations} dias ({fmtDate(data.target.first)} → {fmtDate(data.target.last)})
            </Badge>
            <Badge tone={uni.state === "ok" ? "zinc" : "amber"}>
              Universo: {uni.symbols}/{uni.expected}
              {uni.updated_at ? ` · atualizado ${fmtDateTime(uni.updated_at)}` : ""}
              {uni.state === "desatualizado" ? " (desatualizado)" : ""}
            </Badge>
          </div>
        </div>
        <button className={btnGhost} onClick={() => void startRefresh()} disabled={running}>
          {running ? `Baixando… ${refresh?.done ?? 0}/${refresh?.total ?? 0}` : "Atualizar universo"}
        </button>
      </div>

      {refresh?.state === "error" && (
        <p className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">
          A atualização do universo falhou: {refresh.error}
        </p>
      )}
      {uni.state === "vazio" && !running && (
        <p className="rounded-md border border-amber-900 bg-amber-950/40 p-3 text-sm text-amber-200">
          O universo de candidatos ainda não foi baixado. Clique em "Atualizar universo" (leva de 1 a 2 minutos; os dados
          ficam guardados localmente). Sem ele só existem os dados do próprio ativo.
        </p>
      )}
      {uni.missing.length > 0 && uni.state !== "vazio" && (
        <p className="text-xs text-zinc-500">Sem dados para: {uni.missing.join(", ")}.</p>
      )}

      {data.parecer && (
        <Card title="Parecer por código">
          <ul className="space-y-1.5 text-sm text-zinc-300">
            {data.parecer.lines.map((line, i) => (
              <li key={i} className={i === data.parecer!.lines.length - 1 ? "text-xs text-zinc-500" : ""}>
                {line}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Referências fixas">
        <FixedTable rows={data.fixed} />
      </Card>

      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Correlações descobertas</h4>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
          Mostrar instáveis e mecânicas
        </label>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data.discovered.map((g) => (
          <GroupCard key={g.name} name={g.name} items={g.items} showAll={showAll} />
        ))}
      </div>
      {data.discovered.length === 0 && uni.state !== "vazio" && (
        <p className="text-sm text-zinc-500">Nenhum candidato com observações suficientes.</p>
      )}

      <Charts charts={data.charts} />

      <p className="text-[11px] text-zinc-600">
        "Estável" = mesmo sinal em ≥ {fmtPct(data.params.stable_share)} das janelas de {data.params.roll_days} dias, correlação
        semanal concordando e |corr| ≥ {fmtNum(data.params.min_abs_corr, 2)}. Correlação de retornos diários, sem prever nada:
        mostra com o que o ativo andou junto, não por quê.
      </p>
    </section>
  );
}

function FixedTable({ rows }: { rows: PairRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-zinc-500">
          <tr>
            <th className="pb-2 font-normal">Referência</th>
            <th className="pb-2 font-normal">Leitura</th>
            <th className="pb-2 text-right font-normal">Corr. total</th>
            <th className="pb-2 text-right font-normal">250d</th>
            <th className="pb-2 text-right font-normal">60d (faixa)</th>
            <th className="pb-2 text-right font-normal">Estab.</th>
            <th className="pb-2 text-right font-normal">Beta</th>
            <th className="pb-2 pl-3 font-normal">20d: ativo × ref.</th>
            <th className="pb-2 font-normal">Descolamento 20d</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td className="py-2 pr-3 font-medium">{r.label}</td>
              <td className="py-2 pr-3">
                <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
              </td>
              <td className={`py-2 text-right tabular-nums ${corrCls(r.corr_full)}`}>{fmtCorr(r.corr_full)}</td>
              <td className="py-2 text-right tabular-nums text-zinc-300">{fmtCorr(r.corr_250)}</td>
              <td className="py-2 text-right tabular-nums text-zinc-300">
                {fmtCorr(r.corr_60)}
                <span className="ml-1 text-xs text-zinc-500">
                  ({fmtCorr(r.roll_min)} a {fmtCorr(r.roll_max)})
                </span>
              </td>
              <td className="py-2 text-right tabular-nums text-zinc-300">{fmtPct(r.stability)}</td>
              <td className="py-2 text-right tabular-nums text-zinc-300">{fmtNum(r.beta, 2)}</td>
              <td className="py-2 pl-3 tabular-nums text-zinc-400">{moveText(r)}</td>
              <td className="py-2 text-xs text-zinc-400">{nowText(r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupCard({ name, items, showAll }: { name: string; items: PairRow[]; showAll: boolean }) {
  const shown = showAll ? items : items.filter((r) => r.status === "estável").slice(0, 3);
  return (
    <Card title={name}>
      {shown.length === 0 ? (
        <p className="text-xs text-zinc-500">Nenhuma correlação estável neste grupo.</p>
      ) : (
        <ul className="space-y-2">
          {shown.map((r) => (
            <li key={r.symbol} className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate">{r.label}</span>
                <span className={`tabular-nums font-medium ${corrCls(r.corr_full)}`}>{fmtCorr(r.corr_full)}</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-zinc-500">
                <span>250d {fmtCorr(r.corr_250)}</span>
                <span>estab. {fmtPct(r.stability)}</span>
                <span>{nowText(r)}</span>
                {showAll && r.status !== "estável" && <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function baseOption(): Record<string, unknown> {
  return {
    backgroundColor: "transparent",
    textStyle: { color: CHART.text },
    grid: { left: 48, right: 16, top: 36, bottom: 28 },
    legend: { top: 0, textStyle: { color: CHART.text } },
  };
}

function axisStyle() {
  return {
    axisLine: { lineStyle: { color: CHART.axis } },
    axisLabel: { color: CHART.text },
    splitLine: { lineStyle: { color: CHART.grid } },
  };
}

function Charts({ charts }: { charts: CorrCharts }) {
  const rebased = useMemo<EChartsCoreOption | null>(() => {
    const c = charts.rebased;
    if (!c) return null;
    return {
      ...baseOption(),
      color: CHART.palette,
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: c.dates, ...axisStyle(), splitLine: { show: false } },
      yAxis: { type: "value", scale: true, ...axisStyle() },
      series: Object.entries(c.series).map(([name, values]) => ({
        name,
        type: "line",
        showSymbol: false,
        data: values,
        lineStyle: { width: name === "Ativo" ? 2.5 : 1.5 },
      })),
    };
  }, [charts.rebased]);

  const rolling = useMemo<EChartsCoreOption | null>(() => {
    const c = charts.rolling;
    if (!c) return null;
    return {
      ...baseOption(),
      color: CHART.palette.slice(1),
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: c.dates, ...axisStyle(), splitLine: { show: false } },
      yAxis: { type: "value", min: -1, max: 1, ...axisStyle() },
      series: Object.entries(c.series).map(([name, values], i) => ({
        name,
        type: "line",
        showSymbol: false,
        data: values,
        lineStyle: { width: 1.8 },
        ...(i === 0
          ? { markLine: { symbol: "none", silent: true, label: { show: false }, data: [{ yAxis: 0 }], lineStyle: { color: CHART.axis } } }
          : {}),
      })),
    };
  }, [charts.rolling]);

  const scatter = useMemo<EChartsCoreOption | null>(() => {
    const c = charts.scatter;
    if (!c) return null;
    const xs = [...c.points, ...c.recent].map((p) => p[0]);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    return {
      ...baseOption(),
      tooltip: { trigger: "item" },
      legend: { top: 0, textStyle: { color: CHART.text }, data: ["Dias", "Últimos 20 dias", "Reta"] },
      xAxis: { type: "value", name: `${c.ref} (%)`, nameTextStyle: { color: CHART.text }, ...axisStyle() },
      yAxis: { type: "value", name: "Ativo (%)", nameTextStyle: { color: CHART.text }, ...axisStyle() },
      series: [
        { name: "Dias", type: "scatter", symbolSize: 4, itemStyle: { color: "#52525b" }, data: c.points },
        { name: "Últimos 20 dias", type: "scatter", symbolSize: 6, itemStyle: { color: "#34d399" }, data: c.recent },
        {
          name: "Reta",
          type: "line",
          showSymbol: false,
          lineStyle: { color: "#fbbf24", width: 1.5 },
          data: [
            [x0, c.slope * x0 + c.intercept],
            [x1, c.slope * x1 + c.intercept],
          ],
        },
      ],
    };
  }, [charts.scatter]);

  if (!rebased && !rolling && !scatter) return null;
  return (
    <div className="grid gap-3 xl:grid-cols-3">
      {rebased && (
        <Card title="Ativo × referências (base 100, 120 dias)">
          <EChart option={rebased} />
        </Card>
      )}
      {rolling && (
        <Card title="Correlação móvel de 60 dias">
          <EChart option={rolling} />
        </Card>
      )}
      {scatter && (
        <Card title="Retornos diários: ativo × primeira referência">
          <EChart option={scatter} />
        </Card>
      )}
    </div>
  );
}
