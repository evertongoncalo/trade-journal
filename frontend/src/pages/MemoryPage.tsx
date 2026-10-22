import { Fragment, useCallback, useEffect, useState } from "react";
import {
  api,
  CAUSE_TITLE,
  DECISION_LABEL,
  MARKET_LABEL,
  TRIGGER_TEXT,
  VISIBILITY_TEXT,
  type AlertSide,
  type EligibleEntry,
  type MemoryOverview,
  type Status,
} from "../api";
import PostmortemPanel from "../components/PostmortemPanel";
import { AlertLine } from "../components/MemoryCard";
import { RateBar } from "../components/RateBar";
import { Badge, Card, btnGhost, btnPrimary, type Tone } from "../components/ui";
import { fmtDateTime, fmtR, fmtUsd } from "../format";

const STATUS_TONE: Record<Status, Tone> = { aberta: "sky", alvo: "emerald", invalidada: "rose", expirada: "zinc" };
const STATUS_TEXT: Record<Status, string> = { aberta: "Aberta", alvo: "Alvo", invalidada: "Invalidada", expirada: "Expirada" };

const sampleOf = (n: number) => (n < 10 ? "insuficiente" : n < 30 ? "pequena" : "ok");

function Side({ s }: { s: AlertSide }) {
  return (
    <div>
      <div className="mb-1 text-[11px] text-zinc-500">{s.rotulo}</div>
      <RateBar rate={s.taxa_acerto} ci={s.ic95} hits={s.alvo} n={s.fechadas} amostra={sampleOf(s.fechadas)} />
    </div>
  );
}

