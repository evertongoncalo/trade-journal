type Maybe = number | null | undefined;

export function fmtPrice(n: Maybe): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  const digits = abs >= 100 ? 2 : abs >= 1 ? 4 : 6;
  return n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: digits });
}

export function fmtNum(n: Maybe, digits = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPct(p: Maybe, digits = 0): string {
  if (p == null) return "—";
  return `${(p * 100).toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

export function fmtR(r: Maybe): string {
  if (r == null) return "—";
  return `${r > 0 ? "+" : ""}${fmtNum(r, 2)} R`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";
}

export function fmtUsd(n: Maybe): string {
  if (n == null) return "—";
  return `US$ ${n.toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 4 })}`;
}

/** Data (UTC) de uma barra diária: o rótulo da barra cai em horários diferentes conforme a bolsa. */
export function fmtDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("pt-BR", { timeZone: "UTC" }) : "—";
}

/** Horário de uma barra H4 no fuso da grade do mercado: Nova York para ações e forex, UTC para cripto. */
export function fmtBar(iso: string | null | undefined, market: string): string {
  if (!iso) return "—";
  const crypto = market === "cripto";
  const text = new Date(iso).toLocaleString("pt-BR", {
    timeZone: crypto ? "UTC" : "America/New_York",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${text} ${crypto ? "UTC" : "NY"}`;
}

/** Arredonda um preço para ~6 algarismos significativos (sugestões de nível). */
export function roundPrice(n: number): number {
  return Number(n.toPrecision(6));
}
