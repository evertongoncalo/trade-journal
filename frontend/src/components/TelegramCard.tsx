import { useCallback, useEffect, useState } from "react";
import { api, type TelegramChat, type TelegramStatus } from "../api";
import { fmtDateTime } from "../format";
import { Badge, Card, btnGhost, btnPrimary } from "./ui";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Alertas no Telegram: o bot é do usuário (token no .env); aqui ele vincula a conversa, testa e liga ou desliga o envio. */
export default function TelegramCard({ onChanged }: { onChanged?: () => void }) {
  const [s, setS] = useState<TelegramStatus | null>(null);
  const [chats, setChats] = useState<TelegramChat[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setS(await api.telegramStatus());
    } catch (e) {
      setMsg({ tone: "err", text: errText(e) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(action: () => Promise<string | void>) {
    setBusy(true);
    setMsg(null);
    try {
      const text = await action();
      await load();
      onChanged?.();
      if (text) setMsg({ tone: "ok", text });
    } catch (e) {
      setMsg({ tone: "err", text: errText(e) });
    } finally {
      setBusy(false);
    }
  }

  if (!s) return null;

  return (
    <Card title="Alertas no Telegram">
      <div className="flex flex-wrap items-center gap-2">
        {!s.token_configured ? (
          <Badge tone="amber">Sem token no .env</Badge>
        ) : s.error ? (
          <Badge tone="rose">Token com problema</Badge>
        ) : (
          <Badge tone="sky">Bot @{s.bot?.username}</Badge>
        )}
        {s.chat ? (
          <Badge tone={s.ready ? "emerald" : "zinc"}>
            {s.ready ? "Enviando para" : "Envio desligado para"} {s.chat.label}
          </Badge>
        ) : (
          s.token_configured && !s.error && <Badge tone="amber">Nenhuma conversa vinculada</Badge>
        )}
        {s.chat?.source === "env" && <span className="text-xs text-zinc-500">(TELEGRAM_CHAT_ID no .env)</span>}
      </div>

      {s.error && <p className="mt-3 rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">{s.error}</p>}

      {!s.token_configured && (
        <ol className="mt-3 list-inside list-decimal space-y-1 text-xs text-zinc-400">
          <li>
            No Telegram, abra o <b className="text-zinc-300">@BotFather</b>, envie <code>/newbot</code> e siga os passos. Ele devolve um token.
          </li>
          <li>
            Cole o token no arquivo <code>.env</code> do app como <code>TELEGRAM_BOT_TOKEN=...</code> e <b className="text-zinc-300">reinicie o app</b>.
            O token fica só nesse arquivo: o app nunca o mostra nem o grava no diário ou no git.
          </li>
          <li>Volte aqui para vincular a sua conversa.</li>
        </ol>
      )}

      {s.token_configured && !s.error && !s.chat && (
        <div className="mt-3 space-y-3">
          <ol className="list-inside list-decimal space-y-1 text-xs text-zinc-400">
            <li>
              Abra o seu bot no Telegram (@{s.bot?.username}) e envie qualquer mensagem, por exemplo <code>/start</code>.
            </li>
            <li>Clique em "Procurar conversas" e vincule a SUA conversa.</li>
          </ol>
          <button
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const r = await api.telegramDiscover();
                setChats(r.chats);
                if (r.chats.length === 0) return "Nenhuma conversa encontrada: mande uma mensagem ao bot e procure de novo (o Telegram guarda as das últimas 24 h).";
              })
            }
          >
            Procurar conversas
          </button>
          {chats && chats.length > 0 && (
            <ul className="space-y-2">
              {chats.map((c) => (
                <li key={c.chat_id} className="flex flex-wrap items-center gap-3 rounded-md border border-zinc-800 p-2 text-sm">
                  <span className="font-medium">{c.rotulo}</span>
                  <Badge>{c.tipo}</Badge>
                  <span className="min-w-0 flex-1 truncate text-xs text-zinc-500">
                    “{c.ultima_mensagem}” · {fmtDateTime(c.quando)}
                  </span>
                  <button
                    className={btnPrimary}
                    disabled={busy}
                    onClick={() =>
                      void act(async () => {
                        await api.telegramLink(c.chat_id);
                        setChats(null);
                        return "Conversa vinculada: uma mensagem de confirmação foi enviada a ela.";
                      })
                    }
                  >
                    Vincular
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="text-[11px] text-zinc-600">
            O app lista as conversas e deixa você escolher, em vez de pegar a mais recente: qualquer pessoa que descubra o bot pode
            escrever a ele, e só a conversa vinculada recebe os alertas.
          </p>
        </div>
      )}

      {s.chat && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={s.enabled}
                disabled={busy}
                onChange={(e) => void act(async () => void (await api.telegramOptions({ enabled: e.target.checked })))}
              />
              Enviar os alertas disparados ao Telegram
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={s.include_note}
                disabled={busy}
                onChange={(e) => void act(async () => void (await api.telegramOptions({ include_note: e.target.checked })))}
              />
              Incluir a nota do alerta
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className={btnGhost}
              disabled={busy || !s.bot}
              onClick={() =>
                void act(async () => {
                  await api.telegramTest();
                  return "Mensagem de teste enviada. Confira o Telegram.";
                })
              }
            >
              Enviar mensagem de teste
            </button>
            {s.chat.source === "app" && (
              <button
                className={btnGhost}
                disabled={busy}
                onClick={() => void act(async () => void (await api.telegramUnlink()))}
              >
                Desvincular
              </button>
            )}
          </div>
        </div>
      )}

      {msg && (
        <p
          className={`mt-3 rounded-md border p-3 text-sm ${
            msg.tone === "ok" ? "border-emerald-900 bg-emerald-950/40 text-emerald-300" : "border-rose-900 bg-rose-950/50 text-rose-300"
          }`}
        >
          {msg.text}
        </p>
      )}

      <p className="mt-3 text-[11px] leading-relaxed text-zinc-600">
        Cada alerta disparado vira também uma mensagem no seu bot: ativo, nível, o preço tocado, o horário da barra e a nota. Nos alertas do
        plano a nota começa com um trecho da tese; desmarque "Incluir a nota" se não quiser isso fora do computador. As mensagens passam
        pelos servidores do Telegram (não são ponta a ponta). Se o envio falhar, o app tenta de novo com espera crescente (até 6 tentativas) e
        mostra o resultado em cada alerta. Como o resto da vigilância, <b className="text-zinc-500">só funciona com o app aberto</b>; o app
        só envia mensagens: não lê nem responde ao que você escrever ao bot.
      </p>
    </Card>
  );
}