function SectionTitle({ title, note }: { title: string; note?: string }) {
  return (
    <div className="mb-3 mt-8">
      <h2 className="text-base font-semibold text-zinc-100">{title}</h2>
      {note && <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">{note}</p>}
    </div>
  );
}

export default function MemoryPage({ active }: { active: boolean }) {
  const [data, setData] = useState<MemoryOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [batch, setBatch] = useState<{ done: number; total: number } | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<{ version: string; fingerprint: string; causes_version: string; prompt: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.memory());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    if (active) void load();
  }, [active, load]);

  async function runAll(pending: EligibleEntry[]) {
    const cost = data?.ia.avg_cost_usd;
    const estimate = cost == null ? "o custo ainda não foi medido" : `≈ ${fmtUsd(cost * pending.length)} (custo médio recente × ${pending.length})`;
    if (
      !window.confirm(
        `Fazer ${pending.length} pós-mortem(ns), um de cada vez: ${estimate}.\n\nCada um envia à OpenRouter os dados de mercado do caso e a tese e o motivo de saída que você escreveu.\n\nContinuar?`,
      )
    )
      return;
    setBatchError(null);
    setBatch({ done: 0, total: pending.length });
    try {
      for (let i = 0; i < pending.length; i++) {
        await api.runPostmortem(pending[i].id);
        setBatch({ done: i + 1, total: pending.length });
      }
    } catch (err) {
      setBatchError(err instanceof Error ? err.message : String(err));
    } finally {
      setBatch(null);
      await load();
    }
  }

  async function showPrompt() {
    setPrompt(prompt ? null : await api.memoryPrompt());
  }

  if (error) return <p className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">{error}</p>;
  if (!data) return <p className="text-sm text-zinc-500">Carregando…</p>;

  const al = data.alertas;
  const pending = data.elegiveis.filter((e) => e.postmortem == null);
  const dist = data.distribuicao_das_causas;

  return (
    <div>
      <h2 className="text-lg font-semibold">Memória da IA</h2>
      <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">
        A IA não aprende sozinha: o app lembra por ela. Quando uma tese falha ou você sai antes, o <strong>pós-mortem</strong> classifica a
        causa numa lista fixa. Os <strong>casos parecidos</strong> aparecem na ficha do ativo e podem entrar na análise com IA (opção
        "Usar a memória"). Os <strong>alertas estatísticos</strong> são calculados só por código, sempre com o número de casos; a IA só
        levanta hipóteses, marcadas como hipótese.
      </p>

      <SectionTitle
        title="Alertas estatísticos (só código)"
        note={`Um alerta só aparece quando duas partes do diário diferem de forma distinguível do acaso: ao menos ${al.minimo_por_grupo} teses resolvidas em cada lado e intervalo de 95% da diferença fora do zero. É a mesma conta da aba Revisão.`}
      />
      <Card>
        <p className="text-xs text-zinc-400">
          {al.registros} registro(s), {al.resolvidas} resolvido(s). O app testou <strong>{al.testadas}</strong> comparação(ões); <strong>{al.distinguiveis}</strong>{" "}
          saíram distinguíveis, e só por acaso ≈ <strong>{al.esperados_por_acaso}</strong> apareceriam. Um alerta é indício para olhar os casos e ver se
          se repete em registros novos, nunca uma regra.
        </p>
        {al.alertas.length === 0 ? (
          <p className="mt-3 text-sm text-zinc-500">
            {al.testadas === 0
              ? `Ainda não há comparação possível: precisa de ao menos ${al.minimo_por_grupo} teses resolvidas dos dois lados de algum recorte.`
              : "Nenhuma diferença distinguível do acaso até agora."}
          </p>
        ) : (
          <ul className="mt-3 space-y-3">
            {al.alertas.map((a) => (
              <li key={a.id} className="space-y-2">
                <AlertLine a={a} />
                <div className="grid gap-3 pl-1 sm:grid-cols-2">
                  <Side s={a.grupo} />
                  <Side s={a.contra} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <SectionTitle
        title="Pós-mortem das teses que falharam"
        note="Para teses invalidadas e para saídas antecipadas. Cada pós-mortem é uma chamada paga ao modelo, feita só quando você pede. A IA vê o que já era visível no registro e, separado, o que aconteceu depois (caminho do preço e das referências, calculados por código), e escolhe uma causa da lista fixa. Sem dados que sustentem uma causa, a resposta certa é “sem causa identificável”."
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-zinc-300">
            {data.elegiveis.length} caso(s) pedem pós-mortem; {pending.length} ainda não foram analisados.
          </span>
          <button
            className={btnPrimary}
            disabled={!data.ia.configured || pending.length === 0 || batch != null}
            onClick={() => void runAll(pending)}
          >
            {batch ? `Analisando ${batch.done + 1} de ${batch.total}…` : "Fazer todos os pendentes"}
          </button>
          <span className="text-xs text-zinc-500">
            {data.ia.model} · {data.ia.prompt_version} ({data.ia.prompt_fingerprint})
            {data.ia.avg_cost_usd != null ? ` · custo médio ${fmtUsd(data.ia.avg_cost_usd)}` : " · custo ainda não medido"}
          </span>
        </div>
        {!data.ia.configured && (
          <p className="mt-3 rounded-md border border-amber-900 bg-amber-950/40 p-3 text-sm text-amber-200">
            A chave da OpenRouter ainda não está configurada (OPENROUTER_API_KEY no .env; reinicie o app).
          </p>
        )}
        {batchError && <p className="mt-3 rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">{batchError}</p>}
        <p className="mt-3 text-[11px] leading-relaxed text-zinc-600">
          O que vai para a OpenRouter em cada pós-mortem: dados de mercado do caso, o plano, o caminho do preço, a leitura dos blocos de
          código e das lentes de IA na época, <strong className="text-zinc-400">a tese e o motivo da saída que você escreveu</strong>. O pacote
          exato fica gravado e pode ser aberto em cada caso.
        </p>

        {data.elegiveis.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-900 text-xs uppercase text-zinc-500">
                <tr>
                  <th className="px-3 py-2">Data</th>
                  <th className="px-3 py-2">Ativo</th>
                  <th className="px-3 py-2">Decisão</th>
                  <th className="px-3 py-2">Por que pede</th>
                  <th className="px-3 py-2">Tese</th>
                  <th className="px-3 py-2">Causa (IA)</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {data.elegiveis.map((e) => (
                  <Fragment key={e.id}>
                    <tr className="align-top">
                      <td className="whitespace-nowrap px-3 py-2 text-zinc-400">{fmtDateTime(e.created_at)}</td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{e.symbol}</div>
                        <div className="text-xs text-zinc-500">
                          {MARKET_LABEL[e.market]} · {e.direction}
                        </div>
                      </td>
                      <td className="px-3 py-2">{DECISION_LABEL[e.decision]}</td>
                      <td className="px-3 py-2 text-xs text-zinc-400">{e.trigger ? TRIGGER_TEXT[e.trigger] : "—"}</td>
                      <td className="px-3 py-2">
                        <Badge tone={STATUS_TONE[e.status]}>{STATUS_TEXT[e.status]}</Badge>
                        {e.r_multiple != null && <span className="ml-2 text-xs tabular-nums">{fmtR(e.r_multiple)}</span>}
                      </td>
                      <td className="px-3 py-2">
                        {e.postmortem ? (
                          <div className="space-y-1">
                            <Badge tone={e.postmortem.causa_principal === "sem_causa_identificavel" ? "zinc" : "amber"}>
                              {CAUSE_TITLE[e.postmortem.causa_principal]}
                            </Badge>
                            <div className="text-[11px] text-zinc-500">
                              {VISIBILITY_TEXT[e.postmortem.visibilidade]}
                              {e.postmortem.avisos > 0 && <span className="ml-1 text-amber-400">· ⚠ {e.postmortem.avisos}</span>}
                            </div>
                          </div>
                        ) : (
                          <span className="text-xs text-zinc-600">pendente</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button className={btnGhost} onClick={() => setOpen(open === e.id ? null : e.id)}>
                          {open === e.id ? "Fechar" : e.postmortem ? "Abrir" : "Analisar"}
                        </button>
                      </td>
                    </tr>
                    {open === e.id && e.trigger && (
                      <tr className="bg-zinc-900/40">
                        <td colSpan={7} className="px-4 py-4">
                          <PostmortemPanel
                            entryId={e.id}
                            trigger={e.trigger}
                            hasPostmortem={e.postmortem != null}
                            avgCost={data.ia.avg_cost_usd}
                            onChanged={() => void load()}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 text-xs">
          <button className="text-sky-400 hover:underline" onClick={() => void showPrompt()}>
            {prompt ? "Ocultar" : "Ver"} o texto fixo do pós-mortem
          </button>
        </div>
        {prompt && (
          <div className="mt-2">
            <div className="mb-1 text-[11px] text-zinc-600">
              {prompt.version} ({prompt.fingerprint}) · lista de causas {prompt.causes_version}. Editar este texto exige criar uma nova versão.
            </div>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-zinc-950 p-3 text-[11px] text-zinc-400">
              {prompt.prompt}
            </pre>
          </div>
        )}
      </Card>

      <SectionTitle
        title="Causas apontadas"
        note="Quantas vezes a IA apontou cada causa nos pós-mortems. É classificação da IA (hipótese), não uma medição do código; com poucos casos é só indício."
      />
      <Card>
        {dist.n === 0 ? (
          <p className="text-sm text-zinc-500">Nenhum pós-mortem feito ainda.</p>
        ) : (
          <div className="space-y-3">
            <div className="text-xs text-zinc-400">{dist.n} pós-mortem(ns).</div>
            <ul className="grid gap-3 sm:grid-cols-2">
              {dist.itens.map((i) => (
                <li key={i.causa}>
                  <div className="mb-1 text-xs text-zinc-300">{i.titulo}</div>
                  <RateBar rate={i.taxa} ci={i.ic95} hits={i.n} n={dist.n} amostra={dist.amostra} />
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
              {(Object.entries(dist.visibilidade) as [keyof typeof VISIBILITY_TEXT, number][]).map(([k, v]) => (
                <span key={k}>
                  {VISIBILITY_TEXT[k]}: {v}
                </span>
              ))}
            </div>
            <p className="text-[11px] text-zinc-600">{dist.nota}</p>
          </div>
        )}
        <details className="mt-4 text-xs text-zinc-400">
          <summary className="cursor-pointer text-zinc-300">A lista fixa de causas ({data.causas.versao})</summary>
          <ul className="mt-2 space-y-2">
            {data.causas.lista.map((c) => (
              <li key={c.id}>
                <span className="font-medium text-zinc-200">{c.title}</span>
                {c.only_if_entered && <span className="ml-2 text-zinc-500">(só para quem entrou)</span>}
                <div className="text-zinc-500">{c.definition}</div>
              </li>
            ))}
          </ul>
        </details>
      </Card>
    </div>
  );
}
