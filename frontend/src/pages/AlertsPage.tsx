import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  api,
  MARKET_LABEL,
  type AlertDirection,
  type AlertDraft,
  type AlertKind,
  type AlertResponse,
  type AlertsStatus,
  type Market,
  type PriceAlert,
} from "../api";
import TelegramCard from "../components/TelegramCard";
import { Badge, Card, Field, btnGhost, btnPrimary, inputCls, type Tone } from "../components/ui";
import { fmtDateTime, fmtNum, fmtPrice } from "../format";

const KIND_LABEL: Record<AlertKind, string> = {
  avulso: "Avulso",
  entrada: "Entrada",
  invalidacao: "Invalidação",
  alvo: "Alvo",
};
const KIND_TONE: Record<AlertKind, Tone> = { avulso: "sky", entrada: "zinc", invalidacao: "rose", alvo: "emerald" };
const RESPONSES: { value: AlertResponse; label: string }[] = [
  { value: "entrei", label: "Entrei" },
  { value: "ignorei", label: "Ignorei" },
  { value: "observando", label: "Observando" },
];
const POLL_MS = 15000;

const arrow = (d: AlertDirection) => (d === "acima" ? "↑" : "↓");
const TELEGRAM_MAX_TRIES = 6; // espelha MAX_TRIES do backend

/** Como a mensagem do Telegram deste alerta saiu (nada aparece se o envio estava desligado). */
function TelegramBadge({ a }: { a: PriceAlert }) {
  if (a.telegram_ok === true) return <Badge tone="sky">Telegram enviado</Badge>;
  if (a.telegram_ok === false) {
    const more = a.telegram_tries < TELEGRAM_MAX_TRIES;
    return (
      <span title={a.telegram_detail ?? undefined}>
        <Badge tone="amber">
          Telegram falhou ({a.telegram_tries}/{TELEGRAM_MAX_TRIES}){more ? ", tentando de novo" : ""}
        </Badge>
      </span>
    );
  }
  return null;
}

