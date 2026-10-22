import { useState } from "react";
import type { Draft } from "./api";
import AssetPage from "./pages/AssetPage";
import JournalPage from "./pages/JournalPage";

type Tab = "ativo" | "diario";

export default function App() {
  const [tab, setTab] = useState<Tab>("ativo");
  const [draft, setDraft] = useState<Draft | null>(null);

  const tabCls = (t: Tab) =>
    `rounded-md px-3 py-1.5 text-sm font-medium ${
      tab === t ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
    }`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800 bg-zinc-950/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <h1 className="text-base font-semibold tracking-tight">
            Trade Journal <span className="font-normal text-zinc-500">· análise e diário de decisões</span>
          </h1>
          <nav className="flex gap-1">
            <button className={tabCls("ativo")} onClick={() => setTab("ativo")}>
              Ativo
            </button>
            <button className={tabCls("diario")} onClick={() => setTab("diario")}>
              Diário
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        {/* As duas páginas ficam montadas para não perder o estado ao trocar de aba. */}
        <div hidden={tab !== "ativo"}>
          <AssetPage
            onRegister={(d) => {
              setDraft(d);
              setTab("diario");
            }}
          />
        </div>
        <div hidden={tab !== "diario"}>
          <JournalPage draft={draft} />
        </div>
      </main>
    </div>
  );
}
