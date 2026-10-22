import { useCallback, useEffect, useState } from "react";
import {
  api,
  CAUSE_TITLE,
  TRIGGER_TEXT,
  VISIBILITY_TEXT,
  type PmTrigger,
  type Postmortem,
} from "../api";
import { fmtDateTime, fmtNum, fmtUsd } from "../format";
import { Badge, btnPrimary, type Tone } from "./ui";

const CONFIDENCE = { baixa: "confiança baixa", media: "confiança média", alta: "confiança alta" } as const;
const CHECK_TEXT = {
  nao_se_aplica: "Não se aplica",
  sem_base: "Sem base nos dados",
  incoerente: "Resposta incoerente",
  citacao: "Citação não confere",
} as const;
const VISIBILITY_TONE: Record<Postmortem["result"]["visibilidade"], Tone> = {
  visivel_na_epoca: "sky",
  so_ficou_claro_depois: "amber",
  misto: "zinc",
  nao_se_aplica: "zinc",
};

/** Um pós-mortem já feito: causa da lista fixa, o que era visível na época × o que só ficou claro depois, e os avisos do código. */
export function PostmortemView({ pm }: { pm: Postmortem }) {
  const [showPackage, setShowPackage] = useState(false);
  const [pkg, setPkg] = useState<unknown>(null);
  const r = pm.result;

  async function togglePackage() {
    if (!showPackage && pkg == null) setPkg((await api.postmortem(pm.entry_id)).package ?? null);
    setShowPackage((v) => !v);
  }

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={r.causa_principal === "sem_causa_identificavel" ? "zinc" : "amber"}>{CAUSE_TITLE[r.causa_principal]}</Badge>
        {r.causas_secundarias.map((c) => (
          <Badge key={c}>{CAUSE_TITLE[c]} (secundária)</Badge>
        ))}
        <Badge tone={VISIBILITY_TONE[r.visibilidade]}>{VISIBILITY_TEXT[r.visibilidade]}</Badge>
        <span className="text-xs text-zinc-500">{CONFIDENCE[r.confianca]} · causa atribuída por IA, não medida</span>
      </div>
      <p className="text-zinc-200">{r.resumo}</p>

      {pm.checks.length > 0 && (
        <ul className="space-y-1 rounded-md border border-amber-900/60 bg-amber-950/30 p-2 text-xs text-amber-200/90">
          {pm.checks.map((c, i) => (
            <li key={i}>
              <span className="font-medium">⚠ {CHECK_TEXT[c.tipo]}:</span> {c.mensagem}
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <Listing title="O que já era visível no registro" items={r.o_que_era_visivel} />
        <Listing title="O que só ficou claro depois" items={r.o_que_so_ficou_claro_depois} />
      </div>

      {r.evidencias.length > 0 && (
        <div>
          <div className="mb-1 text-xs text-zinc-500">Evidências (o app confere cada citação com o pacote enviado)</div>
          <ul className="space-y-1">
            {r.evidencias.map((e, i) => (
              <li key={i} className="flex gap-2 text-xs">
                <span className={e.verificada === true ? "text-emerald-400" : e.verificada === false ? "text-amber-400" : "text-zinc-500"} title={e.motivo_da_verificacao || undefined}>
                  {e.verificada === true ? "✓" : e.verificada === false ? "⚠" : "?"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-zinc-300">{e.leitura}</span>{" "}
                  <span className="break-all font-mono text-[11px] text-zinc-500">
                    {e.campo} = {e.valor}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {r.hipoteses.length > 0 && (
        <div className="rounded-md border border-sky-900/60 bg-sky-950/20 p-2 text-xs">
          <div className="mb-1 font-medium text-sky-300">Hipóteses (para testar; não são conclusões nem alertas)</div>
          <ul className="list-inside list-disc text-zinc-300">
            {r.hipoteses.map((h, i) => (
              <li key={i}>
                <span className="text-sky-300">Hipótese:</span> {h}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Listing title="O que faltou nos dados" items={r.o_que_faltou} />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-600">
        <span>
          {TRIGGER_TEXT[pm.trigger]} · {fmtDateTime(pm.created_at)} · {pm.model} · {pm.prompt_version} ({pm.prompt_fingerprint}) ·{" "}
          {pm.causes_version} · {fmtNum((pm.duration_ms ?? 0) / 1000, 1)} s · custo {fmtUsd(pm.cost_usd)}
        </span>
        <button className="text-sky-400 hover:underline" onClick={() => void togglePackage()}>
          {showPackage ? "Ocultar" : "Ver"} o pacote enviado
        </button>
      </div>
      {showPackage && pkg != null && (
        <pre className="max-h-96 overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-[11px] text-zinc-400">
          {JSON.stringify(pkg, null, 1)}
        </pre>
      )}
    </div>
  );
}

function Listing({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="text-xs">
      <div className="mb-1 text-zinc-500">{title}</div>
      <ul className="list-inside list-disc space-y-0.5 text-zinc-300">
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

/** Mostra o pós-mortem de um registro (carrega sob demanda) ou o botão para fazê-lo. Cada execução é uma chamada paga ao modelo. */
export default function PostmortemPanel({
  entryId,
  trigger,
  hasPostmortem,
  avgCost,
  onChanged,
}: {
  entryId: number;
  trigger: PmTrigger;
  hasPostmortem: boolean;
  avgCost?: number | null;
  onChanged: () => void;
}) {
  const [pm, setPm] = useState<Postmortem | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setPm(await api.postmortem(entryId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [entryId]);

  useEffect(() => {
    if (hasPostmortem) void load();
  }, [hasPostmortem, load]);

  async function run() {
    const cost = avgCost == null ? "o custo ainda não foi medido" : `custo médio recente: ${fmtUsd(avgCost)}`;
    const note = pm ? "Isto refaz o pós-mortem (o anterior fica guardado)." : "";
    if (
      !window.confirm(
        `Fazer o pós-mortem envia uma chamada paga à OpenRouter (${cost}).\n\nVai junto, além dos dados de mercado do caso: a tese e o motivo da saída que você escreveu. ${note}\n\nContinuar?`,
      )
    )
      return;
    setRunning(true);
    setError(null);
    try {
      setPm(await api.runPostmortem(entryId));
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone="amber">{TRIGGER_TEXT[trigger]}</Badge>
        <button className={btnPrimary} onClick={() => void run()} disabled={running}>
          {running ? "Analisando… (até 1 min)" : pm ? "Refazer o pós-mortem" : "Fazer o pós-mortem com IA"}
        </button>
        {!pm && !running && (
          <span className="text-xs text-zinc-500">
            A IA recebe o caso, o que já era visível no registro, o caminho do preço e o das referências depois dele, e escolhe uma causa de uma
            lista fixa (ou "sem causa identificável").
          </span>
        )}
      </div>
      {error && <p className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">{error}</p>}
      {pm && <PostmortemView pm={pm} />}
    </div>
  );
}
