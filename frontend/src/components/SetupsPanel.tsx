import { useState } from "react";
import {
  api,
  MARKET_LABEL,
  type ConditionSpec,
  type Direction,
  type Market,
  type Setup,
  type SetupCondition,
  type Timeframe,
  TIMEFRAME_LABEL,
} from "../api";
import { Badge, Card, Field, btnGhost, btnPrimary, inputCls, inputSm } from "./ui";

const MARKETS = Object.keys(MARKET_LABEL) as Market[];

interface CondDraft {
  type: string;
  params: Record<string, string>;
}

interface Draft {
  name: string;
  enabled: boolean;
  direction: Direction;
  markets: Market[];
  timeframe: Timeframe;
  required: CondDraft[];
  confirmations: CondDraft[];
  minConfirmations: string;
  minPrice: string;
  minDollarVolumeM: string; // em milhões de dólares por dia
}

const num = (s: string) => Number(s.replace(",", "."));

/** Uma cópia de um setup, já no outro timeframe: o caminho curto para ter a versão H4 (ou D1) das mesmas condições. */
interface Copy {
  from: Setup;
  timeframe: Timeframe;
}

function toDraft(s: Setup | null, catalog: ConditionSpec[], copy?: Copy): Draft {
  const conv = (c: SetupCondition): CondDraft => ({
    type: c.type,
    params: Object.fromEntries(Object.entries(c.params).map(([k, v]) => [k, String(v)])),
  });
  if (!s) {
    const first = catalog[0];
    return {
      name: "",
      enabled: true,
      direction: "alta",
      markets: [...MARKETS],
      timeframe: "D1",
      required: first ? [defaultCond(first)] : [],
      confirmations: [],
      minConfirmations: "0",
      minPrice: "5",
      minDollarVolumeM: "20",
    };
  }
  const f = s.definition.filters;
  return {
    name: copy ? `${s.name} (${copy.timeframe})` : s.name,
    enabled: s.enabled,
    direction: s.direction,
    markets: s.markets,
    timeframe: copy ? copy.timeframe : s.timeframe,
    required: s.definition.required.map(conv),
    confirmations: s.definition.confirmations.map(conv),
    minConfirmations: String(s.definition.min_confirmations),
    minPrice: String(f.min_price),
    minDollarVolumeM: String(f.min_dollar_volume / 1e6),
  };
}

function defaultCond(spec: ConditionSpec): CondDraft {
  return { type: spec.id, params: Object.fromEntries(spec.params.map((p) => [p.name, String(p.default)])) };
}

function condText(c: SetupCondition, catalog: ConditionSpec[]): string {
  const spec = catalog.find((s) => s.id === c.type);
  if (!spec) return c.type;
  const params = spec.params.map((p) => `${p.label} ${c.params[p.name] ?? p.default}`).join(", ");
  return params ? `${spec.title} (${params})` : spec.title;
}

