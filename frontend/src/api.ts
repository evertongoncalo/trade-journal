export type Market = "acoes" | "cripto" | "forex";
export type Decision = "entrei" | "nao_entrei" | "observando";
export type Direction = "alta" | "baixa";
export type Status = "aberta" | "alvo" | "invalidada" | "expirada";
export type Timeframe = "D1" | "H4";
export const TIMEFRAME_LABEL: Record<Timeframe, string> = { D1: "Diário", H4: "4 horas" };
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
  /** Resumo da estrutura de preço; vai no snapshot do diário. null se o histórico não permitiu. */
  price_action: {
    estrutura: string;
    variacao_pct: Record<string, number | null>;
    posicao_no_range_52s: number | null;
    dist_maxima_52s_pct: number | null;
    dist_minima_52s_pct: number | null;
  } | null;
}

export type PmTrigger = "invalidada" | "saida_antecipada" | "ambos";

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
  /** Por que o caso pede pós-mortem (null: não pede). */
  postmortem_trigger: PmTrigger | null;
  postmortem: PostmortemBrief | null;
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
  setup?: string;
}

export interface ParamSpec {
  name: string;
  label: string;
  default: number;
  step: number;
  min: number | null;
  max: number | null;
}

export interface ConditionSpec {
  id: string;
  title: string;
  needs_volume: boolean;
  params: ParamSpec[];
}

export interface SetupCondition {
  type: string;
  params: Record<string, number>;
}

export interface SetupDefinition {
  required: SetupCondition[];
  confirmations: SetupCondition[];
  min_confirmations: number;
  filters: { min_price: number; min_dollar_volume: number };
}

export interface Setup {
  id: number;
  name: string;
  enabled: boolean;
  direction: Direction;
  markets: Market[];
  timeframe: Timeframe;
  definition: SetupDefinition;
}

export type SetupInput = Omit<Setup, "id">;

export interface ScanHit {
  id: number;
  run_id: number;
  setup_id: number | null;
  setup_name: string;
  market: Market;
  symbol: string;
  direction: Direction;
  timeframe: Timeframe;
  price: number | null;
  name: string | null;
  opened_at: string | null;
  details: {
    price: number;
    timeframe: Timeframe;
    /** D1: a data da barra. H4: o início da barra (UTC, ISO). */
    as_of: string;
    /** Só em H4: o fim da barra (UTC, ISO). */
    as_of_end: string | null;
    rsi14: number | null;
    macd_hist: number | null;
    trend: string;
    atr_pct: number | null;
    volume_ratio: number | null;
    bb_pctb: number | null;
    required: string[];
    confirmations: string[];
    confirmations_applicable: number;
    not_applicable: string[];
  };
}

export interface ScanRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  state: string;
  markets: Market[];
  setups: string[];
  symbols_total: number;
  symbols_ok: number;
  errors?: Record<string, string>;
  errors_count: number;
  as_of: Record<string, string | null>;
  error: string | null;
}

