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

/** Data (UTC) de uma barra diária: o rótulo da barra cai em horários diferentes conforme a bolsa. */
export function fmtDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("pt-BR", { timeZone: "UTC" }) : "—";
}

/** Arredonda um preço para ~6 algarismos significativos (sugestões de nível). */
export function roundPrice(n: number): number {
  return Number(n.toPrecision(6));
}
