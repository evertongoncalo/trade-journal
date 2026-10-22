import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  api,
  DECISION_LABEL,
  MARKET_LABEL,
  type AlertKind,
  type Decision,
  type Market,
  type Review,
  type ReviewCell,
  type ReviewConcordance,
  type ReviewDiff,
  type ReviewGroup,
} from "../api";
import { cellRate, decisionRate } from "../components/RateBar";
import { Badge, Card, btnGhost, type Tone } from "../components/ui";
import { fmtDate, fmtNum } from "../format";

const KIND_LABEL: Record<AlertKind, string> = { avulso: "Avulso", entrada: "Entrada", invalidacao: "Invalidação", alvo: "Alvo" };
const RESPONSE_LABEL: Record<string, string> = { entrei: "Entrei", ignorei: "Ignorei", observando: "Observando" };

const label = (key: string) => DECISION_LABEL[key as Decision] ?? MARKET_LABEL[key as Market] ?? RESPONSE_LABEL[key] ?? key;

function Count({ c }: { c: ReviewCell }) {
  return (
    <span className="tabular-nums" title={c.ids.length ? `Registros: ${c.ids.map((i) => `#${i}`).join(" ")}` : undefined}>
      {c.registros}
    </span>
  );
}

const TH = "pb-2 pr-3 text-left text-xs font-normal text-zinc-500";
const TD = "py-2 pr-3 align-middle text-sm tabular-nums";

function GroupTable({ rows, base, empty }: { rows: ReviewGroup[]; base?: number | null; empty: string }) {
  if (!rows.length) return <p className="text-sm text-zinc-500">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr>
            <th className={TH}></th>
            <th className={TH}>Registros</th>
            <th className={TH}>Alvo</th>
            <th className={TH}>Invalidada</th>
            <th className={TH}>Expirada</th>
            <th className={TH}>Aberta</th>
            <th className={TH}>A tese bateu o alvo</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/70">
          {rows.map((r) => (
            <tr key={r.chave}>
              <td className="py-2 pr-3 text-sm text-zinc-200">{label(r.chave)}</td>
              <td className={TD}>
                <Count c={r} />
              </td>
              <td className={`${TD} text-emerald-400`}>{r.alvo}</td>
              <td className={`${TD} text-rose-400`}>{r.invalidada}</td>
              <td className={`${TD} text-zinc-400`}>{r.expirada}</td>
              <td className={`${TD} text-sky-400`}>{r.aberta}</td>
              <td className={TD}>{cellRate(r, base)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const DIFF_TONE: Record<ReviewDiff["leitura"], Tone> = { a_maior: "emerald", b_maior: "rose", indistinta: "zinc", "sem dados": "amber" };

function DiffLine({ d, aMaior, bMaior }: { d: ReviewDiff; aMaior: string; bMaior: string }) {
  const range = d.ic95_pp ? `IC95 ${fmtNum(d.ic95_pp[0], 0)} a ${fmtNum(d.ic95_pp[1], 0)} pp` : "";
  const pp = d.pp == null ? "" : `${d.pp > 0 ? "+" : ""}${fmtNum(d.pp, 0)} pp`;
  const text =
    d.leitura === "sem dados"
      ? "Sem dados para comparar: é preciso ao menos 10 resolvidas em cada lado."
      : d.leitura === "indistinta"
        ? `${pp} (${range}): indistinguível de zero.`
        : `${d.leitura === "a_maior" ? aMaior : bMaior}: ${pp} (${range}).`;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
      <Badge tone={DIFF_TONE[d.leitura]}>
        {d.leitura === "a_maior" ? "Diferença distinguível" : d.leitura === "b_maior" ? "Diferença ao contrário" : d.leitura === "indistinta" ? "Indistinta" : "Sem dados"}
      </Badge>
      <span>{text}</span>
    </div>
  );
}

function SideRow({ name, c, base }: { name: string; c: ReviewCell; base: number | null }) {
  return (
    <tr>
      <td className="py-1.5 pr-3 text-xs text-zinc-300">{name}</td>
      <td className="py-1.5 pr-3 text-xs tabular-nums text-zinc-400">
        <Count c={c} />
      </td>
      <td className="py-1.5 text-sm">{cellRate(c, base)}</td>
    </tr>
  );
}

/** Quando o bloco (ou a lente) concordava com a tese × quando discordava × quando não apontava lado. */
function ConcordanceCard({
  title,
  rule,
  data,
  base,
  missing,
}: {
  title: string;
  rule?: string;
  data: ReviewConcordance;
  base: number | null;
  missing: string;
}) {
  return (
    <Card>
      <h4 className="text-sm font-semibold text-zinc-100">{title}</h4>
      {rule && <p className="mt-0.5 text-[11px] leading-snug text-zinc-500">{rule}</p>}
      <table className="mt-3 w-full">
        <thead>
          <tr>
            <th className={TH}>Lado do bloco</th>
            <th className={TH}>Reg.</th>
            <th className={TH}>A tese bateu o alvo</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/70">
          <SideRow name="Concordava com a tese" c={data.a_favor} base={base} />
          <SideRow name="Discordava da tese" c={data.contra} base={base} />
          <SideRow name="Sem lado (indistinta ou sem dados)" c={data.sem_inclinacao} base={base} />
        </tbody>
      </table>
      <div className="mt-3 space-y-1.5">
        <DiffLine d={data.diferenca} aMaior="Concordar coincidiu com mais acertos" bMaior="Discordar coincidiu com mais acertos" />
        {data.sem_registro > 0 && (
          <p className="text-[11px] text-zinc-600">
            {data.sem_registro} registro(s) {missing}: fora desta conta.
          </p>
        )}
      </div>
    </Card>
  );
}

function Stat({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-zinc-500">{k}</dt>
      <dd className="mt-0.5 text-sm tabular-nums text-zinc-100">{children}</dd>
    </div>
  );
}

function SectionTitle({ children, note }: { children: ReactNode; note?: string }) {
  return (
    <div className="mb-3 mt-8">
      <h2 className="text-base font-semibold text-zinc-100">{children}</h2>
      {note && <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">{note}</p>}
    </div>
  );
}

export default function ReviewPage({ active }: { active: boolean }) {
  const [data, setData] = useState<Review | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.review());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  // as páginas ficam montadas: recarrega toda vez que a aba volta a ser a ativa
  useEffect(() => {
    if (active) void load();
  }, [active, load]);

  async function reevaluate() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.refresh();
      setNote(`${r.avaliadas} tese(s) aberta(s) reavaliada(s), ${r.encerradas} encerrada(s)${r.erros.length ? `, ${r.erros.length} falha(s) de dados` : ""}.`);
      await load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">{error}</p>;
  if (!data) return <p className="text-sm text-zinc-500">Carregando…</p>;

  const a = data.amostra;
  const base = a.taxa_acerto;
  const d = data.por_decisao;
  const al = data.alertas;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Revisão do acerto</h2>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">
            Acerto da tese = alvo ÷ (alvo + invalidada); expiradas e abertas ficam fora da taxa. Cada taxa mostra o n e o intervalo de 95%
            (barra azul); o ponto é a taxa e o traço claro é a taxa geral. Nada aqui é somado num score, e o app não diz o que fazer.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {note && <span className="text-xs text-zinc-400">{note}</span>}
          <button className={btnGhost} onClick={reevaluate} disabled={busy}>
            {busy ? "Reavaliando…" : "Reavaliar teses abertas"}
          </button>
        </div>
      </div>

      <Card className="mt-4">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Stat k="Registros">{a.registros}</Stat>
          <Stat k="Resolvidas (alvo ou invalidada)">{a.fechadas}</Stat>
          <Stat k="Expiradas / abertas">
            {a.expirada} / {a.aberta}
          </Stat>
          <Stat k="Ativos distintos">{a.ativos_distintos}</Stat>
          <Stat k="Período">{a.primeiro ? `${fmtDate(a.primeiro)} a ${fmtDate(a.ultimo)}` : "—"}</Stat>
          <Stat k="Taxa geral da tese">{cellRate(a)}</Stat>
        </dl>
      </Card>

      <ul className="mt-3 space-y-1.5">
        {data.avisos.map((t) => (
          <li key={t} className="rounded-md border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-xs leading-relaxed text-amber-200/90">
            {t}
          </li>
        ))}
      </ul>

      <SectionTitle note="O que você fez com cada tese. Entrar e a tese bater o alvo, ou ficar de fora e ela ser invalidada, contam como decisão certa; o inverso é decisão errada. Boa decisão com resultado ruim existe, e este quadro não separa uma da outra.">
        Por tipo de decisão
      </SectionTitle>
      <Card>
        {a.registros === 0 ? (
          <p className="text-sm text-zinc-500">Ainda não há registros no diário.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className={TH}></th>
                    <th className={TH}>Registros</th>
                    <th className={TH}>Alvo</th>
                    <th className={TH}>Invalidada</th>
                    <th className={TH}>Expirada</th>
                    <th className={TH}>Aberta</th>
                    <th className={TH}>A tese bateu o alvo</th>
                    <th className={TH}>Decisão certa</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/70">
                  {d.linhas.map((r) => (
                    <tr key={r.chave}>
                      <td className="py-2 pr-3 text-sm text-zinc-200">{label(r.chave)}</td>
                      <td className={TD}>
                        <Count c={r} />
                      </td>
                      <td className={`${TD} text-emerald-400`}>{r.alvo}</td>
                      <td className={`${TD} text-rose-400`}>{r.invalidada}</td>
                      <td className={`${TD} text-zinc-400`}>{r.expirada}</td>
                      <td className={`${TD} text-sky-400`}>{r.aberta}</td>
                      <td className={TD}>{cellRate(r, base)}</td>
                      <td className={TD}>{decisionRate(r.decisao_certa)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 space-y-2 border-t border-zinc-800 pt-3">
              <p className="text-xs text-zinc-400">
                Seu filtro: as teses em que você entrou bateram o alvo mais do que as que deixou de fora?
              </p>
              <DiffLine d={d.entrei_vs_fora.diferenca} aMaior="Entrar coincidiu com mais acertos" bMaior="As que ficaram de fora acertaram mais" />
              <p className="text-xs text-zinc-500">
                Saída antecipada: {d.saida_antecipada.registros} registro(s).
                {d.saida_antecipada.registros > 0 &&
                  ` Depois de sair, a tese ${d.saida_antecipada.depois.alvo} bateu o alvo, ${d.saida_antecipada.depois.invalidada} foi invalidada, ${d.saida_antecipada.depois.expirada} expirou e ${d.saida_antecipada.depois.aberta} segue aberta.`}
              </p>
            </div>
          </>
        )}
      </Card>

      <SectionTitle>Por mercado</SectionTitle>
      <Card>
        <GroupTable rows={data.por_mercado} base={base} empty="Sem registros." />
      </Card>

      <SectionTitle note="Setup = os nomes gravados no registro. Um registro com dois setups conta nos dois.">Por setup</SectionTitle>
      <Card>
        <GroupTable rows={data.por_setup} base={base} empty="Sem registros." />
      </Card>

      <SectionTitle note={`Cada bloco de código olhou o ativo no momento do registro. A pergunta é se a tese bateu o alvo mais vezes quando o bloco concordava do que quando discordava: se o bloco não soubesse nada, as duas taxas seriam iguais. Regras de leitura: ${data.regras_versao}. Registros anteriores à versão atual não guardaram price action nem correlação.`}>
        Por bloco de código
      </SectionTitle>
      <div className="grid gap-4 lg:grid-cols-2">
        {data.por_bloco.map((b) => (
          <ConcordanceCard
            key={b.bloco}
            title={b.titulo}
            rule={b.regra}
            data={b}
            base={base}
            missing="sem este bloco (anteriores a ele, ou ele não se aplica ao ativo)"
          />
        ))}
      </div>

      <SectionTitle note="Mesma conta para cada lente da análise com IA que estava aberta na ficha quando você registrou. A IA nunca vê o diário; aqui o diário é que mede a IA.">
        Por lente de IA
      </SectionTitle>
      {data.por_lente.lentes.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500">
            Nenhum registro levou uma análise de IA. Rode “Analisar com IA” na ficha do ativo antes de “Registrar no diário” para a lente entrar na revisão.
          </p>
        </Card>
      ) : (
        <>
          <p className="mb-3 text-xs text-zinc-500">
            {data.por_lente.registros_com_ia} de {a.registros} registro(s) têm análise de IA.{" "}
            {data.por_lente.versoes.map((v) => `${v.model ?? "?"} · prompt ${v.prompt_version ?? "?"}: ${v.registros}`).join("; ")}
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {data.por_lente.lentes.map((l) => (
              <ConcordanceCard
                key={l.lente}
                title={l.lente}
                data={l}
                base={base}
                missing="sem esta lente (sem análise de IA na hora do registro, ou lente de outro mercado)"
              />
            ))}
          </div>
        </>
      )}

      <SectionTitle note="O que você respondeu quando o alerta disparou. Só o alerta de entrada tem desfecho a medir: os de alvo e invalidação disparam justamente quando a tese termina. Alertas avulsos não têm plano, então só entram na contagem.">
        Respostas dos alertas
      </SectionTitle>
      <Card>
        <p className="mb-3 text-xs text-zinc-400">
          {al.criados} criado(s), {al.disparados} disparado(s), {al.sem_resposta} aguardando resposta, {al.cancelados} cancelado(s).
        </p>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className={TH}>Tipo</th>
                <th className={TH}>Criados</th>
                <th className={TH}>Disparados</th>
                <th className={TH}>Entrei</th>
                <th className={TH}>Ignorei</th>
                <th className={TH}>Observando</th>
                <th className={TH}>Sem resposta</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/70">
              {al.por_tipo.map((k) => (
                <tr key={k.tipo}>
                  <td className="py-2 pr-3 text-sm text-zinc-200">{KIND_LABEL[k.tipo]}</td>
                  <td className={TD}>{k.criados}</td>
                  <td className={TD}>{k.disparados}</td>
                  <td className={TD}>{k.entrei}</td>
                  <td className={TD}>{k.ignorei}</td>
                  <td className={TD}>{k.observando}</td>
                  <td className={`${TD} ${k.sem_resposta ? "text-amber-400" : "text-zinc-500"}`}>{k.sem_resposta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h4 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          Alerta de entrada disparou e eu respondi… e a tese depois
        </h4>
        <GroupTable rows={al.entrada_por_resposta} base={base} empty="Sem alertas de entrada respondidos." />
      </Card>
    </div>
  );
}
