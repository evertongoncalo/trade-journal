import type { ReactNode } from "react";

export const inputCls =
  "w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-emerald-500 focus:outline-none";
export const btnPrimary =
  "rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50";
export const btnGhost =
  "rounded-md border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50";

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 ${className}`}>
      {title && <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-400">{title}</h3>}
      {children}
    </section>
  );
}

const TONES = {
  emerald: "border-emerald-800 bg-emerald-950 text-emerald-300",
  rose: "border-rose-800 bg-rose-950 text-rose-300",
  amber: "border-amber-800 bg-amber-950 text-amber-300",
  sky: "border-sky-800 bg-sky-950 text-sky-300",
  zinc: "border-zinc-700 bg-zinc-800 text-zinc-300",
} as const;

export type Tone = keyof typeof TONES;

export function Badge({ tone = "zinc", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function Field({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block text-xs text-zinc-400 ${className}`}>
      <span className="mb-1 block">{label}</span>
      {children}
    </label>
  );
}
