import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  api,
  DECISION_LABEL,
  MARKET_LABEL,
  type Decision,
  type Direction,
  type Draft,
  type Entry,
  type GroupStats,
  type Market,
  type Stats,
  type Status,
} from "../api";
import { Badge, Card, Field, btnGhost, btnPrimary, inputCls, type Tone } from "../components/ui";
import { fmtDateTime, fmtPct, fmtPrice, fmtR } from "../format";

const STATUS_TONE: Record<Status, Tone> = { aberta: "sky", alvo: "emerald", invalidada: "rose", expirada: "zinc" };
const STATUS_TEXT: Record<Status, string> = {
  aberta: "Aberta",
  alvo: "Alvo atingido",
  invalidada: "Invalidada",
  expirada: "Expirada",
};

interface Form {
  market: Market;
  symbol: string;
  decision: Decision;
  direction: Direction;
  entry: string;
  invalidation: string;
  target: string;
  horizon: string;
  thesis: string;
  setup: string;
}

const EMPTY: Form = {
  market: "acoes",
  symbol: "",
  decision: "observando",
  direction: "alta",
  entry: "",
  invalidation: "",
  target: "",
  horizon: "10",
  thesis: "",
  setup: "",
};

const num = (s: string) => Number(s.replace(",", "."));

export default function JournalPage({ draft }: { draft: Draft | null }) {
  const [form, setForm] = useState<Form>(EMPTY);
  const [snapshot, setSnapshot] = useState<Record<string, unknown>>({});
  const [entries, setEntries] = useState<Entry[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [e, s] = await Promise.all([api.entries(), api.stats()]);
    setEntries(e);
    setStats(s);
  }, []);

  useEffect(() => {
    load().catch((err) => setMsg({ tone: "err", text: String(err) }));
  }, [load]);

  useEffect(() => {
    if (!draft) return;
    setForm((f) => ({
      ...f,
      market: draft.market,
      symbol: draft.symbol,
      direction: draft.direction,
      entry: String(draft.entry_price),
      invalidation: String(draft.invalidation),
      target: String(draft.target),
      setup: draft.setup ?? f.setup,
    }));
    setSnapshot(draft.snapshot);
  }, [draft]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function run(action: () => Promise<string | void>) {
    setBusy(true);
    setMsg(null);
    try {
      const text = await action();
      await load();
      if (text) setMsg({ tone: "ok", text });
    } catch (err) {
      setMsg({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      const created = await api.createEntry({
        market: form.market,
        symbol: form.symbol,
        decision: form.decision,
        direction: form.direction,
        entry_price: num(form.entry),
        invalidation: num(form.invalidation),
        target: num(form.target),
        horizon_days: Number(form.horizon),
        thesis: form.thesis,
        setup: form.setup,
        snapshot,
      });
      setForm(EMPTY);
      setSnapshot({});
      const n = created.alerts?.length ?? 0;
      const kinds = (created.alerts ?? []).map((a) => ({ entrada: "entrada", invalidacao: "invalidação", alvo: "alvo", avulso: "avulso" })[a.kind]);
      return n > 0
        ? `Registrado no diário. ${n} alertas de preço criados (${kinds.join(", ")}): veja na aba Alertas.`
        : "Registrado no diário.";
    });
  }

  const refresh = () =>
    run(async () => {
      const r = await api.refresh();
      const errs = r.erros.length ? ` Erros: ${r.erros.map((x) => `${x.symbol}: ${x.erro}`).join("; ")}` : "";
      return `${r.avaliadas} avaliadas, ${r.encerradas} encerradas.${errs}`;
    });

  const earlyExit = (en: Entry) => {
    const price = window.prompt(`Preço da saída antecipada de ${en.symbol}:`);
    if (!price) return;
    const reason = window.prompt("Motivo (ex.: price action mudou, notícia, medo):") ?? "";
    void run(async () => {
      await api.earlyExit(en.id, num(price), reason);
      return "Saída antecipada registrada; o plano continua sendo acompanhado.";
    });
  };

  const remove = (en: Entry) => {
    if (window.confirm(`Excluir o registro de ${en.symbol}?`)) void run(() => api.remove(en.id));
  };

  return (
    <div className="space-y-6">
      <StatsBar stats={stats} />

      <Card title="Novo registro">
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-6">
          <Field label="Mercado">
            <select className={inputCls} value={form.market} onChange={(e) => set("market", e.target.value as Market)}>
              {(Object.keys(MARKET_LABEL) as Market[]).map((m) => (
                <option key={m} value={m}>
                  {MARKET_LABEL[m]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Símbolo">
            <input className={inputCls} value={form.symbol} onChange={(e) => set("symbol", e.target.value)} required />
          </Field>
          <Field label="Decisão">
            <select className={inputCls} value={form.decision} onChange={(e) => set("decision", e.target.value as Decision)}>
              {(Object.keys(DECISION_LABEL) as Decision[]).map((d) => (
                <option key={d} value={d}>
                  {DECISION_LABEL[d]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Direção da tese">
            <select className={inputCls} value={form.direction} onChange={(e) => set("direction", e.target.value as Direction)}>
              <option value="alta">Alta</option>
              <option value="baixa">Baixa</option>
            </select>
          </Field>
          <Field label="Horizonte (dias)">
            <input className={inputCls} type="number" min={1} max={365} value={form.horizon} onChange={(e) => set("horizon", e.target.value)} required />
          </Field>
          <Field label="Setup (opcional)">
            <input className={inputCls} value={form.setup} onChange={(e) => set("setup", e.target.value)} />
          </Field>
          <Field label="Entrada">
            <input className={inputCls} inputMode="decimal" value={form.entry} onChange={(e) => set("entry", e.target.value)} required />
          </Field>
          <Field label="Invalidação">
            <input className={inputCls} inputMode="decimal" value={form.invalidation} onChange={(e) => set("invalidation", e.target.value)} required />
          </Field>
          <Field label="Alvo">
            <input className={inputCls} inputMode="decimal" value={form.target} onChange={(e) => set("target", e.target.value)} required />
          </Field>
          <Field label="Tese" className="md:col-span-3">
            <input className={inputCls} value={form.thesis} placeholder="Por que esse movimento é provável?" onChange={(e) => set("thesis", e.target.value)} />
          </Field>
          <div className="flex items-end gap-2 md:col-span-6">
            <button type="submit" className={btnPrimary} disabled={busy}>
              Registrar
            </button>
            <p className="text-xs text-zinc-500">
              Vale também para o que você decidiu não fazer: o app acompanha o que teria acontecido.
              {Object.keys(snapshot).length > 0 && " Os dados da ficha serão gravados junto."}
            </p>
          </div>
        </form>
      </Card>

      {msg && (
        <p
          className={`rounded-md border p-3 text-sm ${
            msg.tone === "ok" ? "border-emerald-900 bg-emerald-950/40 text-emerald-300" : "border-rose-900 bg-rose-950/50 text-rose-300"
          }`}
        >
          {msg.text}
        </p>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">Registros ({entries.length})</h2>
        <button className={btnGhost} onClick={() => void refresh()} disabled={busy}>
          Atualizar resultados
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900 text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-3 py-2">Data</th>
              <th className="px-3 py-2">Ativo</th>
              <th className="px-3 py-2">Decisão</th>
              <th className="px-3 py-2">Plano (entrada → invalidação / alvo)</th>
              <th className="px-3 py-2">Resultado da tese</th>
              <th className="px-3 py-2">Saída antecipada</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {entries.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-zinc-500">
                  Nenhum registro ainda.
                </td>
              </tr>
            )}
            {entries.map((en) => (
              <tr key={en.id} className="align-top" title={en.thesis}>
                <td className="whitespace-nowrap px-3 py-2 text-zinc-400">{fmtDateTime(en.created_at)}</td>
                <td className="px-3 py-2">
                  <div className="font-medium">{en.symbol}</div>
                  <div className="text-xs text-zinc-500">
                    {MARKET_LABEL[en.market]} · {en.direction}
                  </div>
                </td>
                <td className="px-3 py-2">{DECISION_LABEL[en.decision]}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                  {fmtPrice(en.entry_price)} → {fmtPrice(en.invalidation)} / {fmtPrice(en.target)}
                  <div className="text-xs text-zinc-500">{en.horizon_days} dias</div>
                </td>
                <td className="px-3 py-2">
                  <Badge tone={STATUS_TONE[en.status]}>{STATUS_TEXT[en.status]}</Badge>
                  {en.r_multiple != null && <span className="ml-2 tabular-nums">{fmtR(en.r_multiple)}</span>}
                </td>
                <td className="px-3 py-2 text-xs">
                  {en.early_exit_at ? (
                    <>
                      <div className="tabular-nums">
                        {fmtPrice(en.early_exit_price)} ({fmtR(en.early_exit_r)})
                      </div>
                      <div className="text-zinc-500">{en.early_exit_reason}</div>
                    </>
                  ) : en.decision === "entrei" ? (
                    <button className="text-sky-400 hover:underline" onClick={() => earlyExit(en)}>
                      Registrar
                    </button>
                  ) : (
                    <span className="text-zinc-600">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  <button className="text-xs text-zinc-500 hover:text-rose-400" onClick={() => remove(en)}>
                    Excluir
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatBox({ title, g }: { title: string; g: GroupStats | null | undefined }) {
  return (
    <Card title={title}>
      <div className="text-2xl font-semibold tabular-nums">{g ? fmtPct(g.taxa_acerto) : "—"}</div>
      <div className="text-xs text-zinc-500">
        {g ? `${g.alvo} alvo · ${g.invalidada} invalidadas · ${g.expirada} expiradas · ${g.aberta} abertas` : "sem registros"}
      </div>
    </Card>
  );
}

function StatsBar({ stats }: { stats: Stats | null }) {
  return (
    <div className="grid gap-3 md:grid-cols-4">
      <StatBox title="Acerto da tese (geral)" g={stats?.geral} />
      <StatBox title="Quando entrei" g={stats?.por_decisao["entrei"]} />
      <StatBox title="Quando não entrei" g={stats?.por_decisao["nao_entrei"]} />
      <StatBox title="Observando" g={stats?.por_decisao["observando"]} />
      <p className="text-[11px] text-zinc-600 md:col-span-4">
        Acerto da tese = alvo atingido antes da invalidação ÷ (alvo + invalidadas). Expiradas e abertas ficam fora da taxa.
        Em amostras pequenas a taxa oscila muito; olhe sempre o número de casos.
      </p>
    </div>
  );
}