export interface ScanStatus {
  state: "idle" | "running" | "done" | "error";
  phase: string;
  done: number;
  total: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  run_id: number | null;
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

export type AlertKind = "avulso" | "entrada" | "invalidacao" | "alvo";
export type AlertDirection = "acima" | "abaixo";
export type AlertResponse = "entrei" | "ignorei" | "observando";

export interface PriceAlert {
  id: number;
  created_at: string;
  market: Market;
  symbol: string;
  price: number;
  direction: AlertDirection;
  note: string;
  kind: AlertKind;
  entry_id: number | null;
  status: "ativo" | "disparado" | "cancelado";
  base_price: number | null;
  last_price: number | null;
  last_checked_at: string | null;
  distance_pct: number | null;
  triggered_at: string | null;
  trigger_bar: string | null;
  triggered_price: number | null;
  notified_at: string | null;
  notify_ok: boolean | null;
  notify_detail: string | null;
  /** Telegram: null = não tentado (envio desligado); true = enviado; false = falhou (o app reenvia com espera crescente). */
  telegram_ok: boolean | null;
  telegram_detail: string | null;
  telegram_at: string | null;
  telegram_tries: number;
  response: AlertResponse | null;
  response_note: string | null;
  response_at: string | null;
  cancel_reason: string | null;
}

export interface AlertsStatus {
  active: number;
  pending: number;
  watcher: {
    running: boolean;
    interval: number;
    last_cycle_at: string | null;
    last_error: string | null;
    cycles: number;
    errors: Record<string, string>;
  };
  notifications: { available: boolean; detail: string };
  telegram: { configured: boolean; ready: boolean };
}

export interface TelegramStatus {
  token_configured: boolean;
  bot: { username: string | null; name: string | null } | null;
  error: string | null;
  chat: { id: string; label: string | null; source: "env" | "app" } | null;
  enabled: boolean;
  include_note: boolean;
  ready: boolean;
}

export interface TelegramChat {
  chat_id: number;
  tipo: "privado" | "grupo";
  rotulo: string;
  ultima_mensagem: string;
  quando: string;
}

export interface NewAlert {
  market: Market;
  symbol: string;
  price: number;
  direction: AlertDirection;
  note: string;
}

export type Stance = "para_alta" | "para_baixa" | "indistinta" | "sem_dados";

export interface AiEvidence {
  campo: string;
  valor: string;
  leitura: string;
  aponta_para: "alta" | "baixa" | "neutro";
  verificada: boolean | null;
  motivo_da_verificacao: string;
}

export interface AiLensOutput {
  inclinacao: Stance;
  confianca: "baixa" | "media" | "alta";
  resumo: string;
  evidencias: AiEvidence[];
  lacunas: string[];
  mudaria_a_conclusao: string[];
}

export interface AiLens {
  lente: string;
  titulo: string;
  status: "ok" | "erro";
  resultado?: AiLensOutput;
  citacoes?: { total: number; conferem: number; nao_conferem: number };
  erro?: { tipo: string; mensagem: string };
  uso: { prompt_tokens: number | null; completion_tokens: number | null; cost: number | null } | null;
  duracao_ms: number;
}

export interface AiAnalysis {
  id: number;
  created_at: string;
  market: Market;
  symbol: string;
  horizon_days: number;
  prompt_version: string;
  prompt_fingerprint: string;
  model: string;
  effort: string | null;
  lenses: AiLens[];
  cost_usd: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  duration_ms: number | null;
  package?: unknown;
}

export interface AiStatus {
  configured: boolean;
  model: string;
  effort: string | null;
  prompt_version: string;
  prompt_fingerprint: string;
  memory_prompt_version: string;
  memory_prompt_fingerprint: string;
  lenses: Record<Market, { id: string; title: string }[]>;
  avg_cost_usd: number | null;
}

/** Pedido para abrir o formulário de alerta já preenchido (vem da ficha do ativo). */
export interface AlertDraft {
  market: Market;
  symbol: string;
  price: number;
}

/** Um grupo de registros: contagem de desfechos e acerto da tese (alvo / (alvo + invalidada)) com Wilson. */
export interface ReviewCell {
  registros: number;
  alvo: number;
  invalidada: number;
  expirada: number;
  aberta: number;
  fechadas: number;
  taxa_acerto: number | null;
  ic95: [number, number] | null;
  amostra: "insuficiente" | "pequena" | "ok";
  ids: number[];
}

export interface ReviewRate {
  acertos: number;
  fechadas: number;
  taxa: number | null;
  ic95: [number, number] | null;
  amostra: ReviewCell["amostra"];
}

export interface ReviewDiff {
  pp: number | null;
  ic95_pp: [number, number] | null;
  leitura: "a_maior" | "b_maior" | "indistinta" | "sem dados";
}

export type ReviewGroup = ReviewCell & { chave: string };

/** Registros separados pelo lado que o bloco (ou a lente) apontava em relação à direção da tese. */
export interface ReviewConcordance {
  a_favor: ReviewCell;
  contra: ReviewCell;
  sem_inclinacao: ReviewCell;
  sem_registro: number;
  diferenca: ReviewDiff;
}

export interface ReviewAlertKind {
  tipo: AlertKind;
  criados: number;
  disparados: number;
  entrei: number;
  ignorei: number;
  observando: number;
  sem_resposta: number;
}

export interface Review {
  regras_versao: string;
  amostra: ReviewCell & { ativos_distintos: number; primeiro: string | null; ultimo: string | null };
  por_decisao: {
    linhas: (ReviewGroup & { decisao_certa: ReviewRate })[];
    entrei_vs_fora: { entrei: ReviewCell; fora: ReviewCell; diferenca: ReviewDiff };
    saida_antecipada: { registros: number; depois: ReviewCell };
  };
  por_mercado: ReviewGroup[];
  por_setup: ReviewGroup[];
  por_bloco: (ReviewConcordance & { bloco: string; titulo: string; regra: string })[];
  por_lente: {
    registros_com_ia: number;
    versoes: { prompt_version: string | null; model: string | null; registros: number }[];
    lentes: (ReviewConcordance & { lente: string })[];
  };
  alertas: {
    criados: number;
    disparados: number;
    sem_resposta: number;
    cancelados: number;
    por_tipo: ReviewAlertKind[];
    entrada_por_resposta: ReviewGroup[];
  };
  avisos: string[];
}

// ---- Memória da IA ----

export type CauseId =
  | "evento_macro"
  | "referencia_divergiu"
  | "indicador_deu_ruido"
  | "invalidacao_ignorada"
  | "entrada_tardia"
  | "sem_causa_identificavel";
/** A lista é fixa e versionada no backend (causas-v1): estes títulos a espelham. */
export const CAUSE_TITLE: Record<CauseId, string> = {
  evento_macro: "Evento macro",
  referencia_divergiu: "Referência divergiu",
  indicador_deu_ruido: "Indicador deu ruído",
  invalidacao_ignorada: "Invalidação ignorada",
  entrada_tardia: "Entrada tardia",
  sem_causa_identificavel: "Sem causa identificável",
};
export type Visibility = "visivel_na_epoca" | "so_ficou_claro_depois" | "misto" | "nao_se_aplica";
export const VISIBILITY_TEXT: Record<Visibility, string> = {
  visivel_na_epoca: "Já era visível na época",
  so_ficou_claro_depois: "Só ficou claro depois",
  misto: "Parte visível, parte só depois",
  nao_se_aplica: "Não se aplica",
};
export const TRIGGER_TEXT: Record<PmTrigger, string> = {
  invalidada: "Tese invalidada",
  saida_antecipada: "Saída antecipada",
  ambos: "Invalidada e com saída antecipada",
};

export interface CauseInfo {
  id: CauseId;
  title: string;
  definition: string;
  only_if_entered: boolean;
}

export interface PostmortemBrief {
  id: number;
  created_at: string;
  causa_principal: CauseId;
  causas_secundarias: CauseId[];
  visibilidade: Visibility;
  confianca: "baixa" | "media" | "alta";
  resumo: string;
  avisos: number;
  model: string;
  cost_usd: number | null;
}

export interface Postmortem {
  id: number;
  entry_id: number;
  created_at: string;
  trigger: PmTrigger;
  prompt_version: string;
  prompt_fingerprint: string;
  causes_version: string;
  model: string;
  effort: string | null;
  result: {
    causa_principal: CauseId;
    causas_secundarias: CauseId[];
    visibilidade: Visibility;
    confianca: "baixa" | "media" | "alta";
    resumo: string;
    o_que_era_visivel: string[];
    o_que_so_ficou_claro_depois: string[];
    evidencias: { campo: string; valor: string; leitura: string; verificada: boolean | null; motivo_da_verificacao: string }[];
    hipoteses: string[];
    o_que_faltou: string[];
  };
  checks: { tipo: "nao_se_aplica" | "sem_base" | "incoerente" | "citacao"; mensagem: string }[];
  cost_usd: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  duration_ms: number | null;
  package?: unknown;
}

export interface AlertSide {
  rotulo: string;
  alvo: number;
  invalidada: number;
  fechadas: number;
  taxa_acerto: number | null;
  ic95: [number, number] | null;
  ids: number[];
}

export interface MemoryAlert {
  id: string;
  tipo: "setup" | "mercado" | "decisao" | "saida_antecipada" | "bloco" | "lente";
  chave: string;
  titulo: string;
  texto: string;
  sentido: "melhor" | "pior";
  n: number;
  grupo: AlertSide;
  contra: AlertSide;
  diferenca_pp: number;
  ic95_pp: [number, number];
}

export interface MemoryAlerts {
  alertas: MemoryAlert[];
  testadas: number;
  distinguiveis: number;
  esperados_por_acaso: number;
  minimo_por_grupo: number;
  registros: number;
  resolvidas: number;
}

export interface EligibleEntry {
  id: number;
  market: Market;
  symbol: string;
  direction: Direction;
  decision: Decision;
  setup: string;
  created_at: string;
  status: Status;
  closed_at: string | null;
  r_multiple: number | null;
  early_exit_at: string | null;
  early_exit_r: number | null;
  trigger: PmTrigger | null;
  postmortem: PostmortemBrief | null;
}

export interface MemoryOverview {
  causas: { versao: string; lista: CauseInfo[] };
  elegiveis: EligibleEntry[];
  pendentes: number;
  distribuicao_das_causas: {
    n: number;
    amostra: "insuficiente" | "pequena" | "ok";
    itens: { causa: CauseId; titulo: string; n: number; taxa: number; ic95: [number, number] }[];
    visibilidade: Partial<Record<Visibility, number>>;
    nota: string;
  };
  alertas: MemoryAlerts;
  ia: { configured: boolean; model: string; prompt_version: string; prompt_fingerprint: string; avg_cost_usd: number | null };
}

export interface SimilarCase {
  id: number;
  mercado: Market;
  simbolo: string;
  direcao: Direction;
  decisao: Decision;
  registrado_em: string;
  setup: string;
  desfecho: Status;
  r: number | null;
  dias_ate_desfecho: number | null;
  pontos: number;
  por_que_parecido: string[];
  blocos: Record<string, string>;
  pos_mortem: { causa: CauseId; visibilidade: Visibility; confianca: "baixa" | "media" | "alta" } | null;
}

export interface AssetMemory {
  estado_atual: Record<string, string>;
  historico_do_ativo: ReviewCell;
  setups: (ReviewCell & { setup: string })[];
  parecidos: {
    casos: SimilarCase[];
    total_parecidos: number;
    grupo: { todos: ReviewCell; teses_de_alta: ReviewCell; teses_de_baixa: ReviewCell };
    criterio: { minimo_de_pontos: number; maximo_de_casos: number };
  };
  alertas_aplicaveis: MemoryAlert[];
  comparacoes: { testadas: number; distinguiveis: number; esperados_por_acaso: number; minimo_por_grupo: number };
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
  review: () => request<Review>("/api/review"),
  createEntry: (body: NewEntry) =>
    request<Entry & { alerts?: { id: number; kind: AlertKind; price: number; direction: AlertDirection }[] }>(
      "/api/journal",
      { method: "POST", body: JSON.stringify(body) },
    ),
  aiStatus: () => request<AiStatus>("/api/ai/status"),
  aiAnalyze: (market: Market, symbol: string, horizon: number, memory = false) =>
    request<AiAnalysis>("/api/ai/analyze", { method: "POST", body: JSON.stringify({ market, symbol, horizon, memory }) }),
  aiAnalyses: (market: Market, symbol: string) =>
    request<AiAnalysis[]>(`/api/ai/analyses?market=${market}&symbol=${encodeURIComponent(symbol)}`),
  aiAnalysis: (id: number) => request<AiAnalysis>(`/api/ai/analyses/${id}`),
  aiPrompts: (version = "v1") =>
    request<{ version: string; fingerprint: string; prompts: Record<string, Record<string, string>> }>(
      `/api/ai/prompts?version=${version}`,
    ),
  memory: () => request<MemoryOverview>("/api/memory"),
  memoryPrompt: () =>
    request<{ version: string; fingerprint: string; causes_version: string; prompt: string }>("/api/memory/prompt"),
  runPostmortem: (entryId: number) => request<Postmortem>(`/api/memory/postmortem/${entryId}`, { method: "POST" }),
  postmortem: (entryId: number) => request<Postmortem>(`/api/memory/postmortem/${entryId}`),
  assetMemory: (market: Market, symbol: string, horizon: number, setups: string[]) =>
    request<AssetMemory>(
      `/api/memory/asset/${market}/${encodeURIComponent(symbol)}?horizon=${horizon}&setups=${encodeURIComponent(setups.join(","))}`,
    ),
  alerts: () => request<PriceAlert[]>("/api/alerts"),
  alertsStatus: () => request<AlertsStatus>("/api/alerts/status"),
  createAlert: (body: NewAlert) => request<PriceAlert>("/api/alerts", { method: "POST", body: JSON.stringify(body) }),
  cancelAlert: (id: number) => request<PriceAlert>(`/api/alerts/${id}/cancel`, { method: "POST" }),
  respondAlert: (id: number, response: AlertResponse) =>
    request<PriceAlert>(`/api/alerts/${id}/respond`, { method: "POST", body: JSON.stringify({ response }) }),
  deleteAlert: (id: number) => request<void>(`/api/alerts/${id}`, { method: "DELETE" }),
  checkAlertsNow: () => request<{ fired: PriceAlert[] }>("/api/alerts/check", { method: "POST" }),
  telegramStatus: () => request<TelegramStatus>("/api/telegram/status"),
  telegramDiscover: () => request<{ chats: TelegramChat[] }>("/api/telegram/discover", { method: "POST" }),
  telegramLink: (chatId: number) =>
    request<TelegramStatus>("/api/telegram/link", { method: "POST", body: JSON.stringify({ chat_id: chatId }) }),
  telegramUnlink: () => request<TelegramStatus>("/api/telegram/link", { method: "DELETE" }),
  telegramOptions: (body: { enabled?: boolean; include_note?: boolean }) =>
    request<TelegramStatus>("/api/telegram/options", { method: "POST", body: JSON.stringify(body) }),
  telegramTest: () => request<{ ok: boolean }>("/api/telegram/test", { method: "POST" }),
  testNotification: () => request<{ ok: boolean; detail: string }>("/api/alerts/test-notification", { method: "POST" }),
  refresh: () => request<RefreshResult>("/api/journal/refresh", { method: "POST" }),
  earlyExit: (id: number, price: number, reason: string) =>
    request<Entry>(`/api/journal/${id}/early-exit`, { method: "POST", body: JSON.stringify({ price, reason }) }),
  remove: (id: number) => request<void>(`/api/journal/${id}`, { method: "DELETE" }),
  correlation: (market: Market, symbol: string) =>
    request<CorrelationData>(`/api/correlation/${market}/${encodeURIComponent(symbol)}`),
  scannerCatalog: () => request<ConditionSpec[]>("/api/scanner/catalog"),
  scannerSetups: () => request<Setup[]>("/api/scanner/setups"),
  saveSetup: (id: number | null, body: SetupInput) =>
    request<Setup>(id == null ? "/api/scanner/setups" : `/api/scanner/setups/${id}`, {
      method: id == null ? "POST" : "PUT",
      body: JSON.stringify(body),
    }),
  deleteSetup: (id: number) => request<void>(`/api/scanner/setups/${id}`, { method: "DELETE" }),
  scannerRun: (markets: Market[]) =>
    request<{ started: boolean; status: ScanStatus }>("/api/scanner/run", {
      method: "POST",
      body: JSON.stringify({ markets }),
    }),
  scannerStatus: () => request<ScanStatus>("/api/scanner/status"),
  scannerLatest: () => request<{ run: ScanRun | null; hits: ScanHit[] }>("/api/scanner/runs/latest"),
  hitOpened: (id: number) => request<void>(`/api/scanner/hits/${id}/opened`, { method: "POST" }),
  correlationStatus: () => request<{ refresh: RefreshStatus; universe: UniverseState }>("/api/correlation/status"),
  correlationRefresh: () =>
    request<{ started: boolean; refresh: RefreshStatus }>("/api/correlation/refresh", { method: "POST" }),
};
