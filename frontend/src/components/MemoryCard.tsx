import { useEffect, useState } from "react";
import { api, CAUSE_TITLE, DECISION_LABEL, MARKET_LABEL, type AssetMemory, type Market, type MemoryAlert, type SimilarCase, type Status } from "../api";
import { fmtDate, fmtPct } from "../format";
import { cellRate } from "./RateBar";
import { Badge, Card, type Tone } from "./ui";

const OUTCOME: Record<Status, { label: string; tone: Tone }> = {
  alvo: { label: "Alvo", tone: "emerald" },
  invalidada: { label: "Invalidada", tone: "rose" },
  expirada: { label: "Expirada", tone: "zinc" },
  aberta: { label: "Aberta", tone: "sky" },
};

export function AlertLine({ a }: { a: MemoryAlert }) {
  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-950/40 p-2 text-xs">
      <div className="mb-0.5 flex flex-wrap items-center gap-2">
        <Badge tone={a.sentido === "melhor" ? "emerald" : "rose"}>
          {a.grupo.rotulo}: {a.sentido === "melhor" ? "acima" : "abaixo"}
        </Badge>
        <span className="font-medium text-zinc-200">{a.titulo}</span>
      </div>
      <p className="text-zinc-400">{a.texto}</p>
    </li>
  );
}

function CaseRow({ c }: { c: SimilarCase }) {
  const o = OUTCOME[c.desfecho];
  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-950/40 p-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-zinc-200">{c.simbolo}</span>
        <span className="text-zinc-500">
          {MARKET_LABEL[c.mercado]} · tese de {c.direcao} · {DECISION_LABEL[c.decisao].toLowerCase()} · {fmtDate(c.registrado_em)}
        </span>
        <Badge tone={o.tone}>{o.label}</Badge>
        {c.dias_ate_desfecho != null && <span className="text-zinc-500">em {c.dias_ate_desfecho} dias</span>}
        {c.pos_mortem && (
          <Badge tone="amber">
            {CAUSE_TITLE[c.pos_mortem.causa]} <span className="opacity-70">(IA)</span>
          </Badge>
        )}
        <span className="ml-auto text-zinc-600">{c.pontos} pts</span>
      </div>
      <div className="mt-1 text-zinc-500">Parecido porque: {c.por_que_parecido.join(" · ")}</div>
    </li>
  );
}

/** O que o diário sabe sobre este ativo e este estado: histórico, casos parecidos e os alertas estatísticos que se aplicam. */
export default function MemoryCard({
  market,
  symbol,
  horizon,
  setups,
}: {
  market: Market;
  symbol: string;
  horizon: number;
  setups: string[];
}) {
  const [data, setData] = useState<AssetMemory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = setups.join(",");

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    api
      .assetMemory(market, symbol, horizon, setups)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market, symbol, horizon, key]);

  if (error) return null; // a memória é um apoio: se falhar, a ficha continua inteira
  if (!data) {
    return (
      <Card title="Memória do diário">
        <p className="text-xs text-zinc-500">Lendo o diário…</p>
      </Card>
    );
  }

  const g = data.parecidos.grupo;
  const hist = data.historico_do_ativo;
  const nothing = hist.registros === 0 && data.parecidos.total_parecidos === 0;

  return (
    <Card title="Memória do diário">
      <p className="mb-3 text-xs text-zinc-500">
        Tudo calculado por código a partir das suas teses já resolvidas. Poucos casos são indício, não regra: leia sempre o n.
      </p>
      {nothing ? (
        <p className="text-sm text-zinc-400">
          O diário ainda não tem teses resolvidas deste ativo nem de estado parecido com o de agora.
        </p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div>
              <div className="mb-1 text-xs text-zinc-500">Este ativo no diário ({hist.registros} registro(s))</div>
              {cellRate(hist)}
            </div>
            {data.setups.filter((s) => s.registros > 0).map((s) => (
              <div key={s.setup}>
                <div className="mb-1 text-xs text-zinc-500">Setup "{s.setup}" ({s.registros} registro(s))</div>
                {cellRate(s)}
              </div>
            ))}
            <div>
              <div className="mb-1 text-xs text-zinc-500">
                Casos de estado parecido ({data.parecidos.total_parecidos} acima do corte de {data.parecidos.criterio.minimo_de_pontos} pontos)
              </div>
              {data.parecidos.total_parecidos > 0 ? (
                <div className="space-y-2 text-xs text-zinc-400">
                  <div>Todas as teses: {cellRate(g.todos)}</div>
                  <div className="flex flex-wrap gap-4">
                    <span>
                      De alta: {g.teses_de_alta.alvo} de {g.teses_de_alta.fechadas} ({fmtPct(g.teses_de_alta.taxa_acerto)})
                    </span>
                    <span>
                      De baixa: {g.teses_de_baixa.alvo} de {g.teses_de_baixa.fechadas} ({fmtPct(g.teses_de_baixa.taxa_acerto)})
                    </span>
                  </div>
                </div>
              ) : (
                <span className="text-xs text-zinc-600">nenhum caso passa do corte</span>
              )}
            </div>
          </div>

          <div className="space-y-3">
            {data.parecidos.casos.length > 0 && (
              <ul className="space-y-1.5">
                {data.parecidos.casos.map((c) => (
                  <CaseRow key={c.id} c={c} />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {data.alertas_aplicaveis.length > 0 && (
        <div className="mt-4">
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-400">Alertas estatísticos que se aplicam</div>
          <ul className="space-y-1.5">
            {data.alertas_aplicaveis.map((a) => (
              <AlertLine key={a.id} a={a} />
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-zinc-600">
            O app testou {data.comparacoes.testadas} comparações (mínimo de {data.comparacoes.minimo_por_grupo} teses resolvidas por lado):{" "}
            {data.comparacoes.distinguiveis} saíram distinguíveis e ≈ {data.comparacoes.esperados_por_acaso} apareceriam só por acaso.
          </p>
        </div>
      )}
    </Card>
  );
}