export default function SetupsPanel({
  setups,
  catalog,
  onChanged,
}: {
  setups: Setup[];
  catalog: ConditionSpec[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<Setup | "new" | Copy | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(s: Setup) {
    setError(null);
    try {
      await api.saveSetup(s.id, { ...s, enabled: !s.enabled });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function remove(s: Setup) {
    if (!window.confirm(`Excluir o setup "${s.name}"?`)) return;
    setError(null);
    try {
      await api.deleteSetup(s.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Card title="Setups">
      <p className="mb-3 text-xs text-zinc-500">
        Um setup é um conjunto de condições na última barra fechada do timeframe escolhido (diário ou 4 horas): todas as
        obrigatórias precisam bater, mais um mínimo das confirmações. Os três iniciais vêm das regras do scanner antigo (sem
        score, em timeframe diário). Não há evidência de que elas superem o acaso: o diário é que vai medir.
      </p>
      <p className="mb-3 text-xs text-zinc-500">
        <span className="text-zinc-400">Barras de 4 horas:</span> ações usam 09:30–13:30 e 13:30–16:00 (Nova York); forex e ouro,
        blocos de 4 h a partir das 17:00 de Nova York; cripto, a grade UTC da Binance (00, 04, 08, 12, 16, 20). Só entram barras já
        fechadas. Nas condições, "barras" são dias em D1 e barras de 4 h em H4, e o volume em H4 é comparado com o mesmo horário do dia.
      </p>
      {error && <p className="mb-3 rounded-md border border-rose-900 bg-rose-950/50 p-2 text-sm text-rose-300">{error}</p>}

      {editing ? (
        <SetupEditor
          key={editing === "new" ? "new" : "from" in editing ? `copy:${editing.from.id}` : editing.id}
          initial={editing === "new" || "from" in editing ? null : editing}
          copy={editing !== "new" && "from" in editing ? editing : undefined}
          catalog={catalog}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      ) : (
        <>
          <ul className="space-y-2">
            {setups.map((s) => (
              <li key={s.id} className="rounded-md border border-zinc-800 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <input type="checkbox" checked={s.enabled} onChange={() => void toggle(s)} />
                    {s.name}
                    <Badge tone={s.timeframe === "H4" ? "amber" : "zinc"}>{s.timeframe}</Badge>
                    <Badge tone={s.direction === "alta" ? "emerald" : "rose"}>{s.direction}</Badge>
                    {s.markets.map((m) => (
                      <Badge key={m}>{MARKET_LABEL[m]}</Badge>
                    ))}
                  </label>
                  <span className="flex gap-3 text-xs">
                    <button className="text-sky-400 hover:underline" onClick={() => setEditing(s)}>
                      Editar
                    </button>
                    <button
                      className="text-sky-400 hover:underline"
                      title="Abre um novo setup com as mesmas condições no outro timeframe"
                      onClick={() => setEditing({ from: s, timeframe: s.timeframe === "H4" ? "D1" : "H4" })}
                    >
                      Duplicar em {s.timeframe === "H4" ? "D1" : "H4"}
                    </button>
                    <button className="text-zinc-500 hover:text-rose-400" onClick={() => void remove(s)}>
                      Excluir
                    </button>
                  </span>
                </div>
                <div className="mt-2 text-xs text-zinc-400">
                  <div>
                    <span className="text-zinc-500">Obrigatórias:</span>{" "}
                    {s.definition.required.map((c) => condText(c, catalog)).join(" · ") || "—"}
                  </div>
                  <div>
                    <span className="text-zinc-500">
                      Confirmações (mín. {s.definition.min_confirmations}):
                    </span>{" "}
                    {s.definition.confirmations.map((c) => condText(c, catalog)).join(" · ") || "—"}
                  </div>
                  <div className="text-zinc-500">
                    Ações: preço ≥ US$ {s.definition.filters.min_price} e liquidez ≥ US${" "}
                    {s.definition.filters.min_dollar_volume / 1e6} mi/dia
                  </div>
                </div>
              </li>
            ))}
            {setups.length === 0 && <li className="text-sm text-zinc-500">Nenhum setup. Crie um para poder varrer.</li>}
          </ul>
          <button className={`${btnGhost} mt-3`} onClick={() => setEditing("new")}>
            Novo setup
          </button>
        </>
      )}
    </Card>
  );
}

function SetupEditor({
  initial,
  copy,
  catalog,
  onCancel,
  onSaved,
}: {
  initial: Setup | null;
  copy?: Copy;
  catalog: ConditionSpec[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [d, setD] = useState<Draft>(() => toDraft(initial ?? copy?.from ?? null, catalog, copy));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));

  const toggleMarket = (m: Market) =>
    set("markets", d.markets.includes(m) ? d.markets.filter((x) => x !== m) : [...d.markets, m]);

  async function save() {
    setBusy(true);
    setError(null);
    const conv = (c: CondDraft): SetupCondition => ({
      type: c.type,
      params: Object.fromEntries(Object.entries(c.params).map(([k, v]) => [k, num(v)])),
    });
    try {
      await api.saveSetup(initial?.id ?? null, {
        name: d.name.trim(),
        enabled: d.enabled,
        direction: d.direction,
        markets: d.markets,
        timeframe: d.timeframe,
        definition: {
          required: d.required.map(conv),
          confirmations: d.confirmations.map(conv),
          min_confirmations: Number(d.minConfirmations),
          filters: { min_price: num(d.minPrice) || 0, min_dollar_volume: (num(d.minDollarVolumeM) || 0) * 1e6 },
        },
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-5">
        <Field label="Nome" className="md:col-span-2">
          <input className={inputCls} value={d.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Direção">
          <select className={inputCls} value={d.direction} onChange={(e) => set("direction", e.target.value as Direction)}>
            <option value="alta">Alta</option>
            <option value="baixa">Baixa</option>
          </select>
        </Field>
        <Field label="Timeframe">
          <select className={inputCls} value={d.timeframe} onChange={(e) => set("timeframe", e.target.value as Timeframe)}>
            {(Object.keys(TIMEFRAME_LABEL) as Timeframe[]).map((t) => (
              <option key={t} value={t}>
                {t} · {TIMEFRAME_LABEL[t]}
              </option>
            ))}
          </select>
        </Field>
        <div className="text-xs text-zinc-400">
          <span className="mb-1 block">Mercados</span>
          <div className="flex gap-3 pt-2">
            {MARKETS.map((m) => (
              <label key={m} className="flex items-center gap-1">
                <input type="checkbox" checked={d.markets.includes(m)} onChange={() => toggleMarket(m)} />
                {MARKET_LABEL[m]}
              </label>
            ))}
          </div>
        </div>
      </div>

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Obrigatórias (todas)</h4>
        <ConditionRows catalog={catalog} items={d.required} onChange={(v) => set("required", v)} />
      </div>
      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Confirmações</h4>
        <ConditionRows catalog={catalog} items={d.confirmations} onChange={(v) => set("confirmations", v)} />
        <label className="mt-2 flex items-center gap-2 text-xs text-zinc-400">
          Mínimo de confirmações que precisam bater:
          <input
            className={`${inputSm} w-16`}
            type="number"
            min={0}
            max={d.confirmations.length}
            value={d.minConfirmations}
            onChange={(e) => set("minConfirmations", e.target.value)}
          />
          <span className="text-zinc-500">(de {d.confirmations.length})</span>
        </label>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Ações: preço mínimo (US$)" className="w-44">
          <input className={inputCls} inputMode="decimal" value={d.minPrice} onChange={(e) => set("minPrice", e.target.value)} />
        </Field>
        <Field label="Ações: liquidez mínima (US$ mi/dia)" className="w-60">
          <input
            className={inputCls}
            inputMode="decimal"
            value={d.minDollarVolumeM}
            onChange={(e) => set("minDollarVolumeM", e.target.value)}
          />
        </Field>
        <p className="pb-2 text-xs text-zinc-500">Os filtros valem só para ações (cripto já vem filtrada por volume; forex não tem volume).</p>
      </div>

      {error && <p className="rounded-md border border-rose-900 bg-rose-950/50 p-2 text-sm text-rose-300">{error}</p>}
      <div className="flex gap-2">
        <button className={btnPrimary} onClick={() => void save()} disabled={busy}>
          Salvar setup
        </button>
        <button className={btnGhost} onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}

function ConditionRows({
  catalog,
  items,
  onChange,
}: {
  catalog: ConditionSpec[];
  items: CondDraft[];
  onChange: (v: CondDraft[]) => void;
}) {
  const replace = (i: number, c: CondDraft) => onChange(items.map((x, j) => (j === i ? c : x)));
  return (
    <div className="space-y-2">
      {items.map((c, i) => {
        const spec = catalog.find((s) => s.id === c.type);
        return (
          <div key={i} className="flex flex-wrap items-end gap-2">
            <select
              className={`${inputSm} w-60`}
              value={c.type}
              onChange={(e) => {
                const next = catalog.find((s) => s.id === e.target.value);
                if (next) replace(i, defaultCond(next));
              }}
            >
              {catalog.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
            {spec?.params.map((p) => (
              <label key={p.name} className="text-[11px] text-zinc-500">
                <span className="block">{p.label}</span>
                <input
                  className={`${inputSm} w-24`}
                  type="number"
                  step={p.step}
                  min={p.min ?? undefined}
                  max={p.max ?? undefined}
                  value={c.params[p.name] ?? String(p.default)}
                  onChange={(e) => replace(i, { ...c, params: { ...c.params, [p.name]: e.target.value } })}
                />
              </label>
            ))}
            {spec?.needs_volume && <span className="pb-2 text-[11px] text-zinc-500">ignorada onde não há volume (forex)</span>}
            <button
              type="button"
              className="pb-2 text-xs text-zinc-500 hover:text-rose-400"
              onClick={() => onChange(items.filter((_, j) => j !== i))}
            >
              remover
            </button>
          </div>
        );
      })}
      <button
        type="button"
        className="text-xs text-sky-400 hover:underline"
        onClick={() => catalog[0] && onChange([...items, defaultCond(catalog[0])])}
      >
        + condição
      </button>
    </div>
  );
}
