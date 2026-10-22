import type { ReviewCell, ReviewRate } from "../api";
import { fmtPct } from "../format";

const SAMPLE_TEXT = { insuficiente: "n < 10: não diz nada", pequena: "amostra pequena", ok: "n ≥ 30" } as const;

/** Taxa com o intervalo de 95% numa escala de 0 a 100%; o traço vertical é a taxa geral (base). */
export function RateBar({
  rate,
  ci,
  hits,
  n,
  amostra,
  base,
}: {
  rate: number | null;
  ci: [number, number] | null;
  hits: number;
  n: number;
  amostra: ReviewCell["amostra"];
  base?: number | null;
}) {
  if (rate == null || ci == null) return <span className="text-xs text-zinc-600">sem resolvidas</span>;
  const dim = amostra === "insuficiente";
  return (
    <div className={`min-w-44 ${dim ? "opacity-50" : ""}`} title={`${hits} de ${n} · ${SAMPLE_TEXT[amostra]}`}>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium tabular-nums text-zinc-100">{fmtPct(rate)}</span>
        <span className="tabular-nums text-zinc-500">
          {hits}/{n} · IC {fmtPct(ci[0])}–{fmtPct(ci[1])}
        </span>
      </div>
      <div className="relative mt-1 h-1.5 rounded-full bg-zinc-800">
        <div
          className="absolute h-full rounded-full bg-sky-700"
          style={{ left: `${ci[0] * 100}%`, width: `${Math.max((ci[1] - ci[0]) * 100, 1)}%` }}
        />
        <div className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-400" style={{ left: `${rate * 100}%` }} />
        {base != null && <div className="absolute -top-0.5 h-2.5 w-px bg-zinc-300" style={{ left: `${base * 100}%` }} title={`Taxa geral: ${fmtPct(base)}`} />}
      </div>
    </div>
  );
}

export const cellRate = (c: ReviewCell, base?: number | null) => (
  <RateBar rate={c.taxa_acerto} ci={c.ic95} hits={c.alvo} n={c.fechadas} amostra={c.amostra} base={base} />
);

export const decisionRate = (r: ReviewRate) => (
  <RateBar rate={r.taxa} ci={r.ic95} hits={r.acertos} n={r.fechadas} amostra={r.amostra} />
);

