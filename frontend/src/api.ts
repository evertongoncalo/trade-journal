export type Market = "acoes" | "cripto" | "forex";
export type Decision = "entrei" | "nao_entrei" | "observando";
export type Direction = "alta" | "baixa";
export type Status = "aberta" | "alvo" | "invalidada" | "expirada";
export type ProbLabel = "alta" | "baixa" | "indistinta" | "sem dados";

export const MARKET_LABEL: Record<Market, string> = { acoes: "Ações", cripto: "Cripto", forex: "Forex" };
export const DECISION_LABEL: Record<Decision, string> = {
  entrei: "Entrei",
  nao_entrei: "Não entrei",
  observando: "Observando",
};

export interface Health {
  source: string;
  symbol_at_source: string;
  interval: string;
  last_bar_utc: string | null;
  last_bar_age_minutes: number | null;
  note: string;
}

export interface Snapshot {
  close: number;
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  atr14: number | null;
  atr_pct: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  bb_pctb: number | null;
  trend: "alta" | "baixa" | "lateral" | "indefinida";
  volume_ratio: number | null;
  bars: number;
}

export interface StateRow {
  state_label: string;
  is_current: boolean;
  n: number;
  p_up: number | null;
  ci: [number, number] | null;
  lift_pp: number | null;
  label: ProbLabel;
}

export interface Probability {
  horizon_days: number;
  min_n: number;
  state_label: string | null;
  n: number;
  p_up: number | null;
  ci: [number, number] | null;
  base: number | null;
  lift_pp: number | null;
  label: ProbLabel;
  reason: string;
  history_bars: number;
  history_start: string | null;
  all_states: StateRow[];
}

export interface Asset {
  market: Market;
  symbol: string;
  price: number;
  price_time: string | null;
  tradingview_symbol: string;
  health: { daily: Health; intraday: Health | null };
  snapshot: Snapshot;
  probability: Probability;
}

export interface Entry {
  id: number;
  created_at: string;
  market: Market;
  symbol: string;
  decision: Decision;
  direction: Direction;
  entry_price: number;
  invalidation: number;
  target: number;
  horizon_days: number;
  thesis: string;
  setup: string;
  snapshot: Record<string, unknown>;
  status: Status;
  closed_at: string | null;
  exit_price: number | null;
  r_multiple: number | null;
  early_exit_at: string | null;
  early_exit_price: number | null;
  early_exit_reason: string | null;
  early_exit_r: number | null;
  last_evaluated_at: string | null;
  risk: number;
}

export interface NewEntry {
  market: Market;
  symbol: string;
  decision: Decision;
  direction: Direction;
  entry_price: number;
  invalidation: number;
  target: number;
  horizon_days: number;
  thesis: string;
  setup: string;
  snapshot: Record<string, unknown>;
}

/** Rascunho levado da ficha do ativo para o formulário do diário. */
export interface Draft {
  market: Market;
  symbol: string;
  direction: Direction;
  entry_price: number;
  invalidation: number;
  target: number;
  snapshot: Record<string, unknown>;
}

export interface GroupStats {
  alvo: number;
  invalidada: number;
  expirada: number;
  aberta: number;
  fechadas: number;
  taxa_acerto: number | null;
}

export interface Stats {
  total: number;
  geral: GroupStats | null;
  por_decisao: Record<string, GroupStats>;
  por_mercado: Record<string, GroupStats>;
  saida_antecipada: number;
}

export interface RefreshResult {
  avaliadas: number;
  encerradas: number;
  erros: { symbol: string; erro: string }[];
}

export type PairStatus = "estável" | "sem relação estável" | "mecânica" | "sem dados";

export interface PairRow {
  symbol: string;
  label: string;
  mechanical: boolean;
  status: PairStatus;
  n: number;
  corr_full?: number | null;
  corr_250?: number | null;
  corr_60?: number | null;
  corr_20?: number | null;
  roll_min?: number | null;
  roll_max?: number | null;
  stability?: number | null;
  weekly?: number | null;
  beta?: number | null;
  move20_target?: number | null;
  move20_other?: number | null;
  other_unit?: "%" | "pts";
  agree?: "concordam" | "divergem" | "indefinido";
  z20?: number | null;
}

export interface Parecer {
  lines: string[];
  refs_used: string[];
  r2: number | null;
  r2_first: number | null;
  expected20_pp: number | null;
  actual20_pp: number | null;
  gap20_pp: number | null;
  z20: number | null;
}

export interface CorrCharts {
  rebased: { dates: string[]; series: Record<string, number[]> } | null;
  rolling: { dates: string[]; series: Record<string, (number | null)[]> } | null;
  scatter: {
    ref: string;
    points: [number, number][];
    recent: [number, number][];
    slope: number;
    intercept: number;
  } | null;
}

export interface UniverseState {
  state: "vazio" | "ok" | "desatualizado";
  symbols: number;
  expected: number;
  updated_at: string | null;
  missing: string[];
}

export interface RefreshStatus {
  state: "idle" | "running" | "done" | "error";
  done: number;
  total: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  missing: string[];
}

export interface CorrelationData {
  target: { symbol: string; yahoo: string; market: Market; observations: number; first: string | null; last: string | null };
  universe: UniverseState;
  refresh: RefreshStatus;
  params: { roll_days: number; recent_days: number; stable_share: number; min_abs_corr: number; min_obs: number; alignment: string };
  fixed: PairRow[];
  discovered: { name: string; items: PairRow[] }[];
  parecer: Parecer | null;
  charts: CorrCharts;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
    } catch {
      /* resposta sem JSON */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  asset: (market: Market, symbol: string, horizon: number) =>
    request<Asset>(`/api/asset/${market}/${encodeURIComponent(symbol)}?horizon=${horizon}`),
  entries: () => request<Entry[]>("/api/journal"),
  stats: () => request<Stats>("/api/journal/stats"),
  createEntry: (body: NewEntry) => request<Entry>("/api/journal", { method: "POST", body: JSON.stringify(body) }),
  refresh: () => request<RefreshResult>("/api/journal/refresh", { method: "POST" }),
  earlyExit: (id: number, price: number, reason: string) =>
    request<Entry>(`/api/journal/${id}/early-exit`, { method: "POST", body: JSON.stringify({ price, reason }) }),
  remove: (id: number) => request<void>(`/api/journal/${id}`, { method: "DELETE" }),
  correlation: (market: Market, symbol: string) =>
    request<CorrelationData>(`/api/correlation/${market}/${encodeURIComponent(symbol)}`),
  correlationStatus: () => request<{ refresh: RefreshStatus; universe: UniverseState }>("/api/correlation/status"),
  correlationRefresh: () =>
    request<{ started: boolean; refresh: RefreshStatus }>("/api/correlation/refresh", { method: "POST" }),
};
