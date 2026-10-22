import { useCallback, useEffect, useState } from "react";
import { api, type AiAnalysis, type AiEvidence, type AiLens, type AiStatus, type Market, type Stance } from "../api";
import { fmtDateTime, fmtNum, fmtUsd } from "../format";
import { Badge, Card, btnPrimary, inputSm, type Tone } from "./ui";

const STANCE: Record<Stance, { label: string; tone: Tone }> = {
  para_alta: { label: "Inclina para alta", tone: "emerald" },
  para_baixa: { label: "Inclina para baixa", tone: "rose" },
  indistinta: { label: "Indistinta", tone: "zinc" },
  sem_dados: { label: "Sem dados", tone: "amber" },
};
const CONFIDENCE = { baixa: "confiança baixa", media: "confiança média", alta: "confiança alta" } as const;
const POINTS = { alta: "↑", baixa: "↓", neutro: "•" } as const;
const POINT_CLS = { alta: "text-emerald-300", baixa: "text-rose-300", neutro: "text-zinc-500" } as const;

export default function AiPanel({
  market,
  symbol,
  horizon,
  onAnalysis,
}: {
  market: Market;
  symbol: string;
  horizon: number;
  onAnalysis: (a: AiAnalysis | null) => void;
}) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [history, setHistory] = useState<AiAnalysis[]>([]);
  const [current, setCurrent] = useState<AiAnalysis | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pkg, setPkg] = useState<unknown>(null);
  const [prompts, setPrompts] = useState<Record<string, string> | null>(null);

  const loadHistory = useCallback(async () => {
    const list = await api.aiAnalyses(market, symbol);
    setHistory(list);
    return list;
  }, [market, symbol]);

  useEffect(() => {
    api.aiStatus().then(setStatus).catch((e) => setError(String(e)));
    loadHistory()
      .then((list) => {
        // reabre a análise mais recente do ativo, para não gastar de novo só para olhar
        if (list[0]) {
          setCurrent(list[0]);
          onAnalysis(list[0]);
        }
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadHistory]);

  async function run() {
    setRunning(true);
    setError(null);
    setPkg(null);
    try {
      const a = await api.aiAnalyze(market, symbol, horizon);
      setCurrent(a);
      onAnalysis(a);
      await loadHistory();
      api.aiStatus().then(setStatus).catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  function pick(id: number) {
    const a = history.find((h) => h.id === id);
    if (a) {
      setCurrent(a);
      onAnalysis(a);
      setPkg(null);
    }
  }

  async function showPackage() {
    if (!current) return;
    setPkg((await api.aiAnalysis(current.id)).package ?? null);
  }

  async function showPrompts() {
    const p = await api.aiPrompts();
    setPrompts(p.prompts[market] ?? {});
  }

  const lenses = status?.lenses[market] ?? [];
  const directional = new Set((current?.lenses ?? []).flatMap((l) => (l.resultado && ["para_alta", "para_baixa"].includes(l.resultado.inclinacao) ? [l.resultado.inclinacao] : [])));

  return (
    <Card title="Análise com IA (lentes)">
      <div className="flex flex-wrap items-center gap-3">
        <button className={btnPrimary} onClick={() => void run()} disabled={running || !status?.configured}>
          {running ? "Analisando… (até 1 min)" : current ? "Analisar de novo" : "Analisar com IA"}
        </button>
        {status && (
          <span className="text-xs text-zinc-500">
            {lenses.length} lentes ({lenses.map((l) => l.title).join(", ")}) · {status.model}
            {status.effort ? ` · raciocínio ${status.effort}` : ""} · prompt {status.prompt_version}
            {status.avg_cost_usd != null ? ` · custo médio ${fmtUsd(status.avg_cost_usd)} por análise` : ""}
          </span>
        )}
        {history.length > 1 && (
          <select className={`${inputSm} ml-auto`} value={current?.id ?? ""} onChange={(e) => pick(Number(e.target.value))}>
            {history.map((h) => (
              <option key={h.id} value={h.id}>
                {fmtDateTime(h.created_at)} · {h.model.split("/").pop()} · {fmtUsd(h.cost_usd)}
              </option>
            ))}
          </select>
        )}
      </div>

      {status && !status.configured && (
        <p className="mt-3 rounded-md border border-amber-900 bg-amber-950/40 p-3 text-sm text-amber-200">
          A chave da OpenRouter ainda não está configurada. Copie <code>.env.example</code> para <code>.env</code>, preencha{" "}
          <code>OPENROUTER_API_KEY</code> (crie em openrouter.ai/keys e ponha saldo em openrouter.ai/credits) e reinicie o app.
        </p>
      )}
      {error && <p className="mt-3 rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">{error}</p>}
      {!current && !running && status?.configured && (
        <p className="mt-3 text-xs text-zinc-500">
          Cada lente recebe só a sua parte dos dados (calculados por código) e responde em JSON com inclinação, confiança,
          evidências citadas, lacunas e o que mudaria a conclusão. Não há veredito final: as lentes podem divergir, e isso é
          informação. Nada do seu diário é enviado.
        </p>
      )}

      {current && (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {current.lenses.map((l) => (
              <Badge key={l.lente} tone={l.resultado ? STANCE[l.resultado.inclinacao].tone : "amber"}>
                {l.titulo}: {l.resultado ? STANCE[l.resultado.inclinacao].label.toLowerCase() : "erro"}
              </Badge>
            ))}
            {directional.size > 1 && <Badge tone="sky">As lentes divergem entre si</Badge>}
          </div>
          <div className="text-[11px] text-zinc-600">
            Análise #{current.id} · {fmtDateTime(current.created_at)} · {current.model} · prompt {current.prompt_version} (
            {current.prompt_fingerprint}) · horizonte {current.horizon_days} dias · {fmtNum((current.duration_ms ?? 0) / 1000, 1)} s ·{" "}
            {current.prompt_tokens ?? "—"} tokens de entrada, {current.completion_tokens ?? "—"} de saída · custo {fmtUsd(current.cost_usd)}
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            {current.lenses.map((l) => (
              <LensCard key={l.lente} lens={l} />
            ))}
          </div>

          <div className="flex flex-wrap gap-4 text-xs">
            <button className="text-sky-400 hover:underline" onClick={() => void showPackage()}>
              Ver o pacote de dados enviado
            </button>
            <button className="text-sky-400 hover:underline" onClick={() => void showPrompts()}>
              Ver os prompts desta versão
            </button>
          </div>
          {pkg != null && (
            <pre className="max-h-96 overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-[11px] text-zinc-400">
              {JSON.stringify(pkg, null, 1)}
            </pre>
          )}
          {prompts && (
            <div className="space-y-2">
              {Object.entries(prompts).map(([lens, text]) => (
                <details key={lens} className="rounded-md border border-zinc-800 p-2 text-xs text-zinc-400">
                  <summary className="cursor-pointer text-zinc-300">{lens}</summary>
                  <pre className="mt-2 whitespace-pre-wrap">{text}</pre>
                </details>
              ))}
            </div>
          )}
          <p className="text-[11px] text-zinc-600">
            Interpretação de dados calculados por código, não recomendação. A IA pode errar: as citações marcadas com ⚠ não
            conferem com o pacote enviado.
          </p>
        </div>
      )}
    </Card>
  );
}

function EvidenceRow({ e }: { e: AiEvidence }) {
  const mark = e.verificada === true ? "✓" : e.verificada === false ? "⚠" : "?";
  const cls = e.verificada === true ? "text-emerald-400" : e.verificada === false ? "text-amber-400" : "text-zinc-500";
  return (
    <li className="flex gap-2 text-xs">
      <span className={`mt-0.5 w-3 shrink-0 text-center ${POINT_CLS[e.aponta_para]}`}>{POINTS[e.aponta_para]}</span>
      <span className="min-w-0 flex-1">
        <span className="text-zinc-300">{e.leitura}</span>{" "}
        <span className="break-all font-mono text-[11px] text-zinc-500">
          {e.campo} = {e.valor}
        </span>
      </span>
      <span className={`shrink-0 ${cls}`} title={e.verificada === true ? "Confere com o pacote" : e.motivo_da_verificacao || "Não dá para conferir"}>
        {mark}
      </span>
    </li>
  );
}

function LensCard({ lens }: { lens: AiLens }) {
  if (lens.status === "erro" || !lens.resultado) {
    return (
      <div className="rounded-lg border border-rose-900 bg-rose-950/30 p-3">
        <div className="mb-1 text-sm font-medium">{lens.titulo}</div>
        <p className="text-xs text-rose-300">{lens.erro?.mensagem ?? "Falhou."}</p>
        <p className="mt-1 text-[11px] text-zinc-600">{lens.erro?.tipo}</p>
      </div>
    );
  }
  const r = lens.resultado;
  const s = STANCE[r.inclinacao];
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{lens.titulo}</span>
        <Badge tone={s.tone}>{s.label}</Badge>
        <span className="text-xs text-zinc-500">{CONFIDENCE[r.confianca]}</span>
        {lens.citacoes && lens.citacoes.nao_conferem > 0 && (
          <Badge tone="amber">
            {lens.citacoes.nao_conferem} de {lens.citacoes.total} citações não conferem
          </Badge>
        )}
      </div>
      <p className="text-sm text-zinc-300">{r.resumo}</p>
      {r.evidencias.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {r.evidencias.map((e, i) => (
            <EvidenceRow key={i} e={e} />
          ))}
        </ul>
      )}
      {r.lacunas.length > 0 && (
        <div className="mt-3 text-xs">
          <div className="text-zinc-500">Faltou:</div>
          <ul className="list-inside list-disc text-zinc-400">
            {r.lacunas.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      )}
      {r.mudaria_a_conclusao.length > 0 && (
        <div className="mt-2 text-xs">
          <div className="text-zinc-500">Mudaria a conclusão:</div>
          <ul className="list-inside list-disc text-zinc-400">
            {r.mudaria_a_conclusao.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