export default function AlertsPage({
  draft,
  onPending,
  onOpenAsset,
}: {
  draft: AlertDraft | null;
  onPending: (n: number) => void;
  onOpenAsset: (market: Market, symbol: string) => void;
}) {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [status, setStatus] = useState<AlertsStatus | null>(null);
  const [form, setForm] = useState({ market: "acoes" as Market, symbol: "", direction: "acima" as AlertDirection, price: "", note: "" });
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [a, s] = await Promise.all([api.alerts(), api.alertsStatus()]);
    setAlerts(a);
    setStatus(s);
    onPending(s.pending);
  }, [onPending]);

  useEffect(() => {
    const run = () => void load().catch(() => undefined);
    run();
    const t = window.setInterval(run, POLL_MS);
    return () => window.clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (!draft) return;
    setForm((f) => ({ ...f, market: draft.market, symbol: draft.symbol, price: String(draft.price) }));
  }, [draft]);

  async function act(action: () => Promise<string | void>) {
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
    void act(async () => {
      await api.createAlert({
        market: form.market,
        symbol: form.symbol,
        price: Number(form.price.replace(",", ".")),
        direction: form.direction,
        note: form.note,
      });
      setForm((f) => ({ ...f, price: "", note: "" }));
      return "Alerta criado.";
    });
  }

  const pending = alerts.filter((a) => a.status === "disparado" && a.response == null);
  const active = alerts.filter((a) => a.status === "ativo");
  const history = alerts.filter((a) => (a.status === "disparado" && a.response != null) || a.status === "cancelado").slice(0, 40);
  const w = status?.watcher;
  const errors = w ? Object.entries(w.errors) : [];

  return (
    <div className="space-y-6">
      <Card title="Alertas de preço">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={w?.running ? "emerald" : "amber"}>
            {w?.running ? `Vigilância ligada · a cada ${fmtNum(w.interval, 0)} s` : "Vigilância desligada"}
          </Badge>
          <Badge>Última verificação: {w?.last_cycle_at ? fmtDateTime(w.last_cycle_at) : "—"}</Badge>
          <Badge tone={status?.notifications.available ? "zinc" : "amber"}>
            {status?.notifications.available ? "Notificação do Windows disponível" : `Sem notificação: ${status?.notifications.detail ?? "—"}`}
          </Badge>
          <span className="ml-auto flex gap-2">
            <button className={btnGhost} disabled={busy} onClick={() => void act(async () => {
              const r = await api.checkAlertsNow();
              return r.fired.length ? `${r.fired.length} alerta(s) disparado(s).` : "Verificado: nenhum nível foi tocado.";
            })}>
              Verificar agora
            </button>
            <button className={btnGhost} disabled={busy} onClick={() => void act(async () => {
              const r = await api.testNotification();
              if (!r.ok) throw new Error(`A notificação não saiu: ${r.detail}`);
              return "Notificação de teste enviada. Se não apareceu, confira o modo Não incomodar do Windows.";
            })}>
              Testar notificação
            </button>
          </span>
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          A vigilância roda dentro do app: <b className="text-zinc-400">só vigia enquanto o app está aberto</b> (ao ligar, ela
          confere o que aconteceu enquanto esteve desligada). Um alerta "acima" dispara quando a <b>máxima</b> de uma barra de 1
          minuto toca o nível, e "abaixo" quando a <b>mínima</b> toca, então um pavio rápido também conta. O atraso do alerta é o
          atraso do dado. Nos testes de 22/10: cripto (Binance) e ações dos EUA (Yahoo) chegaram com ~1 min; forex, 1 a 2 min;
          ouro (futuro), DXY e índices europeus, 10 a 15 min.
        </p>
        {errors.length > 0 && (
          <ul className="mt-2 text-xs text-amber-300">
            {errors.map(([k, v]) => (
              <li key={k}>
                Não consegui verificar {k.replace(":", " · ")}: {v}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <TelegramCard onChanged={() => void load().catch(() => undefined)} />

      {msg && (
        <p
          className={`rounded-md border p-3 text-sm ${
            msg.tone === "ok" ? "border-emerald-900 bg-emerald-950/40 text-emerald-300" : "border-rose-900 bg-rose-950/50 text-rose-300"
          }`}
        >
          {msg.text}
        </p>
      )}

      <Card title="Novo alerta">
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-6">
          <Field label="Mercado">
            <select className={inputCls} value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value as Market })}>
              {(Object.keys(MARKET_LABEL) as Market[]).map((m) => (
                <option key={m} value={m}>
                  {MARKET_LABEL[m]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Símbolo">
            <input className={inputCls} value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} required />
          </Field>
          <Field label="Avisar quando tocar">
            <select
              className={inputCls}
              value={form.direction}
              onChange={(e) => setForm({ ...form, direction: e.target.value as AlertDirection })}
            >
              <option value="acima">↑ por cima (máxima)</option>
              <option value="abaixo">↓ por baixo (mínima)</option>
            </select>
          </Field>
          <Field label="Preço">
            <input className={inputCls} inputMode="decimal" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} required />
          </Field>
          <Field label="Nota (opcional)" className="md:col-span-2">
            <input className={inputCls} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} maxLength={200} />
          </Field>
          <div className="md:col-span-6">
            <button type="submit" className={btnPrimary} disabled={busy}>
              Criar alerta
            </button>
            <span className="ml-3 text-xs text-zinc-500">
              A direção precisa combinar com o preço atual (acima só se o preço está abaixo do nível). Os níveis do plano do diário
              viram alertas sozinhos.
            </span>
          </div>
        </form>
      </Card>

      {pending.length > 0 && (
        <Card title={`Disparados: o que você fez? (${pending.length})`} className="border-amber-900">
          <ul className="space-y-3">
            {pending.map((a) => (
              <li key={a.id} className="rounded-md border border-zinc-800 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <button className="font-semibold hover:underline" onClick={() => onOpenAsset(a.market, a.symbol)}>
                    {a.symbol}
                  </button>
                  <Badge tone={KIND_TONE[a.kind]}>{KIND_LABEL[a.kind]}</Badge>
                  <span className="text-sm">
                    {arrow(a.direction)} tocou {fmtPrice(a.price)}{" "}
                    <span className="text-zinc-500">
                      ({a.direction === "acima" ? "máxima" : "mínima"} {fmtPrice(a.triggered_price)} na barra de {fmtDateTime(a.trigger_bar)})
                    </span>
                  </span>
                  {a.notify_ok === false && <Badge tone="amber">notificação falhou</Badge>}
                  <TelegramBadge a={a} />
                </div>
                {a.telegram_ok === false && a.telegram_detail && <div className="mt-1 text-xs text-amber-300">{a.telegram_detail}</div>}
                {a.note && <div className="mt-1 text-xs text-zinc-400">{a.note}</div>}
                <div className="mt-2 flex gap-2">
                  {RESPONSES.map((r) => (
                    <button key={r.value} className={btnGhost} disabled={busy} onClick={() => void act(async () => { await api.respondAlert(a.id, r.value); })}>
                      {r.label}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={`Ativos (${active.length})`}>
        {active.length === 0 ? (
          <p className="text-sm text-zinc-500">Nenhum alerta ativo.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-zinc-500">
                <tr>
                  <th className="pb-2 font-normal">Ativo</th>
                  <th className="pb-2 font-normal">Tipo</th>
                  <th className="pb-2 text-right font-normal">Nível</th>
                  <th className="pb-2 text-right font-normal">Falta</th>
                  <th className="pb-2 text-right font-normal">Último preço visto</th>
                  <th className="pb-2 pl-4 font-normal">Nota</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {active.map((a) => (
                  <tr key={a.id}>
                    <td className="py-2 pr-3">
                      <button className="font-medium hover:underline" onClick={() => onOpenAsset(a.market, a.symbol)}>
                        {a.symbol}
                      </button>
                      <div className="text-xs text-zinc-500">{MARKET_LABEL[a.market]}</div>
                    </td>
                    <td className="py-2 pr-3">
                      <Badge tone={KIND_TONE[a.kind]}>{KIND_LABEL[a.kind]}</Badge>
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {arrow(a.direction)} {fmtPrice(a.price)}
                    </td>
                    <td className="py-2 text-right tabular-nums text-zinc-400">
                      {a.distance_pct == null ? "—" : `${a.distance_pct > 0 ? "+" : ""}${fmtNum(a.distance_pct, 2)}%`}
                    </td>
                    <td className="py-2 text-right tabular-nums text-zinc-400">
                      {a.last_price == null ? "aguardando" : fmtPrice(a.last_price)}
                      {a.last_checked_at && <div className="text-[11px] text-zinc-600">{fmtDateTime(a.last_checked_at)}</div>}
                    </td>
                    <td className="max-w-xs truncate py-2 pl-4 text-xs text-zinc-400" title={a.note}>
                      {a.note}
                    </td>
                    <td className="py-2 text-right">
                      <button className="text-xs text-zinc-500 hover:text-rose-400" disabled={busy} onClick={() => void act(async () => { await api.cancelAlert(a.id); })}>
                        Cancelar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {history.length > 0 && (
        <Card title="Histórico">
          <ul className="space-y-1.5 text-sm">
            {history.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2">
                <span className="w-24 font-medium">{a.symbol}</span>
                <Badge tone={KIND_TONE[a.kind]}>{KIND_LABEL[a.kind]}</Badge>
                <span className="tabular-nums text-zinc-300">
                  {arrow(a.direction)} {fmtPrice(a.price)}
                </span>
                {a.status === "disparado" ? (
                  <span className="text-xs text-zinc-500">
                    tocou em {fmtDateTime(a.trigger_bar)} · você: <b className="text-zinc-300">{a.response}</b>
                    {a.telegram_ok === true && " · Telegram ✓"}
                    {a.telegram_ok === false && " · Telegram ✗"}
                  </span>
                ) : (
                  <span className="text-xs text-zinc-600">cancelado · {a.cancel_reason}</span>
                )}
                <button
                  className="ml-auto text-xs text-zinc-600 hover:text-rose-400"
                  onClick={() => void act(async () => { await api.deleteAlert(a.id); })}
                >
                  remover
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
