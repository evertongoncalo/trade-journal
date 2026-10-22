import { useEffect, useRef } from "react";

/**
 * Widget "Advanced Chart" do TradingView (gratuito, hospedado por eles; o script monta o iframe).
 * Só exibição: o app não lê os valores do gráfico nem desenha níveis nele.
 */
export default function TradingViewChart({
  symbol,
  height = 520,
  interval = "D",
}: {
  symbol: string;
  height?: number;
  /** "D" (diário) ou "240" (4 horas). */
  interval?: "D" | "240";
}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    el.innerHTML = "";
    const inner = document.createElement("div");
    inner.className = "tradingview-widget-container__widget";
    inner.style.height = "100%";
    inner.style.width = "100%";
    el.appendChild(inner);

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.type = "text/javascript";
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "br",
      allow_symbol_change: false,
      calendar: false,
      support_host: "https://www.tradingview.com",
    });
    el.appendChild(script);
    return () => {
      el.innerHTML = "";
    };
  }, [symbol, interval]);

  return (
    <div
      ref={host}
      className="tradingview-widget-container overflow-hidden rounded-lg border border-zinc-800"
      style={{ height, width: "100%" }}
    />
  );
}
